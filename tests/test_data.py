"""L4 数据归一测试：序列、numpy、字典、表格对象与自定义注册。"""

from types import MappingProxyType

import numpy as np
import pytest
from numpy.typing import NDArray

from stockchart import PlotData, normalize_data, register_data_type


class FakeFrame:
    """最小 pandas DataFrame 结构，测试鸭子类型而不引入 pandas。"""

    def __init__(
        self,
        values: list[list[float]],
        *,
        index: tuple[str, ...],
        columns: tuple[str, ...],
    ) -> None:
        self._values = np.asarray(values, dtype=float)
        self._index = index
        self._columns = columns

    @property
    def index(self) -> tuple[str, ...]:
        return self._index

    @property
    def columns(self) -> tuple[str, ...]:
        return self._columns

    def to_numpy(self) -> NDArray[np.float64]:
        return self._values


class FakeSeries:
    """最小 pandas Series 结构。"""

    def __init__(self, values: list[float], *, index: tuple[str, ...]) -> None:
        self._values = np.asarray(values, dtype=float)
        self._index = index

    @property
    def index(self) -> tuple[str, ...]:
        return self._index

    def to_numpy(self) -> NDArray[np.float64]:
        return self._values


class TestSequences:
    def test_1d_list(self) -> None:
        assert normalize_data([1.0, 2.0, 3.0]) == PlotData(
            values=((1.0,), (2.0,), (3.0,)), is_1d=True
        )

    def test_2d_list(self) -> None:
        assert normalize_data([[1.0, 2.0], [3.0, 4.0]]) == PlotData(
            values=((1.0, 2.0), (3.0, 4.0)), is_1d=False
        )

    def test_tuple(self) -> None:
        assert normalize_data((1, 2)).values == ((1.0,), (2.0,))

    def test_empty_raises(self) -> None:
        with pytest.raises(ValueError, match="为空"):
            normalize_data([])
        with pytest.raises(ValueError, match="空组"):
            normalize_data([[]])

    def test_ragged_raises(self) -> None:
        with pytest.raises(ValueError, match="一致"):
            normalize_data([[1.0, 2.0], [3.0]])

    def test_non_numeric_raises(self) -> None:
        with pytest.raises(ValueError, match="非数值"):
            normalize_data([1.0, object()])

    def test_string_rejected(self) -> None:
        with pytest.raises(TypeError):
            normalize_data("abc")


class TestNumpy:
    def test_1d_and_2d(self) -> None:
        assert normalize_data(np.array([1.0, 2.0])).is_1d
        two_d = normalize_data(np.array([[1.0, 2.0], [3.0, 4.0]]))
        assert two_d.values == ((1.0, 2.0), (3.0, 4.0))
        assert not two_d.is_1d

    def test_too_many_dims(self) -> None:
        with pytest.raises(ValueError, match="最多支持 2 维"):
            normalize_data(np.zeros((2, 2, 2)))

    def test_zero_dim(self) -> None:
        with pytest.raises(ValueError, match="1 维或 2 维"):
            normalize_data(np.array(3.0))


class TestMapping:
    def test_scalars_become_labels(self) -> None:
        data = normalize_data({"一月": 3, "二月": 5})
        assert data == PlotData(
            values=((3.0,), (5.0,)),
            is_1d=True,
            labels=("一月", "二月"),
        )

    def test_sequences_become_series(self) -> None:
        data = normalize_data({"本站": [1, 2], "隔壁": [3, 4]})
        assert data.values == ((1.0, 3.0), (2.0, 4.0))
        assert data.series_labels == ("本站", "隔壁")
        assert not data.is_1d

    def test_mixed_values_rejected(self) -> None:
        with pytest.raises(ValueError, match="全为标量或全为等长序列"):
            normalize_data({"a": 1, "b": [2, 3]})

    def test_nested_mapping_rejected(self) -> None:
        with pytest.raises(ValueError, match="嵌套字典"):
            normalize_data({"a": {"b": 1}})

    def test_uneven_series_rejected(self) -> None:
        with pytest.raises(ValueError, match="等长"):
            normalize_data({"a": [1, 2], "b": [3]})

    def test_non_dict_mapping(self) -> None:
        data = normalize_data(MappingProxyType({"a": 1}))
        assert data.labels == ("a",)

    def test_dict_of_series_like(self) -> None:
        data = normalize_data(
            {
                "甲": FakeSeries([1.0, 2.0], index=("x", "y")),
                "乙": FakeSeries([3.0, 4.0], index=("x", "y")),
            }
        )
        assert data.values == ((1.0, 3.0), (2.0, 4.0))
        assert data.series_labels == ("甲", "乙")


class TestPlotData:
    def test_passthrough(self) -> None:
        data = PlotData(values=((1.0,), (2.0,)), is_1d=True)
        assert normalize_data(data) is data

    def test_empty_values_rejected(self) -> None:
        with pytest.raises(ValueError, match="为空"):
            PlotData(values=(), is_1d=True)

    def test_empty_group_rejected(self) -> None:
        with pytest.raises(ValueError, match="空组"):
            PlotData(values=((),), is_1d=True)

    def test_ragged_rejected(self) -> None:
        with pytest.raises(ValueError, match="一致"):
            PlotData(values=((1.0, 2.0), (3.0,)), is_1d=False)

    def test_label_lengths_checked(self) -> None:
        with pytest.raises(ValueError, match="labels"):
            PlotData(values=((1.0,),), is_1d=True, labels=("a", "b"))
        with pytest.raises(ValueError, match="series_labels"):
            PlotData(values=((1.0, 2.0),), is_1d=False, series_labels=("a",))

    def test_1d_requires_one_series(self) -> None:
        with pytest.raises(ValueError, match="只能有 1 个值"):
            PlotData(values=((1.0, 2.0),), is_1d=True)

    def test_non_finite_rejected(self) -> None:
        with pytest.raises(ValueError, match="非有限"):
            PlotData(values=((1.0,), (float("nan"),)), is_1d=True)
        with pytest.raises(ValueError, match="非有限"):
            normalize_data([1.0, float("inf")])


class TestTableLike:
    def test_dataframe_like(self) -> None:
        data = normalize_data(
            FakeFrame(
                [[1.0, 3.0], [2.0, 4.0]],
                index=("一", "二"),
                columns=("甲", "乙"),
            )
        )
        assert data.values == ((1.0, 3.0), (2.0, 4.0))
        assert data.labels == ("一", "二")
        assert data.series_labels == ("甲", "乙")
        assert not data.is_1d

    def test_series_like(self) -> None:
        data = normalize_data(FakeSeries([1.0, 2.0], index=("a", "b")))
        assert data.values == ((1.0,), (2.0,))
        assert data.labels == ("a", "b")
        assert data.series_labels is None
        assert data.is_1d

    def test_series_labels_length_mismatch(self) -> None:
        # 列名数量与数据列数不一致的表对象，归一阶段就应报错
        frame = FakeFrame([[1.0, 2.0]], index=("一",), columns=("甲",))
        with pytest.raises(ValueError, match="series_labels"):
            normalize_data(frame)


class Celsius:
    def __init__(self, value: float) -> None:
        self.value = value


def _read_celsius(data: Celsius) -> PlotData:
    return PlotData(values=((data.value,),), is_1d=True)


class BadValue:
    pass


def _read_bad(data: BadValue) -> PlotData:
    return PlotData(values=(), is_1d=True)


register_data_type(Celsius, _read_celsius)
register_data_type(BadValue, _read_bad)


class TestCustomTypes:
    def test_registered_type(self) -> None:
        assert normalize_data(Celsius(21.5)).values == ((21.5,),)

    def test_handler_output_is_validated(self) -> None:
        with pytest.raises(ValueError, match="为空"):
            normalize_data(BadValue())

    def test_unknown_type_rejected(self) -> None:
        with pytest.raises(TypeError, match="不支持的数据类型"):
            normalize_data(object())
