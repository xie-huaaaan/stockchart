"""L2 自由柱状图：BarPlot。

BarPlot 采用“记录意图 → render 时统一布局 → 固定顺序绘制”的三段式；
本模块同时包含挂在 BarPlot 上的 L3 布局封装方法（add_bars 等）。
所有布局坐标都是设计像素，`render(scale=)` 才统一放大到输出像素。
布局计算与绘制实现在同包的 layout / draw 模块。
"""

from __future__ import annotations

import math
import random
from collections.abc import Callable, Sequence
from pathlib import Path

import numpy as np
from numpy.typing import NDArray
from PIL import Image as PilImage

from stockchart.canvas import Canvas
from stockchart.color import Color
from stockchart.defaults import (
    DEFAULT_AXIS_NAME_SIZE,
    DEFAULT_AXIS_STYLE,
    DEFAULT_BACKGROUND,
    DEFAULT_BAR_GAP,
    DEFAULT_GROUP_GAP,
    DEFAULT_OUTPUT_SCALE,
    DEFAULT_STOCKING_STYLE,
    DEFAULT_TEXT_COLOR,
    DEFAULT_TITLE_ALIGN,
    DEFAULT_TITLE_SIZE,
    DEFAULT_Y_EXTENT,
)
from stockchart.legs import Leg
from stockchart.library import LegLibrary
from stockchart.plot.draw import draw_all
from stockchart.plot.layout import compute_layout, legend_layout
from stockchart.plot.scale import Scale, nice_ticks
from stockchart.plot.styles import (
    check_cycle,
    check_pairing,
    cycle_styles,
    normalize_style_seq,
    resolve_style,
    select_legs_for_groups,
)
from stockchart.plot.types import (
    AxisNameRecord,
    AxisStyle,
    BarRecord,
    BarSide,
    LegendLoc,
    LegendRecord,
    LegSpec,
    Pairing,
    PlotLayout,
    RenderInput,
    StyleCycle,
    TitleAlign,
    TitleRecord,
    XLabelPos,
    XLabelRotation,
    XLabelsRecord,
    YAxisRecord,
)
from stockchart.stocking import (
    StockingStyle,
    StyleLike,
    StyleSeq,
)
from stockchart.text import (
    FontSpec,
)


def _is_cjk_text(text: str) -> bool:
    """判断文字是否以中日韩字符为主。

    Args:
        text: 待判断文本；空白字符忽略。

    Returns:
        CJK 字符数不少于非空白字符一半时返回 True。
    """
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


class BarPlot:
    """自由柱状图：以 X 轴为基线，腿的位置与丝袜高度全部由调用者按设计像素指定。

    `width_px` 是绘图区宽度；`extent_up` / `extent_down` 只在基线上下为腿预留
    高度，不含标题、轴名称、刻度数字、x 标签、图例等边缘。轴、文字、图例与
    标题的空间在 render 时另行计算，所以最终画布通常大于
    `width_px × (extent_up + extent_down)`；腿高于预留时柱区会自动扩张。

    Args:
        width_px: 绘图区宽度（设计像素），也是腿与坐标使用的 x 范围。
        extent_up: 基线以上为腿预留的设计像素高度；不含标题、图例等边缘。
        extent_down: 基线以下为向下腿预留的设计像素高度；不含 x 标签等边缘。
        background: 画布背景色。
        axis_style: "clean" 画直线坐标轴与网格；"handdrawn" 使用 seed
            控制的手绘抖动。
        font: 全图默认字体（家族名、字体文件路径或候选列表）；各 add_*
            方法与数值标签不另指定 font 时使用，None 用平台默认链。
        seed: 随机源；影响默认的柱纹理、基线与手绘抖动，不传则每次随机。

    腿高于 extent_up / extent_down 时，柱区会自动向上/向下扩张；轴、标题、
    标签与图例另占空间，不计入这两个值。

    Raises:
        ValueError: width_px 不是正数、extent_up / extent_down 为负数，或
            axis_style 不是允许值。

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
        font: FontSpec | None = None,
        seed: int | None = None,
    ) -> None:
        if width_px <= 0:
            raise ValueError(f"width_px 须为正数，得到 {width_px}")
        if extent_up < 0 or extent_down < 0:
            raise ValueError(f"extent_up / extent_down 须 >= 0，得到 {extent_up} / {extent_down}")
        if axis_style not in ("clean", "handdrawn"):
            raise ValueError(f"axis_style 须为 'clean' 或 'handdrawn'，得到 {axis_style!r}")
        self._width_px = width_px
        self._extent_up = extent_up
        self._extent_down = extent_down
        self._background = background
        self._axis_style: AxisStyle = axis_style
        self._font = font
        self._rng = random.Random(seed)
        self._bars: list[BarRecord] = []
        self._group_centers: list[float] = []
        self._l3_cursor = 0.0  # L3 方法的续排光标（最后一条腿的右缘）
        self._y_axis: YAxisRecord | None = None
        self._x_labels: XLabelsRecord | None = None
        self._title: TitleRecord | None = None
        self._x_axis_name: AxisNameRecord | None = None
        self._y_axis_name: AxisNameRecord | None = None
        self._legend: LegendRecord | None = None
        # 基线的抖动 seed 在构造期固定，保证多次 render 结果一致
        self._baseline_seed = self._rng.getrandbits(32)

    # ------------------------------------------------------------------
    # L2 公开接口
    # ------------------------------------------------------------------

    @property
    def width_px(self) -> int:
        """绘图区宽度（腿与坐标使用的 x 范围）。

        Returns:
            宽度（设计像素）；不等于最终画布宽度。
        """
        return self._width_px

    def _resolve_font(self, font: FontSpec | None) -> FontSpec | None:
        """解析元素级字体的两级继承链：元素 font → 全图 font → None。

        Args:
            font: add_* 方法传入的元素级字体。

        Returns:
            元素级字体非空时原样返回，否则回落到构造时的全图默认。
        """
        return font if font is not None else self._font

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
        """在 x 处贴一条腿。

        x 是足底中心的目标位置：腿宽不一，按脚对齐才均匀。

        Args:
            x: 足底中心在绘图区坐标中的 x（设计像素）。
            height_px: 丝袜高度（设计像素）；<= 0 为裸腿。腿本身始终按
                完整 leg.height 绘制。
            leg: 腿素材。
            style: StockingStyle 实例或 STYLES 预设名。
            side: "up" 贴基线向上；"down" 竖直翻转、脚贴基线朝下。
            seed: 该柱纹理随机源；缺省时由构造时的 seed 派生，保证整图可复现。

        Returns:
            self，便于链式调用。

        Raises:
            ValueError: style 是未知的预设名、side 不是 "up" / "down"，或
                x / height_px 不是有限数值。
        """
        if side not in ("up", "down"):
            raise ValueError(f"side 须为 'up' 或 'down'，得到 {side!r}")
        if not math.isfinite(float(x)) or not math.isfinite(float(height_px)):
            raise ValueError(f"x / height_px 须为有限数值，得到 {x!r} / {height_px!r}")
        bar_seed = self._rng.getrandbits(32) if seed is None else seed
        self._bars.append(
            BarRecord(
                x=float(x),
                height_px=float(height_px),
                leg=leg,
                style=resolve_style(style),
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
        font: FontSpec | None = None,
    ) -> BarPlot:
        """添加 y 轴（含刻度数字）。

        轴与网格的线条样式由构造参数 axis_style 决定。刻度按 scale 映射到
        基线上下两侧：domain 含负值时干线向下延伸、下方刻度照常绘制，箭头
        仍在最上端。轴名称用 `add_y_axis_name()` 单独添加。

        Args:
            scale: 数据值到像素的换算；刻度位置与下方延伸都来自它。
            ticks: 要绘制的刻度值；None 时由 scale.domain 自动生成。
            grid: 是否沿各刻度画横向虚线（压在腿与袜之下）。
            font: 刻度数字字体；None 继承全图默认。

        Returns:
            self，便于链式调用。

        Raises:
            ValueError: ticks 含非有限数值。
        """
        tick_values = [float(v) for v in (ticks if ticks is not None else nice_ticks(scale.domain))]
        if any(not math.isfinite(v) for v in tick_values):
            raise ValueError("ticks 含非有限数值（NaN / Infinity）")
        self._y_axis = YAxisRecord(
            scale=scale,
            ticks=tick_values,
            grid=grid,
            seed=self._rng.getrandbits(32),
            font=self._resolve_font(font),
        )
        return self

    def add_y_axis_name(
        self,
        text: str,
        *,
        size_px: float = DEFAULT_AXIS_NAME_SIZE,
        color: Color = DEFAULT_TEXT_COLOR,
        font: FontSpec | None = None,
    ) -> BarPlot:
        """添加 y 轴名称。

        中日韩文字逐字竖排，其余文字旋转 90° 写在刻度数字左侧；名称长于
        轴干线时自动续列/折行，并沿轴干线整体垂直居中。

        Args:
            text: 轴名称。
            size_px: 字号（设计像素）。
            color: 文字颜色。
            font: 轴名称字体；None 继承全图默认。

        Returns:
            self，便于链式调用。
        """
        self._y_axis_name = AxisNameRecord(
            text=text,
            size_px=size_px,
            color=color,
            rotate=not _is_cjk_text(text),
            font=self._resolve_font(font),
        )
        return self

    def add_x_labels(
        self,
        labels: Sequence[str],
        *,
        xs: Sequence[float] | None = None,
        pos: XLabelPos = "content",
        rotation: XLabelRotation = "auto",
        font: FontSpec | None = None,
    ) -> BarPlot:
        """添加 x 轴标签。

        位置与旋转规则：

        - "content"（默认）画在全部内容最低点之下（含朝下腿与 y 轴向下延伸
          的部分），与基线解耦；没有下方内容时自然贴着基线下方。
        - "auto" 紧贴基线、选没有柱子的一侧；两侧都有腿时退回 "content"。
        - "above" / "below" 强制写在基线上方 / 下方，该侧有腿时会重叠。
        - rotation="auto" 在相邻标签会互相压住时依次尝试 45°/60°/75°/90°；
          传 0 禁用旋转；传固定角度（0–90）则始终按该角度倾斜。

        Args:
            labels: 标签文本。
            xs: 标签锚点在绘图区坐标中的位置（足底中心基准）；None 时优先
                使用 `add_bars` 系列记录的组中心，否则沿绘图区宽度均分。
            pos: 标签位置策略。
            rotation: "auto" 或 0–90 的固定角度。
            font: 标签字体；None 继承全图默认。

        Returns:
            self，便于链式调用。

        Raises:
            ValueError: pos 不合法、xs 与 labels 长度不一致、xs 含非有限
                数值，或 rotation 不在允许范围。
        """
        if pos not in ("content", "auto", "above", "below"):
            raise ValueError(f"pos 须为 'content'/'auto'/'above'/'below'，得到 {pos!r}")
        if xs is not None and len(xs) != len(labels):
            raise ValueError(f"xs 与 labels 长度不一致：{len(xs)} != {len(labels)}")
        if xs is not None and any(not math.isfinite(float(v)) for v in xs):
            raise ValueError("xs 含非有限数值（NaN / Infinity）")
        if rotation != "auto" and not 0 <= float(rotation) <= 90:
            raise ValueError(f"rotation 须为 'auto' 或 0–90 的角度，得到 {rotation!r}")
        self._x_labels = XLabelsRecord(
            labels=list(labels),
            xs=[float(v) for v in xs] if xs is not None else None,
            pos=pos,
            rotation=rotation,
            font=self._resolve_font(font),
        )
        return self

    def add_x_axis_name(
        self,
        text: str,
        *,
        size_px: float = DEFAULT_AXIS_NAME_SIZE,
        color: Color = DEFAULT_TEXT_COLOR,
        font: FontSpec | None = None,
    ) -> BarPlot:
        """添加 x 轴名称，横向居中写在 x 标签之下（底部图例之上）。

        Args:
            text: 轴名称。
            size_px: 字号（设计像素）。
            color: 文字颜色。
            font: 轴名称字体；None 继承全图默认。

        Returns:
            self，便于链式调用。
        """
        self._x_axis_name = AxisNameRecord(
            text=text,
            size_px=size_px,
            color=color,
            font=self._resolve_font(font),
        )
        return self

    def add_title(
        self,
        text: str,
        *,
        align: TitleAlign = DEFAULT_TITLE_ALIGN,
        size_px: float = DEFAULT_TITLE_SIZE,
        color: Color = DEFAULT_TEXT_COLOR,
        font: FontSpec | None = None,
    ) -> BarPlot:
        """添加整图标题。

        Args:
            text: 标题文本。
            align: "center" 在绘图区上方居中；"left" 与绘图区左缘对齐。
            size_px: 字号（设计像素）。
            color: 文字颜色。
            font: 标题字体；None 继承全图默认。

        Returns:
            self，便于链式调用。

        Raises:
            ValueError: align 不是 "center" 或 "left"。
        """
        if align not in ("center", "left"):
            raise ValueError(f"align 须为 'center' 或 'left'，得到 {align!r}")
        self._title = TitleRecord(
            text=text,
            align=align,
            size_px=size_px,
            color=color,
            font=self._resolve_font(font),
        )
        return self

    def add_legend(
        self,
        items: Sequence[tuple[str, StyleLike]],
        *,
        ncol: int | None = None,
        loc: LegendLoc = "top",
        font: FontSpec | None = None,
    ) -> BarPlot:
        """添加图例。

        每项为真实渲染的织物纹理色块 + 文字；色块取自该样式袜身中部。
        图例占据的高度自动计入布局。

        Args:
            items: (标签, 样式) 列表；样式可为 StockingStyle 或预设名。
            ncol: 一行几项；None 表示单行放得下就单行，否则按宽度换行。
            loc: "top" 画在标题下方、绘图区上方；"bottom" 画在最底部。
            font: 图例文字字体；None 继承全图默认。

        Returns:
            self，便于链式调用；items 为空时直接返回。

        Raises:
            ValueError: ncol < 1、loc 不合法，或样式预设名不存在。
        """
        if ncol is not None and ncol < 1:
            raise ValueError(f"ncol 须 >= 1，得到 {ncol}")
        if loc not in ("top", "bottom"):
            raise ValueError(f"loc 须为 'top' 或 'bottom'，得到 {loc!r}")
        if not items:
            return self
        self._legend = LegendRecord(
            items=[(label, resolve_style(st)) for label, st in items],
            ncol=ncol,
            loc=loc,
            seed=self._rng.getrandbits(32),
            font=self._resolve_font(font),
        )
        return self

    # ------------------------------------------------------------------
    # L3 布局封装：间距 + 选腿
    # ------------------------------------------------------------------

    def _style_list(self, style: StyleSeq) -> list[StockingStyle]:
        """把样式参数归一为非空的实例列表。

        Args:
            style: 单个样式或样式序列。

        Returns:
            StockingStyle 列表。

        Raises:
            ValueError: 序列为空或含未知预设名。
        """
        return normalize_style_seq(style)

    def _place_group(
        self,
        heights: Sequence[float],
        *,
        bar_gap: float,
        styles: Sequence[StockingStyle],
        legs: Sequence[Leg],
        side_for: Callable[[int], BarSide] | None = None,
    ) -> float:
        """从当前光标处向右排一组腿，并返回组中心。

        按腿边缘之间的 bar_gap 推进；同时把组中心记入 `_group_centers`，
        供 x 标签对齐。

        Args:
            heights: 每根腿的丝袜高度（设计像素）。
            bar_gap: 相邻腿边缘之间的空隙。
            styles: 已解析的样式，与 heights 等长。
            legs: 腿素材，与 heights 等长。
            side_for: 按索引返回腿朝向；None 时全部朝上。

        Returns:
            本组中心在绘图区坐标中的 x。

        Raises:
            ValueError: heights 为空，或 legs/styles 与 heights 长度不一致。
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
        paired: Pairing = "auto",
        legs: Sequence[Leg] | None = None,
        seed: int | None = None,
    ) -> BarPlot:
        """单序列：统一间距从左到右排开，自动交替选腿。

        legs 可显式指定每根柱的素材（长度须与 heights_px 一致，不参与循环，
        此时 paired 忽略）。style 为列表时按柱序循环取用。多次调用 L3 方法
        时从上一次内容的右缘续排。

        Args:
            heights_px: 每根柱的丝袜高度（设计像素）。
            bar_gap: 相邻腿边缘之间的空隙。
            style: 单个样式或样式列表。
            paired: 选腿配对策略；"auto" 在单序列下等价于 "none"。
            legs: 显式指定腿素材；None 时自动选取。
            seed: 自动选腿的随机源；None 时由构造时的 seed 派生。

        Returns:
            self，便于链式调用。

        Raises:
            ValueError: heights_px 为空、legs 长度不符、自动选腿时 paired
                不合法，或样式列表为空/含未知预设。
        """
        heights = list(heights_px)
        if not heights:
            raise ValueError("heights_px 为空")
        if legs is None:
            check_pairing(paired)
            seed_value = self._rng.getrandbits(32) if seed is None else seed
            sizes = [1] * len(heights)
            rows = select_legs_for_groups(sizes, paired=paired, seed=seed_value)
            legs = [leg for row in rows for leg in row]
        elif len(legs) != len(heights):
            raise ValueError(f"legs 与 heights_px 长度不一致：{len(legs)} != {len(heights)}")
        self._advance_cursor(DEFAULT_GROUP_GAP)
        styles = cycle_styles(self._style_list(style), len(heights))
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
        paired: Pairing = "auto",
        legs: Sequence[Leg] | None = None,
        seed: int | None = None,
    ) -> BarPlot:
        """按 (组数, 系列数) 的像素高度排布分组柱状图。

        组内用 bar_gap、组间用 group_gap；跨列按左、右、左、右……交替选腿。

        Args:
            heights_px: 二维高度表；每行一组，组内每列一个系列。
            bar_gap: 组内相邻腿边缘之间的空隙。
            group_gap: 相邻组之间的空隙。
            style: 单个样式或样式列表。
            cycle: "group" 按组内位置循环；"sequence" 按全部柱子的绘制顺序循环。
            paired: 选腿配对策略；"auto" 单系列用 "none"、多系列用 "global"。
            legs: 显式腿素材，按行优先展平；None 时自动选取。
            seed: 自动选腿的随机源；None 时由构造时的 seed 派生。

        Returns:
            self，便于链式调用。

        Raises:
            ValueError: heights_px 为空、含空组、各组系列数不一致、legs 长度
                不符、自动选腿时 paired 不合法、cycle 不合法，或样式列表
                为空/含未知预设。
        """
        groups = [list(g) for g in heights_px]
        if not groups:
            raise ValueError("heights_px 为空")
        if any(not group for group in groups):
            raise ValueError("heights_px 存在空组")
        series = len(groups[0])
        if any(len(group) != series for group in groups):
            counts = sorted({len(group) for group in groups})
            raise ValueError(f"各组系列数须一致，得到 {counts}")
        check_cycle(cycle)
        total = sum(len(g) for g in groups)
        if legs is None:
            check_pairing(paired)
            seed_value = self._rng.getrandbits(32) if seed is None else seed
            rows = select_legs_for_groups(
                [len(group) for group in groups], paired=paired, seed=seed_value
            )
            legs = [leg for row in rows for leg in row]
        elif len(legs) != total:
            raise ValueError(f"legs 与总柱数不一致：{len(legs)} != {total}")
        self._advance_cursor(group_gap)
        flat_styles = cycle_styles(self._style_list(style), total)
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

        Args:
            heights_px: 每组的 (左腿高度, 右腿高度)。
            group_gap: 相邻组之间的空隙。
            style: 单个样式或样式列表。
            cycle: "group" 按组内位置循环；"sequence" 按全部柱子的绘制顺序循环。
            pairs: 显式素材对，长度须等于组数；None 时自动选取。
            seed: 自动选对的随机源；None 时由构造时的 seed 派生。

        Returns:
            self，便于链式调用。

        Raises:
            ValueError: heights_px 为空、某组不是恰好 2 个值、pairs 长度/形状
                不符、cycle 不合法，或样式列表为空/含未知预设。
        """
        groups = [tuple(g) for g in heights_px]
        if not groups:
            raise ValueError("heights_px 为空")
        if any(len(group) != 2 for group in groups):
            raise ValueError("add_paired_bars 每组须恰好 2 个值")
        check_cycle(cycle)
        if pairs is None:
            lib = LegLibrary(seed=self._rng.getrandbits(32) if seed is None else seed)
            pair_list = lib.sample_pairs(len(groups))
        else:
            if len(pairs) != len(groups):
                raise ValueError(f"pairs 与组数不一致：{len(pairs)} != {len(groups)}")
            if any(len(pair) != 2 for pair in pairs):
                raise ValueError("pairs 中每项须恰好包含 2 条腿")
            pair_list = [tuple(p) for p in pairs]
        self._advance_cursor(group_gap)
        flat_styles = cycle_styles(self._style_list(style), 2 * len(groups))
        for g, (group, pair) in enumerate(zip(groups, pair_list, strict=True)):
            styles = flat_styles[2 * g : 2 * g + 2] if cycle == "sequence" else flat_styles[:2]
            self._place_group(group, bar_gap=DEFAULT_BAR_GAP, styles=styles, legs=list(pair))
            self._l3_cursor += group_gap
        return self

    def _advance_cursor(self, gap: float) -> None:
        """续排前把光标与已有内容拉开指定间距。

        Args:
            gap: 与已有内容右缘之间的空隙；尚无内容时不推进。
        """
        if self._group_centers:
            self._l3_cursor += gap

    def _add_columns(
        self,
        slots: Sequence[Sequence[Sequence[LegSpec]]],
        *,
        bar_gap: float,
        slot_gap: float,
        slots_px: Sequence[float],
        lead: float,
    ) -> list[list[list[BarRecord]]]:
        """按槽位居中排布腿，返回与 slots 同构的柱记录（L4 自适应布局专用）。

        槽 → 列 → 腿规格：列从左到右排开（列间 bar_gap），同一列的腿共享
        足底中心 x（镜像图的上下双腿）。每槽占宽 slots_px，腿在其中居中；
        槽中心记入 `_group_centers` 供 x 标签对齐。

        Args:
            slots: 槽 → 列 → 腿规格的嵌套结构。
            bar_gap: 同槽相邻列之间的空隙。
            slot_gap: 相邻槽之间的空隙。
            slots_px: 每个槽的宽度，与 slots 等长。
            lead: 第一个槽的左缘 x。

        Returns:
            与 slots 同构的 `BarRecord` 列表。
        """
        records: list[list[list[BarRecord]]] = []
        x = float(lead)
        for slot, slot_w in zip(slots, slots_px, strict=True):
            natural = sum(col[0].leg.width for col in slot) + (len(slot) - 1) * bar_gap
            cursor = x + (slot_w - natural) / 2
            slot_records: list[list[BarRecord]] = []
            for column in slot:
                col_x = cursor + column[0].leg.foot_center_x
                col_records: list[BarRecord] = []
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
        """计算布局并绘制整张图。

        Args:
            scale: 输出像素密度（1 = 设计尺寸，默认 2）。只影响输出分辨率与
                纹理细节，不改变设计像素布局。

        Returns:
            绘制完成的 Canvas；尺寸为 round(final_w × scale) ×
            round(final_h × scale)。

        Raises:
            ValueError: scale 不是正的有限数。
        """
        if not math.isfinite(scale) or scale <= 0:
            raise ValueError(f"scale 须为正数，得到 {scale}")
        inp = self._render_input()
        layout = compute_layout(inp)
        canvas = Canvas(
            round(layout.final_w * scale),
            round(layout.final_h * scale),
            background=self._background,
        )
        canvas._skia_canvas().scale(scale, scale)  # pyright: ignore[reportPrivateUsage]
        draw_all(canvas, layout, inp, scale=scale)
        return canvas

    def save(self, path: str | Path, *, scale: float = DEFAULT_OUTPUT_SCALE) -> Path:
        """渲染并写出 PNG。

        Args:
            path: 输出路径，父目录须已存在。
            scale: 输出像素密度。

        Returns:
            实际写出的路径。
        """
        return self.render(scale=scale).save(path)

    def to_pil(self, *, scale: float = DEFAULT_OUTPUT_SCALE) -> PilImage.Image:
        """渲染并导出 PIL Image。

        Args:
            scale: 输出像素密度。

        Returns:
            RGBA 模式的 PIL Image。
        """
        return self.render(scale=scale).to_pil()

    def to_numpy(self, *, scale: float = DEFAULT_OUTPUT_SCALE) -> NDArray[np.uint8]:
        """渲染并导出 NumPy 数组。

        Args:
            scale: 输出像素密度。

        Returns:
            (H, W, 4) uint8 RGBA 数组，H / W 为输出像素。
        """
        return self.render(scale=scale).to_numpy()

    # ------------------------------------------------------------------
    # 布局与绘制
    # ------------------------------------------------------------------

    def _render_input(self) -> RenderInput:
        """收集一次渲染所需的全部状态。

        Returns:
            布局与绘制共用的输入记录。
        """
        return RenderInput(
            bars=self._bars,
            extent_up=self._extent_up,
            extent_down=self._extent_down,
            width_px=self._width_px,
            group_centers=self._group_centers,
            axis_style=self._axis_style,
            baseline_seed=self._baseline_seed,
            font=self._font,
            y_axis=self._y_axis,
            y_axis_name=self._y_axis_name,
            x_axis_name=self._x_axis_name,
            x_labels=self._x_labels,
            title=self._title,
            legend=self._legend,
        )

    def _layout(self) -> PlotLayout:
        """计算整张图的最终几何。

        Returns:
            所有元素位置与最终画布尺寸（设计像素）。
        """
        return compute_layout(self._render_input())

    def _legend_layout(
        self, rec: LegendRecord
    ) -> tuple[list[list[int]], list[float], float, list[list[str]]]:
        """计算图例的分行、折行与整体高度。

        Args:
            rec: 图例记录。

        Returns:
            `(行内项下标, 各行高, 图例带总高, 每项折行文本)`。
        """
        return legend_layout(rec, self._width_px)
