# L4 — data input

← [API index](index.md) · Related: [L4 — bar() and mirror_bar()](charts.md)

## Data input (L4)

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

pandas is **not** a runtime dependency and is never imported: DataFrame / Series are recognized structurally (`index` / `columns` / `to_numpy()`); the rest of the functionality is unaffected when pandas is not installed. Explicitly provided `labels` / `series_labels` override labels inferred from the data. Empty data, empty groups, ragged rows, and non-numeric values all raise `ValueError`.

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
    """Normalized data: a (groups, series) float matrix + optional labels.

    Attributes:
        values: per-group values for each series; row count = groups,
            column count = series; rows must be non-empty and equal length.
        is_1d: whether the input was 1D (determines style cycling defaults
            and the like).
        labels: one x axis label per group; None means decided by the
            caller or an even default spread.
        series_labels: one name per series; None means no legend.
    """

    values: tuple[tuple[float, ...], ...]
    is_1d: bool
    labels: tuple[str, ...] | None = None
    series_labels: tuple[str, ...] | None = None


@singledispatch
def normalize_data(data: object) -> PlotData:
    """Normalize various data formats into PlotData; unrecognized types raise TypeError."""


def register_data_type[T](cls: type[T], handler: Callable[[T], PlotData]) -> None:
    """Register a normalizer for a custom data type (equivalent to normalize_data.register)."""
```
