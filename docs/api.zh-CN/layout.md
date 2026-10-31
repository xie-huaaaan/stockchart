# L3 — 布局封装

← [API 索引](index.md) · 相关：[L2 — 自由柱状图](barplot.md) · [L4 — bar() 与 mirror_bar()](charts.md)

以下均为 `BarPlot` 的便捷方法：只解决"间距 + 选腿"，丝袜高度仍由调用者给像素。

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
    """单序列：统一间距从左到右排开，自动按左、右、左、右……交替选腿。

    legs 可显式指定每根柱子的素材（长度须与 heights_px 一致，不参与循环，
    此时 paired 忽略）。单序列下 "auto" 用 "none"；显式 "group" 时每根柱子
    取新素材对的左腿，"global" 时相邻柱子成对取素材。style 为列表时按柱序
    循环取用。
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
    """(组数, 系列数) 的像素高度：组内用 bar_gap、组间用 group_gap，
    跨列按左、右、左、右……交替选腿。

    paired="auto"（默认）单系列用 "none"、多系列用 "global"；"group"
    时每组独立取完整对（相邻两腿同一对素材，单系列即每组取左腿），
    "global" 时整张图连续取对，"none" 时每条腿来自不同素材对。legs
    显式时 paired 忽略。

    style 为列表时按 cycle 取用："group"（默认）按组内位置循环，组内第 i 根
    用 styles[i % len]，列表长度等于系列数时即"每系列一个样式"；"sequence"
    按全部柱子的绘制顺序循环（组 0 第 0 根、组 0 第 1 根、组 1 第 0 根……）。
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

    style 为列表时按 cycle 取用（"group" 默认：系列 0 取 styles[0]、系列 1
    取 styles[1 % len]；"sequence" 按全部柱子的绘制顺序循环）。
    pairs 缺省时自动选取不重复的素材对。
    """
```

`add_grouped_bars` 的 `heights_px` 须为矩形表（非空、各组等长且非空）；`add_paired_bars`
每组须恰好 2 个值，显式 `pairs` 每项也须恰好 2 条腿；`cycle` 只接受 "group" / "sequence"。
`legs` / `pairs` 显式传入时，`paired` 不参与校验。

**间距语义**：`bar_gap` / `group_gap` 均指相邻腿**边缘之间**的空隙（腿宽 144–181 不等，
按边缘留白视觉才均匀），不是足底中心距。
