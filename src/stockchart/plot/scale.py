"""比例尺与数值格式化。

Scale 负责数据值到设计像素的换算；刻度选取与数值格式化也在这里，
刻度数字与数值标签共用同一套格式规则。
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass


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

    def __post_init__(self) -> None:
        lo, hi = self.domain
        if not lo < hi:
            raise ValueError(f"Scale.domain 须下限 < 上限，得到 {self.domain!r}")
        r_lo, r_hi = self.range_px
        if not r_lo < r_hi:
            raise ValueError(f"Scale.range_px 须下限 < 上限，得到 {self.range_px!r}")

    def to_px(self, value: float) -> float:
        """把数据值换算为基线相对的像素。

        Args:
            value: 数据值。

        Returns:
            对应的像素值；向上为正。
        """
        d_lo, d_hi = self.domain
        r_lo, r_hi = self.range_px
        return r_lo + (value - d_lo) / (d_hi - d_lo) * (r_hi - r_lo)

    def from_px(self, px: float) -> float:
        """把基线相对的像素换算为数据值。

        Args:
            px: 像素值；向上为正。

        Returns:
            对应的数据值。
        """
        d_lo, d_hi = self.domain
        r_lo, r_hi = self.range_px
        return d_lo + (px - r_lo) / (r_hi - r_lo) * (d_hi - d_lo)

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
        if not values:
            raise ValueError("values 为空，无法构造比例尺")
        if any(not math.isfinite(float(v)) for v in values):
            raise ValueError("values 含非有限数值（NaN / Infinity）")
        if extent_px <= 0:
            raise ValueError(f"extent_px 须为正数，得到 {extent_px}")
        if margin < 0:
            raise ValueError(f"margin 须 >= 0，得到 {margin}")
        lo, hi = min(values), max(values)
        if not lo < hi:
            raise ValueError(f"values 全部相同（{lo}），无法构造比例尺")
        pad = (hi - lo) * margin
        return cls((lo - pad, hi + pad), (0.0, float(extent_px)))


def format_number(value: float) -> str:
    """把数值格式化为宽度有界的短文本（刻度与数值标签共用）。

    绝对值小于 10^6 的整数不带小数点；其余统一 6 位有效数字，绝对值 >= 10^6
    或 < 10^-4 时切科学计数法（如 1.23457e+06、1e-10）。输出长度上限约 13 字符——
    数值标签不参与布局预留，必须避免 repr 产生 0.30000000000000004 这类
    超长串。

    Args:
        value: 待格式化的有限数值。

    Returns:
        紧凑的可读字符串。
    """
    number = float(value)
    if number.is_integer() and abs(number) < 1e6:
        return str(int(number))
    return f"{number:g}"


def format_tick(value: float) -> str:
    """格式化刻度数字（与数值标签同一规则，见 `format_number`）。

    Args:
        value: 刻度值。

    Returns:
        适合轴标签的短字符串。
    """
    return format_number(value)


def nice_ticks(domain: tuple[float, float], *, max_ticks: int = 7) -> list[float]:
    """按 1/2/2.5/5×10^k 的整步长生成刻度。

    取能放进 max_ticks 个的最小步长。domain 含 0 时 0 必在刻度中；负区间
    同样按步长取到，避免轴向下延伸却没有下方刻度。

    Args:
        domain: (下限, 上限)。
        max_ticks: 最多刻度数。

    Returns:
        升序刻度值列表。
    """
    lo, hi = domain
    span = hi - lo
    if span <= 0:
        return [lo]
    mag = 10.0 ** math.floor(math.log10(span / 5))
    candidates = [mag * m for m in (1.0, 2.0, 2.5, 5.0)]
    candidates += [mag * 10.0 * m for m in (1.0, 2.0, 2.5, 5.0)]
    ticks: list[float] = []
    for step in candidates:
        start = math.ceil(lo / step - 1e-9) * step
        ticks = []
        v = start
        while v <= hi + 1e-9:
            ticks.append(round(v, 10))
            v += step
        if len(ticks) <= max_ticks:
            return ticks
    return ticks or [lo]
