# L2 — 自由柱状图

← [API 索引](index.md) · 相关：[L1 — 渲染原语](rendering.md) · [L3 — 布局封装](layout.md)

```python
@dataclass(slots=True, frozen=True)
class Scale:
    """线性比例尺：数据值 ↔ 基线上方像素。柱高与轴刻度共用同一个 Scale 即可保证一致。

    Attributes:
        domain: (值下限, 值上限)，须下限 < 上限。
        range_px: (像素下限, 像素上限)，基线为 0、向上为正；须下限 < 上限。

    Raises:
        ValueError: domain 或 range_px 的下限不小于上限。
    """

    domain: tuple[float, float]
    range_px: tuple[float, float]

    def to_px(self, value: float) -> float:
        """数据值 → 像素。"""

    def from_px(self, px: float) -> float:
        """像素 → 数据值。"""

    @classmethod
    def fit(cls, values: Sequence[float], extent_px: float, *, margin: float = 0.0) -> Scale:
        """构造 [min(values), max(values)] → [0, extent_px] 的比例尺，margin 两端留边。

        Raises:
            ValueError: values 为空、含非有限数值、extent_px 不是正数、
                margin 为负，或 values 全部相同。
        """
```

```python
class BarPlot:
    """自由柱状图：以 X 轴为基线，腿的位置与丝袜高度全部由调用者按设计像素指定。

    `width_px` 是绘图区宽度；`extent_up` / `extent_down` 只在基线上下为腿预留
    高度，不含标题、轴名称、刻度数字、x 标签、图例等边缘；腿高于预留时柱区
    自动扩张，轴、文字与图例另占空间。

    Args:
        width_px: 绘图区宽度，也是腿与坐标使用的 x 范围。
        extent_up: 基线以上为腿预留的设计像素高度；不含标题、图例等边缘。
        extent_down: 基线以下为向下腿预留的设计像素高度；不含 x 标签等边缘。
        background: 画布背景色。
        axis_style: "clean"（默认）画直线坐标轴与网格；"handdrawn" 使用
            seed 控制的手绘抖动。
        seed: 随机源；影响默认的柱纹理、基线与手绘抖动。

    Raises:
        ValueError: width_px 不是正数、extent_up / extent_down 为负数，或
            axis_style 不是允许值。
    """

    def __init__(
        self,
        width_px: int,
        *,
        extent_up: int = DEFAULT_Y_EXTENT,
        extent_down: int = 0,
        background: Color = DEFAULT_BACKGROUND,
        axis_style: Literal["clean", "handdrawn"] = "clean",
        seed: int | None = None,
    ) -> None: ...

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
        """在 x 处贴一条腿：x 是足底中心的目标位置（腿宽不一，按脚对齐才均匀）。

        Args:
            height_px: 丝袜高度（设计像素）。小于等于 0 为裸腿。
            leg: 腿素材；side="down" 时素材竖直翻转、脚贴基线朝下。
            style: StockingStyle 实例或 STYLES 预设名。

        Raises:
            ValueError: style 是未知预设名、side 不是 "up" / "down"，或
                x / height_px 不是有限数值。
        """

    def add_y_axis(
        self,
        scale: Scale,
        *,
        ticks: Sequence[float] | None = None,
        grid: bool = False,
    ) -> BarPlot:
        """添加 y 轴（含刻度数字）。ticks 缺省由 scale.domain 按整步长生成。

        轴线与网格样式由构造参数 axis_style 决定。刻度按 scale 映射到基线
        上下两侧：domain 含负值时干线向下延伸、下方刻度照常绘制，箭头仍在
        最上端；刻度高于 extent_up 时画布顶部自动扩展以容纳轴顶与刻度数字。
        grid=True 时沿各刻度画横向虚线（浅色，压在腿与袜之下）。
        轴名称用 add_y_axis_name() 单独添加。

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
    ) -> BarPlot:
        """添加 x 轴标签。pos 决定标签写在哪儿，rotation 决定是否倾斜：

        - "content"（默认）：全部内容最低点之下（含朝下腿与 y 轴向下延伸的
          部分），与基线解耦——没有下方内容时自然贴着基线下方；
        - "auto"：紧贴基线、选没有柱子的一侧（上方无腿→基线上方，下方无
          腿→基线下方，两侧都有腿→退回 "content"）；
        - "above" / "below"：强制写在基线上方 / 下方，该侧有腿时会与腿重叠。

        rotation="auto"（默认）在相邻标签会互相压住时依次尝试 45°/60°/
        75°/90°，取第一个不重叠的角度；传 0 禁止旋转，传固定角度（0–90）
        始终按该角度倾斜。旋转方向随标签在基线上/下自动决定，画布也会
        补足对应的上/下与左右边距。

        xs 缺省沿宽度均分；与 add_bars 系列方法配合时自动对齐组中心。

        Raises:
            ValueError: pos / rotation 不合法、xs 与 labels 长度不一致，或
                xs 含非有限数值。
        """

    def add_title(
        self,
        text: str,
        *,
        align: Literal["center", "left"] = "center",
        size_px: float = DEFAULT_TITLE_SIZE,
        color: Color = DEFAULT_TEXT_COLOR,
    ) -> BarPlot:
        """添加整图标题（单行）。

        默认在绘图区上方水平居中（中心对齐柱子所占范围，而不是画布）；
        align="left" 靠绘图区左缘。标题比画布宽时自动对称扩宽画布，不折行、
        不裁字。标题占据的顶部高度自动计入布局，图例仍画在标题下方。
        """

    def add_x_axis_name(
        self,
        text: str,
        *,
        size_px: float = DEFAULT_AXIS_NAME_SIZE,
        color: Color = DEFAULT_TEXT_COLOR,
    ) -> BarPlot:
        """添加 x 轴名称：横向居中写在 x 标签之下（底部图例之上）。

        没有 x 标签时直接写在内容最低点之下。名称过长时扩宽画布，不裁字。
        """

    def add_y_axis_name(
        self,
        text: str,
        *,
        size_px: float = DEFAULT_AXIS_NAME_SIZE,
        color: Color = DEFAULT_TEXT_COLOR,
    ) -> BarPlot:
        """添加 y 轴名称，写在刻度数字左侧。

        中日韩文字逐字竖排（契合书写习惯）；拉丁、数字等文字整体旋转 90°
        自下而上阅读。纵向以 y 轴上下延展范围居中；占用左侧边距，不影响
        绘图区坐标。
        """

    def add_legend(
        self,
        items: Sequence[tuple[str, StyleLike]],
        *,
        ncol: int | None = None,
        loc: Literal["top", "bottom"] = "top",
    ) -> BarPlot:
        """添加图例：每项为织物纹理色块 + 文字，色块取该样式袜身中部的织物。

        loc="top"（默认）画在标题下方、绘图区上方，"bottom" 画在最底部；
        ncol 为一行几项，缺省自动：单行放得下就单行，否则按宽度换行。
        ncol 指定时各列等宽。单个标签超过一行可用宽度时自动折成多行
        （最多 3 行，仍放不下则末行省略），ncol 下按列宽折行，避免列错位。
        图例占据的高度与折行后的行高自动计入布局。
        """

    def render(self, *, scale: float = DEFAULT_OUTPUT_SCALE) -> Canvas:
        """渲染。scale 为输出像素密度，不影响设计像素坐标。"""

    def save(self, path: str | Path, *, scale: float = DEFAULT_OUTPUT_SCALE) -> Path:
        """渲染并直接写出 PNG。"""

    def to_pil(self, *, scale: float = DEFAULT_OUTPUT_SCALE) -> Image:
        """渲染并直接导出 PIL Image。"""
```
