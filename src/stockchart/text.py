"""L1 渲染原语：文字绘制与测量。

逐字符解析字体回退：主字体缺字形时改查系统回退字体，仍找不到则画
“豆腐块”而不抛异常。所有坐标与字号都以 Canvas 的输出像素计；排版规则
见 docs/design.zh-CN.md 的“字体”一节。
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Literal

import skia

from stockchart.canvas import Canvas, skia_color
from stockchart.color import Color
from stockchart.defaults import DEFAULT_TEXT_COLOR

type HorizontalAnchor = Literal["left", "center", "right"]
type VerticalAnchor = Literal["top", "middle", "baseline", "bottom"]
type TextAnchor = tuple[HorizontalAnchor, VerticalAnchor]
"""(x, y) 锚在文字包围盒的哪一处；baseline 指文字基线。"""

type FontSpec = str | Path | Sequence[str]
"""字体：家族名、字体文件路径，或依次尝试的家族名列表。"""

# 手写/楷体偏好回退链（design.zh-CN.md"字体"），按平台取用
_FALLBACK_FAMILIES: dict[str, tuple[str, ...]] = {
    "win32": ("楷体", "华文行楷", "Ink Free", "Segoe Print"),
    "darwin": ("Kaiti SC", "Bradley Hand", "Marker Felt"),
    "linux": ("Noto Serif CJK", "WenQuanYi", "Noto Sans CJK"),
}
_DEFAULT_FAMILIES: tuple[str, ...] = _FALLBACK_FAMILIES.get(
    sys.platform, _FALLBACK_FAMILIES["linux"]
)

# 字体解析较慢（磁盘/注册表），按名字缓存；None 表示"没有这个家族"
_typeface_cache: dict[str, skia.Typeface | None] = {}
# 每个缺字字符的系统回退字体同样缓存
_fallback_cache: dict[int, skia.Typeface | None] = {}


def _typeface_from_name(name: str) -> skia.Typeface | None:
    """按家族名或字体文件路径解析 Typeface，并缓存结果。

    `MakeFromName` 对未知家族会静默返回系统默认字体，因此家族名先经
    FontMgr 做存在性检查；None 表示该名字不可用。

    Args:
        name: 字体家族名或字体文件路径。

    Returns:
        解析到的 Typeface；名字不可用时返回 None。
    """
    if name in _typeface_cache:
        return _typeface_cache[name]
    path = Path(name)
    tf: skia.Typeface | None
    if path.is_file():
        tf = skia.Typeface.MakeFromFile(str(path))
    else:
        tf = skia.FontMgr.RefDefault().matchFamilyStyle(name, skia.FontStyle.Normal())
    _typeface_cache[name] = tf
    return tf


def _resolve_typeface(spec: FontSpec | None) -> skia.Typeface:
    """把 FontSpec 解析为 Typeface。

    按顺序尝试候选字体，全部失败时退回系统默认字体，不抛异常。

    Args:
        spec: 字体家族名、文件路径、候选列表或 None（使用内置回退链）。

    Returns:
        可用的 Typeface；兜底为 skia 的默认字体。
    """
    names: Sequence[str]
    if spec is None:
        names = _DEFAULT_FAMILIES
    elif isinstance(spec, Path):
        names = [str(spec)]
    elif isinstance(spec, str):
        names = [spec]
    else:
        names = list(spec)
    for name in names:
        tf = _typeface_from_name(name)
        if tf is not None:
            return tf
    return skia.Typeface.MakeFromName("", skia.FontStyle.Normal())


def _fallback_typeface(ch: str) -> skia.Typeface | None:
    """查找包含指定字符的系统回退字体。

    Args:
        ch: 需要显示的单个字符。

    Returns:
        含该字形的 Typeface；系统没有可用字体时返回 None。
    """
    cp = ord(ch)
    if cp in _fallback_cache:
        return _fallback_cache[cp]
    tf = skia.FontMgr.RefDefault().matchFamilyStyleCharacter("", skia.FontStyle.Normal(), [], cp)
    _fallback_cache[cp] = tf
    return tf


def _layout_runs(text: str, base: skia.Font) -> list[tuple[str, skia.Font, float]]:
    """把文本切成逐字符的绘制 run。

    主字体缺字形时改用系统回退字体，仍找不到则保留主字体（最终画“豆腐块”）。

    Args:
        text: 待排版的单行文本。
        base: 主字体。

    Returns:
        (字符, 实际字体, 该字符前进宽度) 的列表；每个字符一项。
    """
    runs: list[tuple[str, skia.Font, float]] = []
    for ch in text:
        font = base
        if base.unicharToGlyph(ord(ch)) == 0:
            tf = _fallback_typeface(ch)
            if tf is not None:
                font = skia.Font(tf, base.getSize())
        runs.append((ch, font, font.measureText(ch)))
    return runs


def _anchor_point(
    x: float,
    y: float,
    width: float,
    metrics: skia.FontMetrics,
    anchor: TextAnchor,
) -> tuple[float, float]:
    """把用户锚点换算为文字包围盒的绘制起点。

    Args:
        x: 用户给定的锚点 x。
        y: 用户给定的锚点 y（基线或包围盒边缘）。
        width: 文字总宽度。
        metrics: 主字体度量，用于推算顶/底/垂直居中。
        anchor: (水平, 垂直) 锚点组合。

    Returns:
        文字绘制的起始 x 与基线 y。
    """
    h, v = anchor
    if h == "left":
        x0 = x
    elif h == "center":
        x0 = x - width / 2
    else:
        x0 = x - width
    if v == "baseline":
        y0 = y
    elif v == "top":
        y0 = y - metrics.fAscent
    elif v == "middle":
        y0 = y - (metrics.fAscent + metrics.fDescent) / 2
    else:
        y0 = y - metrics.fDescent
    return x0, y0


def draw_text(
    canvas: Canvas,
    text: str,
    x: float,
    y: float,
    *,
    size_px: float,
    color: Color = DEFAULT_TEXT_COLOR,
    font: FontSpec | None = None,
    anchor: TextAnchor = ("left", "baseline"),
    rotation: float = 0.0,
) -> None:
    """画一段单行文字。

    逐字符字体回退保证中文可显示；缺字形画“豆腐块”，不抛异常。不处理换行。

    Args:
        canvas: 目标画布。
        text: 待绘制文本；空串直接返回。
        x: 锚点 x（画布输出像素）。
        y: 锚点 y（画布输出像素）。
        size_px: 字号（像素）。
        color: 文字颜色。
        font: 字体家族名、文件路径、候选列表或 None（内置回退链）。
        anchor: (x, y) 对应文字包围盒的哪一处；垂直 baseline 指文字基线。
        rotation: 绕 (x, y) 顺时针旋转的角度（度）。

    Raises:
        ValueError: color 不是合法的 RGB/RGBA 元组。
    """
    if not text:
        return
    base = skia.Font(_resolve_typeface(font), size_px)
    runs = _layout_runs(text, base)
    width = sum(adv for _, _, adv in runs)
    x0, y0 = _anchor_point(x, y, width, base.getMetrics(), anchor)
    paint = skia.Paint(AntiAlias=True, Color=skia_color(color))
    sc = canvas._skia_canvas()  # pyright: ignore[reportPrivateUsage]
    if rotation:
        sc.save()
        sc.translate(x, y)
        sc.rotate(rotation)
        cursor, baseline = x0 - x, y0 - y
        for ch, f, adv in runs:
            sc.drawString(ch, cursor, baseline, f, paint)
            cursor += adv
        sc.restore()
        return
    cursor = x0
    for ch, f, adv in runs:
        sc.drawString(ch, cursor, y0, f, paint)
        cursor += adv


def measure_text(
    text: str,
    *,
    size_px: float,
    font: FontSpec | None = None,
) -> float:
    """测量一段文字按 `draw_text` 相同规则绘制后的宽度。

    Args:
        text: 待测量文本；空串返回 0。
        size_px: 字号（像素）。
        font: 字体家族名、文件路径、候选列表或 None（内置回退链）。

    Returns:
        文字前进宽度（像素）。
    """
    if not text:
        return 0.0
    base = skia.Font(_resolve_typeface(font), size_px)
    return sum(adv for _, _, adv in _layout_runs(text, base))


def measure_text_height(
    text: str,
    *,
    size_px: float,
    font: FontSpec | None = None,
) -> float:
    """测量单行文字的字面高度。

    Args:
        text: 待测量文本；空串按当前字号估算。
        size_px: 字号（像素）。
        font: 字体家族名、文件路径、候选列表或 None（内置回退链）。

    Returns:
        升部到降部的高度（像素）。
    """
    base = skia.Font(_resolve_typeface(font), size_px)
    metrics = base.getMetrics()
    return float(metrics.fDescent - metrics.fAscent)


_EMPTY_ELLIPSIS = "\u2026"
# 优先在这些字符之后断行：空白与常见中英文标点
_BREAK_AFTER = frozenset(" \t,，、;；:：/\\|-—")


def _run_width(text: str, base: skia.Font) -> float:
    """按给定主字体（含逐字回退）测量整段文字宽度。

    Args:
        text: 待测量文本。
        base: 主字体。

    Returns:
        前进宽度（像素）。
    """
    return sum(_measure_chars(ch, base) for ch in text)


def _truncate_to_width(text: str, max_width: float, base: skia.Font) -> str:
    """把文本截到指定宽度并追加省略号。

    Args:
        text: 待截断文本。
        max_width: 最大宽度（像素）。
        base: 主字体。

    Returns:
        不超过 max_width 的文本；宽度不足时只保留省略号。
    """
    if _run_width(text, base) <= max_width:
        return text
    ell = _EMPTY_ELLIPSIS
    avail = max_width - _run_width(ell, base)
    if avail <= 0:
        return ell
    kept: list[str] = []
    width = 0.0
    for ch in text:
        adv = _measure_chars(ch, base)
        if width + adv > avail:
            break
        kept.append(ch)
        width += adv
    return "".join(kept).rstrip() + ell


def wrap_text(
    text: str,
    *,
    max_width: float,
    size_px: float,
    font: FontSpec | None = None,
    max_lines: int | None = None,
) -> list[str]:
    """按像素宽度把单行文本折成多行。

    采用贪心断行，优先在空白或常见标点之后断开；中文可按字断行，英文单词
    过长时仍会断开。超过 max_lines 时末行加省略号；除单个字形本身超宽外，
    每行都不超过 max_width。

    Args:
        text: 待折行文本；空串返回 [""]。
        max_width: 每行最大宽度（像素）。
        size_px: 字号（像素）。
        font: 字体家族名、文件路径、候选列表或 None（内置回退链）。
        max_lines: 最多行数；None 表示不限。

    Returns:
        折行后的文本列表，至少包含一个元素。
    """
    if not text:
        return [""]
    base = skia.Font(_resolve_typeface(font), size_px)
    widths = [_measure_chars(ch, base) for ch in text]
    lines: list[str] = []
    start = 0
    while start < len(text):
        width = 0.0
        end = start
        while end < len(text) and width + widths[end] <= max_width:
            width += widths[end]
            end += 1
        if end == start:  # 单字超宽：至少前进一个字符，末行再截断
            end = start + 1
        if end < len(text):
            # 在当前行里找最后一个可断点，避免英文单词被切得太碎
            for cut in range(end, start, -1):
                if text[cut - 1] in _BREAK_AFTER:
                    end = cut
                    break
        lines.append(text[start:end].rstrip())
        start = end
        while start < len(text) and text[start] == " ":
            start += 1
        if max_lines is not None and len(lines) == max_lines:
            if start < len(text):
                lines[-1] = _truncate_to_width(lines[-1] + text[start:], max_width, base).rstrip()
            break
    for i, line in enumerate(lines):
        if measure_text(line, size_px=size_px, font=font) > max_width:
            lines[i] = _truncate_to_width(line, max_width, base)
    return lines or [""]


def _measure_chars(ch: str, base: skia.Font) -> float:
    """测量单个字符在字体回退后的前进宽度。

    Args:
        ch: 单个字符。
        base: 主字体。

    Returns:
        字符前进宽度（像素）。
    """
    if base.unicharToGlyph(ord(ch)) == 0:
        tf = _fallback_typeface(ch)
        if tf is not None:
            return skia.Font(tf, base.getSize()).measureText(ch)
    return base.measureText(ch)
