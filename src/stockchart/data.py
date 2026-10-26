"""L4 数据归一：把常见数据结构统一为组标签 + 系列名 + 数值矩阵。

pandas 等第三方库不进入运行时依赖：带 ``index`` / ``columns`` / ``to_numpy()``
的对象按结构识别，未安装时不影响其他功能。
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from functools import singledispatch
from typing import Protocol, SupportsFloat, cast

import numpy as np
from numpy.typing import NDArray


class _DataFrameLike(Protocol):
    """pandas DataFrame 等表格对象的最小结构。"""

    @property
    def columns(self) -> Iterable[object]: ...

    @property
    def index(self) -> Iterable[object]: ...

    def to_numpy(self) -> object: ...


class _SeriesLike(Protocol):
    """pandas Series 等带索引的一维对象的最小结构。"""

    @property
    def index(self) -> Iterable[object]: ...

    def to_numpy(self) -> object: ...


@dataclass(slots=True, frozen=True)
class PlotData:
    """归一后的数据：(组数, 系列数) 的浮点矩阵与可选标签。

    Attributes:
        values: 每组的各系列数值；行数即组数、列数即系列数，行不能为空且等长。
        is_1d: 输入是否为一维（决定样式循环默认值等）。
        labels: 每组一个 x 轴标签；None 表示由调用方或默认均分决定。
        series_labels: 每系列一个名字；None 表示不出图例。
    """

    values: tuple[tuple[float, ...], ...]
    is_1d: bool
    labels: tuple[str, ...] | None = None
    series_labels: tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        if not self.values:
            raise ValueError("values 为空")
        series = len(self.values[0])
        if series == 0:
            raise ValueError("values 存在空组")
        if any(len(row) != series for row in self.values):
            raise ValueError("values 各组系列数须一致")
        if self.is_1d and series != 1:
            raise ValueError("is_1d=True 时每组只能有 1 个值")
        if self.labels is not None and len(self.labels) != len(self.values):
            raise ValueError(f"labels 与组数不一致：{len(self.labels)} != {len(self.values)}")
        if self.series_labels is not None and len(self.series_labels) != series:
            raise ValueError(f"series_labels 与系列数不一致：{len(self.series_labels)} != {series}")


type DataInput = (
    Sequence[float]
    | Sequence[Sequence[float]]
    | Mapping[str, float | Sequence[float]]
    | NDArray[np.generic]
    | _DataFrameLike
    | _SeriesLike
    | PlotData
)
"""`bar` / `mirror_bar` 接受的数据形式；完整说明见 docs/api.md“数据输入”。"""


@singledispatch
def normalize_data(data: object) -> PlotData:
    """把各种数据格式归一为 `PlotData`。

    支持一维/二维序列、`numpy.ndarray`、`dict` / `Mapping`、已归一化的
    `PlotData`，以及带 `index` + `to_numpy()` 的表对象（pandas DataFrame /
    Series 等）。无法识别或数值非法时抛 `ValueError` / `TypeError`。
    """
    if isinstance(data, np.ndarray):
        return _from_numpy(cast(NDArray[np.generic], data))
    if isinstance(data, Mapping):
        return _from_mapping(cast(Mapping[object, object], data))
    table = _from_table_like(data)
    if table is not None:
        return table
    if isinstance(data, Sequence) and not isinstance(data, (str, bytes, bytearray)):
        return _from_sequence(cast(Sequence[object], data))
    raise TypeError(
        "不支持的数据类型；可用 list/tuple、numpy.ndarray、dict/Mapping、"
        "带 index/to_numpy() 的表对象（如 pandas DataFrame/Series）或 PlotData"
    )


def register_data_type[T](cls: type[T], handler: Callable[[T], PlotData]) -> None:
    """为自定义数据类型注册归一化函数（等价于 `normalize_data.register`）。"""
    normalize_data.register(cls, handler)


def _normalize_sequence(data: object) -> PlotData:
    assert isinstance(data, Sequence)
    return _from_sequence(cast(Sequence[object], data))


def _normalize_mapping(data: object) -> PlotData:
    assert isinstance(data, Mapping)
    return _from_mapping(cast(Mapping[object, object], data))


def _normalize_plotdata(data: object) -> PlotData:
    assert isinstance(data, PlotData)
    return data


normalize_data.register(list, _normalize_sequence)
normalize_data.register(tuple, _normalize_sequence)
normalize_data.register(dict, _normalize_mapping)
normalize_data.register(PlotData, _normalize_plotdata)


def _as_float(value: object) -> float:
    """转成 float，非数值给出统一错误信息。"""
    try:
        return float(cast(str | SupportsFloat, value))
    except (TypeError, ValueError):
        raise ValueError(f"数据包含非数值元素：{value!r}") from None


def _is_row(value: object) -> bool:
    """该值是否可视为一行（序列）数据；字符串、字典与 0 维数组不算。"""
    if isinstance(value, Mapping):
        return False
    if isinstance(value, np.ndarray):
        return value.ndim > 0
    if callable(getattr(value, "to_numpy", None)):
        # pandas Series 等一维带索引对象；二维表对象不能当一行
        return getattr(value, "ndim", 1) == 1
    return isinstance(value, (list, tuple, range)) or (
        isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))
    )


def _row_values(value: object) -> list[object]:
    """把一组数据内的行统一取成 Python 列表。"""
    to_numpy = getattr(value, "to_numpy", None)
    if callable(to_numpy):
        return list(np.asarray(cast(Callable[[], object], to_numpy)()).tolist())
    return list(cast(Iterable[object], value))


def _from_rows(raw_rows: Iterable[object]) -> PlotData:
    """由“每组一个值”或“每组一行值”的序列构造 PlotData。"""
    rows = list(raw_rows)
    if not rows:
        raise ValueError("data 为空")
    if _is_row(rows[0]):
        values: list[tuple[float, ...]] = []
        for item in rows:
            if not _is_row(item):
                raise ValueError("二维数据各行须为数值序列")
            row = tuple(_as_float(v) for v in _row_values(item))
            if not row:
                raise ValueError("data 存在空组")
            values.append(row)
        if len({len(row) for row in values}) != 1:
            counts = sorted({len(row) for row in values})
            raise ValueError(f"二维数据各组系列数须一致，得到 {counts}")
        return PlotData(values=tuple(values), is_1d=False)
    return PlotData(values=tuple((_as_float(v),) for v in rows), is_1d=True)


def _from_sequence(data: Sequence[object]) -> PlotData:
    return _from_rows(data)


def _from_mapping(data: Mapping[object, object]) -> PlotData:
    """字典：值全为标量→键作 x 标签；值全为等长序列→键作系列名并转置。"""
    items = list(data.items())
    if not items:
        raise ValueError("data 为空")
    if any(isinstance(value, Mapping) for _, value in items):
        raise ValueError("不支持嵌套字典；请传入标量、序列或表格对象")
    if _is_row(items[0][1]):
        if not all(_is_row(value) for _, value in items):
            raise ValueError("字典的值须全为标量或全为等长序列")
        columns = [_row_values(value) for _, value in items]
        groups = len(columns[0])
        if groups == 0:
            raise ValueError("data 存在空组")
        if any(len(column) != groups for column in columns):
            raise ValueError("字典中各序列须等长")
        values = tuple(
            tuple(_as_float(columns[s][g]) for s in range(len(columns))) for g in range(groups)
        )
        return PlotData(
            values=values,
            is_1d=False,
            series_labels=tuple(str(key) for key, _ in items),
        )
    if any(_is_row(value) for _, value in items):
        raise ValueError("字典的值须全为标量或全为等长序列")
    return PlotData(
        values=tuple((_as_float(value),) for _, value in items),
        is_1d=True,
        labels=tuple(str(key) for key, _ in items),
    )


def _from_numpy(data: NDArray[np.generic]) -> PlotData:
    if data.ndim == 0:
        raise ValueError("data 须为 1 维或 2 维数组")
    if data.ndim > 2:
        raise ValueError(f"data 最多支持 2 维，得到 {data.ndim} 维")
    return _from_rows(cast(Iterable[object], data.tolist()))


def _from_table_like(data: object) -> PlotData | None:
    """识别 pandas 风格表对象；不像表时返回 None。"""
    to_numpy = getattr(data, "to_numpy", None)
    index = getattr(data, "index", None)
    if not callable(to_numpy) or index is None:
        return None
    array = np.asarray(cast(Callable[[], object], to_numpy)())
    if array.ndim == 0:
        raise ValueError("表格对象须为 1 维或 2 维")
    if array.ndim > 2:
        raise ValueError(f"表格对象最多支持 2 维，得到 {array.ndim} 维")
    labels = tuple(str(v) for v in cast(Iterable[object], index))
    columns = getattr(data, "columns", None)
    normalized = _from_rows(cast(Iterable[object], array.tolist()))
    if columns is None:
        return PlotData(values=normalized.values, is_1d=normalized.is_1d, labels=labels)
    series_labels = tuple(str(v) for v in cast(Iterable[object], columns))
    return PlotData(
        values=normalized.values,
        is_1d=False,
        labels=labels,
        series_labels=series_labels,
    )
