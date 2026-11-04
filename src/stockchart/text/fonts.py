"""字体解析层：FontSpec 解析、字体栈、逐码点回退与共享排版单例。

解析链（docs/design.zh-CN.md「字体」）：FontSpec 每项为字体文件路径（文件
存在即按路径加载）或家族名（经系统 FontMgr 匹配）；字体栈内按顺序逐码点取
首个含该字形的字体，栈内全缺时用 matchFamilyStyleCharacter 做系统逐码点
回退，仍无字形则返回 None，由上层画方框占位。

Typeface、字体栈、码点回退与 skia Font 对象均全局缓存——旧实现每次绘制
重建 Font、逐字符解析回退，是文字渲染性能问题的主要来源。
"""

# skia-python 不带类型桩：pyright 只认识核心成员（Font/Typeface/FontMgr 等），
# Unicodes / textlayout / Typeface.unicharToGlyph / uniqueID 不在其认识范围，
# 本文件定向关闭相关 unknown 报告；其余规则仍按 strict 执行。
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnknownParameterType=false, reportAttributeAccessIssue=false

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import skia

from stockchart.defaults import DEFAULT_FONT_FAMILIES

type FontSpec = str | Path | Sequence[str | Path]
"""字体：家族名、字体文件路径，或依次尝试的候选列表；None 用平台默认链。"""

# Typeface 解析较慢（磁盘/注册表），按名字缓存；None 表示"没有这个字体"
_typeface_cache: dict[str, skia.Typeface | None] = {}
# 字体栈缓存：规范化候选名元组 → Typeface 元组
_stack_cache: dict[tuple[str, ...], tuple[skia.Typeface, ...]] = {}
# 逐码点的系统回退字体缓存；None 表示系统也没有该字形（走方框占位）
_codepoint_cache: dict[int, skia.Typeface | None] = {}
# skia.Font 缓存（key 为 Typeface.uniqueID 与字号）
_font_cache: dict[tuple[int, float], skia.Font] = {}
# Typeface → TypefaceFontProvider 别名
_alias_cache: dict[int, str] = {}

_manager: skia.FontMgr | None = None
_provider: skia.textlayout.TypefaceFontProvider | None = None
_collection: skia.textlayout.FontCollection | None = None
_unicode: skia.Unicode | None = None


def system_font_manager() -> skia.FontMgr:
    """取系统字体管理器单例（win=DirectWrite / mac=CoreText / linux=FontConfig）。"""
    global _manager
    if _manager is None:
        _manager = skia.FontMgr.RefDefault()
    return _manager


def shared_provider() -> skia.textlayout.TypefaceFontProvider:
    """取共享的闭世界字体提供者（engine 用别名注册确定性字体）。"""
    global _provider
    if _provider is None:
        _provider = skia.textlayout.TypefaceFontProvider()
    return _provider


def shared_font_collection() -> skia.textlayout.FontCollection:
    """取共享 FontCollection（默认管理器指向 shared_provider）。

    ICU 与 FontCollection 初始化较重，惰性创建且全进程复用；skia 也在
    FontCollection 上缓存整形结果，复用对性能至关重要。
    """
    global _collection
    if _collection is None:
        collection = skia.textlayout.FontCollection()
        collection.setDefaultFontManager(shared_provider())
        _collection = collection
    return _collection


def shared_unicode() -> skia.Unicode:
    """取 ICU Unicode 单例（Paragraph 构造必需，惰性加载 icudtl.dat）。"""
    global _unicode
    if _unicode is None:
        _unicode = skia.Unicodes.ICU.Make()
    return _unicode


def normalize_spec(spec: FontSpec | None) -> tuple[str, ...]:
    """把 FontSpec 规范化为候选名字元组（Path 转字符串）。

    Args:
        spec: 字体家族名、文件路径、候选列表或 None（平台默认链）。

    Returns:
        按优先级排列的候选名元组。

    Raises:
        ValueError: 候选列表为空，或候选名存在空字符串。
    """
    if spec is None:
        return DEFAULT_FONT_FAMILIES
    if isinstance(spec, Path):
        return (str(spec),)
    names = (spec,) if isinstance(spec, str) else tuple(str(item) for item in spec)
    if not names or any(not name for name in names):
        raise ValueError("font 候选列表不能为空，也不能包含空名字")
    return names


def _typeface_from_name(name: str) -> skia.Typeface | None:
    """按家族名或字体文件路径解析 Typeface（缓存；None 表示该名字不可用）。

    `MakeFromName` 对未知家族会静默返回系统默认字体，因此家族名必须先经
    FontMgr 做存在性检查，避免用户拼错家族名时悄悄换成默认字体。
    """
    if name in _typeface_cache:
        return _typeface_cache[name]
    path = Path(name)
    tf: skia.Typeface | None
    if path.is_file():
        tf = skia.Typeface.MakeFromFile(str(path))
    else:
        tf = system_font_manager().matchFamilyStyle(name, skia.FontStyle.Normal())
    _typeface_cache[name] = tf
    return tf


def resolve_stack(spec: FontSpec | None) -> tuple[skia.Typeface, ...]:
    """把 FontSpec 解析为按优先级排序的 Typeface 栈（全局缓存）。

    解析失败的候选静默跳过（常见于系统缺某款字体）；全部失败时退回 skia
    默认字体，保证栈非空——绘制永远有字体可用，缺字形才走方框占位。

    Args:
        spec: 字体家族名、文件路径、候选列表或 None（平台默认链）。

    Returns:
        非空的 Typeface 元组，越靠前优先级越高。
    """
    names = normalize_spec(spec)
    stack = _stack_cache.get(names)
    if stack is None:
        stack = tuple(tf for tf in (_typeface_from_name(name) for name in names) if tf is not None)
        if not stack:
            stack = (skia.Typeface.MakeFromName("", skia.FontStyle.Normal()),)
        _stack_cache[names] = stack
    return stack


def resolve_codepoint(stack: tuple[skia.Typeface, ...], cp: int) -> skia.Typeface | None:
    """解析单个码点应使用的字体。

    栈内按顺序找首个含该字形的字体；栈内全缺时查系统逐码点回退；回退字体
    也缺字形（或系统无回退）时返回 None——上层据此画方框占位。

    Args:
        stack: resolve_stack 的结果。
        cp: Unicode 码点。

    Returns:
        含该字形的 Typeface；确定无字体可用时返回 None。
    """
    for tf in stack:
        if tf.unicharToGlyph(cp) != 0:
            return tf
    if cp in _codepoint_cache:
        return _codepoint_cache[cp]
    tf = system_font_manager().matchFamilyStyleCharacter("", skia.FontStyle.Normal(), [], cp)
    # 回退字体必须真的含该字形；部分平台会返回不含该字形的字体
    if tf is not None and tf.unicharToGlyph(cp) == 0:
        tf = None
    _codepoint_cache[cp] = tf
    return tf


def font_for(tf: skia.Typeface, size_px: float) -> skia.Font:
    """取 (Typeface, 字号) 对应的 skia Font（全局缓存）。"""
    key = (tf.uniqueID(), size_px)
    font = _font_cache.get(key)
    if font is None:
        font = skia.Font(tf, size_px)
        _font_cache[key] = font
    return font


def typeface_alias(tf: skia.Typeface) -> str:
    """把 Typeface 注册进共享 TypefaceFontProvider 并返回稳定别名。

    provider 是闭世界（未注册的家族不解析、无系统回退），engine 以别名经
    fontFamilies 喂给 Paragraph，整段必被该字体覆盖，排版行为完全确定。

    Args:
        tf: 已解析的 Typeface。

    Returns:
        按 Typeface.uniqueID 命名的别名；重复注册幂等。
    """
    uid = tf.uniqueID()
    alias = _alias_cache.get(uid)
    if alias is None:
        alias = f"sc{uid}"
        shared_provider().registerTypeface(tf, alias)
        _alias_cache[uid] = alias
    return alias
