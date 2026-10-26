"""L2 自由柱状图：Scale 比例尺与 BarPlot 画布（含 L3 布局封装方法）。"""

from __future__ import annotations

import itertools
import math
import random
from collections.abc import Callable, Sequence
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
    DEFAULT_AXIS_NAME_GAP,
    DEFAULT_AXIS_NAME_LINE_FACTOR,
    DEFAULT_AXIS_NAME_SIZE,
    DEFAULT_AXIS_STYLE,
    DEFAULT_BACKGROUND,
    DEFAULT_BAR_GAP,
    DEFAULT_BOTTOM_PAD,
    DEFAULT_GRID_COLOR,
    DEFAULT_GRID_DASH,
    DEFAULT_GRID_WIDTH,
    DEFAULT_GROUP_GAP,
    DEFAULT_INK_COLOR,
    DEFAULT_LABEL_LINE_FACTOR,
    DEFAULT_LEGEND_ITEM_GAP,
    DEFAULT_LEGEND_LINE_FACTOR,
    DEFAULT_LEGEND_MARGIN,
    DEFAULT_LEGEND_MAX_LINES,
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
    DEFAULT_TEXT_COLOR,
    DEFAULT_TICK_LABEL_GAP,
    DEFAULT_TICK_LABEL_SIZE,
    DEFAULT_TICK_SIZE,
    DEFAULT_TITLE_ALIGN,
    DEFAULT_TITLE_INSET_Y,
    DEFAULT_TITLE_LINE_FACTOR,
    DEFAULT_TITLE_SIZE,
    DEFAULT_VALUE_LABEL_GAP,
    DEFAULT_VALUE_LABEL_SIZE,
    DEFAULT_WOBBLE,
    DEFAULT_X_LABEL_GAP,
    DEFAULT_X_LABEL_ITEM_GAP,
    DEFAULT_X_LABEL_ROTATIONS,
    DEFAULT_X_LABEL_SIZE,
    DEFAULT_Y_EXTENT,
)
from stockchart.legs import Leg
from stockchart.library import LegLibrary
from stockchart.sketch import sketch_axis, sketch_line
from stockchart.stocking import (
    STYLES,
    StockingStyle,
    StyleLike,
    StyleSeq,
    render_stocking,
)
from stockchart.text import (
    TextAnchor,
    draw_text,
    measure_text,
    measure_text_height,
    wrap_text,
)

type BarSide = Literal["up", "down"]
type LegendLoc = Literal["top", "bottom"]
type XLabelPos = Literal["content", "auto", "above", "below"]
type StyleCycle = Literal["group", "sequence"]
type AxisStyle = Literal["clean", "handdrawn"]
type XLabelRotation = float | Literal["auto"]
type TitleAlign = Literal["center", "left"]


def _resolve_style(style: StyleLike) -> StockingStyle:
    """把 StyleLike 归一为 StockingStyle 实例。"""
    if isinstance(style, str):
        try:
            return STYLES[style]
        except KeyError:
            raise ValueError(f"未知样式预设 {style!r}，可选：{'、'.join(STYLES)}") from None
    return style


def _normalize_style_seq(style: StyleSeq) -> list[StockingStyle]:
    """把 StyleSeq 归一为实例列表；空列表视为错误。"""
    styles = [style] if isinstance(style, (str, StockingStyle)) else list(style)
    if not styles:
        raise ValueError("style 列表不能为空")
    return [_resolve_style(s) for s in styles]


def _cycle_styles(styles: Sequence[StockingStyle], n: int) -> list[StockingStyle]:
    """把样式列表按绘制顺序展开为 n 根柱各自的样式（不足则从头循环）。

    调用方决定切片起点：按组内位置循环时每组取头部，按整体循环时沿展开
    结果连续切片。
    """
    return [styles[i % len(styles)] for i in range(n)]


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
class _LegSpec:
    """一根腿的完整绘制规格，由 L4 计算后交给 _add_columns 摆放。"""

    leg: Leg
    height_px: float
    side: BarSide
    style: StockingStyle


@dataclass(slots=True)
class _YAxisRecord:
    """y 轴的绘制意图。ticks 为数据值，绘制时经 scale 换算为像素。"""

    scale: Scale
    ticks: list[float]
    grid: bool
    seed: int


@dataclass(slots=True)
class _TitleRecord:
    """整图标题的绘制意图；align 决定相对绘图区居中还是靠左。"""

    text: str
    align: TitleAlign = DEFAULT_TITLE_ALIGN
    size_px: float = DEFAULT_TITLE_SIZE
    color: Color = DEFAULT_TEXT_COLOR


@dataclass(slots=True)
class _AxisNameRecord:
    """轴名称的绘制意图；y 轴名称按文字种类竖排或旋转。"""

    text: str
    size_px: float = DEFAULT_AXIS_NAME_SIZE
    color: Color = DEFAULT_TEXT_COLOR
    rotate: bool = False


def _is_cjk_text(text: str) -> bool:
    """文字以中日韩字符为主时逐字竖排比旋转更自然。"""
    chars = [ch for ch in text if not ch.isspace()]
    if not chars:
        return False
    cjk = sum(
        "\u3040" <= ch <= "\u30ff"  # 日文假名
        or "\u3400" <= ch <= "\u9fff"  # 汉字（含扩展 A）
        or "\uac00" <= ch <= "\ud7af"  # 韩文
        or "\u3000" <= ch <= "\u303f"  # 中文标点
        for ch in chars
    )
    return cjk * 2 >= len(chars)


@dataclass(slots=True)
class _XLabelsRecord:
    """x 标签的绘制意图；xs 为绘图区坐标，缺省时优先用组中心。"""

    labels: list[str]
    xs: list[float] | None
    pos: XLabelPos = "content"
    rotation: XLabelRotation = "auto"


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
    y_name_x: float = 0.0  # y 轴名称（纵向排列）中心的画布 x
    y_name_y: float = 0.0  # y 轴名称中心的画布 y
    y_up_len: float = 0.0  # y 轴干线向上长度（名称纵向居中用）
    title_x: float = 0.0  # 标题绘制锚点的画布 x
    title_y: float = 0.0  # 标题绘制锚点的画布 y
    x_name_x: float = 0.0  # x 轴名称中心的画布 x
    x_name_y: float | None = None  # x 轴名称绘制锚点的画布 y
    legend_top_y: float = 0.0  # 顶部图例首行的画布 y
    x_label_y: float | None = None  # x 标签锚点的画布 y
    x_label_baseline: bool = False  # True: 标签底边锚定（写在基线之上）
    x_label_angle: float = 0.0  # 已解析的旋转角：正角顺时针，基线下标签取负角
    x_label_height: float = 0.0  # 标签块垂直占位（旋转后的投影高度）
    legend_bottom_y: float | None = None


def _format_tick(value: float) -> str:
    """刻度数字格式：整数不带小数点，小数去尾零。"""
    if abs(value - round(value)) < 1e-9:
        return str(round(value))
    return f"{value:g}"


def _skia_image(arr: NDArray[np.uint8]) -> skia.Image:
    """Numpy RGBA → skia Image。skia 的 numpy 互操作按 BGRA 解释通道，需先换序。"""
    return skia.Image.fromarray(np.ascontiguousarray(arr[:, :, [2, 1, 0, 3]]))


# 位图按 1:1 贴图（袜子已按输出倍率原生渲染），用最近邻避免二次重采样
_SAMPLING_NATIVE = skia.SamplingOptions()


def _nice_ticks(domain: tuple[float, float], *, max_ticks: int = 7) -> list[float]:
    """按 1/2/2.5/5×10^k 的整步长取刻度，取能放进 max_ticks 个的最小步长。

    domain 含 0 时 0 必为步长整数倍、因而必在刻度中；负区间同样按步长取到，
    避免含负值的值域出现"轴向下延伸但下方一个刻度都没有"的空段。
    """
    lo, hi = domain
    span = hi - lo
    if span <= 0:
        return [lo]
    mag = 10.0 ** math.floor(math.log10(span / 5))
    candidates = [mag * m for m in (1.0, 2.0, 2.5, 5.0)]
    candidates += [mag * 10.0 * m for m in (1.0, 2.0, 2.5, 5.0)]
    ticks: list[float] = []
    for step in candidates:
        start = math.ceil(lo / step - 1e-9) * step
        ticks = []
        v = start
        while v <= hi + 1e-9:
            ticks.append(round(v, 10))
            v += step
        if len(ticks) <= max_ticks:
            return ticks
    return ticks or [lo]


def _sock_top_center_x(leg: Leg, height_px: float) -> float:
    """袜口那一行腿轮廓的水平中心（设计坐标），供数值标签对齐袜口。

    腿素材本身是倾斜的，足底中心与袜口中心不在同一竖线上；按足底中心居中
    写数值会让标签明显偏离袜口。裸腿取腿顶端的轮廓中心。
    """
    h = round(height_px)
    row = 0 if h <= 0 else max(0, min(leg.height - h, leg.height - 1))
    row_img = min(round(row * leg.pixels_per_unit), leg.image.shape[0] - 1)
    cols = np.where(leg.image[row_img, :, 3] > 0)[0]
    if len(cols) == 0:
        return float(leg.foot_center_x)
    return float((cols[0] + cols[-1]) / 2 / leg.pixels_per_unit)


# 图例色块统一用同一条固定腿渲染，取其袜身中段的织物
_swatch_leg_cache: Leg | None = None


def _swatch_leg() -> Leg:
    global _swatch_leg_cache
    if _swatch_leg_cache is None:
        _swatch_leg_cache = LegLibrary(seed=0).get("leg_01")
    return _swatch_leg_cache


def _render_swatch(
    style: StockingStyle, size: int, seed: int, *, scale: float = 1.0
) -> NDArray[np.uint8]:
    """渲染该样式并裁取袜身中部的一小块织物，作为图例色块。

    scale > 1 时按该倍率渲染并裁出 size × scale 见方的色块，供 1:1 贴图使用。
    """
    leg = _swatch_leg()
    sh = round(leg.height * 0.55)
    img = render_stocking(leg, style, sh, seed=seed, scale=scale).image
    h, w = img.shape[:2]
    px = max(1, round(size * scale))
    # 袜身中段：袜区（底部 sh 行）内垂直居中的 px 行
    sock_h = round(sh * scale)
    top = (h - sock_h) + max(0, (sock_h - px) // 2)
    band = img[top : top + px]
    cols = np.where(band[:, :, 3].max(axis=0) > 0)[0]
    center = int((cols[0] + cols[-1]) // 2) if len(cols) else w // 2
    left = min(max(0, center - px // 2), max(0, w - px))
    out = np.zeros((px, px, 4), np.uint8)
    crop = band[:, left : left + px]
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
        axis_style: AxisStyle = DEFAULT_AXIS_STYLE,
        seed: int | None = None,
    ) -> None:
        """构造绘图区。

        extent_up / extent_down 为基线上、下各预留的像素高度；基线下方不留
        空间时基线贴住内容底部（x 标签等边距仍会另行留出）。
        axis_style 决定坐标轴与网格线是直线（"clean"，默认）还是手绘抖动
        （"handdrawn"）。
        """
        if width_px <= 0:
            raise ValueError(f"width_px 须为正数，得到 {width_px}")
        if axis_style not in ("clean", "handdrawn"):
            raise ValueError(f"axis_style 须为 'clean' 或 'handdrawn'，得到 {axis_style!r}")
        self._width_px = width_px
        self._extent_up = extent_up
        self._extent_down = extent_down
        self._background = background
        self._axis_style = axis_style
        self._rng = random.Random(DEFAULT_SEED if seed is None else seed)
        self._bars: list[_BarRecord] = []
        self._group_centers: list[float] = []
        self._l3_cursor = 0.0  # L3 方法的续排光标（最后一条腿的右缘）
        self._y_axis: _YAxisRecord | None = None
        self._x_labels: _XLabelsRecord | None = None
        self._title: _TitleRecord | None = None
        self._x_axis_name: _AxisNameRecord | None = None
        self._y_axis_name: _AxisNameRecord | None = None
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
        grid: bool = False,
    ) -> BarPlot:
        """添加 y 轴（含刻度数字）。ticks 缺省由 scale.domain 均匀取值生成。

        轴与网格的线条样式由构造参数 axis_style 决定（默认直线）。刻度按
        scale 映射到基线上下两侧：domain 含负值时干线向下延伸、下方刻度
        照常绘制，箭头仍在最上端。grid=True 时沿各刻度画横向虚线（浅色，
        压在腿与袜之下）。轴名称用 add_y_axis_name() 单独添加。
        """
        self._y_axis = _YAxisRecord(
            scale=scale,
            ticks=[float(v) for v in (ticks if ticks is not None else _nice_ticks(scale.domain))],
            grid=grid,
            seed=self._rng.getrandbits(32),
        )
        return self

    def add_y_axis_name(
        self,
        text: str,
        *,
        size_px: float = DEFAULT_AXIS_NAME_SIZE,
        color: Color = DEFAULT_TEXT_COLOR,
    ) -> BarPlot:
        """添加 y 轴名称：中日韩文字逐字竖排，其余文字旋转 90° 写在刻度数字左侧。"""
        self._y_axis_name = _AxisNameRecord(
            text=text,
            size_px=size_px,
            color=color,
            rotate=not _is_cjk_text(text),
        )
        return self

    def add_x_labels(
        self,
        labels: Sequence[str],
        *,
        xs: Sequence[float] | None = None,
        pos: XLabelPos = "content",
        rotation: XLabelRotation = "auto",
    ) -> BarPlot:
        """添加 x 轴标签，pos 决定标签位置，rotation 决定是否旋转。

        "content"（默认）画在全部内容最低点之下（含朝下腿与 y 轴向下延伸的
        部分），与基线解耦，没有下方内容时自然贴着基线下方；"auto" 紧贴
        基线、选没有柱子的一侧（下方无腿→基线下方，上方无腿→基线上方，
        两侧都有腿→退回 "content"）；"above" / "below" 强制写在基线上方 /
        下方，该侧有腿时会与腿重叠。

        rotation="auto"（默认）在相邻标签会互相压住时依次尝试 45°/60°/75°/
        90° 倾斜，选第一个不重叠的角度；传 0 禁用旋转，传固定角度（0–90）
        则始终按该角度倾斜。旋转方向随标签在基线上/下自动决定。

        xs 为绘图区坐标（足底中心基准），缺省时优先使用 add_bars 系列
        方法记录的组中心，否则沿绘图区宽度均分。
        """
        if pos not in ("content", "auto", "above", "below"):
            raise ValueError(f"pos 须为 'content'/'auto'/'above'/'below'，得到 {pos!r}")
        if xs is not None and len(xs) != len(labels):
            raise ValueError(f"xs 与 labels 长度不一致：{len(xs)} != {len(labels)}")
        if rotation != "auto" and not 0 <= float(rotation) <= 90:
            raise ValueError(f"rotation 须为 'auto' 或 0–90 的角度，得到 {rotation!r}")
        self._x_labels = _XLabelsRecord(
            labels=list(labels),
            xs=[float(v) for v in xs] if xs is not None else None,
            pos=pos,
            rotation=rotation,
        )
        return self

    def add_x_axis_name(
        self,
        text: str,
        *,
        size_px: float = DEFAULT_AXIS_NAME_SIZE,
        color: Color = DEFAULT_TEXT_COLOR,
    ) -> BarPlot:
        """添加 x 轴名称：横向居中写在 x 标签之下（底部图例之上）。"""
        self._x_axis_name = _AxisNameRecord(text=text, size_px=size_px, color=color)
        return self

    def add_title(
        self,
        text: str,
        *,
        align: TitleAlign = DEFAULT_TITLE_ALIGN,
        size_px: float = DEFAULT_TITLE_SIZE,
        color: Color = DEFAULT_TEXT_COLOR,
    ) -> BarPlot:
        """添加整图标题；align 缺省在绘图区上方水平居中。"""
        if align not in ("center", "left"):
            raise ValueError(f"align 须为 'center' 或 'left'，得到 {align!r}")
        self._title = _TitleRecord(text=text, align=align, size_px=size_px, color=color)
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

    # ------------------------------------------------------------------
    # L3 布局封装：间距 + 选腿
    # ------------------------------------------------------------------

    def _style_list(self, style: StyleSeq) -> list[StockingStyle]:
        """把样式参数归一为实例列表；空列表视为错误。"""
        return _normalize_style_seq(style)

    def _place_group(
        self,
        heights: Sequence[float],
        *,
        bar_gap: float,
        styles: Sequence[StockingStyle],
        legs: Sequence[Leg],
        side_for: Callable[[int], BarSide] | None = None,
    ) -> float:
        """从光标处向右排一组腿（按边缘空隙 bar_gap），返回组中心。

        光标推进到本组末尾右缘；同时把组中心记录进 _group_centers。
        styles 与 heights 等长，逐根取用。
        """
        if not heights:
            raise ValueError("heights 为空")
        if len(legs) != len(heights):
            raise ValueError(f"legs 与 heights 长度不一致：{len(legs)} != {len(heights)}")
        if len(styles) != len(heights):
            raise ValueError(f"styles 与 heights 长度不一致：{len(styles)} != {len(heights)}")
        cursor = self._l3_cursor
        first_left = cursor
        for i, (h, leg, style) in enumerate(zip(heights, legs, styles, strict=True)):
            side: BarSide = side_for(i) if side_for is not None else "up"
            self.add_bar(
                cursor + leg.foot_center_x,
                h,
                leg,
                style=style,
                side=side,
            )
            cursor += leg.width + bar_gap
        center = (first_left + (cursor - bar_gap)) / 2
        self._group_centers.append(center)
        self._l3_cursor = cursor - bar_gap
        return center

    def add_bars(
        self,
        heights_px: Sequence[float],
        *,
        bar_gap: float = DEFAULT_BAR_GAP,
        style: StyleSeq = DEFAULT_STOCKING_STYLE,
        legs: Sequence[Leg] | None = None,
        seed: int | None = None,
    ) -> BarPlot:
        """单序列：统一间距从左到右排开，自动按左、右、左、右……交替选腿。

        legs 可显式指定每根柱子的素材（长度须与 heights_px 一致，不参与
        循环）。style 为列表时按柱序循环取用。多次调用 L3 方法时从上一次
        内容的右缘续排。
        """
        heights = list(heights_px)
        if not heights:
            raise ValueError("heights_px 为空")
        if legs is None:
            legs = self._auto_legs(len(heights), seed=seed)
        elif len(legs) != len(heights):
            raise ValueError(f"legs 与 heights_px 长度不一致：{len(legs)} != {len(heights)}")
        self._advance_cursor(DEFAULT_GROUP_GAP)
        styles = _cycle_styles(self._style_list(style), len(heights))
        self._place_group(heights, bar_gap=bar_gap, styles=styles, legs=legs)
        return self

    def add_grouped_bars(
        self,
        heights_px: Sequence[Sequence[float]],
        *,
        bar_gap: float = DEFAULT_BAR_GAP,
        group_gap: float = DEFAULT_GROUP_GAP,
        style: StyleSeq = DEFAULT_STOCKING_STYLE,
        cycle: StyleCycle = "group",
        legs: Sequence[Leg] | None = None,
        seed: int | None = None,
    ) -> BarPlot:
        """(组数, 系列数) 的像素高度。

        组内用 bar_gap、组间用 group_gap，跨列按左、右、左、右……交替选腿。

        style 为列表时按 cycle 取用："group"（默认）按组内位置循环，组内
        第 i 根用 styles[i % len]，列表长度等于系列数时即"每系列一个样式"；
        "sequence" 按全部柱子的绘制顺序循环（组 0 第 0 根、组 0 第 1 根、
        组 1 第 0 根……）。legs 显式时按行优先展平，长度须等于总柱数。
        """
        groups = [list(g) for g in heights_px]
        if not groups:
            raise ValueError("heights_px 为空")
        total = sum(len(g) for g in groups)
        if legs is None:
            legs = self._auto_legs(total, seed=seed)
        elif len(legs) != total:
            raise ValueError(f"legs 与总柱数不一致：{len(legs)} != {total}")
        self._advance_cursor(group_gap)
        flat_styles = _cycle_styles(self._style_list(style), total)
        series = len(groups[0])
        cursor = 0
        for group in groups:
            if cycle == "sequence":
                group_styles = flat_styles[cursor : cursor + len(group)]
            else:
                # 组内位置循环：每组都从样式列表头部起算，与系列一一对应
                group_styles = flat_styles[:series]
            group_legs = legs[cursor : cursor + len(group)]
            self._place_group(group, bar_gap=bar_gap, styles=group_styles, legs=group_legs)
            cursor += len(group)
            self._l3_cursor += group_gap
        return self

    def add_paired_bars(
        self,
        heights_px: Sequence[tuple[float, float]],
        *,
        group_gap: float = DEFAULT_GROUP_GAP,
        style: StyleSeq = DEFAULT_STOCKING_STYLE,
        cycle: StyleCycle = "group",
        pairs: Sequence[tuple[Leg, Leg]] | None = None,
        seed: int | None = None,
    ) -> BarPlot:
        """每组恰好 2 个值：同组使用同一对素材，系列 0 左腿、系列 1 右腿。

        style 为列表时按 cycle 取用（"group" 默认：组内第 i 根取
        styles[i % len]；"sequence" 按全部柱子的绘制顺序循环）。pairs 缺省
        时自动选取不重复的素材对；显式时长度须与组数一致。组内间距用
        DEFAULT_BAR_GAP。
        """
        groups = [tuple(g) for g in heights_px]
        if not groups:
            raise ValueError("heights_px 为空")
        if pairs is None:
            lib = LegLibrary(seed=self._rng.getrandbits(32) if seed is None else seed)
            pair_list = lib.sample_pairs(len(groups))
        else:
            if len(pairs) != len(groups):
                raise ValueError(f"pairs 与组数不一致：{len(pairs)} != {len(groups)}")
            pair_list = [tuple(p) for p in pairs]
        self._advance_cursor(group_gap)
        flat_styles = _cycle_styles(self._style_list(style), 2 * len(groups))
        for g, (group, pair) in enumerate(zip(groups, pair_list, strict=True)):
            styles = flat_styles[2 * g : 2 * g + 2] if cycle == "sequence" else flat_styles[:2]
            self._place_group(group, bar_gap=DEFAULT_BAR_GAP, styles=styles, legs=list(pair))
            self._l3_cursor += group_gap
        return self

    def _auto_legs(self, n: int, *, seed: int | None) -> list[Leg]:
        """自动选腿：左、右、左、右……交替，素材对按 seed 伪随机。"""
        lib = LegLibrary(seed=self._rng.getrandbits(32) if seed is None else seed)
        return lib.alternate(n)

    def _advance_cursor(self, gap: float) -> None:
        """续排时光标与已有内容保持 group_gap 的边缘间距。"""
        if self._group_centers:
            self._l3_cursor += gap

    def _add_columns(
        self,
        slots: Sequence[Sequence[Sequence[_LegSpec]]],
        *,
        bar_gap: float,
        slot_gap: float,
        slots_px: Sequence[float],
        lead: float,
    ) -> list[list[list[_BarRecord]]]:
        """按槽位居中排布腿（L4 自适应布局专用），返回与 slots 同构的记录。

        槽 → 列 → 腿规格：列从左到右排开（列间 bar_gap），同一列的腿共享
        足底中心 x（镜像图的上下双腿）。每槽占宽 slots_px，腿在其中居中，
        槽中心记入 _group_centers 供 x 标签对齐。
        """
        records: list[list[list[_BarRecord]]] = []
        x = float(lead)
        for slot, slot_w in zip(slots, slots_px, strict=True):
            natural = sum(col[0].leg.width for col in slot) + (len(slot) - 1) * bar_gap
            cursor = x + (slot_w - natural) / 2
            slot_records: list[list[_BarRecord]] = []
            for column in slot:
                col_x = cursor + column[0].leg.foot_center_x
                col_records: list[_BarRecord] = []
                for spec in column:
                    before = len(self._bars)
                    self.add_bar(col_x, spec.height_px, spec.leg, style=spec.style, side=spec.side)
                    col_records.append(self._bars[before])
                slot_records.append(col_records)
                cursor += column[0].leg.width + bar_gap
            self._group_centers.append(x + slot_w / 2)
            records.append(slot_records)
            x += slot_w + slot_gap
        self._l3_cursor = x - slot_gap
        return records

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
        self._draw(canvas, layout, scale=scale)
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

    def _legend_layout(
        self, rec: _LegendRecord
    ) -> tuple[list[list[int]], list[float], float, list[list[str]]]:
        """图例分行结果：(行内项下标, 各行高, 带高, 每项折行文本)。

        单个标签超过一行宽时按词/字换行（最多 DEFAULT_LEGEND_MAX_LINES 行，
        仍放不下则末行省略）；ncol 指定时按等宽列折行，避免列错位。
        """
        line_h = DEFAULT_LEGEND_TEXT_SIZE * DEFAULT_LEGEND_LINE_FACTOR
        if rec.ncol is not None:
            col_w = max(
                DEFAULT_LEGEND_SWATCH + DEFAULT_LEGEND_TEXT_GAP + 1.0,
                (self._width_px - (rec.ncol - 1) * DEFAULT_LEGEND_ITEM_GAP) / rec.ncol,
            )
            label_max = max(1.0, col_w - DEFAULT_LEGEND_SWATCH - DEFAULT_LEGEND_TEXT_GAP)
        else:
            col_w = 0.0
            label_max = max(1.0, self._width_px - DEFAULT_LEGEND_SWATCH - DEFAULT_LEGEND_TEXT_GAP)
        lines_all = [
            wrap_text(
                label,
                max_width=label_max,
                size_px=DEFAULT_LEGEND_TEXT_SIZE,
                max_lines=DEFAULT_LEGEND_MAX_LINES,
            )
            for label, _ in rec.items
        ]
        widths: list[float] = []
        heights: list[float] = []
        for lines in lines_all:
            text_w = max(
                (measure_text(line, size_px=DEFAULT_LEGEND_TEXT_SIZE) for line in lines),
                default=0.0,
            )
            width = DEFAULT_LEGEND_SWATCH + DEFAULT_LEGEND_TEXT_GAP + text_w
            widths.append(width if rec.ncol is None else col_w)
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
                if row and row_w + extra > self._width_px:
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

    def _x_label_xs(self) -> list[float]:
        """X 标签锚点在绘图区坐标里的位置。"""
        rec = self._x_labels
        assert rec is not None  # 调用点已保证
        if rec.xs is not None:
            return rec.xs
        if len(rec.labels) == len(self._group_centers):
            return self._group_centers
        n = len(rec.labels)
        return [(i + 0.5) * self._width_px / n for i in range(n)]

    @staticmethod
    def _x_label_line_height() -> float:
        """X 标签单行占位高度（旋转包围盒计算用）。"""
        return DEFAULT_X_LABEL_SIZE * DEFAULT_LABEL_LINE_FACTOR

    def _x_labels_fit_horizontal(self, xs: Sequence[float], widths: Sequence[float]) -> bool:
        """水平排布时相邻标签是否互不重叠。"""
        order = sorted(range(len(xs)), key=lambda i: xs[i])
        return all(
            xs[b] - xs[a] >= (widths[a] + widths[b]) / 2 + DEFAULT_X_LABEL_ITEM_GAP
            for a, b in itertools.pairwise(order)
        )

    def _x_labels_fit_rotated(
        self, xs: Sequence[float], widths: Sequence[float], angle: float, line_h: float
    ) -> bool:
        """旋转 angle 度后相邻标签是否互不重叠。"""
        c = math.cos(math.radians(angle))
        s = math.sin(math.radians(angle))
        order = sorted(range(len(xs)), key=lambda i: xs[i])
        return all(
            xs[b] - xs[a] >= widths[b] * c + line_h * s + DEFAULT_X_LABEL_ITEM_GAP
            for a, b in itertools.pairwise(order)
        )

    def _x_label_fit(self, *, above: bool) -> tuple[float, float, float, float]:
        """解析 x 标签的旋转角与占位。

        返回 (带符号角度, 垂直占位高, 向左溢出, 向右溢出)。角度为
        "auto" 时逐级尝试 DEFAULT_X_LABEL_ROTATIONS，取第一个不重叠的；
        都放不下时用最大角度。标签在基线下方取负角、上方取正角。
        """
        rec = self._x_labels
        assert rec is not None  # 调用点已保证
        xs = self._x_label_xs()
        widths = [measure_text(label, size_px=DEFAULT_X_LABEL_SIZE) for label in rec.labels]
        line_h = self._x_label_line_height()
        if rec.rotation == "auto":
            angle = DEFAULT_X_LABEL_ROTATIONS[-1]
            for candidate in DEFAULT_X_LABEL_ROTATIONS:
                if candidate == 0.0:
                    fits = self._x_labels_fit_horizontal(xs, widths)
                else:
                    fits = self._x_labels_fit_rotated(xs, widths, candidate, line_h)
                if fits:
                    angle = candidate
                    break
        else:
            angle = float(rec.rotation)

        if angle == 0.0:
            height = line_h
            left = max((w / 2 - x for w, x in zip(widths, xs, strict=True)), default=0.0)
            right = max(
                (w / 2 - (self._width_px - x) for w, x in zip(widths, xs, strict=True)),
                default=0.0,
            )
            return 0.0, height, max(0.0, left), max(0.0, right)

        c = math.cos(math.radians(angle))
        s = math.sin(math.radians(angle))
        height = max((w * s + line_h * c for w in widths), default=line_h)
        if angle >= 89.999:
            # 竖排时按旋转后的字面高度居中，左右各占半行高
            left = max((line_h / 2 - x for x in xs), default=0.0)
            right = max((line_h / 2 - (self._width_px - x) for x in xs), default=0.0)
        elif above:
            # 上方标签向左上展开：左边多出字面高度，右边不越界
            left = max(
                (w * c + line_h * s - x for w, x in zip(widths, xs, strict=True)),
                default=0.0,
            )
            right = 0.0
        else:
            # 下方标签向左下展开：左边占文字宽，右边多出字面高度
            left = max((w * c - x for w, x in zip(widths, xs, strict=True)), default=0.0)
            right = max(
                (line_h * s - (self._width_px - x) for x in xs),
                default=0.0,
            )
        signed = angle if above else -angle
        return signed, height, max(0.0, left), max(0.0, right)

    def _layout(self) -> _Layout:
        eff_up, eff_down = self._effective_extents()
        axis = self._y_axis

        # y 轴左侧占位：[画布留白][y 轴名称(纵向)][刻度数字][间距][刻度线][干线]
        down_len = 0.0
        axis_x = 0.0
        plot_left = float(DEFAULT_PLOT_LEFT_PAD)
        y_name_x = 0.0
        tick_px: list[float] = []
        if axis is not None:
            tick_px = [axis.scale.to_px(v) for v in axis.ticks]
            down_len = max([0.0, *(-p for p in tick_px if p < 0)])
        left = float(DEFAULT_PLOT_LEFT_PAD)
        if self._y_axis_name is not None:
            name = self._y_axis_name
            name_w = (
                measure_text_height(name.text, size_px=name.size_px)
                if name.rotate
                else name.size_px
            )
            y_name_x = left + name_w / 2
            left += name_w + DEFAULT_AXIS_NAME_GAP
        if axis is not None:
            label_w = max(
                (
                    measure_text(_format_tick(v), size_px=DEFAULT_TICK_LABEL_SIZE)
                    for v in axis.ticks
                ),
                default=0.0,
            )
            axis_x = left + label_w + DEFAULT_TICK_LABEL_GAP + DEFAULT_TICK_SIZE
            plot_left = axis_x
        elif self._y_axis_name is not None:
            plot_left = left

        x_pos: Literal["above", "below", "content"] | None = None
        x_angle = 0.0
        x_height = 0.0
        x_left = 0.0
        x_right = 0.0
        if self._x_labels is not None and self._x_labels.labels:
            x_pos = self._resolve_x_label_pos()
            x_angle, x_height, x_left, x_right = self._x_label_fit(above=(x_pos == "above"))

        # 顶部带：标题 + 顶部图例；标签写在基线上方时若超出预留高度，补足顶部空间
        top_band = 0.0
        legend_top_y = 0.0
        if self._title is not None:
            top_band = DEFAULT_TITLE_INSET_Y + self._title.size_px * DEFAULT_TITLE_LINE_FACTOR
        if self._legend is not None and self._legend.loc == "top":
            _, _, legend_h, _ = self._legend_layout(self._legend)
            legend_top_y = top_band if self._title is not None else DEFAULT_LEGEND_MARGIN
            top_band = legend_top_y + legend_h + DEFAULT_LEGEND_MARGIN
        elif self._legend is None and self._title is None:
            top_band = 0.0
        if x_pos == "above":
            # 为旋转后的标签留出顶部空间，并保留与画布顶缘的呼吸间距
            top_band += max(0.0, x_height + 2 * DEFAULT_X_LABEL_GAP - eff_up)

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
        if self._x_axis_name is not None:
            x_name_y = bottom + DEFAULT_AXIS_NAME_GAP
            bottom = x_name_y + self._x_axis_name.size_px * DEFAULT_AXIS_NAME_LINE_FACTOR

        legend_bottom_y: float | None = None
        if self._legend is not None and self._legend.loc == "bottom":
            legend_bottom_y = bottom + DEFAULT_LEGEND_MARGIN
            bottom = legend_bottom_y + self._legend_layout(self._legend)[2]

        final_h = bottom + DEFAULT_BOTTOM_PAD
        # 旋转标签可能伸出绘图区左右缘：补画布边距，避免文字被裁
        plot_left += max(0.0, x_left - plot_left)
        plot_right = plot_left + self._width_px
        final_w = plot_right + max(DEFAULT_PLOT_RIGHT_PAD, x_right)

        # 标题与 x 轴名称比画布宽时对称扩宽：左溢出整体右移绘图区，右溢出补画布
        centered = [plot_left + self._width_px / 2] if self._x_axis_name is not None else []
        if self._title is not None:
            title_w = measure_text(self._title.text, size_px=self._title.size_px)
            if self._title.align == "center":
                title_x = plot_left + self._width_px / 2
                title_center = title_x
            else:
                title_x = plot_left
                title_center = title_x + title_w / 2
            centered.append(title_center)
        else:
            title_w = 0.0
            title_x = plot_left
        text_widths = (
            [measure_text(self._x_axis_name.text, size_px=self._x_axis_name.size_px)]
            if self._x_axis_name is not None
            else []
        )
        if self._title is not None:
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
        x_name_x = plot_left + self._width_px / 2

        y_up_len = max([0.0, eff_up, *tick_px])
        y_name_y = baseline + (max(eff_down, down_len) - y_up_len) / 2
        return _Layout(
            final_w=final_w,
            final_h=final_h,
            plot_left=plot_left,
            plot_right=plot_right,
            baseline_y=baseline,
            content_bottom=content_bottom,
            axis_x=axis_x,
            y_name_x=y_name_x,
            y_name_y=y_name_y,
            y_up_len=y_up_len,
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

    def _resolve_x_label_pos(self) -> Literal["above", "below", "content"]:
        """把 pos 参数解析为具体位置；"auto" 选没有柱子的一侧。"""
        rec = self._x_labels
        assert rec is not None  # 调用点已保证
        if rec.pos != "auto":
            return rec.pos
        has_up = any(b.side == "up" for b in self._bars)
        has_down = any(b.side == "down" for b in self._bars)
        if not has_up:
            return "above"
        if not has_down:
            return "below"
        return "content"

    def _draw(self, canvas: Canvas, layout: _Layout, *, scale: float = 1.0) -> None:
        self._draw_grid(canvas, layout)
        self._draw_baseline(canvas, layout)
        self._draw_bars(canvas, layout, scale=scale)
        self._draw_y_axis(canvas, layout)
        self._draw_axis_names(canvas, layout)
        self._draw_title(canvas, layout)
        self._draw_legend(canvas, layout, scale=scale)
        self._draw_x_labels(canvas, layout)
        self._draw_value_labels(canvas, layout)

    def _draw_grid(self, canvas: Canvas, layout: _Layout) -> None:
        axis = self._y_axis
        if axis is None or not axis.grid:
            return
        rng = random.Random(axis.seed)
        dash, gap = DEFAULT_GRID_DASH
        wobble = DEFAULT_WOBBLE * 0.3 if self._axis_style == "handdrawn" else 0.0
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
            wobble=DEFAULT_WOBBLE if self._axis_style == "handdrawn" else 0.0,
            seed=self._baseline_seed,
        )

    def _draw_bars(self, canvas: Canvas, layout: _Layout, *, scale: float = 1.0) -> None:
        sc = canvas.skia_canvas()
        for bar in self._bars:
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

    def _draw_y_axis(self, canvas: Canvas, layout: _Layout) -> None:
        axis = self._y_axis
        if axis is None:
            return
        rng = random.Random(axis.seed)
        t_px = [axis.scale.to_px(v) for v in axis.ticks]
        up_items = [(p, _format_tick(v)) for v, p in zip(axis.ticks, t_px, strict=True) if p >= 0]
        down_items = [(-p, _format_tick(v)) for v, p in zip(axis.ticks, t_px, strict=True) if p < 0]
        eff_up, eff_down = self._effective_extents()
        up_len = max([0.0, eff_up, *t_px])
        down_zone = eff_down if any(b.side == "down" for b in self._bars) else 0.0
        down_len = max([0.0, *(-p for p in t_px if p < 0), down_zone])
        sketch_axis(
            canvas,
            direction="up",
            x=layout.axis_x,
            y=layout.baseline_y,
            length=up_len,
            ticks=up_items,
            arrow=True,
            wobble=DEFAULT_WOBBLE if self._axis_style == "handdrawn" else 0.0,
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
                wobble=DEFAULT_WOBBLE if self._axis_style == "handdrawn" else 0.0,
                seed=rng.getrandbits(32),
            )

    def _draw_axis_names(self, canvas: Canvas, layout: _Layout) -> None:
        y_name = self._y_axis_name
        if y_name is not None and y_name.text:
            if y_name.rotate:
                # 拉丁等文字按常规旋转 90°，自下而上阅读
                draw_text(
                    canvas,
                    y_name.text,
                    layout.y_name_x,
                    layout.y_name_y,
                    size_px=y_name.size_px,
                    color=y_name.color,
                    anchor=("center", "middle"),
                    rotation=-90,
                )
            else:
                # 中日韩文字逐字竖排（契合书写习惯），在轴干线上下之间居中
                cell = y_name.size_px * DEFAULT_AXIS_NAME_LINE_FACTOR
                start = layout.y_name_y - len(y_name.text) * cell / 2
                for i, ch in enumerate(y_name.text):
                    draw_text(
                        canvas,
                        ch,
                        layout.y_name_x,
                        start + (i + 0.5) * cell,
                        size_px=y_name.size_px,
                        color=y_name.color,
                        anchor=("center", "middle"),
                    )
        x_name = self._x_axis_name
        if x_name is not None and layout.x_name_y is not None:
            draw_text(
                canvas,
                x_name.text,
                layout.x_name_x,
                layout.x_name_y,
                size_px=x_name.size_px,
                color=x_name.color,
                anchor=("center", "top"),
            )

    def _draw_title(self, canvas: Canvas, layout: _Layout) -> None:
        if self._title is None:
            return
        draw_text(
            canvas,
            self._title.text,
            layout.title_x,
            layout.title_y,
            size_px=self._title.size_px,
            color=self._title.color,
            anchor=("center" if self._title.align == "center" else "left", "top"),
        )

    def _draw_legend(self, canvas: Canvas, layout: _Layout, *, scale: float = 1.0) -> None:
        rec = self._legend
        if rec is None:
            return
        idx_rows, row_heights, _, lines_all = self._legend_layout(rec)
        if rec.loc == "top":
            y = layout.legend_top_y
        else:
            assert layout.legend_bottom_y is not None  # _layout 保证已填
            y = layout.legend_bottom_y
        sc = canvas.skia_canvas()
        line_h = DEFAULT_LEGEND_TEXT_SIZE * DEFAULT_LEGEND_LINE_FACTOR
        col_w = 0.0
        if rec.ncol is not None:
            col_w = max(
                DEFAULT_LEGEND_SWATCH + DEFAULT_LEGEND_TEXT_GAP + 1.0,
                (self._width_px - (rec.ncol - 1) * DEFAULT_LEGEND_ITEM_GAP) / rec.ncol,
            )
        for row, row_h in zip(idx_rows, row_heights, strict=True):
            widths: list[float] = []
            for i in row:
                text_w = max(
                    (measure_text(line, size_px=DEFAULT_LEGEND_TEXT_SIZE) for line in lines_all[i]),
                    default=0.0,
                )
                widths.append(
                    col_w
                    if rec.ncol is not None
                    else DEFAULT_LEGEND_SWATCH + DEFAULT_LEGEND_TEXT_GAP + text_w
                )
            row_w = sum(widths) + DEFAULT_LEGEND_ITEM_GAP * (len(row) - 1)
            x = layout.plot_left + (0.0 if rec.ncol is not None else (self._width_px - row_w) / 2)
            for i, item_w in zip(row, widths, strict=True):
                label_lines = lines_all[i]
                swatch_y = y + (row_h - DEFAULT_LEGEND_SWATCH) / 2
                swatch = _skia_image(
                    _render_swatch(
                        rec.items[i][1],
                        DEFAULT_LEGEND_SWATCH,
                        rec.seed + i,
                        scale=scale,
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
                text_h = len(label_lines) * line_h
                text_top = y + (row_h - text_h) / 2
                for j, line in enumerate(label_lines):
                    draw_text(
                        canvas,
                        line,
                        x + DEFAULT_LEGEND_SWATCH + DEFAULT_LEGEND_TEXT_GAP,
                        text_top + (j + 0.5) * line_h,
                        size_px=DEFAULT_LEGEND_TEXT_SIZE,
                        anchor=("left", "middle"),
                    )
                x += item_w + DEFAULT_LEGEND_ITEM_GAP
            y += row_h + DEFAULT_LEGEND_ROW_GAP

    def _draw_x_labels(self, canvas: Canvas, layout: _Layout) -> None:
        rec = self._x_labels
        if rec is None or layout.x_label_y is None:
            return
        xs = self._x_label_xs()
        above = layout.x_label_baseline
        angle = layout.x_label_angle
        line_h = self._x_label_line_height()
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
                    anchor=anchor,
                )
                continue
            # 竖排时把旋转后的文字块在锚点处左右居中
            pivot = px
            if abs(angle) >= 89.999:
                pivot += line_h / 2 if angle > 0 else -line_h / 2
            draw_text(
                canvas,
                label,
                pivot,
                layout.x_label_y,
                size_px=DEFAULT_X_LABEL_SIZE,
                anchor=("right", "bottom" if above else "top"),
                rotation=angle,
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
            # 对齐袜口中心而非足底中心：倾斜的腿两者不在同一竖线上
            x = (
                layout.plot_left
                + bar.x
                - bar.leg.foot_center_x
                + _sock_top_center_x(bar.leg, bar.height_px)
            )
            draw_text(
                canvas,
                bar.value_label,
                x,
                y,
                size_px=DEFAULT_VALUE_LABEL_SIZE,
                anchor=anchor,
            )
