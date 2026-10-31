# L4 经由 BarPlot 的包内私有接口（槽位摆腿、柱记录）完成布局，
# 不触碰画布；故豁免跨模块私有成员检查。
# pyright: reportPrivateUsage=false

"""L4 一行出图：bar 与 mirror_bar。数据归一化 + 全自动布局。

映射规则见 docs/api.zh-CN/charts.md；腿的摆放经由 BarPlot 的私有槽位接口完成，
本模块不直接操作画布。丝袜高度映射与腿的布局是分开的两层。
"""

from __future__ import annotations

import math
import random
from collections.abc import Sequence
from typing import Literal, TypedDict, Unpack

from stockchart.color import Color
from stockchart.data import DataInput, normalize_data
from stockchart.defaults import (
    DEFAULT_AXIS_NAME_SIZE,
    DEFAULT_AXIS_STYLE,
    DEFAULT_BACKGROUND,
    DEFAULT_BAR_GAP,
    DEFAULT_GROUP_GAP,
    DEFAULT_MAX_FILL,
    DEFAULT_MIN_FILL,
    DEFAULT_STOCKING_STYLE,
    DEFAULT_TITLE_ALIGN,
    DEFAULT_TITLE_SIZE,
    DEFAULT_X_LABEL_SIZE,
    DEFAULT_Y_EXTENT,
)
from stockchart.legs import Leg
from stockchart.plot import (
    AxisStyle,
    BarPlot,
    BarSide,
    LegendLoc,
    Pairing,
    Scale,
    StyleCycle,
    TitleAlign,
    XLabelPos,
    XLabelRotation,
    _BarRecord,
    _LegSpec,
    _normalize_style_seq,
    _select_legs_for_groups,
)
from stockchart.stocking import StyleSeq
from stockchart.text import measure_text

type CycleMode = Literal["auto", "group", "sequence"]


class ChartOptions(TypedDict, total=False):
    """L4 透传给下层的可选参数；键名与 L2 接口一致。

    Attributes:
        axis_style: 坐标轴样式，"clean" 或 "handdrawn"。
        background: 画布背景色。
        bar_gap: 组内相邻腿边缘之间的空隙（设计像素）。
        group_gap: 组间空隙（设计像素）。
        grid: 是否画 y 刻度横向虚线。
        ticks: 显式刻度值；None 表示自动生成。
        x_label_pos: x 标签位置策略。
        x_label_rotation: x 标签旋转策略。
        title_align: 标题对齐方式。
        title_size_px: 标题字号（设计像素）。
        axis_name_size_px: 轴名称字号（设计像素）。
        legend_loc: 图例在顶部或底部。
        legend_ncol: 图例列数；None 表示自动换行。
    """

    axis_style: AxisStyle
    background: Color
    bar_gap: float
    group_gap: float
    grid: bool
    ticks: Sequence[float] | None
    x_label_pos: XLabelPos
    x_label_rotation: XLabelRotation
    title_align: TitleAlign
    title_size_px: float
    axis_name_size_px: float
    legend_loc: LegendLoc
    legend_ncol: int | None


_OPTION_KEYS: frozenset[str] = frozenset(
    {
        "axis_style",
        "background",
        "bar_gap",
        "group_gap",
        "grid",
        "ticks",
        "x_label_pos",
        "x_label_rotation",
        "title_align",
        "title_size_px",
        "axis_name_size_px",
        "legend_loc",
        "legend_ncol",
    }
)

# 槽位两端的呼吸边距与标签加宽余量（默认值级别，不在 L4 参数中暴露）
_EDGE_PAD = DEFAULT_BAR_GAP
_LABEL_BREATH = 2 * DEFAULT_BAR_GAP


def _check_options(options: ChartOptions) -> None:
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


def _check_positive(name: str, value: float) -> None:
    """校验一个映射参数为正的有限数值。

    Args:
        name: 参数名，用于错误信息。
        value: 待校验的值。

    Raises:
        ValueError: 值不是有限正数。
    """
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} 须为正数，得到 {value!r}")


def _check_fill_bounds(max_fill: float, min_fill: float) -> None:
    """校验正负值压缩区间 0 <= min_fill < max_fill <= 1。

    Args:
        max_fill: 最大值映射比例。
        min_fill: 含负值时值域下界比例。

    Raises:
        ValueError: 两个比例不是有限数、max_fill 超过 1，或区间不合法。
    """
    _check_positive("max_fill", max_fill)
    if max_fill > 1.0:
        raise ValueError(f"max_fill 须在 (0, 1]，得到 {max_fill!r}")
    if not math.isfinite(min_fill) or not 0.0 <= min_fill < max_fill:
        raise ValueError(f"min_fill 须满足 0 <= min_fill < max_fill，得到 {min_fill!r}")


def _format_value(value: float) -> str:
    """格式化数值标签。

    与刻度不同，数值标签应尽量保留原始精度：整数直接输出，非整数使用
    Python 的最短往返表示，避免大数被截成 6 位有效数字。

    Args:
        value: 数据值。

    Returns:
        数值的可读字符串。
    """
    number = float(value)
    if number.is_integer():
        return str(int(number))
    return repr(number)


def _select_legs(
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
    return _select_legs_for_groups([len(row) for row in rows], paired=paired, seed=seed)


def _plan_slots(
    specs: list[list[list[_LegSpec]]],
    *,
    labels: Sequence[str] | None,
    bar_gap: float,
) -> list[float]:
    """计算每个槽的宽度。

    槽宽取“腿的自然宽度”与“标签宽度 + 呼吸余量”的较大者。

    Args:
        specs: 槽 → 列 → 腿规格的嵌套结构。
        labels: 每组标签；None 表示不加宽。
        bar_gap: 同槽相邻列之间的空隙。

    Returns:
        每个槽的宽度（设计像素）。
    """
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
    xlabel: str | None,
    bar_gap: float,
    slot_gap: float,
    width_px: int | None,
    extent_up: int,
    extent_down: int,
    x_label_pos: XLabelPos,
    seed: int | None,
    options: ChartOptions,
) -> tuple[BarPlot, list[list[list[_BarRecord]]]]:
    """按槽位建图并摆好腿。

    Args:
        specs: 槽 → 列 → 腿规格的嵌套结构。
        labels: 每组标签；None 表示不加 x 标签。
        title: 整图标题；None 表示不加。
        xlabel: x 轴名称；None 表示不加。
        bar_gap: 同槽相邻列之间的空隙。
        slot_gap: 相邻槽之间的空隙。
        width_px: 显式绘图区宽度；None 时按槽宽与边距自适应。
        extent_up: 基线以上为腿预留的高度；不含标题、标签等边缘。
        extent_down: 基线以下为向下腿预留的高度。
        x_label_pos: x 标签位置策略。
        seed: BarPlot 与选腿的随机源。
        options: 其余 L2 透传选项。

    Returns:
        `(BarPlot, 与 specs 同构的柱记录)`。
    """
    slots_px = _plan_slots(specs, labels=labels, bar_gap=bar_gap)
    # 显式 width_px 不做内容宽度校验：过小时腿会超出画布被裁，已知边界，暂不处理。
    width = (
        width_px
        if width_px is not None
        else round(2 * _EDGE_PAD + sum(slots_px) + (len(specs) - 1) * slot_gap)
    )
    plot = BarPlot(
        width,
        extent_up=extent_up,
        extent_down=extent_down,
        background=options.get("background", DEFAULT_BACKGROUND),
        axis_style=options.get("axis_style", DEFAULT_AXIS_STYLE),
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


def _check_labels(labels: Sequence[str] | None, n: int) -> Sequence[str] | None:
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


def _check_series_labels(series_labels: Sequence[str] | None, n: int) -> Sequence[str] | None:
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


def _resolve_cycle(cycle: CycleMode, *, is_1d: bool) -> StyleCycle:
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


def _style_index(cycle: StyleCycle, *, g: int, s: int, series: int) -> int:
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
    y_extent: int = DEFAULT_Y_EXTENT,
    width_px: int | None = None,
    seed: int | None = None,
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
        ylabel: y 轴名称，逐字竖排在刻度数字左侧。
        style: 单个样式，或样式列表——循环方式由 cycle 决定。
        cycle: "group" 按组内位置循环（组内第 i 根取 styles[i % len]），
            "sequence" 按全部柱子的绘制顺序循环；"auto"（默认）一维取
            "sequence"（每根柱按顺序取样式）、二维取 "group"（长度等于系列数
            时即"每系列一个样式"）。二维数据下若 "sequence" 无法与图例的系列
            样式对应，同时传 series_labels 抛 ValueError。
        paired: 选腿的配对策略。"auto"（默认）单系列用 "none"、多系列用
            "global"；"group" 每组独立取完整对：系列 0、1 同一对（左、右），
            系列 2 起继续取下一对（单系列即每组取新素材对的左腿）；
            "global" 整张图连续取对，配对可以跨组；"none" 每条腿来自不同
            素材对。
        value_labels: True 时在袜口上方手写数值。
        max_fill: 最大值映射到 y_extent 的比例，须在 (0, 1]（默认 0.8）。
        min_fill: 仅当数据含负值时启用（默认 0.1），见下。
        y_extent: 柱区在基线上方预留的设计像素高度，不含标题、标签、图例等
            边缘区域。
        width_px: 绘图区宽度；缺省按腿数、间距与标签宽度自适应。最终画布会
            因轴、标签与标题更宽。
        options: 透传给下层的可选项（grid、axis_style、legend_loc、bar_gap
            等），见 docs/api.zh-CN/charts.md 的 ChartOptions 表。

    Returns:
        已布局并添加图例/轴/标题的 BarPlot；可直接 `.save()` / `.render()`，
        也可继续手工微调。

    Raises:
        TypeError: 数据类型不受支持，或 options 含未知键。
        ValueError: 标签长度不符、series_labels 用于一维数据、cycle 不合法、
            max_fill/min_fill/y_extent 不合法、样式列表为空/未知预设，或
            数据内容不合法。

    数据 → 丝袜高度（基线对应的数据值默认 0）:
        - 全部数据为 0: 全部裸腿。
        - 无负值: height = v / max × max_fill × y_extent，0 值即裸腿。
        - 含负值: 整个值域 [min, max] 线性压缩到 [min_fill, max_fill]。
          此时 0 值的腿带一段丝袜、y 轴 0 刻度悬在丝袜中间某处——这是为完整
          保留大小关系所做的既定取舍。全负数据同规则：值越大丝袜越高；
          全负且所有值相同（没有大小关系）时统一取 min_fill。
    """
    _check_options(options)
    _check_positive("y_extent", float(y_extent))
    _check_fill_bounds(max_fill, min_fill)
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
    _check_labels(labels, len(rows))
    _check_series_labels(series_labels, series)
    mode = _resolve_cycle(cycle, is_1d=is_1d)
    if series_labels is not None and mode == "sequence":
        raise ValueError("series_labels 需要固定的系列样式，请用 cycle='group'")

    rng = random.Random(seed)
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
        if span == 0:
            # 全部为同一负值：没有可压缩的大小关系，统一取下界；刻度按
            # [vmin, 0] 展开，避免除零并让 0 刻度落在正常位置。
            heights = [[min_fill * y_extent] * len(row) for row in rows]
            scale = Scale((vmin, 0.0), (min_fill * y_extent, max_fill * y_extent))
            ticks = None
        else:
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

    bar_gap = options.get("bar_gap", DEFAULT_BAR_GAP)
    slot_gap = options.get("group_gap", DEFAULT_BAR_GAP if is_1d else DEFAULT_GROUP_GAP)
    plot, records = _assemble(
        specs,
        labels=labels,
        title=title,
        xlabel=xlabel,
        bar_gap=bar_gap,
        slot_gap=slot_gap,
        width_px=width_px,
        extent_up=y_extent,
        extent_down=0,
        x_label_pos=options.get("x_label_pos", "content"),
        seed=seed,
        options=options,
    )
    if value_labels:
        for g, row in enumerate(rows):
            for s, v in enumerate(row):
                records[g][s][0].value_label = _format_value(v)
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
    y_extent: int = DEFAULT_Y_EXTENT,
    width_px: int | None = None,
    seed: int | None = None,
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
        ylabel: y 轴名称。
        style: 语义同 bar()。
        cycle: 语义同 bar()。
        paired: 语义同 bar()；镜像图同样默认 "auto"。
        value_labels: True 时手写数值，上方腿写在袜口上方、下方腿写在袜口下方。
        max_abs_fill: 最大绝对值映射到 y_extent 的比例，须在 (0, 1]（默认 0.8）。
        y_extent: 柱区在基线上方预留的设计像素高度，不含标题、标签、图例等
            边缘区域。
        width_px: 绘图区宽度；缺省自适应。最终画布会因轴、标签与标题更宽。
        options: 语义同 bar()。x_label_pos 默认 "auto"：镜像图常有一侧全空，
            会把标签贴到没有腿的一侧的基线旁（如全负数据标签在基线上方）；
            两侧都有腿（正负混合或 mode="both"）时退回 "content"，画在全部
            内容最低点之下。

    Returns:
        已布局并添加图例/轴/标题的 BarPlot；可直接 `.save()` / `.render()`，
        也可继续手工微调。

    Raises:
        TypeError: 数据类型不受支持，或 options 含未知键。
        ValueError: 标签长度不符、series_labels 用于一维数据、mode/cycle
            不合法、max_abs_fill/y_extent 不合法、样式列表为空/未知预设，
            或数据内容不合法。

    规则:
        - 比例 = max_abs_fill × y_extent / max|v|，正负同比例。
        - 0 视为 +0: "single" 下画一条朝上裸腿；"both" 下上下均画裸腿（上为数据侧）。
        - 下方空间: "single" 仅在存在负值时保留；"both" 始终保留。
    """
    _check_options(options)
    if mode not in ("single", "both"):
        raise ValueError(f"mode 须为 'single' 或 'both'，得到 {mode!r}")
    _check_positive("y_extent", float(y_extent))
    _check_positive("max_abs_fill", max_abs_fill)
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
    _check_labels(labels, len(rows))
    _check_series_labels(series_labels, series)
    mode_cycle = _resolve_cycle(cycle, is_1d=is_1d)
    if series_labels is not None and mode_cycle == "sequence":
        raise ValueError("series_labels 需要固定的系列样式，请用 cycle='group'")

    rng = random.Random(seed)
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

    bar_gap = options.get("bar_gap", DEFAULT_BAR_GAP)
    slot_gap = options.get("group_gap", DEFAULT_BAR_GAP if is_1d else DEFAULT_GROUP_GAP)
    # 全负数据没有上方腿，但仍预留完整 y_extent，会留出空白顶部；已知取舍，暂不处理。
    plot, records = _assemble(
        specs,
        labels=labels,
        title=title,
        xlabel=xlabel,
        bar_gap=bar_gap,
        slot_gap=slot_gap,
        width_px=width_px,
        extent_up=y_extent,
        extent_down=0,
        x_label_pos=options.get("x_label_pos", "auto"),
        seed=seed,
        options=options,
    )
    if value_labels:
        for g, row in enumerate(rows):
            for s, v in enumerate(row):
                records[g][s][0].value_label = _format_value(v)
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
