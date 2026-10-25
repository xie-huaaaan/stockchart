"""L2 自由柱状图：Scale 比例尺与 BarPlot 画布（含 L3 布局封装方法）。"""

from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import numpy as np
import skia
from numpy.typing import NDArray
from PIL import Image as PilImage

from stockchart.canvas import Canvas, skia_color
from stockchart.color import Color
from stockchart.defaults import (
    DEFAULT_BACKGROUND,
    DEFAULT_BOTTOM_PAD,
    DEFAULT_GRID_COLOR,
    DEFAULT_GRID_DASH,
    DEFAULT_GRID_WIDTH,
    DEFAULT_INK_COLOR,
    DEFAULT_LABEL_LINE_FACTOR,
    DEFAULT_LEGEND_ITEM_GAP,
    DEFAULT_LEGEND_MARGIN,
    DEFAULT_LEGEND_ROW_GAP,
    DEFAULT_LEGEND_SWATCH,
    DEFAULT_LEGEND_TEXT_GAP,
    DEFAULT_LEGEND_TEXT_SIZE,
    DEFAULT_OUTPUT_SCALE,
    DEFAULT_PLOT_LEFT_PAD,
    DEFAULT_PLOT_RIGHT_PAD,
    DEFAULT_SEED,
    DEFAULT_STOCKING_STYLE,
    DEFAULT_SWATCH_RADIUS,
    DEFAULT_SWATCH_STROKE,
    DEFAULT_TICK_LABEL_GAP,
    DEFAULT_TICK_LABEL_SIZE,
    DEFAULT_TICK_SIZE,
    DEFAULT_TITLE_INSET_X,
    DEFAULT_TITLE_INSET_Y,
    DEFAULT_TITLE_LINE_FACTOR,
    DEFAULT_TITLE_SIZE,
    DEFAULT_VALUE_LABEL_GAP,
    DEFAULT_VALUE_LABEL_SIZE,
    DEFAULT_WOBBLE,
    DEFAULT_X_LABEL_GAP,
    DEFAULT_X_LABEL_SIZE,
    DEFAULT_Y_EXTENT,
)
from stockchart.legs import Leg
from stockchart.library import LegLibrary
from stockchart.sketch import sketch_axis, sketch_line
from stockchart.stocking import STYLES, StockingStyle, StyleLike, render_stocking
from stockchart.text import TextAnchor, draw_text, measure_text

type BarSide = Literal["up", "down"]
type LegendLoc = Literal["top", "bottom"]


def _resolve_style(style: StyleLike) -> StockingStyle:
    """把 StyleLike 归一为 StockingStyle 实例。"""
    if isinstance(style, str):
        try:
            return STYLES[style]
        except KeyError:
            raise ValueError(f"未知样式预设 {style!r}，可选：{'、'.join(STYLES)}") from None
    return style


@dataclass(slots=True, frozen=True)
class Scale:
    """线性比例尺：数据值 ↔ 基线上方像素。

    柱高与轴刻度共用同一个 Scale 即可保证一致。
    domain 为 (值下限, 值上限)；range_px 为 (像素下限, 像素上限)，
    以基线为 0、向上为正（负像素表示基线下方）。
    """

    domain: tuple[float, float]
    range_px: tuple[float, float]

    def __post_init__(self) -> None:
        lo, hi = self.domain
        if not lo < hi:
            raise ValueError(f"Scale.domain 须下限 < 上限，得到 {self.domain!r}")

    def to_px(self, value: float) -> float:
        """数据值 → 像素。"""
        d_lo, d_hi = self.domain
        r_lo, r_hi = self.range_px
        return r_lo + (value - d_lo) / (d_hi - d_lo) * (r_hi - r_lo)

    def from_px(self, px: float) -> float:
        """像素 → 数据值。"""
        d_lo, d_hi = self.domain
        r_lo, r_hi = self.range_px
        return d_lo + (px - r_lo) / (r_hi - r_lo) * (d_hi - d_lo)

    @classmethod
    def fit(cls, values: Sequence[float], extent_px: float, *, margin: float = 0.0) -> Scale:
        """构造 [min(values), max(values)] → [0, extent_px] 的比例尺。

        margin 为两侧留边比例：domain 每端向外扩 (max - min) × margin。
        values 为空或全部相同时抛 ValueError。
        """
        if not values:
            raise ValueError("values 为空，无法构造比例尺")
        if margin < 0:
            raise ValueError(f"margin 须 >= 0，得到 {margin}")
        lo, hi = min(values), max(values)
        if not lo < hi:
            raise ValueError(f"values 全部相同（{lo}），无法构造比例尺")
        pad = (hi - lo) * margin
        return cls((lo - pad, hi + pad), (0.0, float(extent_px)))


@dataclass(slots=True)
class _BarRecord:
    """一根柱子的绘制意图，几何在 render 时统一计算。"""

    x: float
    height_px: float
    leg: Leg
    style: StockingStyle
    side: BarSide
    seed: int
    value_label: str | None = None


@dataclass(slots=True)
class _YAxisRecord:
    """y 轴的绘制意图。ticks 为数据值，绘制时经 scale 换算为像素。"""

    scale: Scale
    ticks: list[float]
    label: str | None
    grid: bool
    seed: int


@dataclass(slots=True)
class _XLabelsRecord:
    """x 标签的绘制意图；xs 为绘图区坐标，缺省时优先用组中心。"""

    labels: list[str]
    xs: list[float] | None


@dataclass(slots=True)
class _LegendRecord:
    """图例的绘制意图；样式已归一为实例。"""

    items: list[tuple[str, StockingStyle]]
    ncol: int | None
    loc: LegendLoc
    seed: int


@dataclass(slots=True)
class _Layout:
    """一次 render 的整体几何。坐标均为最终画布像素。"""

    final_w: float
    final_h: float
    plot_left: float  # 绘图区（用户坐标系 x=0）的画布 x
    plot_right: float
    baseline_y: float  # 基线的画布 y
    content_bottom: float  # 全部腿与轴内容的最低点（x 标签锚此之下）
    axis_x: float = 0.0  # y 轴干线的画布 x
    y_label_x: float = 0.0  # y 轴标题（纵向排列）中心的画布 x
    y_up_len: float = 0.0  # y 轴干线向上长度（标题纵向居中用）
    legend_top_y: float = 0.0  # 顶部图例首行的画布 y
    x_label_top: float | None = None
    legend_bottom_y: float | None = None


def _format_tick(value: float) -> str:
    """刻度数字格式：整数不带小数点，小数去尾零。"""
    if abs(value - round(value)) < 1e-9:
        return str(round(value))
    return f"{value:g}"


def _skia_image(arr: NDArray[np.uint8]) -> skia.Image:
    """Numpy RGBA → skia Image。skia 的 numpy 互操作按 BGRA 解释通道，需先换序。"""
    return skia.Image.fromarray(np.ascontiguousarray(arr[:, :, [2, 1, 0, 3]]))


def _even_ticks(domain: tuple[float, float], n: int = 4) -> list[float]:
    """把 domain 均分为 n 段，返回 n+1 个刻度值（含两端）。"""
    lo, hi = domain
    step = (hi - lo) / n
    return [round(lo + i * step, 10) for i in range(n)] + [hi]


# 图例色块统一用同一条固定腿渲染，取其袜身中段的织物
_swatch_leg_cache: Leg | None = None


def _swatch_leg() -> Leg:
    global _swatch_leg_cache
    if _swatch_leg_cache is None:
        _swatch_leg_cache = LegLibrary(seed=0).get("leg_01")
    return _swatch_leg_cache


def _render_swatch(style: StockingStyle, size: int, seed: int) -> NDArray[np.uint8]:
    """渲染该样式并裁取袜身中部的一小块织物，作为图例色块。"""
    leg = _swatch_leg()
    sh = round(leg.height * 0.55)
    img = render_stocking(leg, style, sh, seed=seed).image
    h, w = img.shape[:2]
    # 袜身中段：袜区（底部 sh 行）内垂直居中的 size 行
    top = (h - sh) + max(0, (sh - size) // 2)
    band = img[top : top + size]
    cols = np.where(band[:, :, 3].max(axis=0) > 0)[0]
    center = int((cols[0] + cols[-1]) // 2) if len(cols) else w // 2
    left = min(max(0, center - size // 2), max(0, w - size))
    out = np.zeros((size, size, 4), np.uint8)
    crop = band[:, left : left + size]
    out[: crop.shape[0], : crop.shape[1]] = crop
    return out


class BarPlot:
    """自由柱状图：以 X 轴为基线，腿的位置与丝袜高度全部由调用者按素材像素指定。

    坐标为绘图区像素：x ∈ [0, width_px]，基线之上为正。轴、标题、标签、图例
    的边距在 render 时自动留出，最终画布比 width_px × (extent_up + extent_down)
    略大；预留的 extent 装不下腿时自动向下/向上扩。

    所有 add_* 方法记录绘制意图、返回自身以便链式调用，几何在 render() 统一计算。
    """

    def __init__(
        self,
        width_px: int,
        *,
        extent_up: int = DEFAULT_Y_EXTENT,
        extent_down: int = 0,
        background: Color = DEFAULT_BACKGROUND,
        seed: int | None = None,
    ) -> None:
        """构造绘图区。

        extent_up / extent_down 为基线上、下各预留的像素高度；基线下方不留
        空间时基线贴住内容底部（x 标签等边距仍会另行留出）。
        """
        if width_px <= 0:
            raise ValueError(f"width_px 须为正数，得到 {width_px}")
        self._width_px = width_px
        self._extent_up = extent_up
        self._extent_down = extent_down
        self._background = background
        self._rng = random.Random(DEFAULT_SEED if seed is None else seed)
        self._bars: list[_BarRecord] = []
        self._group_centers: list[float] = []
        self._y_axis: _YAxisRecord | None = None
        self._x_labels: _XLabelsRecord | None = None
        self._title: str | None = None
        self._legend: _LegendRecord | None = None
        # 基线的抖动 seed 在构造期固定，保证多次 render 结果一致
        self._baseline_seed = self._rng.getrandbits(32)

    # ------------------------------------------------------------------
    # L2 公开接口
    # ------------------------------------------------------------------

    @property
    def width_px(self) -> int:
        """绘图区宽度（腿与坐标使用的 x 范围）。"""
        return self._width_px

    def add_bar(
        self,
        x: float,
        height_px: float,
        leg: Leg,
        *,
        style: StyleLike = DEFAULT_STOCKING_STYLE,
        side: BarSide = "up",
        seed: int | None = None,
    ) -> BarPlot:
        """在 x 处贴一条腿：x 是足底中心的目标位置（腿宽不一，按脚对齐才均匀）。

        height_px 为丝袜高度（素材像素），小于等于 0 为裸腿。
        side="down" 时素材竖直翻转、脚贴基线朝下。
        style 为 StockingStyle 实例或 STYLES 预设名；seed 缺省时由构造时的
        seed 派生，保证整图可复现。
        """
        bar_seed = self._rng.getrandbits(32) if seed is None else seed
        self._bars.append(
            _BarRecord(
                x=float(x),
                height_px=float(height_px),
                leg=leg,
                style=_resolve_style(style),
                side=side,
                seed=bar_seed,
            )
        )
        return self

    def add_y_axis(
        self,
        scale: Scale,
        *,
        ticks: Sequence[float] | None = None,
        label: str | None = None,
        grid: bool = False,
    ) -> BarPlot:
        """添加 y 轴（手绘风，含刻度数字）。ticks 缺省由 scale.domain 均匀取值生成。

        刻度按 scale 映射到基线上下两侧：domain 含负值时干线向下延伸、
        下方刻度照常绘制，箭头仍在最上端。grid=True 时沿各刻度画横向
        手绘虚线（浅色，压在腿与袜之下）。label 纵向排列在刻度数字左侧。
        """
        self._y_axis = _YAxisRecord(
            scale=scale,
            ticks=[float(v) for v in (ticks if ticks is not None else _even_ticks(scale.domain))],
            label=label,
            grid=grid,
            seed=self._rng.getrandbits(32),
        )
        return self

    def add_x_labels(
        self,
        labels: Sequence[str],
        *,
        xs: Sequence[float] | None = None,
    ) -> BarPlot:
        """添加 x 轴标签。

        画在全部内容最低点之下（含朝下腿与 y 轴向下延伸的部分），与基线
        解耦——没有下方内容时自然贴着基线下方。

        xs 为绘图区坐标（足底中心基准），缺省时优先使用 add_bars 系列
        方法记录的组中心，否则沿绘图区宽度均分。
        """
        if xs is not None and len(xs) != len(labels):
            raise ValueError(f"xs 与 labels 长度不一致：{len(xs)} != {len(labels)}")
        self._x_labels = _XLabelsRecord(
            labels=list(labels),
            xs=[float(v) for v in xs] if xs is not None else None,
        )
        return self

    def add_title(self, text: str) -> BarPlot:
        """添加左上角标题。"""
        self._title = text
        return self

    def add_legend(
        self,
        items: Sequence[tuple[str, StyleLike]],
        *,
        ncol: int | None = None,
        loc: LegendLoc = "top",
    ) -> BarPlot:
        """添加图例：每项为织物纹理色块 + 文字，色块取该样式袜身中部的织物。

        loc="top"（默认）画在标题下方、绘图区上方，"bottom" 画在最底部；
        ncol 为一行几项，缺省自动：单行放得下就单行，否则按宽度换行。
        图例占据的高度自动计入布局；items 为空时忽略。
        """
        if ncol is not None and ncol < 1:
            raise ValueError(f"ncol 须 >= 1，得到 {ncol}")
        if loc not in ("top", "bottom"):
            raise ValueError(f"loc 须为 'top' 或 'bottom'，得到 {loc!r}")
        if not items:
            return self
        self._legend = _LegendRecord(
            items=[(label, _resolve_style(st)) for label, st in items],
            ncol=ncol,
            loc=loc,
            seed=self._rng.getrandbits(32),
        )
        return self

    def render(self, *, scale: float = DEFAULT_OUTPUT_SCALE) -> Canvas:
        """渲染。scale 为输出放大倍数（抗锯齿），不影响素材像素坐标。"""
        if scale <= 0:
            raise ValueError(f"scale 须为正数，得到 {scale}")
        layout = self._layout()
        canvas = Canvas(
            round(layout.final_w * scale),
            round(layout.final_h * scale),
            background=self._background,
        )
        canvas.skia_canvas().scale(scale, scale)
        self._draw(canvas, layout)
        return canvas

    def save(self, path: str | Path, *, scale: float = DEFAULT_OUTPUT_SCALE) -> Path:
        """渲染并直接写出 PNG，返回写出路径。"""
        return self.render(scale=scale).save(path)

    def to_pil(self, *, scale: float = DEFAULT_OUTPUT_SCALE) -> PilImage.Image:
        """渲染并直接导出 PIL Image（RGBA）。"""
        return self.render(scale=scale).to_pil()

    # ------------------------------------------------------------------
    # 布局与绘制
    # ------------------------------------------------------------------

    def _effective_extents(self) -> tuple[float, float]:
        """上下预留高度；装不下腿时自动扩张。"""
        up_legs = [b.leg.height for b in self._bars if b.side == "up"]
        down_legs = [b.leg.height for b in self._bars if b.side == "down"]
        eff_up = max(float(self._extent_up), float(max(up_legs, default=0)))
        eff_down = max(float(self._extent_down), float(max(down_legs, default=0)))
        return eff_up, eff_down

    def _legend_rows(self, rec: _LegendRecord) -> tuple[list[list[int]], float]:
        """图例分行的项下标与带高（不含外边距）。"""
        widths = [
            DEFAULT_LEGEND_SWATCH
            + DEFAULT_LEGEND_TEXT_GAP
            + measure_text(label, size_px=DEFAULT_LEGEND_TEXT_SIZE)
            for label, _ in rec.items
        ]
        idx_rows: list[list[int]] = []
        if rec.ncol is not None:
            for start in range(0, len(widths), rec.ncol):
                idx_rows.append(list(range(start, min(start + rec.ncol, len(widths)))))
        else:
            row: list[int] = []
            row_w = 0.0
            for i, w in enumerate(widths):
                extra = w if not row else DEFAULT_LEGEND_ITEM_GAP + w
                if row and row_w + extra > self._width_px:
                    idx_rows.append(row)
                    row, row_w = [i], w
                else:
                    row.append(i)
                    row_w += extra
            if row:
                idx_rows.append(row)
        band_h = 0.0
        if idx_rows:
            n = len(idx_rows)
            band_h = n * DEFAULT_LEGEND_SWATCH + (n - 1) * DEFAULT_LEGEND_ROW_GAP
        return idx_rows, band_h

    def _layout(self) -> _Layout:
        eff_up, eff_down = self._effective_extents()
        axis = self._y_axis

        # y 轴左侧占位：[画布留白][y 轴标题(纵向)][刻度数字][间距][刻度线][干线]
        down_len = 0.0
        axis_x = 0.0
        y_label_x = 0.0
        plot_left = float(DEFAULT_PLOT_LEFT_PAD)
        if axis is not None:
            t_px = [axis.scale.to_px(v) for v in axis.ticks]
            down_len = max([0.0, *(-p for p in t_px if p < 0)])
            label_w = max(
                (
                    measure_text(_format_tick(v), size_px=DEFAULT_TICK_LABEL_SIZE)
                    for v in axis.ticks
                ),
                default=0.0,
            )
            head = DEFAULT_PLOT_LEFT_PAD
            if axis.label is not None:
                head += DEFAULT_TICK_LABEL_SIZE + DEFAULT_TICK_LABEL_GAP
            axis_x = head + label_w + DEFAULT_TICK_LABEL_GAP + DEFAULT_TICK_SIZE
            y_label_x = head / 2
            plot_left = axis_x

        # 顶部带：标题 + 顶部图例
        top_band = 0.0
        legend_top_y = 0.0
        if self._title is not None:
            top_band = DEFAULT_TITLE_INSET_Y + DEFAULT_TITLE_SIZE * DEFAULT_TITLE_LINE_FACTOR
        if self._legend is not None and self._legend.loc == "top":
            _, legend_h = self._legend_rows(self._legend)
            legend_top_y = top_band if self._title is not None else DEFAULT_LEGEND_MARGIN
            top_band = legend_top_y + legend_h + DEFAULT_LEGEND_MARGIN
        elif self._legend is None and self._title is None:
            top_band = 0.0

        baseline = top_band + eff_up
        content_bottom = baseline + max(eff_down, down_len)

        x_label_top: float | None = None
        bottom = content_bottom
        if self._x_labels is not None and self._x_labels.labels:
            x_label_top = content_bottom + DEFAULT_X_LABEL_GAP
            bottom = x_label_top + DEFAULT_X_LABEL_SIZE * DEFAULT_LABEL_LINE_FACTOR

        legend_bottom_y: float | None = None
        if self._legend is not None and self._legend.loc == "bottom":
            legend_bottom_y = bottom + DEFAULT_LEGEND_MARGIN
            bottom = legend_bottom_y + self._legend_rows(self._legend)[1]

        final_h = bottom + DEFAULT_BOTTOM_PAD
        plot_right = plot_left + self._width_px
        final_w = plot_right + DEFAULT_PLOT_RIGHT_PAD
        y_up_len = 0.0
        if axis is not None:
            y_up_len = max([0.0, eff_up] + [axis.scale.to_px(v) for v in axis.ticks])
        return _Layout(
            final_w=final_w,
            final_h=final_h,
            plot_left=plot_left,
            plot_right=plot_right,
            baseline_y=baseline,
            content_bottom=content_bottom,
            axis_x=axis_x,
            y_label_x=y_label_x,
            y_up_len=y_up_len,
            legend_top_y=legend_top_y,
            x_label_top=x_label_top,
            legend_bottom_y=legend_bottom_y,
        )

    def _draw(self, canvas: Canvas, layout: _Layout) -> None:
        self._draw_grid(canvas, layout)
        self._draw_baseline(canvas, layout)
        self._draw_bars(canvas, layout)
        self._draw_y_axis(canvas, layout)
        self._draw_title(canvas, layout)
        self._draw_legend(canvas, layout)
        self._draw_x_labels(canvas, layout)
        self._draw_value_labels(canvas, layout)

    def _draw_grid(self, canvas: Canvas, layout: _Layout) -> None:
        axis = self._y_axis
        if axis is None or not axis.grid:
            return
        rng = random.Random(axis.seed)
        dash, gap = DEFAULT_GRID_DASH
        for v in axis.ticks:
            y = layout.baseline_y - axis.scale.to_px(v)
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
                    wobble=DEFAULT_WOBBLE * 0.3,  # 网格线抖动比主线条轻
                    seed=rng.getrandbits(32),
                )
                x = seg + gap

    def _draw_baseline(self, canvas: Canvas, layout: _Layout) -> None:
        """基线（x 轴）：带右向箭头，画在腿之下。"""
        sketch_axis(
            canvas,
            direction="right",
            x=layout.plot_left,
            y=layout.baseline_y,
            length=self._width_px,
            ticks=[],
            arrow=True,
            seed=self._baseline_seed,
        )

    def _draw_bars(self, canvas: Canvas, layout: _Layout) -> None:
        sc = canvas.skia_canvas()
        for bar in self._bars:
            stocked = render_stocking(bar.leg, bar.style, round(bar.height_px), seed=bar.seed)
            arr = stocked.image if bar.side == "up" else np.flipud(stocked.image)
            img = _skia_image(arr)
            px = layout.plot_left + bar.x - stocked.foot_center_x
            py = layout.baseline_y - stocked.height if bar.side == "up" else layout.baseline_y
            sc.drawImage(img, px, py)

    def _draw_y_axis(self, canvas: Canvas, layout: _Layout) -> None:
        axis = self._y_axis
        if axis is None:
            return
        rng = random.Random(axis.seed)
        t_px = [axis.scale.to_px(v) for v in axis.ticks]
        up_items = [(p, _format_tick(v)) for v, p in zip(axis.ticks, t_px, strict=True) if p >= 0]
        down_items = [(-p, _format_tick(v)) for v, p in zip(axis.ticks, t_px, strict=True) if p < 0]
        eff_up, _ = self._effective_extents()
        up_len = max([0.0, eff_up, *t_px])
        down_len = max([0.0, *(-p for p in t_px if p < 0)])
        sketch_axis(
            canvas,
            direction="up",
            x=layout.axis_x,
            y=layout.baseline_y,
            length=up_len,
            ticks=up_items,
            arrow=True,
            seed=rng.getrandbits(32),
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
                seed=rng.getrandbits(32),
            )
        if axis.label is not None:
            # 轴标题纵向排列（契合中文书写习惯），在轴干线上下之间居中
            chars = list(axis.label)
            total = len(chars) * DEFAULT_TICK_LABEL_SIZE * 1.15
            y = layout.baseline_y - (layout.y_up_len + total) / 2
            for ch in chars:
                draw_text(
                    canvas,
                    ch,
                    layout.y_label_x,
                    y,
                    size_px=DEFAULT_TICK_LABEL_SIZE,
                    anchor=("center", "top"),
                )
                y += DEFAULT_TICK_LABEL_SIZE * 1.15

    def _draw_title(self, canvas: Canvas, layout: _Layout) -> None:
        if self._title is None:
            return
        draw_text(
            canvas,
            self._title,
            DEFAULT_TITLE_INSET_X,
            DEFAULT_TITLE_INSET_Y,
            size_px=DEFAULT_TITLE_SIZE,
            anchor=("left", "top"),
        )

    def _draw_legend(self, canvas: Canvas, layout: _Layout) -> None:
        rec = self._legend
        if rec is None:
            return
        idx_rows, _ = self._legend_rows(rec)
        if rec.loc == "top":
            y = layout.legend_top_y
        else:
            assert layout.legend_bottom_y is not None  # _layout 保证已填
            y = layout.legend_bottom_y
        sc = canvas.skia_canvas()
        for row in idx_rows:
            row_w = sum(
                DEFAULT_LEGEND_SWATCH
                + DEFAULT_LEGEND_TEXT_GAP
                + measure_text(rec.items[i][0], size_px=DEFAULT_LEGEND_TEXT_SIZE)
                for i in row
            ) + DEFAULT_LEGEND_ITEM_GAP * (len(row) - 1)
            x = layout.plot_left + (self._width_px - row_w) / 2
            for i in row:
                label, style = rec.items[i]
                swatch = _skia_image(_render_swatch(style, DEFAULT_LEGEND_SWATCH, rec.seed + i))
                sc.drawImage(swatch, x, y)
                rect = skia.Rect.MakeXYWH(x, y, DEFAULT_LEGEND_SWATCH, DEFAULT_LEGEND_SWATCH)
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
                draw_text(
                    canvas,
                    label,
                    x + DEFAULT_LEGEND_SWATCH + DEFAULT_LEGEND_TEXT_GAP,
                    y + DEFAULT_LEGEND_SWATCH / 2,
                    size_px=DEFAULT_LEGEND_TEXT_SIZE,
                    anchor=("left", "middle"),
                )
                x += (
                    DEFAULT_LEGEND_SWATCH
                    + DEFAULT_LEGEND_TEXT_GAP
                    + measure_text(label, size_px=DEFAULT_LEGEND_TEXT_SIZE)
                    + DEFAULT_LEGEND_ITEM_GAP
                )
            y += DEFAULT_LEGEND_SWATCH + DEFAULT_LEGEND_ROW_GAP

    def _draw_x_labels(self, canvas: Canvas, layout: _Layout) -> None:
        rec = self._x_labels
        if rec is None or layout.x_label_top is None:
            return
        if rec.xs is not None:
            xs = rec.xs
        elif len(rec.labels) == len(self._group_centers):
            xs = self._group_centers
        else:
            n = len(rec.labels)
            xs = [(i + 0.5) * self._width_px / n for i in range(n)]
        for label, x in zip(rec.labels, xs, strict=True):
            draw_text(
                canvas,
                label,
                layout.plot_left + x,
                layout.x_label_top,
                size_px=DEFAULT_X_LABEL_SIZE,
                anchor=("center", "top"),
            )

    def _draw_value_labels(self, canvas: Canvas, layout: _Layout) -> None:
        for bar in self._bars:
            if bar.value_label is None:
                continue
            if bar.side == "up":
                y = layout.baseline_y - bar.height_px - DEFAULT_VALUE_LABEL_GAP
                anchor: TextAnchor = ("center", "bottom")
            else:
                y = layout.baseline_y + bar.height_px + DEFAULT_VALUE_LABEL_GAP
                anchor = ("center", "top")
            draw_text(
                canvas,
                bar.value_label,
                layout.plot_left + bar.x,
                y,
                size_px=DEFAULT_VALUE_LABEL_SIZE,
                anchor=anchor,
            )
