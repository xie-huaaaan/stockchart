"""绘制：把布局结果画到画布上。

按固定 z 序依次画网格、基线、腿、坐标轴、标注与图例；
腿与图例色块按输出密度原生渲染后 1:1 贴图，保证清晰度。
"""

from __future__ import annotations

import random

import numpy as np
import skia
from numpy.typing import NDArray

from stockchart.canvas import Canvas
from stockchart.color import skia_color
from stockchart.defaults import (
    DEFAULT_GRID_COLOR,
    DEFAULT_GRID_DASH,
    DEFAULT_GRID_WIDTH,
    DEFAULT_INK_COLOR,
    DEFAULT_LEGEND_ITEM_GAP,
    DEFAULT_LEGEND_ROW_GAP,
    DEFAULT_LEGEND_SWATCH,
    DEFAULT_LEGEND_TEXT_GAP,
    DEFAULT_LEGEND_TEXT_SIZE,
    DEFAULT_SWATCH_RADIUS,
    DEFAULT_SWATCH_STROKE,
    DEFAULT_VALUE_LABEL_GAP,
    DEFAULT_VALUE_LABEL_SIZE,
    DEFAULT_WOBBLE,
    DEFAULT_X_LABEL_SIZE,
)
from stockchart.legs import Leg
from stockchart.plot.layout import (
    axis_name_metrics,
    effective_extents,
    legend_layout,
    legend_line_height,
    x_label_xs,
)
from stockchart.plot.scale import format_tick
from stockchart.plot.types import PlotLayout, RenderInput
from stockchart.sketch import sketch_axis, sketch_line
from stockchart.stocking import render_stocking
from stockchart.stocking.swatch import render_swatch
from stockchart.text import TextAnchor, draw_text, measure_text, measure_text_height

_SAMPLING_NATIVE = skia.SamplingOptions()


def _skia_image(arr: NDArray[np.uint8]) -> skia.Image:
    """把 NumPy RGBA 转为 skia Image。

    skia 的 numpy 互操作按 BGRA 解释通道，因此先交换通道顺序。

    Args:
        arr: (H, W, 4) uint8 RGBA。

    Returns:
        可直接绘制的 skia.Image。
    """
    return skia.Image.fromarray(np.ascontiguousarray(arr[:, :, [2, 1, 0, 3]]))


def _sock_top_center_x(leg: Leg, height_px: float) -> float:
    """取袜口那一行腿轮廓的水平中心，供数值标签对齐。

    腿素材是倾斜的，足底中心与袜口中心不在同一竖线上；按足底中心居中写
    数值会让标签明显偏离袜口。裸腿取腿顶端的轮廓中心。

    Args:
        leg: 腿素材。
        height_px: 丝袜高度（设计像素）；<= 0 表示裸腿。

    Returns:
        袜口中心在绘图区坐标中的 x（设计像素）。
    """
    h = round(height_px)
    row = 0 if h <= 0 else max(0, min(leg.height - h, leg.height - 1))
    row_img = min(round(row * leg.pixels_per_unit), leg.image.shape[0] - 1)
    cols = np.where(leg.image[row_img, :, 3] > 0)[0]
    if len(cols) == 0:
        return float(leg.foot_center_x)
    return float((cols[0] + cols[-1]) / 2 / leg.pixels_per_unit)


def _draw_grid(canvas: Canvas, layout: PlotLayout, inp: RenderInput) -> None:
    """在所有内容之下绘制 y 刻度横向虚线。

    Args:
        canvas: 目标画布。
        layout: 布局结果。
        inp: 渲染输入（布局与绘制共用的状态）。
    """
    axis = inp.y_axis
    if axis is None or not axis.grid:
        return
    rng = random.Random(axis.seed)
    dash, gap = DEFAULT_GRID_DASH
    wobble = DEFAULT_WOBBLE * 0.3 if inp.axis_style == "handdrawn" else 0.0
    for v in axis.ticks:
        px = axis.scale.to_px(v)
        if abs(px) < 1e-6:
            continue  # 0 刻度与基线重合，不重复画虚线
        y = layout.baseline_y - px
        x = layout.axis_x
        while x < layout.plot_right:
            seg = min(x + dash, layout.plot_right)
            sketch_line(
                canvas,
                x,
                y,
                seg,
                y,
                color=DEFAULT_GRID_COLOR,
                width_px=DEFAULT_GRID_WIDTH,
                wobble=wobble,
                seed=rng.getrandbits(32),
            )
            x = seg + gap


def _draw_baseline(canvas: Canvas, layout: PlotLayout, inp: RenderInput) -> None:
    """绘制带右向箭头的 x 轴基线，画在腿之下。

    Args:
        canvas: 目标画布。
        layout: 布局结果。
        inp: 渲染输入（布局与绘制共用的状态）。
    """
    sketch_axis(
        canvas,
        direction="right",
        x=layout.plot_left,
        y=layout.baseline_y,
        length=inp.width_px,
        ticks=[],
        arrow=True,
        wobble=DEFAULT_WOBBLE if inp.axis_style == "handdrawn" else 0.0,
        seed=inp.baseline_seed,
        font=inp.font,
    )


def _draw_bars(canvas: Canvas, layout: PlotLayout, inp: RenderInput, *, scale: float = 1.0) -> None:
    """逐条绘制腿与丝袜。

    袜子按输出密度原生渲染；图像像素通过 `1/scale` 变换与设备像素 1:1
    对应。腿按足底中心与整腿高度定位，丝袜高度只影响纹理。

    Args:
        canvas: 目标画布。
        layout: 布局结果。
        inp: 渲染输入（布局与绘制共用的状态）。
        scale: 输出像素密度。
    """
    sc = canvas._skia_canvas()  # pyright: ignore[reportPrivateUsage]
    for bar in inp.bars:
        # 袜子按输出倍率原生生成；图像素 = 设备像素，绘制时抵消画布变换
        stocked = render_stocking(
            bar.leg, bar.style, round(bar.height_px), seed=bar.seed, scale=scale
        )
        arr = stocked.image if bar.side == "up" else np.flipud(stocked.image)
        px = layout.plot_left + bar.x - bar.leg.foot_center_x
        # 贴图按整腿高度定位（不是袜高）：脚贴基线，腿向上展开
        py = layout.baseline_y - bar.leg.height if bar.side == "up" else layout.baseline_y
        sc.save()
        sc.translate(px, py)
        sc.scale(1.0 / scale, 1.0 / scale)
        sc.drawImage(_skia_image(arr), 0.0, 0.0, _SAMPLING_NATIVE, None)
        sc.restore()


def _draw_y_axis(canvas: Canvas, layout: PlotLayout, inp: RenderInput) -> None:
    """绘制 y 轴干线、刻度线、刻度数字与箭头。

    正刻度向上画并带箭头，负刻度向下画、不带箭头。

    Args:
        canvas: 目标画布。
        layout: 布局结果。
        inp: 渲染输入（布局与绘制共用的状态）。
    """
    axis = inp.y_axis
    if axis is None:
        return
    rng = random.Random(axis.seed)
    t_px = [axis.scale.to_px(v) for v in axis.ticks]
    up_items = [(p, format_tick(v)) for v, p in zip(axis.ticks, t_px, strict=True) if p >= 0]
    down_items = [(-p, format_tick(v)) for v, p in zip(axis.ticks, t_px, strict=True) if p < 0]
    eff_up, eff_down = effective_extents(inp.bars, inp.extent_up, inp.extent_down)
    up_len = max([0.0, eff_up, *t_px])
    down_zone = eff_down if any(b.side == "down" for b in inp.bars) else 0.0
    down_len = max([0.0, *(-p for p in t_px if p < 0), down_zone])
    sketch_axis(
        canvas,
        direction="up",
        x=layout.axis_x,
        y=layout.baseline_y,
        length=up_len,
        ticks=up_items,
        arrow=True,
        wobble=DEFAULT_WOBBLE if inp.axis_style == "handdrawn" else 0.0,
        seed=rng.getrandbits(32),
        font=axis.font,
    )
    if down_len > 0:
        sketch_axis(
            canvas,
            direction="down",
            x=layout.axis_x,
            y=layout.baseline_y,
            length=down_len,
            ticks=down_items,
            arrow=False,
            wobble=DEFAULT_WOBBLE if inp.axis_style == "handdrawn" else 0.0,
            seed=rng.getrandbits(32),
            font=axis.font,
        )


def _draw_axis_names(canvas: Canvas, layout: PlotLayout, inp: RenderInput) -> None:
    """绘制 x / y 轴名称。

    Args:
        canvas: 目标画布。
        layout: 布局结果。
        inp: 渲染输入（布局与绘制共用的状态）。
    """
    y_name = inp.y_axis_name
    if y_name is not None and y_name.text:
        # 与布局阶段共用 axis_name_metrics，保证占位与步进一致
        lines, block_w, thickness, step = axis_name_metrics(y_name, layout.y_name_span)
        if y_name.rotate:
            # 拉丁等文字旋转 90° 自下而上阅读；多行时首行靠轴、后续行向左
            for k, line in enumerate(lines):
                draw_text(
                    canvas,
                    line,
                    layout.y_name_x + block_w / 2 - thickness / 2 - k * step,
                    layout.y_name_y,
                    size_px=y_name.size_px,
                    color=y_name.color,
                    font=y_name.font,
                    anchor=("center", "middle"),
                    rotation=-90,
                )
        else:
            # 中日韩文字逐字竖排；首列靠轴，超长时向左续列
            for k, column in enumerate(lines):
                x = layout.y_name_x + block_w / 2 - y_name.size_px / 2 - k * step
                start = layout.y_name_y - len(column) * step / 2
                for i, ch in enumerate(column):
                    draw_text(
                        canvas,
                        ch,
                        x,
                        start + (i + 0.5) * step,
                        size_px=y_name.size_px,
                        color=y_name.color,
                        font=y_name.font,
                        anchor=("center", "middle"),
                    )
    x_name = inp.x_axis_name
    if x_name is not None and layout.x_name_y is not None:
        draw_text(
            canvas,
            x_name.text,
            layout.x_name_x,
            layout.x_name_y,
            size_px=x_name.size_px,
            color=x_name.color,
            font=x_name.font,
            anchor=("center", "top"),
        )


def _draw_title(canvas: Canvas, layout: PlotLayout, inp: RenderInput) -> None:
    """绘制整图标题。

    Args:
        canvas: 目标画布。
        layout: 布局结果。
        inp: 渲染输入（布局与绘制共用的状态）。
    """
    if inp.title is None:
        return
    draw_text(
        canvas,
        inp.title.text,
        layout.title_x,
        layout.title_y,
        size_px=inp.title.size_px,
        color=inp.title.color,
        font=inp.title.font,
        anchor=("center" if inp.title.align == "center" else "left", "top"),
    )


def _draw_legend(
    canvas: Canvas, layout: PlotLayout, inp: RenderInput, *, scale: float = 1.0
) -> None:
    """绘制图例色块、描边与折行文字。

    Args:
        canvas: 目标画布。
        layout: 布局结果。
        inp: 渲染输入（布局与绘制共用的状态）。
        scale: 输出像素密度；色块按该密度渲染后 1:1 贴图。
    """
    rec = inp.legend
    if rec is None:
        return
    idx_rows, row_heights, _, lines_all = legend_layout(rec, inp.width_px)
    if rec.loc == "top":
        y = layout.legend_top_y
    else:
        assert layout.legend_bottom_y is not None  # _layout 保证已填
        y = layout.legend_bottom_y
    sc = canvas._skia_canvas()  # pyright: ignore[reportPrivateUsage]
    col_w = 0.0
    if rec.ncol is not None:
        col_w = max(
            DEFAULT_LEGEND_SWATCH + DEFAULT_LEGEND_TEXT_GAP + 1.0,
            (inp.width_px - (rec.ncol - 1) * DEFAULT_LEGEND_ITEM_GAP) / rec.ncol,
        )
    for row, row_h in zip(idx_rows, row_heights, strict=True):
        full_ncol_row = rec.ncol is not None and len(row) == rec.ncol
        widths: list[float] = []
        for i in row:
            text_w = max(
                (measure_text(line, size_px=DEFAULT_LEGEND_TEXT_SIZE) for line in lines_all[i]),
                default=0.0,
            )
            widths.append(
                col_w if full_ncol_row else DEFAULT_LEGEND_SWATCH + DEFAULT_LEGEND_TEXT_GAP + text_w
            )
        row_w = sum(widths) + DEFAULT_LEGEND_ITEM_GAP * (len(row) - 1)
        # 每行整体居中；ncol 末行按实际内容宽度居中，不再与上方列对齐。
        x = layout.plot_left + (inp.width_px - row_w) / 2
        for i, item_w in zip(row, widths, strict=True):
            label_lines = lines_all[i]
            swatch_y = y + (row_h - DEFAULT_LEGEND_SWATCH) / 2
            swatch = _skia_image(
                render_swatch(
                    rec.items[i][1],
                    DEFAULT_LEGEND_SWATCH,
                    rec.seed + i,
                    scale,
                )
            )
            sc.save()
            sc.translate(x, swatch_y)
            sc.scale(1.0 / scale, 1.0 / scale)
            sc.drawImage(swatch, 0.0, 0.0, _SAMPLING_NATIVE, None)
            sc.restore()
            rect = skia.Rect.MakeXYWH(x, swatch_y, DEFAULT_LEGEND_SWATCH, DEFAULT_LEGEND_SWATCH)
            rrect = skia.RRect.MakeRectXY(rect, DEFAULT_SWATCH_RADIUS, DEFAULT_SWATCH_RADIUS)
            sc.drawRRect(
                rrect,
                skia.Paint(
                    AntiAlias=True,
                    Color=skia_color(DEFAULT_INK_COLOR),
                    Style=skia.Paint.kStroke_Style,
                    StrokeWidth=DEFAULT_SWATCH_STROKE,
                ),
            )
            line_h = legend_line_height(rec.items[i][0], rec.font)
            text_h = len(label_lines) * line_h
            text_top = y + (row_h - text_h) / 2
            for j, line in enumerate(label_lines):
                draw_text(
                    canvas,
                    line,
                    x + DEFAULT_LEGEND_SWATCH + DEFAULT_LEGEND_TEXT_GAP,
                    text_top + (j + 0.5) * line_h,
                    size_px=DEFAULT_LEGEND_TEXT_SIZE,
                    font=rec.font,
                    anchor=("left", "middle"),
                )
            x += item_w + DEFAULT_LEGEND_ITEM_GAP
        y += row_h + DEFAULT_LEGEND_ROW_GAP


def _draw_x_labels(canvas: Canvas, layout: PlotLayout, inp: RenderInput) -> None:
    """按布局结果绘制 x 标签，必要时旋转。

    Args:
        canvas: 目标画布。
        layout: 布局结果。
        inp: 渲染输入（布局与绘制共用的状态）。
    """
    rec = inp.x_labels
    if rec is None or layout.x_label_y is None:
        return
    xs = x_label_xs(rec, inp.group_centers, inp.width_px)
    above = layout.x_label_baseline
    angle = layout.x_label_angle
    for label, x in zip(rec.labels, xs, strict=True):
        px = layout.plot_left + x
        if angle == 0.0:
            anchor: TextAnchor = ("center", "bottom" if above else "top")
            draw_text(
                canvas,
                label,
                px,
                layout.x_label_y,
                size_px=DEFAULT_X_LABEL_SIZE,
                font=rec.font,
                anchor=anchor,
            )
            continue
        if abs(angle) >= 89.999:
            # 90° 字列以 ("right", ·) 锚定时，墨迹在锚点右侧占一个自然
            # 单行块高（新引擎按精确 bbox 锚定、旋转绕锚点进行）；与
            # _x_label_fit 的 90° 分支一致，按实测自然行高把锚点左移
            # 半行，使字列水平居中于刻度
            natural_h = measure_text_height(label, size_px=DEFAULT_X_LABEL_SIZE, font=rec.font)
            px -= natural_h / 2
        draw_text(
            canvas,
            label,
            px,
            layout.x_label_y,
            size_px=DEFAULT_X_LABEL_SIZE,
            font=rec.font,
            anchor=("right", "bottom" if above else "top"),
            rotation=angle,
        )


def _draw_value_labels(canvas: Canvas, layout: PlotLayout, inp: RenderInput) -> None:
    """绘制 L4 写入的数值标签。

    标签对齐袜口中心而非足底中心，因为倾斜的腿两者不在同一竖线上。

    Args:
        canvas: 目标画布。
        layout: 布局结果。
        inp: 渲染输入（布局与绘制共用的状态）。
    """
    # 数值标签不参与布局：极端 max_fill / 超长文本可能压到标题或图例；暂不处理。
    for bar in inp.bars:
        if bar.value_label is None:
            continue
        # 袜高超过整腿时渲染会截到腿顶，标签也应对齐实际可见袜口
        visible_h = max(0.0, min(float(round(bar.height_px)), float(bar.leg.height)))
        if bar.side == "up":
            y = layout.baseline_y - visible_h - DEFAULT_VALUE_LABEL_GAP
            anchor: TextAnchor = ("center", "bottom")
        else:
            y = layout.baseline_y + visible_h + DEFAULT_VALUE_LABEL_GAP
            anchor = ("center", "top")
        # 对齐袜口中心而非足底中心：倾斜的腿两者不在同一竖线上
        x = (
            layout.plot_left
            + bar.x
            - bar.leg.foot_center_x
            + _sock_top_center_x(bar.leg, visible_h)
        )
        draw_text(
            canvas,
            bar.value_label,
            x,
            y,
            size_px=DEFAULT_VALUE_LABEL_SIZE,
            font=inp.font,
            anchor=anchor,
        )


def draw_all(canvas: Canvas, layout: PlotLayout, inp: RenderInput, *, scale: float = 1.0) -> None:
    """按固定 z 序绘制全部元素。

    顺序：网格 → 基线 → 腿 → y 轴 → 轴名称 → 标题 → 图例 → x 标签
    → 数值标签。

    Args:
        canvas: 已按 scale 设置画布变换的目标画布。
        layout: 布局结果。
        inp: 渲染输入。
        scale: 输出像素密度，用于原生渲染腿图与图例色块。
    """
    _draw_grid(canvas, layout, inp)
    _draw_baseline(canvas, layout, inp)
    _draw_bars(canvas, layout, inp, scale=scale)
    _draw_y_axis(canvas, layout, inp)
    _draw_axis_names(canvas, layout, inp)
    _draw_title(canvas, layout, inp)
    _draw_legend(canvas, layout, inp, scale=scale)
    _draw_x_labels(canvas, layout, inp)
    _draw_value_labels(canvas, layout, inp)
