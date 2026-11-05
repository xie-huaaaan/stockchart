# L2 — 自由柱状图

← [API 索引](index.md) · 相关：[L1 — 渲染原语](rendering.md) · [L3 — 布局封装](layout.md)

```python
@dataclass(slots=True, frozen=True)
class Scale:
    """线性比例尺：数据值 ↔ 基线上方像素。

    柱高与轴刻度共用同一个 Scale 即可保证一致。

    Attributes:
        domain: (值下限, 值上限)，须下限 < 上限。
        range_px: (像素下限, 像素上限)，以基线为 0、向上为正；负像素表示
            基线下方，且须下限 < 上限。

    Raises:
        ValueError: domain 或 range_px 的下限不小于上限。
    """

    domain: tuple[float, float]
    range_px: tuple[float, float]

    def to_px(self, value: float) -> float:
        """把数据值换算为基线相对的像素。

        Args:
            value: 数据值。

        Returns:
            对应的像素值；向上为正。
        """

    def from_px(self, px: float) -> float:
        """把基线相对的像素换算为数据值。

        Args:
            px: 像素值；向上为正。

        Returns:
            对应的数据值。
        """

    @classmethod
    def fit(cls, values: Sequence[float], extent_px: float, *, margin: float = 0.0) -> Scale:
        """构造覆盖给定值域的比例尺。

        Args:
            values: 数据值序列；不能为空且不能全部相同。
            extent_px: 映射到的像素高度，须为正数；range_px 为 (0, extent_px)。
            margin: 两侧留边比例；domain 每端向外扩 (max − min) × margin。

        Returns:
            新的 Scale。

        Raises:
            ValueError: values 为空、含非有限数值、extent_px 不是正数、
                margin 为负，或 values 全部相同。
        """
```

```python
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
        axis_style: Literal["clean", "handdrawn"] = "clean",
        font: FontSpec | None = None,
        seed: int | None = None,
    ) -> None: ...

    @property
    def width_px(self) -> int:
        """绘图区宽度（腿与坐标使用的 x 范围）。

        Returns:
            宽度（设计像素）；不等于最终画布宽度。
        """

    def add_bar(
        self,
        x: float,
        height_px: float,
        leg: Leg,
        *,
        style: StockingStyle | str = DEFAULT_STOCKING_STYLE,
        side: Literal["up", "down"] = "up",
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

    def add_columns(
        self,
        slots: Sequence[Sequence[Sequence[LegSpec]]],
        *,
        bar_gap: float,
        slot_gap: float,
        slots_px: Sequence[float],
        lead: float,
    ) -> list[list[list[BarRecord]]]:
        """按槽位居中排布腿，返回与 slots 同构的柱记录。

        槽 → 列 → 腿规格：列从左到右排开（列间 bar_gap），同一列的腿共享
        足底中心 x（镜像图的上下双腿）。每槽占宽 slots_px，腿在其中居中；
        槽中心记入组中心列表，供后续 `add_x_labels()` 对齐。

        槽宽与腿的摆法由调用方算好——本方法只负责摆腿、记组中心，不推断
        布局；不需要自适应槽宽时用 `add_bar()` 逐根贴即可。

        Args:
            slots: 槽 → 列 → 腿规格的嵌套结构。
            bar_gap: 同槽相邻列之间的空隙。
            slot_gap: 相邻槽之间的空隙。
            slots_px: 每个槽的宽度，与 slots 等长。
            lead: 第一个槽的左缘 x。

        Returns:
            与 slots 同构的 `BarRecord` 列表。
        """

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

    def add_x_labels(
        self,
        labels: Sequence[str],
        *,
        xs: Sequence[float] | None = None,
        pos: Literal["content", "auto", "above", "below"] = "content",
        rotation: float | Literal["auto"] = "auto",
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

    def add_title(
        self,
        text: str,
        *,
        align: Literal["center", "left"] = "center",
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

    def add_legend(
        self,
        items: Sequence[tuple[str, StyleLike]],
        *,
        ncol: int | None = None,
        loc: Literal["top", "bottom"] = "top",
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

    def save(self, path: str | Path, *, scale: float = DEFAULT_OUTPUT_SCALE) -> Path:
        """渲染并写出 PNG。

        Args:
            path: 输出路径，父目录须已存在。
            scale: 输出像素密度。

        Returns:
            实际写出的路径。
        """

    def to_pil(self, *, scale: float = DEFAULT_OUTPUT_SCALE) -> Image:
        """渲染并导出 PIL Image。

        Args:
            scale: 输出像素密度。

        Returns:
            RGBA 模式的 PIL Image。
        """

    def to_numpy(self, *, scale: float = DEFAULT_OUTPUT_SCALE) -> np.ndarray:
        """渲染并导出 NumPy 数组。

        Args:
            scale: 输出像素密度。

        Returns:
            (H, W, 4) uint8 RGBA 数组，H / W 为输出像素。
        """
```

## 绘制记录与布局结果

`BarPlot` 记录的是“画什么”，几何在 render 时统一计算。下面这些数据类型是它的
输入输出形状：`BarRecord` / `LegSpec` 用于摆腿，其余是标题、轴、标签、图例等
元素的绘制意图；`PlotLayout` 与 `RenderInput` 分别是布局阶段的产物与输入。

```python
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
    """一根腿的完整绘制规格，由调用方计算后交给 `add_columns` 摆放。

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
    plot_left: float
    plot_right: float
    baseline_y: float
    content_bottom: float
    axis_x: float = 0.0
    y_name_x: float = 0.0
    y_name_y: float = 0.0
    y_up_len: float = 0.0
    y_name_span: float = 0.0
    title_x: float = 0.0
    title_y: float = 0.0
    x_name_x: float = 0.0
    x_name_y: float | None = None
    legend_top_y: float = 0.0
    x_label_y: float | None = None
    x_label_baseline: bool = False
    x_label_angle: float = 0.0
    x_label_height: float = 0.0
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
```

## 最小示例

```python
from stockchart import BarPlot, Scale

plot = BarPlot(1200)
plot.add_grouped_bars([[300], [500], [400]], style="black_sheer")
plot.add_x_labels(["A", "B", "C"])
plot.add_y_axis(Scale((0, 500), (0, 500)))
plot.add_title("自由排版")
plot.save("freeform.png")
```
