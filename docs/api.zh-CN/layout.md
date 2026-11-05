# L3 — 布局封装

← [API 索引](index.md) · 相关：[L2 — 自由柱状图](barplot.md) · [L4 — bar() 与 mirror_bar()](charts.md)

以下均为 `BarPlot` 的便捷方法：只解决“间距 + 选腿”，丝袜高度仍由调用者给像素。

```python
def add_bars(
    self,
    heights_px: Sequence[float],
    *,
    bar_gap: float = DEFAULT_BAR_GAP,
    style: StyleSeq = DEFAULT_STOCKING_STYLE,
    paired: Literal["auto", "none", "group", "global"] = "auto",
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


def add_grouped_bars(
    self,
    heights_px: Sequence[Sequence[float]],
    *,
    bar_gap: float = DEFAULT_BAR_GAP,
    group_gap: float = DEFAULT_GROUP_GAP,
    style: StyleSeq = DEFAULT_STOCKING_STYLE,
    cycle: Literal["group", "sequence"] = "group",
    paired: Literal["auto", "none", "group", "global"] = "auto",
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


def add_paired_bars(
    self,
    heights_px: Sequence[tuple[float, float]],
    *,
    group_gap: float = DEFAULT_GROUP_GAP,
    style: StyleSeq = DEFAULT_STOCKING_STYLE,
    cycle: Literal["group", "sequence"] = "group",
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
```

`add_grouped_bars` 的 `heights_px` 须为矩形表（非空、各组等长且非空）；`add_paired_bars` 每组须恰好 2 个值，显式 `pairs` 每项也须恰好 2 条腿；`cycle` 只接受 “group” / “sequence”。`legs` / `pairs` 显式传入时，`paired` 不参与校验。

**间距语义**：`bar_gap` / `group_gap` 均指相邻腿**边缘之间**的空隙（腿宽 145–183 不等，按边缘留白视觉才均匀），不是足底中心距。

## 最小示例

```python
from stockchart import BarPlot

plot = BarPlot(1200)
plot.add_grouped_bars([[300, 200], [400, 250]], style=["black_sheer", "white_sheer"])
plot.add_x_labels(["一月", "二月"])
plot.save("grouped.png")
```
