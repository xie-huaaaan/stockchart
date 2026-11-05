"""L4 透传选项：ChartOptions 与选项校验。

键名与 L2 接口一致；未知键直接报错，避免拼错的参数被静默忽略。
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Literal, TypedDict

from stockchart.color import Color
from stockchart.plot import AxisStyle, LegendLoc, TitleAlign, XLabelPos, XLabelRotation
from stockchart.text import FontSpec

type CycleMode = Literal["auto", "group", "sequence"]


class ChartOptions(TypedDict, total=False):
    """L4 透传给下层的可选参数；键名与 L2 接口一致。

    Attributes:
        axis_style: 坐标轴样式，"clean" 或 "handdrawn"。
        background: 画布背景色。
        bar_gap: 组内相邻腿边缘之间的空隙（设计像素）。
        group_gap: 组间空隙（设计像素）。
        font: 全图默认字体（家族名、字体文件路径或候选列表），作用于标题、
            轴名称、刻度、x 标签、图例与数值标签；None 用平台默认链。
        grid: 是否画 y 刻度横向虚线。
        ticks: 显式刻度值；None 表示自动生成。
        x_label_pos: x 标签位置策略。
        x_label_rotation: x 标签旋转策略。
        title_align: 标题对齐方式。
        title_size_px: 标题字号（设计像素）。
        axis_name_size_px: 轴名称字号（设计像素）。
        legend_loc: 图例在顶部或底部。
        legend_ncol: 图例列数；None 表示自动换行。
        height_px: 基线上方柱区高度；None 表示按最高腿设计高度再加 10% 留白。
        width_px: 绘图区宽度；None 表示按腿、间距与标签宽度自动计算。
    """

    axis_style: AxisStyle
    background: Color
    bar_gap: float
    group_gap: float
    font: FontSpec | None
    grid: bool
    ticks: Sequence[float] | None
    x_label_pos: XLabelPos
    x_label_rotation: XLabelRotation
    title_align: TitleAlign
    title_size_px: float
    axis_name_size_px: float
    legend_loc: LegendLoc
    legend_ncol: int | None
    height_px: int | None
    width_px: int | None


_OPTION_KEYS: frozenset[str] = frozenset(
    {
        "axis_style",
        "background",
        "bar_gap",
        "group_gap",
        "font",
        "grid",
        "ticks",
        "x_label_pos",
        "x_label_rotation",
        "title_align",
        "title_size_px",
        "axis_name_size_px",
        "legend_loc",
        "legend_ncol",
        "height_px",
        "width_px",
    }
)


def check_options(options: ChartOptions) -> None:
    """拒绝未知选项，避免拼错的参数被静默忽略。

    Args:
        options: 调用方传入的关键字选项。

    Raises:
        TypeError: 含 _OPTION_KEYS 之外的键。
    """
    unknown = sorted(set(options) - _OPTION_KEYS)
    if unknown:
        raise TypeError(
            f"未知参数：{'、'.join(unknown)}；可用选项：{'、'.join(sorted(_OPTION_KEYS))}"
        )


def check_positive(name: str, value: float) -> None:
    """校验一个映射参数为正的有限数值。

    Args:
        name: 参数名，用于错误信息。
        value: 待校验的值。

    Raises:
        ValueError: 值不是有限正数。
    """
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} 须为正数，得到 {value!r}")


def check_fill_bounds(max_fill: float, min_fill: float) -> None:
    """校验正负值压缩区间 0 <= min_fill < max_fill <= 1。

    Args:
        max_fill: 最大值映射比例。
        min_fill: 含负值时值域下界比例。

    Raises:
        ValueError: 两个比例不是有限数、max_fill 超过 1，或区间不合法。
    """
    check_positive("max_fill", max_fill)
    if max_fill > 1.0:
        raise ValueError(f"max_fill 须在 (0, 1]，得到 {max_fill!r}")
    if not math.isfinite(min_fill) or not 0.0 <= min_fill < max_fill:
        raise ValueError(f"min_fill 须满足 0 <= min_fill < max_fill，得到 {min_fill!r}")
