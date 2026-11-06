"""L4 一行出图：bar 与 mirror_bar。数据归一化 + 全自动布局。

映射规则见 docs/api.zh-CN/charts.md；腿的摆放经由 BarPlot 的私有槽位接口完成，
本模块不直接操作画布。丝袜高度映射与腿的布局是分开的两层。
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from typing import Literal, Unpack

from stockchart.data import DataInput, normalize_data
from stockchart.defaults import (
    DEFAULT_AXIS_NAME_SIZE,
    DEFAULT_BAR_GAP,
    DEFAULT_GROUP_GAP,
    DEFAULT_MAX_FILL,
    DEFAULT_MIN_FILL,
    DEFAULT_STOCKING_STYLE,
)
from stockchart.library import DEFAULT_LEG_LIBRARY, LegLibrary
from stockchart.plot import BarPlot, BarSide, Pairing, Scale
from stockchart.plot.styles import normalize_style_seq
from stockchart.plot.types import LegSpec
from stockchart.stocking import StyleSeq
from stockchart.topline.options import (
    ChartOptions,
    CycleMode,
    check_fill_bounds,
    check_options,
    check_positive,
)
from stockchart.topline.plan import (
    assemble,
    check_labels,
    check_series_labels,
    format_value,
    resolve_cycle,
    select_legs,
    style_index,
)


def bar(
    data: DataInput,
    *,
    labels: Sequence[str] | None = None,
    series_labels: Sequence[str] | None = None,
    title: str | None = None,
    xlabel: str | None = None,
    ylabel: str | None = None,
    style: StyleSeq = DEFAULT_STOCKING_STYLE,
    cycle: CycleMode = "auto",
    paired: Pairing = "auto",
    value_labels: bool = False,
    max_fill: float = DEFAULT_MAX_FILL,
    min_fill: float = DEFAULT_MIN_FILL,
    seed: int | None = None,
    library: LegLibrary = DEFAULT_LEG_LIBRARY,
    **options: Unpack[ChartOptions],
) -> BarPlot:
    """全朝上的柱状图：自动完成数据到丝袜高度的映射、选腿与布局。

    自动绘制 y 轴与基线；labels 传入时 x 标签自动与各组对齐；绘图区宽度
    缺省时按腿、间距与标签宽度自适应，最终画布会因轴、标签与标题更宽。
    坐标轴默认直线，axis_style="handdrawn" 改为手绘抖动。

    Args:
        data: 支持一维/二维序列、numpy 数组、dict、pandas 风格表对象与
            PlotData；DataFrame 的 index/columns 会自动成为 x 标签与系列名。
            完整列表见 docs/api.zh-CN/data-input.md。
        labels: 每组（无分组时每根柱）一个标签；缺省用数据里推断的标签。
        series_labels: 每系列一个名字，传入即自动生成图例（marker 为各系列
            样式的织物色块）；缺省用数据里推断的系列名。仅二维数据可用，
            一维数据传入抛 ValueError。
        title: 整图标题，默认在绘图区上方水平居中；title_align="left" 改左对齐。
        xlabel: x 轴名称，写在 x 标签下方。
        ylabel: y 轴名称，写在刻度数字左侧；中日韩文字逐字竖排，拉丁与
            数字整体旋转 90°（详见 add_y_axis_name）。
        style: 单个样式，或样式列表——循环方式由 cycle 决定。
        cycle: "group" 按组内位置循环（组内第 i 根取 styles[i % len]），
            "sequence" 按全部柱子的绘制顺序循环；"auto"（默认）一维取
            "sequence"（每根柱按顺序取样式）、二维取 "group"（长度等于系列数
            时即"每系列一个样式"）。二维数据下若 "sequence" 无法与图例的系列
            样式对应，同时传 series_labels 抛 ValueError。
        paired: 选腿的配对策略。"auto"（默认）单系列用 "none"、多系列用
            "global"；"group" 每组独立取完整对：系列 0、1 同一对（左、右），
            系列 2 起继续取下一对（单系列即每组取新素材对的左腿）；
            "global" 整张图连续取对，配对可以跨组；"none" 从全部腿中优先
            不重复选取，包括未配对素材。
        value_labels: True 时在袜口上方手写数值（6 位有效数字；绝对值 ≥ 10⁶
            或 < 10⁻⁴ 时用科学计数法；不参与布局预留）。
        max_fill: 最大值映射到素材设计高度的比例，须在 (0, 1]（默认 0.85）。
        min_fill: 仅当数据含负值时启用（默认 0.1），见下。
        library: 自动选腿使用的素材库，默认 DEFAULT_LEG_LIBRARY。
        options: 透传给下层的可选项（grid、axis_style、legend_loc、bar_gap、
            height_px、width_px 等），见 docs/api.zh-CN/charts.md 的
            ChartOptions 表。height_px 为基线上方柱区高度，缺省按最高腿设计高度
            再加 10% 留白；显式值小于整腿高度时仍会扩到整腿高。width_px
            为绘图区宽度，缺省自适应。

    Returns:
        已布局并添加图例/轴/标题的 BarPlot；可直接 `.save()` / `.render()`，
        也可继续手工微调。

    Raises:
        TypeError: 数据类型不受支持，或 options 含未知键。
        ValueError: 标签长度不符、series_labels 用于一维数据、cycle 不合法、
            max_fill/min_fill/height_px/width_px 不合法、样式列表为空/未知预设，
            或数据内容不合法。

    数据 → 丝袜高度（基线对应的数据值默认 0）:
        - 参考高度取本次选中腿中最小的设计高度，保证所有腿都不截顶；
          内置素材均为 720。
        - 全部数据为 0: 全部裸腿。
        - 无负值: height = v / max × max_fill × 参考高度，0 值即裸腿。
        - 含负值: 整个值域 [min, max] 线性压缩到 [min_fill, max_fill]。
          此时 0 值的腿带一段丝袜、y 轴 0 刻度悬在丝袜中间某处——这是为完整
          保留大小关系所做的既定取舍。全负数据同规则：值越大丝袜越高；
          全负且所有值相同（没有大小关系）时统一取 min_fill。
    """
    check_options(options)
    check_fill_bounds(max_fill, min_fill)
    normalized = normalize_data(data)
    rows = [list(row) for row in normalized.values]
    is_1d = normalized.is_1d
    if labels is None:
        labels = normalized.labels
    if series_labels is None:
        series_labels = normalized.series_labels
    if series_labels is not None and is_1d:
        raise ValueError("series_labels 仅支持二维（分组）数据；一维数据请用 labels")
    series = len(rows[0])
    check_labels(labels, len(rows))
    check_series_labels(series_labels, series)
    mode = resolve_cycle(cycle, is_1d=is_1d)
    if series_labels is not None and mode == "sequence":
        raise ValueError("series_labels 需要固定的系列样式，请用 cycle='group'")

    rng = random.Random(seed)
    legs = select_legs(rows, paired=paired, seed=rng.getrandbits(32), library=library)
    styles = normalize_style_seq(style)
    # 所有柱共用最矮腿的设计高度作为 100%，排序在截顶保护下仍可直接比较；
    # 内置素材高度均为 720，因此等价于以 720 为参考。
    design_height = float(min(leg.height for row in legs for leg in row))

    flat = [v for row in rows for v in row]
    vmin, vmax = min(flat), max(flat)
    if vmax == 0 and vmin == 0:
        heights = [[0.0] * len(row) for row in rows]
        scale = Scale((0.0, 1.0), (0.0, design_height))
        ticks: list[float] | None = [0.0]
    elif vmin >= 0:
        heights = [[v / vmax * max_fill * design_height for v in row] for row in rows]
        scale = Scale((0.0, vmax), (0.0, max_fill * design_height))
        ticks = None
    else:
        span = vmax - vmin
        if span == 0:
            # 全部为同一负值：没有可压缩的大小关系，统一取下界；刻度按
            # [vmin, 0] 展开，避免除零并让 0 刻度落在正常位置。
            heights = [[min_fill * design_height] * len(row) for row in rows]
            scale = Scale((vmin, 0.0), (min_fill * design_height, max_fill * design_height))
            ticks = None
        else:
            heights = [
                [
                    (v - vmin) / span * (max_fill - min_fill) * design_height
                    + min_fill * design_height
                    for v in row
                ]
                for row in rows
            ]
            scale = Scale((vmin, vmax), (min_fill * design_height, max_fill * design_height))
            ticks = None

    specs: list[list[list[LegSpec]]] = []
    for g, row in enumerate(rows):
        slot: list[list[LegSpec]] = []
        for s in range(len(row)):
            idx = style_index(mode, g=g, s=s, series=len(row))
            slot.append([LegSpec(legs[g][s], heights[g][s], "up", styles[idx % len(styles)])])
        specs.append(slot)

    bar_gap = options.get("bar_gap", DEFAULT_BAR_GAP)
    slot_gap = options.get("group_gap", DEFAULT_BAR_GAP if is_1d else DEFAULT_GROUP_GAP)
    plot, records = assemble(
        specs,
        labels=labels,
        title=title,
        xlabel=xlabel,
        bar_gap=bar_gap,
        slot_gap=slot_gap,
        x_label_pos=options.get("x_label_pos", "content"),
        seed=seed,
        options=options,
        library=library,
    )
    if value_labels:
        for g, row in enumerate(rows):
            for s, v in enumerate(row):
                records[g][s][0].value_label = format_value(v)
    plot.add_y_axis(scale, ticks=options.get("ticks", ticks), grid=options.get("grid", False))
    if ylabel is not None:
        plot.add_y_axis_name(
            ylabel, size_px=options.get("axis_name_size_px", DEFAULT_AXIS_NAME_SIZE)
        )
    if series_labels is not None:
        plot.add_legend(
            [(series_labels[s], styles[s % len(styles)]) for s in range(series)],
            ncol=options.get("legend_ncol"),
            loc=options.get("legend_loc", "top"),
        )
    return plot


def mirror_bar(
    data: DataInput,
    *,
    mode: Literal["single", "both"] = "single",
    labels: Sequence[str] | None = None,
    series_labels: Sequence[str] | None = None,
    title: str | None = None,
    xlabel: str | None = None,
    ylabel: str | None = None,
    style: StyleSeq = DEFAULT_STOCKING_STYLE,
    cycle: CycleMode = "auto",
    paired: Pairing = "auto",
    value_labels: bool = False,
    max_abs_fill: float = DEFAULT_MAX_FILL,
    seed: int | None = None,
    library: LegLibrary = DEFAULT_LEG_LIBRARY,
    **options: Unpack[ChartOptions],
) -> BarPlot:
    """正负镜像柱状图：正值画基线上方腿，负值画下方翻转腿（脚贴基线）。

    y 轴随负刻度向下延伸。

    Args:
        data: 语义同 bar()，支持完全相同的数据格式。
        mode: "single" 只画数据侧的腿；"both" 上下都画，数据侧穿丝袜、
            另一侧裸腿。
        labels: 每组（无分组时每根柱）一个标签；缺省用数据里推断的标签。
        series_labels: 语义同 bar()。
        title: 整图标题，默认居中。
        xlabel: x 轴名称。
        ylabel: 语义同 bar()。
        style: 语义同 bar()。
        cycle: 语义同 bar()。
        paired: 语义同 bar()；镜像图同样默认 "auto"。
        value_labels: True 时手写数值，上方腿写在袜口上方、下方腿写在袜口下方
            （6 位有效数字；绝对值 ≥ 10⁶ 或 < 10⁻⁴ 时用科学计数法；不参与布局预留）。
        max_abs_fill: 最大绝对值映射到素材设计高度的比例，须在 (0, 1]
            （默认 0.85）。
        library: 自动选腿使用的素材库，默认 DEFAULT_LEG_LIBRARY。
        options: 语义同 bar()。height_px 控制基线上方柱区高度，缺省按最高腿设计高度
            再加 10% 留白；width_px 控制绘图区宽度，缺省自适应。显式 height_px
            小于整腿高度时仍会扩到整腿高。x_label_pos 默认 "auto"：
            镜像图常有一侧全空，会把标签贴到没有腿的一侧的基线旁（如全负
            数据标签在基线上方）；两侧都有腿（正负混合或 mode="both"）时
            退回 "content"，画在全部内容最低点之下。

    Returns:
        已布局并添加图例/轴/标题的 BarPlot；可直接 `.save()` / `.render()`，
        也可继续手工微调。

    Raises:
        TypeError: 数据类型不受支持，或 options 含未知键。
        ValueError: 标签长度不符、series_labels 用于一维数据、mode/cycle
            不合法、max_abs_fill/height_px/width_px 不合法、样式列表为空/
            未知预设，或数据内容不合法。

    规则:
        - 参考高度取本次选中腿中最小的设计高度；比例 =
          max_abs_fill × 参考高度 / max|v|，正负同比例。
        - 0 视为 +0: "single" 下画一条朝上裸腿；"both" 下上下均画裸腿（上为数据侧）。
        - 下方空间: "single" 仅在存在负值时保留；"both" 始终保留。
    """
    check_options(options)
    if mode not in ("single", "both"):
        raise ValueError(f"mode 须为 'single' 或 'both'，得到 {mode!r}")
    check_positive("max_abs_fill", max_abs_fill)
    if max_abs_fill > 1.0:
        raise ValueError(f"max_abs_fill 须在 (0, 1]，得到 {max_abs_fill!r}")
    normalized = normalize_data(data)
    rows = [list(row) for row in normalized.values]
    is_1d = normalized.is_1d
    if labels is None:
        labels = normalized.labels
    if series_labels is None:
        series_labels = normalized.series_labels
    if series_labels is not None and is_1d:
        raise ValueError("series_labels 仅支持二维（分组）数据；一维数据请用 labels")
    series = len(rows[0])
    check_labels(labels, len(rows))
    check_series_labels(series_labels, series)
    mode_cycle = resolve_cycle(cycle, is_1d=is_1d)
    if series_labels is not None and mode_cycle == "sequence":
        raise ValueError("series_labels 需要固定的系列样式，请用 cycle='group'")

    rng = random.Random(seed)
    legs = select_legs(rows, paired=paired, seed=rng.getrandbits(32), library=library)
    styles = normalize_style_seq(style)
    # 与 bar() 相同：取最矮腿的设计高度作统一参考，避免矮腿截顶。
    design_height = float(min(leg.height for row in legs for leg in row))

    flat = [v for row in rows for v in row]
    vmax_abs = max(abs(v) for v in flat)
    vmin, vmax = min(flat), max(flat)
    if vmax_abs == 0:
        # 全 0：比例无定义，按裸腿处理，刻度只留 0
        ratio = 0.0
        scale = Scale((0.0, 1.0), (0.0, design_height))
        ticks: list[float] | None = [0.0]
    else:
        ratio = max_abs_fill * design_height / vmax_abs
        lo = min(0.0, vmin)
        hi = max(0.0, vmax)
        scale = Scale((lo, hi), (lo * ratio, hi * ratio))
        ticks = None

    both = mode == "both"
    specs: list[list[list[LegSpec]]] = []
    for g, row in enumerate(rows):
        slot: list[list[LegSpec]] = []
        for s, v in enumerate(row):
            idx = style_index(mode_cycle, g=g, s=s, series=len(row))
            st = styles[idx % len(styles)]
            h = abs(v) * ratio
            side: BarSide = "up" if v >= 0 else "down"
            # 数据侧在首位，value_labels 只标数据侧
            col = [LegSpec(legs[g][s], h, side, st)]
            if both:
                other: BarSide = "down" if side == "up" else "up"
                col.append(LegSpec(legs[g][s], 0.0, other, st))
            slot.append(col)
        specs.append(slot)

    bar_gap = options.get("bar_gap", DEFAULT_BAR_GAP)
    slot_gap = options.get("group_gap", DEFAULT_BAR_GAP if is_1d else DEFAULT_GROUP_GAP)
    # 全负数据没有上方腿，但 height_px 自动仍取整腿高度并加顶部留白，
    # 会留出更大空白顶部；已知取舍，暂不处理。
    plot, records = assemble(
        specs,
        labels=labels,
        title=title,
        xlabel=xlabel,
        bar_gap=bar_gap,
        slot_gap=slot_gap,
        x_label_pos=options.get("x_label_pos", "auto"),
        seed=seed,
        options=options,
        library=library,
    )
    if value_labels:
        for g, row in enumerate(rows):
            for s, v in enumerate(row):
                records[g][s][0].value_label = format_value(v)
    plot.add_y_axis(scale, ticks=options.get("ticks", ticks), grid=options.get("grid", False))
    if ylabel is not None:
        plot.add_y_axis_name(
            ylabel, size_px=options.get("axis_name_size_px", DEFAULT_AXIS_NAME_SIZE)
        )
    if series_labels is not None:
        plot.add_legend(
            [(series_labels[s], styles[s % len(styles)]) for s in range(series)],
            ncol=options.get("legend_ncol"),
            loc=options.get("legend_loc", "top"),
        )
    return plot
