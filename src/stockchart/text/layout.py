r"""折行与块布局：\\n 切分、贪心软折行、max_lines 省略号与块级度量。

行堆叠规则：各行的 baseline 与 height 来自 engine.shape_line 的真实度量；
块内统一行距 step = 最大行高 × line_height（None 视为 1.0），首行基线距
块顶取各行 ascent 的最大值，块高 = (行数-1) × step + 最大行高。layout_text
的结果按（文本, 候选名, 字号, 折行参数）缓存——测量与绘制共享同一份布局，
消灭旧实现"布局阶段与绘制阶段各测一遍"的重复劳动。
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import skia

from stockchart.text.engine import TextLine, char_advance, shape_line
from stockchart.text.fonts import FontSpec, normalize_spec, resolve_stack

# 优先在这些字符之后断行：空白与常见中英文标点
_BREAK_AFTER = frozenset(" \t,，、;；:：/\\|-—")
_ELLIPSIS = "\u2026"


@dataclass(slots=True, frozen=True)
class TextLayout:
    """一段文本的完整布局结果。

    Attributes:
        lines: 依序各行（含空行）。
        width: 最宽行的前进宽度。
        height: 块高（含全部行）。
        baseline: 首行基线距块顶。
        line_step: 相邻行基线间距。
    """

    lines: tuple[TextLine, ...]
    width: float
    height: float
    baseline: float
    line_step: float


def _wrap_segment(
    seg: str,
    stack: tuple[skia.Typeface, ...],
    *,
    size_px: float,
    max_width: float,
    limit: int | None,
) -> tuple[list[str], str]:
    """对一个硬切分段做贪心软折行（移植旧 wrap_text 主循环）。

    Args:
        seg: 不含换行符的单段文本。
        stack: fonts.resolve_stack 的结果。
        size_px: 字号（像素）。
        max_width: 每行最大宽度（像素），逐字符估宽判定。
        limit: 最多输出行数；None 表示不限。

    Returns:
        (行列表, 溢出原文)。达到 limit 后的剩余原文自下一行的原始起点
        （跳过行首空格）返回，供 max_lines 末行拼接；段完整折行时为空串。
    """
    if limit is not None and limit <= 0:
        return [], seg
    if not seg:
        # 空段（连续换行）也占一个空行，保持 \\n 切分的行数语义
        return [""], ""
    widths = [char_advance(ch, stack, size_px=size_px) for ch in seg]
    lines: list[str] = []
    start = 0
    while start < len(seg):
        if limit is not None and len(lines) >= limit:
            break
        width = 0.0
        end = start
        while end < len(seg) and width + widths[end] <= max_width:
            width += widths[end]
            end += 1
        if end == start:  # 单字超宽：至少前进一个字符，末行再截断
            end = start + 1
        if end < len(seg):
            # 在当前行里找最后一个可断点，避免英文单词被切得太碎
            for cut in range(end, start, -1):
                if seg[cut - 1] in _BREAK_AFTER:
                    end = cut
                    break
        lines.append(seg[start:end].rstrip())
        start = end
        while start < len(seg) and seg[start] == " ":
            start += 1
    return lines, seg[start:]


def _truncate_to_width(
    text: str,
    max_width: float,
    stack: tuple[skia.Typeface, ...],
    *,
    size_px: float,
) -> str:
    """把文本截到指定宽度并追加省略号（移植旧 _truncate_to_width 语义）。

    整体放得下时原样返回（不加省略号）；放不下时按逐字符估宽保留前缀，
    再用整形后的真实宽度复核、仍超宽则逐字符回退。省略号自身放不下时
    只保留省略号。

    Args:
        text: 待截断文本。
        max_width: 最大宽度（像素）。
        stack: fonts.resolve_stack 的结果。
        size_px: 字号（像素）。

    Returns:
        不超过 max_width 的文本加省略号；整体放得下时原样返回。
    """
    if shape_line(text, stack, size_px=size_px).advance <= max_width:
        return text
    avail = max_width - shape_line(_ELLIPSIS, stack, size_px=size_px).advance
    kept: list[str] = []
    if avail > 0:
        width = 0.0
        for ch in text:
            adv = char_advance(ch, stack, size_px=size_px)
            if width + adv > avail:
                break
            kept.append(ch)
            width += adv
    # 估宽不含 kerning：候选以整形后的真实宽度复核，超宽则逐字符回退；
    # kept 清空后候选只剩省略号，直接返回（放不下也保留）
    while True:
        candidate = "".join(kept).rstrip() + _ELLIPSIS
        if not kept or shape_line(candidate, stack, size_px=size_px).advance <= max_width:
            return candidate
        kept.pop()


def break_lines(
    text: str,
    *,
    size_px: float,
    font: FontSpec | None = None,
    max_width: float | None = None,
    max_lines: int | None = None,
) -> list[str]:
    r"""把文本折成行字符串列表。

    先按 ``\\n`` 硬切分；给了 max_width 再做贪心软折行（优先在空白/标点后
    断开，中文可按字断行，单字超宽时至少前进一个字符）；行数超过 max_lines
    时保留前 max_lines 行、末行截断加省略号。软折行与截断用逐字符快速估宽，
    最终各行宽度由 layout_text 用整形后的真实 advance 复核。

    Args:
        text: 待折行文本；空串返回 [""]。
        size_px: 字号（像素）。
        font: 字体候选；None 用平台默认链。
        max_width: 每行最大宽度（像素）；None 表示不软折行。
        max_lines: 最多行数；None 表示不限。

    Returns:
        行字符串列表，至少一个元素。

    Raises:
        ValueError: font 候选列表为空或包含空名字。
    """
    names = normalize_spec(font)
    if max_lines is not None and max_lines < 1:
        raise ValueError("max_lines 不能小于 1")
    if not text:
        return [""]
    segments = text.split("\n")
    lines: list[str] = []
    overflow_parts: list[str] = []
    if max_width is None:
        # 不软折行，硬切分结果即行。仍尊重 max_lines：溢出段并入末行并加
        # 省略号——没有宽度上限可截断（省略号只标记行数被截，不丢字）
        for seg in segments:
            if max_lines is not None and len(lines) >= max_lines:
                overflow_parts.append(seg)
            else:
                lines.append(seg)
        if overflow_parts:
            lines[-1] = (lines[-1] + " ".join(overflow_parts)).rstrip() + _ELLIPSIS
        return lines
    stack = resolve_stack(names)
    for seg in segments:
        # limit 是已排出行数之后剩余的行数配额，0 表示整段计入溢出
        limit = None if max_lines is None else max_lines - len(lines)
        wrapped, tail = _wrap_segment(seg, stack, size_px=size_px, max_width=max_width, limit=limit)
        lines.extend(wrapped)
        if tail:
            overflow_parts.append(tail)
    if overflow_parts:
        lines[-1] = _truncate_to_width(
            lines[-1] + " ".join(overflow_parts), max_width, stack, size_px=size_px
        ).rstrip()
    # 估宽不含 kerning：逐行用整形后的真实 advance 复核，超宽行按旧语义截断
    for i, line in enumerate(lines):
        if shape_line(line, stack, size_px=size_px).advance > max_width:
            lines[i] = _truncate_to_width(line, max_width, stack, size_px=size_px)
    return lines


@lru_cache(maxsize=256)
def _layout_cached(
    text: str,
    names: tuple[str, ...],
    size_px: float,
    max_width: float | None,
    max_lines: int | None,
    line_height: float | None,
) -> TextLayout:
    """layout_text 的缓存主体，key 即参数本身（测量与绘制共享同一份布局）。

    Args:
        text: 待排版文本。
        names: normalize_spec 规范化后的候选名元组。
        size_px: 字号（像素）。
        max_width: 每行最大宽度（像素）；None 表示不软折行。
        max_lines: 最多行数；None 表示不限。
        line_height: 行距倍率；None 为 1.0。

    Returns:
        块级布局结果。
    """
    stack = resolve_stack(names)
    rows = break_lines(text, size_px=size_px, font=names, max_width=max_width, max_lines=max_lines)
    lines = tuple(shape_line(row, stack, size_px=size_px) for row in rows)
    # 块级度量取各行真实度量的最大值（行堆叠规则见模块 docstring）
    block_height = max(line.height for line in lines)
    block_baseline = max(line.baseline for line in lines)
    step = block_height * (line_height or 1.0)
    return TextLayout(
        lines=lines,
        width=max((line.advance for line in lines), default=0.0),
        height=(len(lines) - 1) * step + block_height,
        baseline=block_baseline,
        line_step=step,
    )


def layout_text(
    text: str,
    *,
    size_px: float,
    font: FontSpec | None = None,
    max_width: float | None = None,
    max_lines: int | None = None,
    line_height: float | None = None,
) -> TextLayout:
    """排版文本并返回块级度量（结果缓存，测量与绘制共享）。

    Args:
        text: 待排版文本；空串返回单空行布局。
        size_px: 字号（像素）。
        font: 字体候选；None 用平台默认链。
        max_width: 每行最大宽度（像素）；None 表示不软折行。
        max_lines: 最多行数；None 表示不限。
        line_height: 行距相对最大行高的倍率；None 为 1.0（自然行距）。

    Returns:
        块级布局结果 TextLayout。

    Raises:
        ValueError: font 候选列表为空或包含空名字。
    """
    return _layout_cached(text, normalize_spec(font), size_px, max_width, max_lines, line_height)
