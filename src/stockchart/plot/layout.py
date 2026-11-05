"""布局计算：把渲染输入换算成整张图的几何。

只算位置与占位，不碰画布；绘制阶段直接用这里给出的 PlotLayout。
x 标签的旋转与避让、图例的折行与轴名称的竖排在同一处判定，
保证占位与实际绘制一致。
"""

from __future__ import annotations

import itertools
import math
from collections.abc import Sequence
from typing import Literal

from stockchart.defaults import (
    DEFAULT_AXIS_NAME_GAP,
    DEFAULT_AXIS_NAME_LINE_FACTOR,
    DEFAULT_BOTTOM_PAD,
    DEFAULT_LABEL_LINE_FACTOR,
    DEFAULT_LEGEND_ITEM_GAP,
    DEFAULT_LEGEND_LINE_FACTOR,
    DEFAULT_LEGEND_MARGIN,
    DEFAULT_LEGEND_MAX_LINES,
    DEFAULT_LEGEND_ROW_GAP,
    DEFAULT_LEGEND_SWATCH,
    DEFAULT_LEGEND_TEXT_GAP,
    DEFAULT_LEGEND_TEXT_SIZE,
    DEFAULT_PLOT_LEFT_PAD,
    DEFAULT_PLOT_RIGHT_PAD,
    DEFAULT_TICK_LABEL_GAP,
    DEFAULT_TICK_LABEL_SIZE,
    DEFAULT_TICK_SIZE,
    DEFAULT_TITLE_INSET_Y,
    DEFAULT_TITLE_LINE_FACTOR,
    DEFAULT_X_LABEL_GAP,
    DEFAULT_X_LABEL_ITEM_GAP,
    DEFAULT_X_LABEL_ROTATIONS,
    DEFAULT_X_LABEL_SIZE,
)
from stockchart.plot.scale import format_tick
from stockchart.plot.types import (
    AxisNameRecord,
    BarRecord,
    LegendRecord,
    PlotLayout,
    RenderInput,
    XLabelsRecord,
)
from stockchart.text import FontSpec, measure_text, measure_text_height, wrap_text


def axis_name_step(name: AxisNameRecord) -> float:
    """计算 y 轴名称相邻列/行的步进：名称内最高字符的实测行高 × 系数。

    混合文字（如中英文混排）时不同字体的自然行高不同，取名称内所有
    字符的最大值，保证相邻列/行互不重叠；布局与绘制共用同一份计算。

    Args:
        name: y 轴名称记录；text 须非空（调用点已保证）。

    Returns:
        步进（设计像素）。
    """
    return max(
        measure_text_height(
            ch, size_px=name.size_px, font=name.font, line_height=DEFAULT_AXIS_NAME_LINE_FACTOR
        )
        for ch in set(name.text)
    )


def axis_name_metrics(
    name: AxisNameRecord, available_px: float
) -> tuple[list[str], float, float, float]:
    """把 y 轴名称拆成能放进轴长度的列/行，并给出占位度量。

    中日韩文字按字符拆成竖排列（首列靠轴、后续列向左），厚度为一个字面
    宽度；其余文字旋转 90° 后按可用长度折行，厚度为实测自然行高。

    Args:
        name: y 轴名称记录。
        available_px: 轴干线可用的垂直长度（设计像素）。

    Returns:
        `(列/行文本, 名称块的水平占位宽度, 单列/单行厚度, 相邻列/行步进)`，
        均为设计像素。
    """
    if not name.text:
        return [], 0.0, 0.0, 0.0
    step = axis_name_step(name)
    if name.rotate:
        lines = wrap_text(
            name.text,
            max_width=max(1.0, available_px),
            size_px=name.size_px,
            font=name.font,
        )
        thickness = measure_text_height(name.text, size_px=name.size_px, font=name.font)
    else:
        per_column = max(1, int(available_px // step))
        lines = [
            name.text[start : start + per_column] for start in range(0, len(name.text), per_column)
        ]
        thickness = name.size_px
    return lines, thickness + (len(lines) - 1) * step, thickness, step


def layout_axis_name(name: AxisNameRecord, available_px: float) -> tuple[list[str], float]:
    """把 y 轴名称拆成能放进轴长度的列/行，并返回水平占位宽度。

    名称块整体在轴干线上垂直居中；完整度量见 `axis_name_metrics`。

    Args:
        name: y 轴名称记录。
        available_px: 轴干线可用的垂直长度（设计像素）。

    Returns:
        `(列/行文本, 名称块的水平占位宽度)`。
    """
    lines, width, _, _ = axis_name_metrics(name, available_px)
    return lines, width


def effective_extents(
    bars: Sequence[BarRecord], extent_up: float, extent_down: float
) -> tuple[float, float]:
    """返回实际使用的基线上/下预留高度。

    取配置值与实际腿高的较大者；装不下腿时自动扩张。

    Args:
        bars: 已摆放好的柱子记录。
        extent_up: 配置的基线上方预留高度。
        extent_down: 配置的基线下方预留高度。

    Returns:
        `(eff_up, eff_down)`，设计像素。
    """
    up_legs = [b.leg.height for b in bars if b.side == "up"]
    down_legs = [b.leg.height for b in bars if b.side == "down"]
    eff_up = max(float(extent_up), float(max(up_legs, default=0)))
    eff_down = max(float(extent_down), float(max(down_legs, default=0)))
    return eff_up, eff_down


def legend_line_height(label: str, font: FontSpec | None) -> float:
    """图例单行文字的占位高度：实测自然行高 × 行高系数。

    Args:
        label: 图例标签（按单行文本度量自然行高）。
        font: 图例字体。

    Returns:
        单行占位高度（设计像素）。
    """
    return measure_text_height(
        label,
        size_px=DEFAULT_LEGEND_TEXT_SIZE,
        font=font,
        line_height=DEFAULT_LEGEND_LINE_FACTOR,
    )


def legend_layout(
    rec: LegendRecord, width_px: int
) -> tuple[list[list[int]], list[float], float, list[list[str]]]:
    """计算图例的分行、折行与整体高度。

    单个标签超过一行宽时按词/字换行（最多 DEFAULT_LEGEND_MAX_LINES 行，
    仍放不下则末行省略）；ncol 指定时按等宽列折行，每行整体居中。
    行高按各标签的实测自然行高计算，与绘制共用同一字体。

    Args:
        rec: 图例记录。
        width_px: 绘图区宽度（设计像素）。

    Returns:
        `(行内项下标, 各行高, 图例带总高, 每项折行文本)`。
    """
    if rec.ncol is not None:
        # ncol 过大时最小列宽会让整行超出 width_px；已知边界，暂不处理。
        col_w = max(
            DEFAULT_LEGEND_SWATCH + DEFAULT_LEGEND_TEXT_GAP + 1.0,
            (width_px - (rec.ncol - 1) * DEFAULT_LEGEND_ITEM_GAP) / rec.ncol,
        )
        label_max = max(1.0, col_w - DEFAULT_LEGEND_SWATCH - DEFAULT_LEGEND_TEXT_GAP)
    else:
        col_w = 0.0
        label_max = max(1.0, width_px - DEFAULT_LEGEND_SWATCH - DEFAULT_LEGEND_TEXT_GAP)
    lines_all = [
        wrap_text(
            label,
            max_width=label_max,
            size_px=DEFAULT_LEGEND_TEXT_SIZE,
            font=rec.font,
            max_lines=DEFAULT_LEGEND_MAX_LINES,
        )
        for label, _ in rec.items
    ]
    widths: list[float] = []
    heights: list[float] = []
    for i, lines in enumerate(lines_all):
        text_w = max(
            (measure_text(line, size_px=DEFAULT_LEGEND_TEXT_SIZE, font=rec.font) for line in lines),
            default=0.0,
        )
        width = DEFAULT_LEGEND_SWATCH + DEFAULT_LEGEND_TEXT_GAP + text_w
        widths.append(width if rec.ncol is None else col_w)
        line_h = legend_line_height(rec.items[i][0], rec.font)
        heights.append(max(DEFAULT_LEGEND_SWATCH, len(lines) * line_h))

    idx_rows: list[list[int]] = []
    row_heights: list[float] = []
    if rec.ncol is not None:
        for start in range(0, len(widths), rec.ncol):
            row = list(range(start, min(start + rec.ncol, len(widths))))
            idx_rows.append(row)
            row_heights.append(max(heights[i] for i in row))
    else:
        row: list[int] = []
        row_w = 0.0
        for i, w in enumerate(widths):
            extra = w if not row else DEFAULT_LEGEND_ITEM_GAP + w
            if row and row_w + extra > width_px:
                idx_rows.append(row)
                row_heights.append(max(heights[j] for j in row))
                row, row_w = [i], w
            else:
                row.append(i)
                row_w += extra
        if row:
            idx_rows.append(row)
            row_heights.append(max(heights[j] for j in row))
    band_h = sum(row_heights) + (len(row_heights) - 1) * DEFAULT_LEGEND_ROW_GAP
    return idx_rows, row_heights, band_h, lines_all


def x_label_xs(rec: XLabelsRecord, group_centers: list[float], width_px: int) -> list[float]:
    """返回 x 标签锚点在绘图区坐标中的位置。

    优先使用显式 xs；否则在标签数与组中心数一致时用组中心，最后退到
    沿绘图区宽度均分。

    Args:
        rec: x 标签记录。
        group_centers: 各组中心在绘图区坐标中的 x。
        width_px: 绘图区宽度（设计像素）。

    Returns:
        与标签数量相同的 x 坐标（设计像素）。
    """
    rec = rec
    assert rec is not None  # 调用点已保证
    if rec.xs is not None:
        return rec.xs
    if len(rec.labels) == len(group_centers):
        return group_centers
    n = len(rec.labels)
    return [(i + 0.5) * width_px / n for i in range(n)]


def _x_label_line_heights(labels: Sequence[str], font: FontSpec | None) -> list[float]:
    """逐标签实测单行占位高度（旋转包围盒与避让判定用）。

    Args:
        labels: x 标签文本。
        font: x 标签字体。

    Returns:
        与 labels 等长的单行占位高度列表（自然行高 × 行高系数）。
    """
    return [
        measure_text_height(
            label,
            size_px=DEFAULT_X_LABEL_SIZE,
            font=font,
            line_height=DEFAULT_LABEL_LINE_FACTOR,
        )
        for label in labels
    ]


def _x_labels_fit_horizontal(xs: Sequence[float], widths: Sequence[float]) -> bool:
    """判断水平排布时相邻标签是否互不重叠。

    Args:
        xs: 标签锚点 x。
        widths: 各标签宽度。

    Returns:
        所有相邻标签都留出最小空隙时返回 True。
    """
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    return all(
        xs[b] - xs[a] >= (widths[a] + widths[b]) / 2 + DEFAULT_X_LABEL_ITEM_GAP
        for a, b in itertools.pairwise(order)
    )


def _x_labels_fit_rotated(
    xs: Sequence[float], widths: Sequence[float], angle: float, line_hs: Sequence[float]
) -> bool:
    """判断旋转指定角度后相邻标签是否互不重叠。

    Args:
        xs: 标签锚点 x。
        widths: 各标签宽度。
        angle: 旋转角度（度）。
        line_hs: 各标签的单行占位高度，与 xs 等长。

    Returns:
        所有相邻标签都留出最小空隙时返回 True。
    """
    c = math.cos(math.radians(angle))
    s = math.sin(math.radians(angle))
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    return all(
        xs[b] - xs[a] >= widths[b] * c + line_hs[b] * s + DEFAULT_X_LABEL_ITEM_GAP
        for a, b in itertools.pairwise(order)
    )


def _x_label_fit(inp: RenderInput, *, above: bool) -> tuple[float, float, float, float]:
    """解析 x 标签的旋转角与占位。

    rotation="auto" 时逐级尝试 DEFAULT_X_LABEL_ROTATIONS，取第一个不重叠
    的角度；都放不下时用最大角度。标签在基线下方取负角、上方取正角。
    宽度与行高都按标签字体实测（含 kerning 与真实字体度量）。

    Args:
        inp: 渲染输入。
        above: 标签是否写在基线上方。

    Returns:
        `(带符号角度, 垂直占位高, 向左溢出, 向右溢出)`，均为设计像素。
    """
    rec = inp.x_labels
    assert rec is not None  # 调用点已保证
    xs = x_label_xs(rec, inp.group_centers, inp.width_px)
    widths = [
        measure_text(label, size_px=DEFAULT_X_LABEL_SIZE, font=rec.font) for label in rec.labels
    ]
    line_hs = _x_label_line_heights(rec.labels, rec.font)
    if rec.rotation == "auto":
        angle = DEFAULT_X_LABEL_ROTATIONS[-1]
        for candidate in DEFAULT_X_LABEL_ROTATIONS:
            if candidate == 0.0:
                fits = _x_labels_fit_horizontal(xs, widths)
            else:
                fits = _x_labels_fit_rotated(xs, widths, candidate, line_hs)
            if fits:
                angle = candidate
                break
    else:
        angle = float(rec.rotation)

    if angle == 0.0:
        height = max(line_hs, default=0.0)
        left = max((w / 2 - x for w, x in zip(widths, xs, strict=True)), default=0.0)
        right = max(
            (w / 2 - (inp.width_px - x) for w, x in zip(widths, xs, strict=True)),
            default=0.0,
        )
        return 0.0, height, max(0.0, left), max(0.0, right)

    c = math.cos(math.radians(angle))
    s = math.sin(math.radians(angle))
    height = max((w * s + lh * c for w, lh in zip(widths, line_hs, strict=True)), default=0.0)
    if angle >= 89.999:
        # 90° 字列绘制时按实测自然行高把锚点左移半行、水平居中于刻度
        # （见 _draw_x_labels），左右各占半个自然行高；注意这里不带
        # 行高系数——draw_text 的 90° 字列宽就是自然单行块高
        natural_hs = [
            measure_text_height(label, size_px=DEFAULT_X_LABEL_SIZE, font=rec.font)
            for label in rec.labels
        ]
        left = max((nh / 2 - x for nh, x in zip(natural_hs, xs, strict=True)), default=0.0)
        right = max(
            (nh / 2 - (inp.width_px - x) for nh, x in zip(natural_hs, xs, strict=True)),
            default=0.0,
        )
    elif above:
        # 上方标签向左上展开：左边多出字面高度，右边不越界
        left = max(
            (w * c + lh * s - x for w, lh, x in zip(widths, line_hs, xs, strict=True)),
            default=0.0,
        )
        right = 0.0
    else:
        # 下方标签向左下展开：左边占文字宽，右边多出字面高度
        left = max((w * c - x for w, x in zip(widths, xs, strict=True)), default=0.0)
        right = max(
            (lh * s - (inp.width_px - x) for lh, x in zip(line_hs, xs, strict=True)),
            default=0.0,
        )
    signed = angle if above else -angle
    return signed, height, max(0.0, left), max(0.0, right)


def resolve_x_label_pos(
    rec: XLabelsRecord, bars: Sequence[BarRecord]
) -> Literal["above", "below", "content"]:
    """把 x 标签的 pos 参数解析为具体位置。

    "auto" 选择没有柱子的一侧；两侧都有柱子时退回 "content"。

    Args:
        rec: x 标签记录。
        bars: 已摆放好的柱子记录。

    Returns:
        "above" / "below" / "content"。
    """
    rec = rec
    assert rec is not None  # 调用点已保证
    if rec.pos != "auto":
        return rec.pos
    has_up = any(b.side == "up" for b in bars)
    has_down = any(b.side == "down" for b in bars)
    if not has_up:
        return "above"
    if not has_down:
        return "below"
    return "content"


def compute_layout(inp: RenderInput) -> PlotLayout:
    """计算整张图的最终几何。

    顺序：实际 extents → 左侧 y 轴占位 → x 标签位置/旋转 → 顶部带
    （标题、顶部图例、上方标签）→ 基线/底部带（标签、轴名、底部图例）
    → 横向溢出修正。extent_up / extent_down 只参与柱区，标题、轴名称、
    刻度、标签与图例都在此另行占位。

    Args:
        inp: 渲染输入。

    Returns:
        所有元素位置与最终画布尺寸（设计像素）。
    """
    eff_up, eff_down = effective_extents(inp.bars, inp.extent_up, inp.extent_down)
    axis = inp.y_axis

    # y 轴左侧占位：[画布留白][y 轴名称(纵向)][刻度数字][间距][刻度线][干线]
    down_len = 0.0
    axis_x = 0.0
    plot_left = float(DEFAULT_PLOT_LEFT_PAD)
    y_name_x = 0.0
    tick_px: list[float] = []
    up_len = eff_up
    if axis is not None:
        tick_px = [axis.scale.to_px(v) for v in axis.ticks]
        up_len = max([0.0, eff_up, *tick_px])
        down_len = max([0.0, *(-p for p in tick_px if p < 0)])
    y_name_span = up_len + max(eff_down, down_len)
    left = float(DEFAULT_PLOT_LEFT_PAD)
    if inp.y_axis_name is not None:
        name = inp.y_axis_name
        _, name_w = layout_axis_name(name, y_name_span)
        y_name_x = left + name_w / 2
        left += name_w + DEFAULT_AXIS_NAME_GAP
    if axis is not None:
        label_w = max(
            (
                measure_text(format_tick(v), size_px=DEFAULT_TICK_LABEL_SIZE, font=axis.font)
                for v in axis.ticks
            ),
            default=0.0,
        )
        axis_x = left + label_w + DEFAULT_TICK_LABEL_GAP + DEFAULT_TICK_SIZE
        plot_left = axis_x
    elif inp.y_axis_name is not None:
        plot_left = left

    x_pos: Literal["above", "below", "content"] | None = None
    x_angle = 0.0
    x_height = 0.0
    x_left = 0.0
    x_right = 0.0
    if inp.x_labels is not None and inp.x_labels.labels:
        x_pos = resolve_x_label_pos(inp.x_labels, inp.bars)
        x_angle, x_height, x_left, x_right = _x_label_fit(inp, above=(x_pos == "above"))

    # 顶部带：标题 + 顶部图例；标签写在基线上方时若超出预留高度，补足顶部空间
    top_band = 0.0
    legend_top_y = 0.0
    # 空字符串标题/轴名仍会占完整布局空间；已知边界，暂不处理。
    if inp.title is not None:
        title = inp.title
        top_band = DEFAULT_TITLE_INSET_Y + measure_text_height(
            title.text,
            size_px=title.size_px,
            font=title.font,
            line_height=DEFAULT_TITLE_LINE_FACTOR,
        )
    if inp.legend is not None and inp.legend.loc == "top":
        _, _, legend_h, _ = legend_layout(inp.legend, inp.width_px)
        legend_top_y = top_band if inp.title is not None else DEFAULT_LEGEND_MARGIN
        top_band = legend_top_y + legend_h + DEFAULT_LEGEND_MARGIN
    elif inp.legend is None and inp.title is None:
        top_band = 0.0
    if x_pos == "above":
        # 为旋转后的标签留出顶部空间，并保留与画布顶缘的呼吸间距
        top_band += max(0.0, x_height + 2 * DEFAULT_X_LABEL_GAP - eff_up)
    if axis is not None and tick_px:
        # 刻度映射可能高于 extent_up：把轴顶与最上方刻度数字移进画布
        tick_label_half = (
            measure_text_height("0", size_px=DEFAULT_TICK_LABEL_SIZE, font=axis.font) / 2
        )
        top_tick = max((p for p in tick_px if p > 0), default=0.0)
        top_band += max(0.0, top_tick + tick_label_half - eff_up)

    baseline = top_band + eff_up
    content_bottom = baseline + max(eff_down, down_len)

    x_label_y: float | None = None
    x_label_baseline = False
    bottom = content_bottom
    if x_pos is not None:
        if x_pos == "above":
            x_label_y = baseline - DEFAULT_X_LABEL_GAP
            x_label_baseline = True
        elif x_pos == "below":
            x_label_y = baseline + DEFAULT_X_LABEL_GAP
            bottom = max(bottom, x_label_y + x_height)
        else:
            x_label_y = content_bottom + DEFAULT_X_LABEL_GAP
            bottom = x_label_y + x_height

    x_name_y: float | None = None
    if inp.x_axis_name is not None:
        x_name = inp.x_axis_name
        x_name_y = bottom + DEFAULT_AXIS_NAME_GAP
        bottom = x_name_y + measure_text_height(
            x_name.text,
            size_px=x_name.size_px,
            font=x_name.font,
            line_height=DEFAULT_AXIS_NAME_LINE_FACTOR,
        )

    legend_bottom_y: float | None = None
    if inp.legend is not None and inp.legend.loc == "bottom":
        legend_bottom_y = bottom + DEFAULT_LEGEND_MARGIN
        bottom = legend_bottom_y + legend_layout(inp.legend, inp.width_px)[2]

    final_h = bottom + DEFAULT_BOTTOM_PAD
    # 旋转标签可能伸出绘图区左右缘：补画布边距，避免文字被裁
    plot_left += max(0.0, x_left - plot_left)
    plot_right = plot_left + inp.width_px
    final_w = plot_right + max(DEFAULT_PLOT_RIGHT_PAD, x_right)

    # 标题与 x 轴名称比画布宽时对称扩宽：左溢出整体右移绘图区，右溢出补画布
    centered = [plot_left + inp.width_px / 2] if inp.x_axis_name is not None else []
    if inp.title is not None:
        title_w = measure_text(inp.title.text, size_px=inp.title.size_px, font=inp.title.font)
        if inp.title.align == "center":
            title_x = plot_left + inp.width_px / 2
            title_center = title_x
        else:
            title_x = plot_left
            title_center = title_x + title_w / 2
        centered.append(title_center)
    else:
        title_w = 0.0
        title_x = plot_left
    text_widths = (
        [
            measure_text(
                inp.x_axis_name.text,
                size_px=inp.x_axis_name.size_px,
                font=inp.x_axis_name.font,
            )
        ]
        if inp.x_axis_name is not None
        else []
    )
    if inp.title is not None:
        text_widths.append(title_w)
    if text_widths:
        # 标题 / x 轴名称与画布左右缘至少留一个标准边距
        lefts = [c - w / 2 for w, c in zip(text_widths, centered, strict=True)]
        rights = [c + w / 2 for w, c in zip(text_widths, centered, strict=True)]
        extra_left = max(0.0, DEFAULT_PLOT_LEFT_PAD - min(lefts))
        extra_right = max(0.0, max(rights) + DEFAULT_PLOT_LEFT_PAD - final_w)
    else:
        extra_left = extra_right = 0.0
    shift = max(0.0, extra_left)
    plot_left += shift
    plot_right += shift
    axis_x += shift
    y_name_x += shift
    title_x += shift
    final_w += shift + max(0.0, extra_right)
    x_name_x = plot_left + inp.width_px / 2

    y_name_y = baseline + (max(eff_down, down_len) - up_len) / 2
    return PlotLayout(
        final_w=final_w,
        final_h=final_h,
        plot_left=plot_left,
        plot_right=plot_right,
        baseline_y=baseline,
        content_bottom=content_bottom,
        axis_x=axis_x,
        y_name_x=y_name_x,
        y_name_y=y_name_y,
        y_up_len=up_len,
        y_name_span=y_name_span,
        title_x=title_x,
        title_y=DEFAULT_TITLE_INSET_Y,
        x_name_x=x_name_x,
        x_name_y=x_name_y,
        legend_top_y=legend_top_y,
        x_label_y=x_label_y,
        x_label_baseline=x_label_baseline,
        x_label_angle=x_angle,
        x_label_height=x_height,
        legend_bottom_y=legend_bottom_y,
    )
