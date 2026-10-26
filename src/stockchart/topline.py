# L4 经由 BarPlot 的包内私有接口（槽位摆腿、柱记录）完成布局，
# 不触碰画布；故豁免跨模块私有成员检查。
# pyright: reportPrivateUsage=false

"""L4 一行出图：bar 与 mirror_bar。数据归一化 + 全自动布局。

映射规则见 docs/api.md；腿的摆放经由 BarPlot 的私有槽位接口完成，
本模块不直接操作画布。丝袜高度映射与腿的布局是分开的两层。
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from typing import Literal

import numpy as np

from stockchart.defaults import (
    DEFAULT_AXIS_STYLE,
    DEFAULT_BAR_GAP,
    DEFAULT_GROUP_GAP,
    DEFAULT_MAX_FILL,
    DEFAULT_MIN_FILL,
    DEFAULT_SEED,
    DEFAULT_STOCKING_STYLE,
    DEFAULT_X_LABEL_SIZE,
    DEFAULT_Y_EXTENT,
)
from stockchart.legs import Leg
from stockchart.library import LegLibrary
from stockchart.plot import (
    AxisStyle,
    BarPlot,
    BarSide,
    Scale,
    StyleCycle,
    XLabelPos,
    _BarRecord,
    _format_tick,
    _LegSpec,
    _normalize_style_seq,
)
from stockchart.stocking import StyleSeq
from stockchart.text import measure_text

type NestedData = Sequence[float] | Sequence[Sequence[float]]
type CycleMode = Literal["auto", "group", "sequence"]

# 槽位两端的呼吸边距与标签加宽余量（默认值级别，不在 L4 参数中暴露）
_EDGE_PAD = DEFAULT_BAR_GAP
_LABEL_BREATH = 2 * DEFAULT_BAR_GAP


def _normalize(data: NestedData) -> tuple[list[list[float]], bool]:
    """把一维/二维输入统一为 (槽数, 槽内值数) 的浮点矩阵，并标明是否一维。

    一维数据视为"每组 1 个值"。
    """
    rows_raw: Sequence[Sequence[float]]
    is_1d: bool
    if isinstance(data, np.ndarray):
        is_1d = data.ndim == 1
        rows_raw = data.tolist()
    else:
        first = data[0] if data else None
        is_1d = not isinstance(first, (list, tuple, np.ndarray))
        rows_raw = data  # type: ignore[assignment]
    if not rows_raw:
        raise ValueError("data 为空")
    if is_1d:
        rows = [[float(v)] for v in rows_raw]  # type: ignore[arg-type]
    else:
        rows = [[float(v) for v in row] for row in rows_raw]
    if any(not row for row in rows):
        raise ValueError("data 存在空组")
    return rows, is_1d


def _series_count(rows: list[list[float]]) -> int:
    """二维数据的系列数；行不齐时报错。"""
    counts = {len(row) for row in rows}
    if len(counts) != 1:
        raise ValueError(f"二维数据各组系列数须一致，得到 {sorted(counts)}")
    return counts.pop()


def _select_legs(
    rows: list[list[float]],
    *,
    paired: bool,
    seed: int,
) -> list[list[Leg]]:
    """自动选腿。

    恰好 2 系列且 paired 时每组同用一对（系列 0 左腿），否则跨列
    左、右、左、右……交替。
    """
    lib = LegLibrary(seed=seed)
    series = _series_count(rows)
    if series == 2 and paired:
        pairs = lib.sample_pairs(len(rows))
        return [list(pair) for pair in pairs]
    flat = lib.alternate(len(rows) * series)
    return [flat[g * series : (g + 1) * series] for g in range(len(rows))]


def _plan_slots(
    specs: list[list[list[_LegSpec]]],
    *,
    labels: Sequence[str] | None,
    bar_gap: float,
) -> list[float]:
    """每槽占宽 = max(腿自然宽度, 标签宽度 + 呼吸余量)。"""
    slots_px: list[float] = []
    for g, slot in enumerate(specs):
        natural = sum(col[0].leg.width for col in slot) + (len(slot) - 1) * bar_gap
        if labels is not None:
            label_w = measure_text(labels[g], size_px=DEFAULT_X_LABEL_SIZE) + _LABEL_BREATH
            natural = max(natural, label_w)
        slots_px.append(natural)
    return slots_px


def _assemble(
    specs: list[list[list[_LegSpec]]],
    *,
    labels: Sequence[str] | None,
    title: str | None,
    bar_gap: float,
    slot_gap: float,
    width_px: int | None,
    extent_up: int,
    extent_down: int,
    x_label_pos: XLabelPos = "content",
    axis_style: AxisStyle = DEFAULT_AXIS_STYLE,
    seed: int | None,
) -> tuple[BarPlot, list[list[list[_BarRecord]]]]:
    """按槽位建图并摆好腿，返回 (BarPlot, 与 specs 同构的柱记录)。"""
    slots_px = _plan_slots(specs, labels=labels, bar_gap=bar_gap)
    width = (
        width_px
        if width_px is not None
        else round(2 * _EDGE_PAD + sum(slots_px) + (len(specs) - 1) * slot_gap)
    )
    plot = BarPlot(
        width,
        extent_up=extent_up,
        extent_down=extent_down,
        axis_style=axis_style,
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
        plot.add_x_labels(list(labels), pos=x_label_pos)
    if title is not None:
        plot.add_title(title)
    return plot, records


def _check_labels(labels: Sequence[str] | None, n: int) -> Sequence[str] | None:
    if labels is not None and len(labels) != n:
        raise ValueError(f"labels 与组数不一致：{len(labels)} != {n}")
    return labels


def _resolve_cycle(cycle: CycleMode, *, is_1d: bool) -> StyleCycle:
    """解析样式循环方式：auto 一维按整体循环（组内循环会退化为全同）、二维按组内位置。"""
    if cycle != "auto":
        return cycle
    return "sequence" if is_1d else "group"


def _style_index(cycle: StyleCycle, *, g: int, s: int, series: int) -> int:
    """某根柱在样式列表中的序号：整体循环按绘制顺序，组内循环只看系列位置。"""
    return g * series + s if cycle == "sequence" else s


def bar(
    data: NestedData,
    *,
    labels: Sequence[str] | None = None,
    series_labels: Sequence[str] | None = None,
    title: str | None = None,
    style: StyleSeq = DEFAULT_STOCKING_STYLE,
    cycle: CycleMode = "auto",
    paired: bool = True,
    value_labels: bool = False,
    grid: bool = False,
    max_fill: float = DEFAULT_MAX_FILL,
    min_fill: float = DEFAULT_MIN_FILL,
    y_extent: int = DEFAULT_Y_EXTENT,
    width_px: int | None = None,
    axis_style: AxisStyle = DEFAULT_AXIS_STYLE,
    seed: int | None = None,
) -> BarPlot:
    """全朝上的柱状图：自动完成数据到丝袜高度的映射、选腿与布局。

    返回布局完毕的 BarPlot（可直接 .save() / .render()，也可继续手工微调）。

    自动绘制 y 轴与基线；labels 传入时 x 标签自动与各组对齐；画布宽缺省时
    按腿、间距与标签宽度自适应。坐标轴默认直线，axis_style="handdrawn"
    改为手绘抖动。

    Args:
        data: 一维为单序列；二维为 (组数, 系列数) 的分组数据。
        labels: 每组（无分组时每根柱）一个标签。
        series_labels: 每系列一个名字，传入即自动生成图例（marker 为各系列
            样式的织物色块）。仅二维数据可用，一维数据传入抛 ValueError。
        style: 单个样式，或样式列表——循环方式由 cycle 决定。
        cycle: "group" 按组内位置循环（组内第 i 根取 styles[i % len]），
            "sequence" 按全部柱子的绘制顺序循环；"auto"（默认）一维取
            "sequence"（每根柱按顺序取样式）、二维取 "group"（长度等于系列数
            时即"每系列一个样式"）。二维数据下 "sequence" 无法与图例的系列
            样式对应，同时传 series_labels 抛 ValueError。
        paired: 仅当数据恰好 2 系列时生效（默认 True）：每组使用同一对素材，
            系列 0 左腿、系列 1 右腿；其余系列数时忽略此参数。
        value_labels: True 时在袜口上方手写数值。
        grid: True 时沿 y 轴各刻度画横向手绘虚线（浅色，压在腿与袜之下）。
        max_fill: 最大值映射到 y_extent 的比例（默认 0.8）。
        min_fill: 仅当数据含负值时启用（默认 0.1），见下。
        y_extent: 基线上方预留的像素高度。
        width_px: 画布宽；缺省按腿数、间距与标签宽度自适应。
        axis_style: 坐标轴样式，"clean"（默认）为直线，"handdrawn" 为手绘抖动。

    数据 → 丝袜高度（基线对应的数据值默认 0）:
        - 全部数据为 0: 全部裸腿。
        - 无负值: height = v / max × max_fill × y_extent，0 值即裸腿。
        - 含负值: 整个值域 [min, max] 线性压缩到 [min_fill, max_fill]。
          此时 0 值的腿带一段丝袜、y 轴 0 刻度悬在丝袜中间某处——这是为完整
          保留大小关系所做的既定取舍。全负数据同规则：值越大丝袜越高。
    """
    rows, is_1d = _normalize(data)
    if series_labels is not None and is_1d:
        raise ValueError("series_labels 仅支持二维（分组）数据；一维数据请用 labels")
    series = _series_count(rows) if not is_1d else 1
    mode = _resolve_cycle(cycle, is_1d=is_1d)
    if series_labels is not None and mode == "sequence":
        raise ValueError("series_labels 需要固定的系列样式，请用 cycle='group'")
    _check_labels(labels, len(rows))

    rng = random.Random(DEFAULT_SEED if seed is None else seed)
    legs = _select_legs(rows, paired=paired, seed=rng.getrandbits(32))
    styles = _normalize_style_seq(style)

    flat = [v for row in rows for v in row]
    vmin, vmax = min(flat), max(flat)
    if vmax == 0 and vmin == 0:
        heights = [[0.0] * len(row) for row in rows]
        scale = Scale((0.0, 1.0), (0.0, float(y_extent)))
        ticks: list[float] | None = [0.0]
    elif vmin >= 0:
        heights = [[v / vmax * max_fill * y_extent for v in row] for row in rows]
        scale = Scale((0.0, vmax), (0.0, max_fill * y_extent))
        ticks = None
    else:
        span = vmax - vmin
        heights = [
            [
                (v - vmin) / span * (max_fill - min_fill) * y_extent + min_fill * y_extent
                for v in row
            ]
            for row in rows
        ]
        scale = Scale((vmin, vmax), (min_fill * y_extent, max_fill * y_extent))
        ticks = None

    specs: list[list[list[_LegSpec]]] = []
    for g, row in enumerate(rows):
        slot: list[list[_LegSpec]] = []
        for s in range(len(row)):
            idx = _style_index(mode, g=g, s=s, series=len(row))
            slot.append([_LegSpec(legs[g][s], heights[g][s], "up", styles[idx % len(styles)])])
        specs.append(slot)

    slot_gap = DEFAULT_BAR_GAP if is_1d else DEFAULT_GROUP_GAP
    plot, records = _assemble(
        specs,
        labels=labels,
        title=title,
        bar_gap=DEFAULT_BAR_GAP,
        slot_gap=slot_gap,
        width_px=width_px,
        extent_up=y_extent,
        extent_down=0,
        axis_style=axis_style,
        seed=seed,
    )
    if value_labels:
        for g, row in enumerate(rows):
            for s, v in enumerate(row):
                records[g][s][0].value_label = _format_tick(v)
    plot.add_y_axis(scale, ticks=ticks, grid=grid)
    if series_labels is not None:
        plot.add_legend([(series_labels[s], styles[s % len(styles)]) for s in range(series)])
    return plot


def mirror_bar(
    data: NestedData,
    *,
    mode: Literal["single", "both"] = "single",
    labels: Sequence[str] | None = None,
    series_labels: Sequence[str] | None = None,
    title: str | None = None,
    style: StyleSeq = DEFAULT_STOCKING_STYLE,
    cycle: CycleMode = "auto",
    paired: bool = True,
    value_labels: bool = False,
    grid: bool = False,
    max_abs_fill: float = DEFAULT_MAX_FILL,
    x_label_pos: XLabelPos = "auto",
    y_extent: int = DEFAULT_Y_EXTENT,
    width_px: int | None = None,
    axis_style: AxisStyle = DEFAULT_AXIS_STYLE,
    seed: int | None = None,
) -> BarPlot:
    """正负镜像柱状图：正值画基线上方腿，负值画下方翻转腿（脚贴基线）。

    y 轴随负刻度向下延伸。

    Args:
        mode: "single" 只画数据侧的腿；"both" 上下都画，数据侧穿丝袜、
            另一侧裸腿。
        labels: 每组（无分组时每根柱）一个标签。
        series_labels: 语义同 bar()。
        style: 语义同 bar()。
        cycle: 语义同 bar()。
        paired: 语义同 bar()。
        value_labels: True 时手写数值，上方腿写在袜口上方、下方腿写在袜口下方。
        grid: 语义同 bar()。
        max_abs_fill: 最大绝对值映射到 y_extent 的比例（默认 0.8）。
        x_label_pos: x 标签位置（语义见 BarPlot.add_x_labels）。默认 "auto"：
            贴着基线、选没有腿的一侧——例如全负数据标签在基线上方，标签
            紧邻轴而不是挂在最低腿之下；正负混合或 mode="both" 时两侧都有腿，
            退回 "content" 画在全部内容最低点之下。
        axis_style: 坐标轴样式，"clean"（默认）为直线，"handdrawn" 为手绘抖动。

    规则:
        - 比例 = max_abs_fill × y_extent / max|v|，正负同比例。
        - 0 视为 +0: "single" 下画一条朝上裸腿；"both" 下上下均画裸腿（上为数据侧）。
        - 下方空间: "single" 仅在存在负值时保留；"both" 始终保留。
    """
    rows, is_1d = _normalize(data)
    if series_labels is not None and is_1d:
        raise ValueError("series_labels 仅支持二维（分组）数据；一维数据请用 labels")
    series = _series_count(rows) if not is_1d else 1
    mode_cycle = _resolve_cycle(cycle, is_1d=is_1d)
    if series_labels is not None and mode_cycle == "sequence":
        raise ValueError("series_labels 需要固定的系列样式，请用 cycle='group'")
    _check_labels(labels, len(rows))

    rng = random.Random(DEFAULT_SEED if seed is None else seed)
    legs = _select_legs(rows, paired=paired, seed=rng.getrandbits(32))
    styles = _normalize_style_seq(style)

    flat = [v for row in rows for v in row]
    vmax_abs = max(abs(v) for v in flat)
    vmin, vmax = min(flat), max(flat)
    if vmax_abs == 0:
        # 全 0：比例无定义，按裸腿处理，刻度只留 0
        ratio = 0.0
        scale = Scale((0.0, 1.0), (0.0, float(y_extent)))
        ticks: list[float] | None = [0.0]
    else:
        ratio = max_abs_fill * y_extent / vmax_abs
        lo = min(0.0, vmin)
        hi = max(0.0, vmax)
        scale = Scale((lo, hi), (lo * ratio, hi * ratio))
        ticks = None

    both = mode == "both"
    specs: list[list[list[_LegSpec]]] = []
    for g, row in enumerate(rows):
        slot: list[list[_LegSpec]] = []
        for s, v in enumerate(row):
            idx = _style_index(mode_cycle, g=g, s=s, series=len(row))
            st = styles[idx % len(styles)]
            h = abs(v) * ratio
            side: BarSide = "up" if v >= 0 else "down"
            # 数据侧在首位，value_labels 只标数据侧
            col = [_LegSpec(legs[g][s], h, side, st)]
            if both:
                other: BarSide = "down" if side == "up" else "up"
                col.append(_LegSpec(legs[g][s], 0.0, other, st))
            slot.append(col)
        specs.append(slot)

    slot_gap = DEFAULT_BAR_GAP if is_1d else DEFAULT_GROUP_GAP
    plot, records = _assemble(
        specs,
        labels=labels,
        title=title,
        bar_gap=DEFAULT_BAR_GAP,
        slot_gap=slot_gap,
        width_px=width_px,
        extent_up=y_extent,
        extent_down=0,
        x_label_pos=x_label_pos,
        axis_style=axis_style,
        seed=seed,
    )
    if value_labels:
        for g, row in enumerate(rows):
            for s, v in enumerate(row):
                records[g][s][0].value_label = _format_tick(v)
    plot.add_y_axis(scale, ticks=ticks, grid=grid)
    if series_labels is not None:
        plot.add_legend([(series_labels[s], styles[s % len(styles)]) for s in range(series)])
    return plot
