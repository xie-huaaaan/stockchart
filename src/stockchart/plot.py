"""L2 自由柱状图：Scale 比例尺与 BarPlot 画布（含 L3 布局封装方法）。"""

from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import numpy as np
import skia
from PIL import Image as PilImage

from stockchart.canvas import Canvas
from stockchart.color import Color
from stockchart.defaults import (
    DEFAULT_BACKGROUND,
    DEFAULT_BOTTOM_PAD,
    DEFAULT_OUTPUT_SCALE,
    DEFAULT_PLOT_LEFT_PAD,
    DEFAULT_PLOT_RIGHT_PAD,
    DEFAULT_SEED,
    DEFAULT_STOCKING_STYLE,
    DEFAULT_Y_EXTENT,
)
from stockchart.legs import Leg
from stockchart.stocking import STYLES, StockingStyle, StyleLike, render_stocking

type BarSide = Literal["up", "down"]


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
class _Layout:
    """一次 render 的整体几何。坐标均为最终画布像素。"""

    final_w: float
    final_h: float
    plot_left: float  # 绘图区（用户坐标系 x=0）的画布 x
    baseline_y: float  # 基线的画布 y
    content_bottom: float  # 全部腿内容的最低点


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

    def _layout(self) -> _Layout:
        eff_up, eff_down = self._effective_extents()
        top_band = self._top_band_height()
        baseline = top_band + eff_up
        content_bottom = baseline + eff_down
        final_h = content_bottom + DEFAULT_BOTTOM_PAD
        final_w = DEFAULT_PLOT_LEFT_PAD + self._width_px + DEFAULT_PLOT_RIGHT_PAD
        return _Layout(final_w, final_h, DEFAULT_PLOT_LEFT_PAD, baseline, content_bottom)

    def _top_band_height(self) -> float:
        """基线上方、腿区之外的标题与图例带高度。"""
        return 0.0

    def _draw(self, canvas: Canvas, layout: _Layout) -> None:
        self._draw_bars(canvas, layout)

    def _draw_bars(self, canvas: Canvas, layout: _Layout) -> None:
        sc = canvas.skia_canvas()
        for bar in self._bars:
            stocked = render_stocking(bar.leg, bar.style, round(bar.height_px), seed=bar.seed)
            arr = stocked.image if bar.side == "up" else np.flipud(stocked.image)
            img = skia.Image.fromarray(np.ascontiguousarray(arr))
            px = layout.plot_left + bar.x - stocked.foot_center_x
            py = layout.baseline_y - stocked.height if bar.side == "up" else layout.baseline_y
            sc.drawImage(img, px, py)
