"""L2 绘图的数据形状：类型别名与内部记录。

只描述“画什么”，不做任何计算；记录都是 frozen dataclass，
由上层构造后交给布局与绘制模块使用。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from stockchart.color import Color
from stockchart.defaults import (
    DEFAULT_AXIS_NAME_SIZE,
    DEFAULT_TEXT_COLOR,
    DEFAULT_TITLE_ALIGN,
    DEFAULT_TITLE_SIZE,
)
from stockchart.legs import Leg
from stockchart.plot.scale import Scale
from stockchart.stocking import StockingStyle
from stockchart.text import FontSpec

type BarSide = Literal["up", "down"]
type LegendLoc = Literal["top", "bottom"]
type XLabelPos = Literal["content", "auto", "above", "below"]
type StyleCycle = Literal["group", "sequence"]
type AxisStyle = Literal["clean", "handdrawn"]
type XLabelRotation = float | Literal["auto"]
type TitleAlign = Literal["center", "left"]
type Pairing = Literal["auto", "none", "group", "global"]


@dataclass(slots=True)
class BarRecord:
    """一根柱子的绘制意图，几何在 render 时统一计算。

    Attributes:
        x: 足底中心在绘图区坐标中的 x。
        height_px: 丝袜高度（设计像素）；<= 0 为裸腿。
        leg: 腿素材。
        style: 已解析的丝袜样式。
        side: 腿朝上或朝下。
        seed: 该柱纹理的随机源。
        value_label: 数值标签文本；None 表示不画。
    """

    x: float
    height_px: float
    leg: Leg
    style: StockingStyle
    side: BarSide
    seed: int
    value_label: str | None = None


@dataclass(slots=True)
class LegSpec:
    """一根腿的完整绘制规格，由 L4 计算后交给 `_add_columns` 摆放。

    Attributes:
        leg: 腿素材。
        height_px: 丝袜高度（设计像素）。
        side: 腿朝上或朝下。
        style: 已解析的丝袜样式。
    """

    leg: Leg
    height_px: float
    side: BarSide
    style: StockingStyle


@dataclass(slots=True)
class YAxisRecord:
    """y 轴的绘制意图；ticks 为数据值，绘制时经 scale 换算为像素。

    Attributes:
        scale: 数据值到像素的换算。
        ticks: 要绘制的刻度值。
        grid: 是否画水平网格线。
        seed: 轴与网格抖动的随机源。
        font: 刻度数字字体；None 用平台默认链。
    """

    scale: Scale
    ticks: list[float]
    grid: bool
    seed: int
    font: FontSpec | None = None


@dataclass(slots=True)
class TitleRecord:
    """整图标题的绘制意图。

    Attributes:
        text: 标题文本。
        align: 相对绘图区居中或靠左。
        size_px: 字号（设计像素）。
        color: 文字颜色。
        font: 标题字体；None 用平台默认链。
    """

    text: str
    align: TitleAlign = DEFAULT_TITLE_ALIGN
    size_px: float = DEFAULT_TITLE_SIZE
    color: Color = DEFAULT_TEXT_COLOR
    font: FontSpec | None = None


@dataclass(slots=True)
class AxisNameRecord:
    """轴名称的绘制意图。

    Attributes:
        text: 轴名称。
        size_px: 字号（设计像素）。
        color: 文字颜色。
        rotate: True 时整体旋转 90°；False 时逐字竖排。
        font: 轴名称字体；None 用平台默认链。
    """

    text: str
    size_px: float = DEFAULT_AXIS_NAME_SIZE
    color: Color = DEFAULT_TEXT_COLOR
    rotate: bool = False
    font: FontSpec | None = None


@dataclass(slots=True)
class XLabelsRecord:
    """x 标签的绘制意图。

    Attributes:
        labels: 标签文本。
        xs: 标签锚点在绘图区坐标中的位置；None 表示按组中心或均分自动决定。
        pos: "content" / "auto" / "above" / "below"。
        rotation: "auto" 或固定角度（度）。
        font: 标签字体；None 用平台默认链。
    """

    labels: list[str]
    xs: list[float] | None
    pos: XLabelPos = "content"
    rotation: XLabelRotation = "auto"
    font: FontSpec | None = None


@dataclass(slots=True)
class LegendRecord:
    """图例的绘制意图；样式已归一为实例。

    Attributes:
        items: (标签, 样式) 列表。
        ncol: 指定列数；None 表示按宽度自动换行。
        loc: "top" 或 "bottom"。
        seed: 色块纹理的随机源。
        font: 图例文字字体；None 用平台默认链。
    """

    items: list[tuple[str, StockingStyle]]
    ncol: int | None
    loc: LegendLoc
    seed: int
    font: FontSpec | None = None


@dataclass(slots=True)
class PlotLayout:
    """一次 render 的整体几何，全部为设计像素。

    Attributes:
        final_w: 最终画布宽。
        final_h: 最终画布高。
        plot_left: 绘图区（用户坐标 x=0）的画布 x。
        plot_right: 绘图区右缘。
        baseline_y: 基线的画布 y。
        content_bottom: 全部腿与轴内容的最低点。
        axis_x: y 轴干线的画布 x。
        y_name_x: y 轴名称中心的画布 x。
        y_name_y: y 轴名称中心的画布 y。
        y_up_len: y 轴干线向上长度。
        y_name_span: y 轴名称可用的垂直长度（轴干线上下总跨度）。
        title_x: 标题锚点的画布 x。
        title_y: 标题锚点的画布 y。
        x_name_x: x 轴名称中心的画布 x。
        x_name_y: x 轴名称锚点的画布 y；None 表示无 x 轴名称。
        legend_top_y: 顶部图例首行的画布 y。
        x_label_y: x 标签锚点的画布 y；None 表示无标签。
        x_label_baseline: True 时标签底边锚定（写在基线之上）。
        x_label_angle: 已解析的旋转角；正角顺时针，基线下标签取负角。
        x_label_height: 标签块垂直占位（旋转后的投影高度）。
        legend_bottom_y: 底部图例首行的画布 y；None 表示无底部图例。
    """

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
    y_name_span: float = 0.0  # y 轴名称可用垂直长度（干线上下总跨度）
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


@dataclass(slots=True, frozen=True)
class RenderInput:
    """一次 render 所需的全部输入，布局与绘制共用同一份。

    Attributes:
        bars: 已摆放好的柱子记录。
        extent_up: 基线上方为柱子预留的高度（设计像素）。
        extent_down: 基线下方为柱子预留的高度（设计像素）。
        width_px: 绘图区宽度（设计像素）。
        group_centers: 各组中心在绘图区坐标中的 x。
        axis_style: 坐标轴风格。
        baseline_seed: 基线与坐标轴的随机源。
        font: 全图默认字体；None 用平台默认链。
        y_axis: y 轴记录；None 表示不画。
        y_axis_name: y 轴名称记录。
        x_axis_name: x 轴名称记录。
        x_labels: x 标签记录。
        title: 标题记录。
        legend: 图例记录。
    """

    bars: list[BarRecord]
    extent_up: float
    extent_down: float
    width_px: int
    group_centers: list[float]
    axis_style: AxisStyle
    baseline_seed: int
    font: FontSpec | None
    y_axis: YAxisRecord | None
    y_axis_name: AxisNameRecord | None
    x_axis_name: AxisNameRecord | None
    x_labels: XLabelsRecord | None
    title: TitleRecord | None
    legend: LegendRecord | None
