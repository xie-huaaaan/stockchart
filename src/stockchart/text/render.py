r"""L1 文字绘制 API：锚点换算、整块旋转与多行绘制。

约定（docs/api.zh-CN/rendering.md）：anchor 九宫格中垂直方向参照整块文字
（top/middle/baseline/bottom；baseline 指首行基线），水平方向逐行生效
（center/right 按行居中/右对齐）；rotation 为绕 (x, y) 锚点顺时针角度，
先按 anchor 定位整块再旋转。\n 与 max_width 折行在 draw_text 内直接支持；
缺字形画方框占位，不抛异常。
"""

from __future__ import annotations

from typing import Literal

from stockchart.canvas import Canvas, skia_color
from stockchart.color import Color
from stockchart.defaults import DEFAULT_TEXT_COLOR
from stockchart.text.engine import paint_line
from stockchart.text.fonts import FontSpec
from stockchart.text.layout import break_lines, layout_text

type HorizontalAnchor = Literal["left", "center", "right"]
type VerticalAnchor = Literal["top", "middle", "baseline", "bottom"]
type TextAnchor = tuple[HorizontalAnchor, VerticalAnchor]
"""(x, y) 锚在文字块的哪一处；baseline 指首行基线。"""

# anchor 合法取值单独收拢，便于给出与类型别名一致的校验信息
_HORIZONTAL_ANCHORS = frozenset(("left", "center", "right"))
_VERTICAL_ANCHORS = frozenset(("top", "middle", "baseline", "bottom"))


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
    max_width: float | None = None,
    max_lines: int | None = None,
    line_height: float | None = None,
) -> None:
    r"""画一段文字（支持 \n 与按宽折行，逐段整形含 kerning/连字）。

    Args:
        canvas: 目标画布。
        text: 待绘制文本；空串直接返回。
        x: 锚点 x（画布输出像素）。
        y: 锚点 y（画布输出像素）。
        size_px: 字号（像素），须为正数。
        color: 文字颜色（方框占位同色）。
        font: 字体候选；None 用平台默认链。
        anchor: (x, y) 对应文字块的哪一处；垂直参照整块，水平逐行生效。
        rotation: 绕 (x, y) 顺时针旋转的角度（度）。
        max_width: 每行最大宽度（像素）；None 不折行。
        max_lines: 最多行数；None 不限。
        line_height: 行距倍率；None 用自然行距。

    Raises:
        ValueError: color 不是合法的 RGB/RGBA 元组、size_px 非正、
            anchor 取值非法，或 font 候选列表为空。
    """
    # 校验先于空串短路（与 layout.py 一致，fail-fast）：空串也不放过非法参数
    if size_px <= 0:
        raise ValueError(f"size_px 须为正数，得到 {size_px}")
    h, v = anchor
    if h not in _HORIZONTAL_ANCHORS or v not in _VERTICAL_ANCHORS:
        raise ValueError(f"anchor 取值非法：{anchor!r}")
    # 空行没有段可画，skia_color 不会在绘制路径里被触发，这里提前校验一次
    skia_color(color)
    if not text:
        return
    layout = layout_text(
        text,
        size_px=size_px,
        font=font,
        max_width=max_width,
        max_lines=max_lines,
        line_height=line_height,
    )
    # 垂直锚参照整块：先定块顶 y0，各行基线 = y0 + 首行基线 + i × 行距
    if v == "baseline":
        y0 = y - layout.baseline
    elif v == "top":
        y0 = y
    elif v == "middle":
        y0 = y - layout.height / 2
    else:  # bottom
        y0 = y - layout.height
    sc = canvas._skia_canvas()  # pyright: ignore[reportPrivateUsage]
    if rotation:
        # 绕 (x, y) 旋转：原点搬到锚点后，按未旋转坐标减去 (x, y) 的偏移绘制，
        # 与旧实现一致——anchor 定位出的整块绕锚点整体旋转
        sc.save()
        sc.translate(x, y)
        sc.rotate(rotation)
        ox, oy = x, y
    else:
        ox, oy = 0.0, 0.0
    for i, line in enumerate(layout.lines):
        # 水平锚逐行生效：center/right 按该行的前进宽度缩进
        if h == "left":
            x_i = x
        elif h == "center":
            x_i = x - line.advance / 2
        else:
            x_i = x - line.advance
        baseline_i = y0 + layout.baseline + i * layout.line_step
        paint_line(sc, line, x_i - ox, baseline_i - oy, size_px=size_px, color=color)
    if rotation:
        sc.restore()


def measure_text(
    text: str,
    *,
    size_px: float,
    font: FontSpec | None = None,
) -> float:
    """测量文字按 draw_text 相同规则排版后的宽度（多行取最宽行）。

    Args:
        text: 待测量文本；空串返回 0。
        size_px: 字号（像素）。
        font: 字体候选；None 用平台默认链。

    Returns:
        前进宽度（像素，含 kerning/连字）。

    Raises:
        ValueError: font 候选列表为空或包含空名字。
    """
    if not text:
        return 0.0
    return layout_text(text, size_px=size_px, font=font).width


def measure_text_height(
    text: str,
    *,
    size_px: float,
    font: FontSpec | None = None,
    line_height: float | None = None,
) -> float:
    """测量文字块的真实高度（按实际解析到的字体度量，多行含行距）。

    Args:
        text: 待测量文本；空串按单空行估算。
        size_px: 字号（像素）。
        font: 字体候选；None 用平台默认链。
        line_height: 行距倍率；None 用自然行距。

    Returns:
        块高（像素）。

    Raises:
        ValueError: font 候选列表为空或包含空名字。
    """
    return layout_text(text, size_px=size_px, font=font, line_height=line_height).height


def wrap_text(
    text: str,
    *,
    max_width: float,
    size_px: float,
    font: FontSpec | None = None,
    max_lines: int | None = None,
) -> list[str]:
    r"""按像素宽度把文本折成多行（\n 参与切分，末行可加省略号）。

    采用贪心断行，优先在空白或常见标点之后断开；中文可按字断行，英文单词
    过长时仍会断开。超过 max_lines 时末行加省略号；除单个字形本身超宽外，
    每行都不超过 max_width。

    Args:
        text: 待折行文本；空串返回 [""]。
        max_width: 每行最大宽度（像素）。
        size_px: 字号（像素）。
        font: 字体候选；None 用平台默认链。
        max_lines: 最多行数；None 表示不限。

    Returns:
        折行后的行字符串列表，至少包含一个元素。

    Raises:
        ValueError: font 候选列表为空或包含空名字。
    """
    return break_lines(text, size_px=size_px, font=font, max_width=max_width, max_lines=max_lines)
