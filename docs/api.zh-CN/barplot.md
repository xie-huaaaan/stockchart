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
