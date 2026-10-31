# L4 — 数据输入

← [API 索引](index.md) · 相关：[L4 — bar() 与 mirror_bar()](charts.md) · [L3 — 布局封装](layout.md)

`bar` / `mirror_bar` 的 `data` 先经 `normalize_data` 归一为 `PlotData`，再进入高度映射。
支持以下形式：

| 输入 | 解释 |
| --- | --- |
| 一维 `list` / `tuple` / 任意 `Sequence` | 单系列，每组 1 个值 |
| 二维序列 `(组数, 系列数)` | 分组数据 |
| `numpy.ndarray`（1D / 2D） | 同上；更高维度抛 `ValueError` |
| `dict` / `Mapping`，值为标量 | 键作 x 轴组标签，单系列 |
| `dict` / `Mapping`，值为等长序列 | 键作系列名（自动生成图例），行数由序列长度决定 |
| pandas 风格表对象 | 带 `index` + `to_numpy()`：有 `columns` 视为 DataFrame（index → x 标签、columns → 系列名），否则视为 Series（index → x 标签） |
| `PlotData` | 已归一化数据，原样使用 |

pandas **不是**运行时依赖、也不会被 import：DataFrame / Series 通过结构
（`index` / `columns` / `to_numpy()`）识别，未安装 pandas 时其余功能不受影响。
显式传入的 `labels` / `series_labels` 覆盖数据推断出的标签。空数据、空组、
行不齐、非数值以及 NaN / Infinity 都会抛 `ValueError`。

`DataInput` 是对上述形式的类型别名（表对象用结构协议描述，不硬依赖具体库）：

```python
type DataInput = (
    Sequence[float]
    | Sequence[Sequence[float]]
    | Mapping[str, float | Sequence[float]]
    | np.ndarray
    | DataFrameLike  # 带 columns / index / to_numpy()
    | SeriesLike  # 带 index / to_numpy()
    | PlotData
)
```

```python
@dataclass(slots=True, frozen=True)
class PlotData:
    """归一后的数据：(组数, 系列数) 浮点矩阵 + 可选标签。

    Attributes:
        values: 每组的各系列数值，行数即组数、列数即系列数；行不能为空、
            等长且全部为有限数值。
        is_1d: 输入是否为一维（决定样式循环默认值等）。
        labels: 每组一个 x 轴标签；None 表示由调用方或默认均分决定。
        series_labels: 每系列一个名字；None 表示不出图例。

    Raises:
        ValueError: 矩阵为空、存在空组、各组长度不一致、含非有限数值、
            is_1d 与系列数矛盾，或标签/系列名数量与数据不符。
    """

    values: tuple[tuple[float, ...], ...]
    is_1d: bool
    labels: tuple[str, ...] | None = None
    series_labels: tuple[str, ...] | None = None


@singledispatch
def normalize_data(data: object) -> PlotData:
    """把各种数据格式归一为 PlotData；未识别的类型抛 TypeError。"""


def register_data_type[T](cls: type[T], handler: Callable[[T], PlotData]) -> None:
    """为自定义数据类型注册归一化函数（等价于 normalize_data.register）。"""
```
