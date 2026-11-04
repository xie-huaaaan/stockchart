"""整形引擎：一行文本按字体分段，逐段经 skia.textlayout 整形、度量、绘制。

每段是"单字体、单行"的 Paragraph（内部 HarfBuzz + ICU）：kerning、连字与
段内 RTL 正确；段级 advance 取 LongestLine，基线距行顶取 AlphabeticBaseline
（=|ascent|，Paragraph.paint 的 y 传的是段落框顶部，二者配合即可精确共基线）。

无法解析字形的码点归入豆腐段（typeface 为 None），绘制时画描边方框占位，
不抛异常。段级 Paragraph 全局缓存：度量与颜色无关（共用一份），带颜色的
绘制缓存按颜色区分；缓存超限整体清空，避免长进程无界增长。
"""

# skia-python 不带类型桩：textlayout（Paragraph/TextStyle 等）成员均为
# unknown 类型，本文件定向关闭相关 unknown 报告；其余规则仍按 strict 执行。
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnknownParameterType=false, reportAttributeAccessIssue=false

from __future__ import annotations

from dataclasses import dataclass

import skia

from stockchart.canvas import skia_color
from stockchart.color import Color
from stockchart.defaults import DEFAULT_TOFU_ADVANCE_RATIO
from stockchart.text.fonts import (
    font_for,
    resolve_codepoint,
    shared_font_collection,
    shared_unicode,
    typeface_alias,
)

# layout 的折行比较是严格小于，传极宽宽度保证单行不折行
_NO_WRAP_WIDTH = 1e9
# 段级 Paragraph 缓存上限（超过整体清空；图表标签量级远小于此）
_PARAGRAPH_CACHE_LIMIT = 1024
# 度量用 Paragraph 的颜色（任意值皆可，黑色即 skia 的 0）
_METRICS_COLOR = 0

# 段级 Paragraph：key = (文本, Typeface.uniqueID, 字号, 颜色)
_paragraph_cache: dict[tuple[str, int, float, int], skia.textlayout.Paragraph] = {}


@dataclass(slots=True, frozen=True)
class Segment:
    """一行内同字体的连续文本段。

    Attributes:
        text: 段文本。
        typeface: 段字体；None 表示整段为方框占位（无可用字形）。
        advance: 段前进宽度（像素）。
        baseline: 段基线距行顶（像素，即 |ascent|）。
        descent: 段基线以下的深度（像素）。
    """

    text: str
    typeface: skia.Typeface | None
    advance: float
    baseline: float
    descent: float


@dataclass(slots=True, frozen=True)
class TextLine:
    """整形后的一行文本及其真实度量（混合字体时取各段最大值）。

    Attributes:
        text: 行文本（不含换行符）。
        segments: 按出现顺序的段列表。
        advance: 行前进宽度（各段 advance 之和）。
        baseline: 行基线距行顶（各段 ascent 的最大值）。
        height: 行高（baseline 加各段 descent 的最大值）。
    """

    text: str
    segments: tuple[Segment, ...]
    advance: float
    baseline: float
    height: float


def tofu_advance(size_px: float) -> float:
    """单个方框占位符的前进宽度。"""
    return DEFAULT_TOFU_ADVANCE_RATIO * size_px


def char_advance(ch: str, stack: tuple[skia.Typeface, ...], *, size_px: float) -> float:
    """单字符前进宽度的快速估计（折行判定用，不含 kerning/连字）。

    Args:
        ch: 单个字符。
        stack: fonts.resolve_stack 的结果。
        size_px: 字号（像素）。

    Returns:
        字符前进宽度（像素）；无可用字形时返回方框宽度。
    """
    tf = resolve_codepoint(stack, ord(ch))
    if tf is None:
        return tofu_advance(size_px)
    return font_for(tf, size_px).measureText(ch)


def _paragraph(
    text: str, tf: skia.Typeface, size_px: float, color_int: int
) -> skia.textlayout.Paragraph:
    """构建并布局单字体单行 Paragraph（缓存命中直接返回）。"""
    key = (text, tf.uniqueID(), size_px, color_int)
    paragraph = _paragraph_cache.get(key)
    if paragraph is None:
        style = skia.textlayout.TextStyle()
        style.setFontFamilies([typeface_alias(tf)])
        style.setFontSize(size_px)
        style.setColor(color_int)
        paragraph_style = skia.textlayout.ParagraphStyle()
        paragraph_style.setTextStyle(style)
        builder = skia.textlayout.ParagraphBuilder(
            paragraph_style, shared_font_collection(), shared_unicode()
        )
        builder.pushStyle(style)
        builder.addText(text)
        paragraph = builder.Build()
        paragraph.layout(_NO_WRAP_WIDTH)
        if len(_paragraph_cache) >= _PARAGRAPH_CACHE_LIMIT:
            _paragraph_cache.clear()
        _paragraph_cache[key] = paragraph
    return paragraph


def _segment(
    text: str,
    tf: skia.Typeface | None,
    stack: tuple[skia.Typeface, ...],
    *,
    size_px: float,
) -> Segment:
    """计算单个文本段的度量（豆腐段的度量取栈首字体）。"""
    if tf is None:
        return Segment(
            text, None, tofu_advance(size_px) * len(text), *_primary_metrics(stack, size_px)
        )
    paragraph = _paragraph(text, tf, size_px, _METRICS_COLOR)
    baseline = float(paragraph.AlphabeticBaseline)
    return Segment(
        text,
        tf,
        float(paragraph.LongestLine),
        baseline,
        float(paragraph.Height) - baseline,
    )


def _primary_metrics(stack: tuple[skia.Typeface, ...], size_px: float) -> tuple[float, float]:
    """栈首字体的 (基线距行顶, 基线下深度)，用于空行与豆腐段的度量。"""
    metrics = font_for(stack[0], size_px).getMetrics()
    return -float(metrics.fAscent), float(metrics.fDescent)


def _split_segments(
    line: str, stack: tuple[skia.Typeface, ...], *, size_px: float
) -> list[Segment]:
    """按逐码点解析结果把一行切成同字体连续段。

    相邻且 Typeface.uniqueID 相同的字符合并（不同候选名可能解析到同一
    字体，按字体合并避免无谓分段破坏 kerning）。
    """
    groups: list[tuple[int, skia.Typeface | None, list[str]]] = []
    for ch in line:
        tf = resolve_codepoint(stack, ord(ch))
        uid = -1 if tf is None else tf.uniqueID()
        if groups and groups[-1][0] == uid:
            groups[-1][2].append(ch)
        else:
            groups.append((uid, tf, [ch]))
    return [_segment("".join(chars), tf, stack, size_px=size_px) for _, tf, chars in groups]


def shape_line(line: str, stack: tuple[skia.Typeface, ...], *, size_px: float) -> TextLine:
    """把一行文本整形为段级结构并计算真实度量。

    Args:
        line: 单行文本（不含换行符）；空串返回零宽行，度量取栈首字体。
        stack: fonts.resolve_stack 的结果。
        size_px: 字号（像素）。

    Returns:
        整形后的 TextLine。
    """
    if not line:
        baseline, descent = _primary_metrics(stack, size_px)
        return TextLine(line, (), 0.0, baseline, baseline + descent)
    segments = _split_segments(line, stack, size_px=size_px)
    baseline = max(seg.baseline for seg in segments)
    descent = max(seg.descent for seg in segments)
    return TextLine(
        line,
        tuple(segments),
        sum(seg.advance for seg in segments),
        baseline,
        baseline + descent,
    )


def paint_line(
    sc: skia.Canvas,
    line: TextLine,
    x: float,
    baseline_y: float,
    *,
    size_px: float,
    color: Color,
) -> None:
    """把一行文本画到 skia 画布的指定基线位置。

    Args:
        sc: skia 画布（当前变换矩阵生效，外层缩放/旋转均可）。
        line: shape_line 的结果。
        x: 行左缘 x。
        baseline_y: 行基线 y。
        size_px: 字号（像素），用于查段级绘制缓存与豆腐框尺寸。
        color: 文字颜色（豆腐框描边同色）。
    """
    color_int = skia_color(color)
    cursor = x
    for seg in line.segments:
        if seg.typeface is None:
            _paint_tofu(sc, cursor, baseline_y, line, len(seg.text), size_px, color_int)
        else:
            paragraph = _paragraph(seg.text, seg.typeface, size_px, color_int)
            # paint 的 y 是段落框顶部；段自身 baseline 对齐到目标基线
            paragraph.paint(sc, cursor, baseline_y - paragraph.AlphabeticBaseline)
        cursor += seg.advance


def _paint_tofu(
    sc: skia.Canvas,
    x: float,
    baseline_y: float,
    line: TextLine,
    count: int,
    size_px: float,
    color_int: int,
) -> None:
    """画 count 个缺字形方框占位（描边矩形，保证有墨迹且可测量）。"""
    box_w = tofu_advance(size_px)
    stroke = max(1.0, size_px * 0.04)
    top = baseline_y - line.baseline + stroke
    bottom = baseline_y + (line.height - line.baseline) - stroke
    paint = skia.Paint(
        AntiAlias=True,
        Color=color_int,
        Style=skia.Paint.kStroke_Style,
        StrokeWidth=stroke,
    )
    for i in range(count):
        left = x + i * box_w + stroke / 2
        sc.drawRect(skia.Rect.MakeLTRB(left, top, left + box_w - stroke, bottom), paint)
