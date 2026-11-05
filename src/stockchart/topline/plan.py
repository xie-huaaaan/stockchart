# L4 经由 BarPlot 的包内私有接口（槽位摆腿、柱记录）完成布局，
# 不触碰画布；故豁免跨模块私有成员检查。
# pyright: reportPrivateUsage=false

"""L4 规划：把数据变成摆好腿的 BarPlot。

选腿、算槽宽、组装柱子与样式循环都在这里；不触碰画布。
"""

from __future__ import annotations

from collections.abc import Sequence

from stockchart.defaults import (
    DEFAULT_AXIS_NAME_SIZE,
    DEFAULT_AXIS_STYLE,
    DEFAULT_BACKGROUND,
    DEFAULT_BAR_GAP,
    DEFAULT_HEIGHT_HEADROOM_RATIO,
    DEFAULT_TITLE_ALIGN,
    DEFAULT_TITLE_SIZE,
    DEFAULT_X_LABEL_SIZE,
)
from stockchart.legs import Leg
from stockchart.plot import BarPlot, Pairing, StyleCycle, XLabelPos
from stockchart.plot.scale import format_number
from stockchart.plot.styles import select_legs_for_groups
from stockchart.plot.types import BarRecord, LegSpec
from stockchart.text import FontSpec, measure_text
from stockchart.topline.options import ChartOptions, CycleMode

# 槽位两端的呼吸边距与标签加宽余量（默认值级别，不在 L4 参数中暴露）
_EDGE_PAD = DEFAULT_BAR_GAP
_LABEL_BREATH = 2 * DEFAULT_BAR_GAP


def format_value(value: float) -> str:
    """格式化数值标签（与刻度同一紧凑规则，宽度有界）。

    数值标签不参与画布布局预留，宽度必须有上界：6 位有效数字，绝对值 >= 10^6
    或 < 10^-4 时自动科学计数法；避免最短往返表示产生 0.30000000000000004
    这类超长串。

    Args:
        value: 数据值。

    Returns:
        数值的可读字符串。
    """
    return format_number(value)


def select_legs(
    rows: list[list[float]],
    *,
    paired: Pairing,
    seed: int,
) -> list[list[Leg]]:
    """按每组的系列数自动选腿。

    Args:
        rows: 二维数据；每行一组。
        paired: 配对策略。
        seed: 选腿随机源。

    Returns:
        与 rows 同构的 Leg 列表。
    """
    return select_legs_for_groups([len(row) for row in rows], paired=paired, seed=seed)


def plan_slots(
    specs: list[list[list[LegSpec]]],
    *,
    labels: Sequence[str] | None,
    bar_gap: float,
    font: FontSpec | None,
) -> list[float]:
    """计算每个槽的宽度。

    槽宽取“腿的自然宽度”与“标签宽度 + 呼吸余量”的较大者。

    Args:
        specs: 槽 → 列 → 腿规格的嵌套结构。
        labels: 每组标签；None 表示不加宽。
        bar_gap: 同槽相邻列之间的空隙。
        font: 标签字体，与 x 标签绘制保持一致；None 用平台默认链。

    Returns:
        每个槽的宽度（设计像素）。
    """
    slots_px: list[float] = []
    for g, slot in enumerate(specs):
        natural = sum(col[0].leg.width for col in slot) + (len(slot) - 1) * bar_gap
        if labels is not None:
            label_w = (
                measure_text(labels[g], size_px=DEFAULT_X_LABEL_SIZE, font=font) + _LABEL_BREATH
            )
            natural = max(natural, label_w)
        slots_px.append(natural)
    return slots_px


def assemble(
    specs: list[list[list[LegSpec]]],
    *,
    labels: Sequence[str] | None,
    title: str | None,
    xlabel: str | None,
    bar_gap: float,
    slot_gap: float,
    x_label_pos: XLabelPos,
    seed: int | None,
    options: ChartOptions,
) -> tuple[BarPlot, list[list[list[BarRecord]]]]:
    """按槽位建图并摆好腿。

    Args:
        specs: 槽 → 列 → 腿规格的嵌套结构。
        labels: 每组标签；None 表示不加 x 标签。
        title: 整图标题；None 表示不加。
        xlabel: x 轴名称；None 表示不加。
        bar_gap: 同槽相邻列之间的空隙。
        slot_gap: 相邻槽之间的空隙。
        x_label_pos: x 标签位置策略。
        seed: BarPlot 与选腿的随机源。
        options: 其余 L2 透传选项，含 height_px / width_px。

    Returns:
        `(BarPlot, 与 specs 同构的柱记录)`。
    """
    slots_px = plan_slots(specs, labels=labels, bar_gap=bar_gap, font=options.get("font"))
    width_px = options.get("width_px")
    if width_px is not None and width_px <= 0:
        raise ValueError(f"width_px 须为正数，得到 {width_px!r}")
    # 显式 width_px 不做内容宽度校验：过小时腿会超出画布被裁，已知边界，暂不处理。
    width = (
        width_px
        if width_px is not None
        else round(2 * _EDGE_PAD + sum(slots_px) + (len(specs) - 1) * slot_gap)
    )
    height_px = options.get("height_px")
    if height_px is None:
        # 腿始终按整腿高度绘制；在最高腿之上再留 10%，避免轴顶与腿口齐平。
        tallest_leg = max(spec.leg.height for slot in specs for column in slot for spec in column)
        height_px = tallest_leg + round(tallest_leg * DEFAULT_HEIGHT_HEADROOM_RATIO)
    elif height_px <= 0:
        raise ValueError(f"height_px 须为正数，得到 {height_px!r}")
    plot = BarPlot(
        width,
        extent_up=height_px,
        extent_down=0,
        background=options.get("background", DEFAULT_BACKGROUND),
        axis_style=options.get("axis_style", DEFAULT_AXIS_STYLE),
        font=options.get("font"),
        seed=seed,
    )
    records = plot._add_columns(
        specs,
        bar_gap=bar_gap,
        slot_gap=slot_gap,
        slots_px=slots_px,
        lead=_EDGE_PAD,
    )
    if labels is not None:
        plot.add_x_labels(
            list(labels),
            pos=x_label_pos,
            rotation=options.get("x_label_rotation", "auto"),
        )
    if title is not None:
        plot.add_title(
            title,
            align=options.get("title_align", DEFAULT_TITLE_ALIGN),
            size_px=options.get("title_size_px", DEFAULT_TITLE_SIZE),
        )
    if xlabel is not None:
        plot.add_x_axis_name(
            xlabel,
            size_px=options.get("axis_name_size_px", DEFAULT_AXIS_NAME_SIZE),
        )
    return plot, records


def check_labels(labels: Sequence[str] | None, n: int) -> Sequence[str] | None:
    """校验标签数量与组数一致。

    Args:
        labels: 标签序列或 None。
        n: 组数。

    Returns:
        原标签序列（或 None）。

    Raises:
        ValueError: 标签数量与组数不一致。
    """
    if labels is not None and len(labels) != n:
        raise ValueError(f"labels 与组数不一致：{len(labels)} != {n}")
    return labels


def check_series_labels(series_labels: Sequence[str] | None, n: int) -> Sequence[str] | None:
    """校验系列名数量与系列数一致。

    Args:
        series_labels: 系列名序列或 None。
        n: 系列数。

    Returns:
        原系列名序列（或 None）。

    Raises:
        ValueError: 系列名数量与系列数不一致。
    """
    if series_labels is not None and len(series_labels) != n:
        raise ValueError(f"series_labels 与系列数不一致：{len(series_labels)} != {n}")
    return series_labels


def resolve_cycle(cycle: CycleMode, *, is_1d: bool) -> StyleCycle:
    """解析样式循环方式。

    "auto" 在一维数据下用 "sequence"（组内循环会退化为全同），二维数据下
    用 "group"。

    Args:
        cycle: 调用方指定的循环方式。
        is_1d: 输入是否为一维。

    Returns:
        实际使用的 "group" 或 "sequence"。

    Raises:
        ValueError: cycle 不是 "auto" / "group" / "sequence"。
    """
    if cycle not in ("auto", "group", "sequence"):
        raise ValueError(f"cycle 须为 'auto'/'group'/'sequence'，得到 {cycle!r}")
    if cycle != "auto":
        return cycle
    return "sequence" if is_1d else "group"


def style_index(cycle: StyleCycle, *, g: int, s: int, series: int) -> int:
    """计算某根柱在样式列表中的序号。

    Args:
        cycle: 实际循环方式。
        g: 组索引。
        s: 系列索引。
        series: 每组系列数。

    Returns:
        样式列表下标（调用方再对长度取模）。
    """
    return g * series + s if cycle == "sequence" else s
