# L4 — bar() 与 mirror_bar()

← [API 索引](index.md) · 相关：[L4 — 数据输入](data-input.md) · [L3 — 布局封装](layout.md)

## L4 参数透传

`bar` / `mirror_bar` 只保留图表语义参数；当前层不消耗、需要传给 [BarPlot](barplot.md) 或
`add_*` 的选项通过 `**options` 接收。选项集中定义在 `ChartOptions`：

```python
class ChartOptions(TypedDict, total=False):
    """L4 透传给下层的可选参数；键名与 L2 接口保持一致。"""

    axis_style: Literal["clean", "handdrawn"]
    background: Color
    bar_gap: float
    group_gap: float
    grid: bool
    ticks: Sequence[float] | None
    x_label_pos: Literal["content", "auto", "above", "below"]
    x_label_rotation: float | Literal["auto"]
    title_align: Literal["center", "left"]
    title_size_px: float
    axis_name_size_px: float
    legend_loc: Literal["top", "bottom"]
    legend_ncol: int | None
```

| 选项 | 默认 | 去向 |
| --- | --- | --- |
| `axis_style` | `"clean"` | `BarPlot(axis_style=)` |
| `background` | `DEFAULT_BACKGROUND` | `BarPlot(background=)` |
| `bar_gap` | `DEFAULT_BAR_GAP`（28） | 组内腿间距 |
| `group_gap` | 一维 28 / 二维 120 | 组间距 |
| `grid` | `False` | `add_y_axis(grid=)` |
| `ticks` | `None`（自动整步长刻度） | `add_y_axis(ticks=)` |
| `x_label_pos` | `bar`→`"content"`，`mirror_bar`→`"auto"` | `add_x_labels(pos=)` |
| `x_label_rotation` | `"auto"` | `add_x_labels(rotation=)` |
| `title_align` | `"center"` | `add_title(align=)` |
| `title_size_px` | `DEFAULT_TITLE_SIZE`（52） | `add_title(size_px=)` |
| `axis_name_size_px` | `DEFAULT_AXIS_NAME_SIZE`（30） | 两个轴名字号 |
| `legend_loc` | `"top"` | `add_legend(loc=)` |
| `legend_ncol` | `None`（自动） | `add_legend(ncol=)` |

未知键在运行时报 `TypeError` 并列出可用选项；静态类型由 `TypedDict` 检查。
`axis_style` / `grid` / `x_label_pos` 等旧关键字仍可照常传入，只是不再出现在
函数签名里。

## L4 一行出图

```python
def bar(
    data: DataInput,
    *,
    labels: Sequence[str] | None = None,
    series_labels: Sequence[str] | None = None,
    title: str | None = None,
    xlabel: str | None = None,
    ylabel: str | None = None,
    style: StyleSeq = DEFAULT_STOCKING_STYLE,
    cycle: Literal["auto", "group", "sequence"] = "auto",
    paired: bool = True,
    value_labels: bool = False,
    max_fill: float = 0.8,
    min_fill: float = 0.1,
    y_extent: int = DEFAULT_Y_EXTENT,
    width_px: int | None = None,
    seed: int | None = None,
    **options: Unpack[ChartOptions],
) -> BarPlot:
    """全朝上的柱状图：自动完成数据 → 丝袜高度映射、选腿与布局，
    返回布局完毕的 BarPlot（可直接 .save() / .render()，也可继续手工微调）。

    自动绘制 y 轴与基线（默认直线，axis_style="handdrawn" 改为手绘抖动）；
    labels 传入时 x 标签自动与各组对齐，过长时自动倾斜避让；画布宽缺省时
    按腿、间距与标签宽度自适应。图例标签超过画布宽时自动折行。
    labels 传给 x 标签，series_labels 传给图例——后者区分"系列"（每组的
    第几根腿），前者区分"组"。

    Args:
        data: 支持一维/二维序列、numpy 数组、dict、pandas 风格表对象与
            PlotData；DataFrame 的 index/columns 会自动成为 x 标签与系列名。
            完整列表见[数据输入](data-input.md)。
        labels: 每组（无分组时每根柱）一个标签；缺省用数据里推断的标签。
        series_labels: 每系列一个名字，传入即自动生成图例（marker 为各系列
            样式的织物色块）；缺省用数据里推断的系列名。仅二维数据可用，
            一维数据传入抛 ValueError。
        title: 整图标题，默认在绘图区上方水平居中；title_align="left" 可改左对齐。
        xlabel: x 轴名称，写在 x 标签下方。
        ylabel: y 轴名称，写在刻度数字左侧（中日韩文字竖排，其余旋转）。
        style: 单个样式，或样式列表——循环方式由 cycle 决定。
        cycle: 样式列表的循环方式："group" 按组内位置（组内第 i 根用
            styles[i % len]，列表长度等于系列数时即"每系列一个样式"）；
            "sequence" 按全部柱子的绘制顺序循环；"auto"（默认）一维数据
            取 "sequence"（即每根柱按顺序取样式）、二维数据取 "group"。
            二维数据下 "sequence" 与 series_labels 无法对应固定的系列样式，
            同时传入抛 ValueError。
        paired: 仅当数据恰好 2 系列时生效（默认 True）：每组使用同一对素材，
            系列 0 左腿、系列 1 右腿；其余系列数时忽略此参数。
        value_labels: True 时在袜口上方手写数值。
        max_fill: 最大值映射到 y_extent 的比例（默认 0.8）。
        min_fill: 仅当数据含负值时启用（默认 0.1），见下。
        y_extent: 基线上方预留的像素高度。
        width_px: 画布宽；缺省按腿数、间距与标签宽度自适应；图例在固定
            宽度内自动折行。
        options: 透传给下层的可选项，见 `ChartOptions` 表（grid、axis_style、
            legend_loc、bar_gap 等）。

    数据 → 丝袜高度（基线对应的数据值默认 0）:
        - 全部数据为 0: 全部裸腿。
        - 无负值: height = v / max × max_fill × y_extent，0 值即裸腿。
        - 含负值: 整个值域 [min, max] 线性压缩到 [min_fill, max_fill]。
          此时 0 值的腿带一段丝袜、y 轴 0 刻度悬在丝袜中间某处——这是为完整
          保留大小关系所做的既定取舍。全负数据同规则：值越大丝袜越高。
    """


def mirror_bar(
    data: DataInput,
    *,
    mode: Literal["single", "both"] = "single",
    labels: Sequence[str] | None = None,
    series_labels: Sequence[str] | None = None,
    title: str | None = None,
    xlabel: str | None = None,
    ylabel: str | None = None,
    style: StyleSeq = DEFAULT_STOCKING_STYLE,
    cycle: Literal["auto", "group", "sequence"] = "auto",
    paired: bool = True,
    value_labels: bool = False,
    max_abs_fill: float = 0.8,
    y_extent: int = DEFAULT_Y_EXTENT,
    width_px: int | None = None,
    seed: int | None = None,
    **options: Unpack[ChartOptions],
) -> BarPlot:
    """正负镜像柱状图：正值画基线上方腿，负值画下方翻转腿（脚贴基线）。

    Args:
        data: 语义同 bar()，支持完全相同的数据格式。
        mode: "single" 只画数据侧的腿；"both" 上下都画，数据侧穿丝袜、
            另一侧裸腿。
        labels: 每组（无分组时每根柱）一个标签；缺省用数据里推断的标签。
        series_labels: 语义同 bar()。
        title: 整图标题，默认居中。
        xlabel: x 轴名称。
        ylabel: y 轴名称。
        style: 语义同 bar()。
        cycle: 语义同 bar()。
        paired: 语义同 bar()。
        value_labels: True 时手写数值，上方腿写在袜口上方、下方腿写在袜口下方。
        max_abs_fill: 最大绝对值映射到 y_extent 的比例（默认 0.8）。
        y_extent: 基线上方预留的像素高度。
        width_px: 画布宽；缺省自适应。
        options: 语义同 bar()。x_label_pos 默认 "auto"：镜像图常有一侧全空，
            会把标签贴到没有腿的一侧的基线旁（如全负数据标签在基线上方）；
            两侧都有腿（正负混合或 mode="both"）时退回 "content"，画在全部
            内容最低点之下。

    规则:
        - 比例 = max_abs_fill × y_extent / max|v|，正负同比例。
        - 0 视为 +0: "single" 下画一条朝上裸腿；"both" 下上下均画裸腿（上为数据侧）。
        - 下方空间: "single" 仅在存在负值时保留；"both" 始终保留。
    """
```

## 默认值集中定义

所有 `DEFAULT_*` 常量集中放在 `src/stockchart/defaults.py`：`DEFAULT_Y_EXTENT`（760）、
`DEFAULT_BAR_GAP`（28）、`DEFAULT_GROUP_GAP`（120）、`DEFAULT_OUTPUT_SCALE`、背景色、墨色、
文字色、`DEFAULT_AXIS_STYLE`（clean）、抖动幅度、字号（刻度 26 / x 标签 30 / 标题 52 /
轴名 30 / 图例 28 / 数值标签 26）、`DEFAULT_TITLE_ALIGN`（center）、轴名间距与行高、
x 标签避让角度、图例折行行数与行高、图例色块尺寸与间距、网格线颜色等。
绘制代码里不自带魔法数字，调参改一处。
