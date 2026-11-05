# L4 — data input

← [API index](index.md) · Related: [L4 — bar() and mirror_bar()](charts.md)

The `data` of `bar` / `mirror_bar` is first normalized by `normalize_data` into `PlotData`, then fed into height mapping. The following forms are supported:

| Input | Interpretation |
| --- | --- |
| 1D `list` / `tuple` / any `Sequence` | single series, 1 value per group |
| 2D sequence `(groups, series)` | grouped data |
| `numpy.ndarray` (1D / 2D) | same as above; higher dimensions raise `ValueError` |
| `dict` / `Mapping` with scalar values | keys become x axis group labels, single series |
| `dict` / `Mapping` with equal-length sequence values | keys become series names (legend generated automatically); the row count is determined by the sequence length |
| pandas-style table object | has `index` + `to_numpy()`: with `columns` it is treated as a DataFrame (index -> x labels, columns -> series names), otherwise as a Series (index -> x labels) |
| `PlotData` | already-normalized data, used as-is |

pandas is **not** a runtime dependency and is never imported: DataFrame / Series are recognized structurally (`index` / `columns` / `to_numpy()`); the rest of the functionality is unaffected when pandas is not installed. Explicitly provided `labels` / `series_labels` override labels inferred from the data. Empty data, empty groups, ragged rows, non-numeric values, and NaN / Infinity all raise `ValueError`.

`DataInput` is a type alias for the forms above (table objects are described with structural protocols, without hard-depending on any specific library):

```python
type DataInput = (
    Sequence[float]
    | Sequence[Sequence[float]]
    | Mapping[str, float | Sequence[float]]
    | np.ndarray
    | DataFrameLike  # has columns / index / to_numpy()
    | SeriesLike  # has index / to_numpy()
    | PlotData
)
```

```python
@dataclass(slots=True, frozen=True)
class PlotData:
    """Normalized data: a (group count, series count) float matrix plus optional labels.

    Attributes:
        values: the values of each series for each group; the row count is the
            group count and the column count is the series count; rows must not be
            empty, must be of equal length, and must all be finite numbers.
        is_1d: whether the input was 1D (decides the style cycling default and the
            like).
        labels: one x axis label per group; None means it is decided by the caller
            or by an even default spread.
        series_labels: one name per series; None means no legend is drawn.

    Raises:
        ValueError: the matrix is empty, holds an empty group, the groups have
            inconsistent lengths, is_1d contradicts the series count, it contains
            non-finite numbers, or the number of labels/series names does not match
            the data.
    """

    values: tuple[tuple[float, ...], ...]
    is_1d: bool
    labels: tuple[str, ...] | None = None
    series_labels: tuple[str, ...] | None = None


@singledispatch
def normalize_data(data: object) -> PlotData:
    """Normalize the various data formats into PlotData.

    Supports 1D/2D sequences, `numpy.ndarray`, `dict` / `Mapping`, the already
    normalized `PlotData`, as well as table objects with `index` + `to_numpy()`
    (pandas DataFrame / Series and the like).

    Args:
        data: the data to normalize; the concrete forms are listed in DataInput.

    Returns:
        A PlotData of a uniform shape.

    Raises:
        TypeError: the data type is not supported.
        ValueError: the data structure or the values are invalid (empty data, too
            many dimensions, non-numeric values, etc.).
    """


def register_data_type[T](cls: type[T], handler: Callable[[T], PlotData]) -> None:
    """Register a normalization function for a custom data type.

    Equivalent to `normalize_data.register(cls, handler)`.

    Args:
        cls: the type to register.
        handler: the function that converts that type into PlotData.
    """
```

## Minimal example

```python
from stockchart import normalize_data

data = normalize_data({"Jan": 320, "Feb": 450})
print(data.labels)  # ("Jan", "Feb")
print(data.values)  # ((320.0,), (450.0,))
print(normalize_data([[1, 2], [3, 4]]).values)  # ((1.0, 2.0), (3.0, 4.0))
```
