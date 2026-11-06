"""L0 素材层：腿部素材源、设计元数据与一次渲染结果。"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from hashlib import sha256
from typing import Literal

import numpy as np
from numpy.typing import NDArray

type LegSourceType = Literal["png", "svg"]


@dataclass(slots=True)
class _LegState:
    """素材专属的小型派生状态；不持有大型像素数组。"""

    digest: bytes | None = None


@dataclass(slots=True, frozen=True)
class Leg:
    """一条腿部素材：不可变源字节与设计像素元数据。

    所有几何值均使用设计像素。来源方向由素材提供者保证：脚应位于底部，
    素材应已按预期方向准备好。

    Args:
        source: PNG 或 SVG 原始字节。
        source_type: 素材格式。
        width: 设计像素宽。
        height: 设计像素高。
        foot_center_x: 足底中心的设计坐标 x。
        leg_id: 可选的库内腿标识。
        pair_id: 可选的配对标识；只有同时提供 side 才参与配对。
        side: 可选的左右侧。

    Raises:
        ValueError: 源为空、格式无效、尺寸非正或足底锚点越界。

    Attributes:
        source: 原始 PNG 或 SVG 字节。
        source_type: 素材格式。
        width: 设计像素宽。
        height: 设计像素高。
        foot_center_x: 足底中心的设计坐标 x。
        leg_id: 可选的腿标识。
        pair_id: 可选的配对标识。
        side: 可选的左右侧。
    """

    source: bytes
    source_type: LegSourceType
    width: float
    height: float
    foot_center_x: float
    leg_id: str | None = None
    pair_id: str | None = None
    side: Literal["left", "right"] | None = None
    _state: _LegState = field(default_factory=_LegState, init=False, repr=False, compare=False)

    def _source_digest(self) -> bytes:
        """计算一次源摘要；源和元数据冻结后可安全复用。"""
        if self._state.digest is None:
            self._state.digest = sha256(self.source).digest()
        return self._state.digest

    def __post_init__(self) -> None:
        if type(self.source) is not bytes:
            raise ValueError("Leg.source 须为不可变 bytes")
        if not self.source:
            raise ValueError("Leg.source 不能为空")
        if self.source_type not in ("png", "svg"):
            raise ValueError(f"source_type 须为 'png' 或 'svg'，得到 {self.source_type!r}")
        if (
            not math.isfinite(self.width)
            or not math.isfinite(self.height)
            or self.width <= 0
            or self.height <= 0
        ):
            raise ValueError(f"Leg 宽高须为正的有限数，得到 {self.width}×{self.height}")
        if not math.isfinite(self.foot_center_x) or not 0 <= self.foot_center_x < self.width:
            raise ValueError(f"Leg.foot_center_x 须在 [0, {self.width})，得到 {self.foot_center_x}")
        if self.side not in (None, "left", "right"):
            raise ValueError(f"side 须为 'left' 或 'right'，得到 {self.side!r}")

    def raster_at(self, scale: float = 1.0) -> NDArray[np.uint8]:
        """将素材按目标输出倍率栅格化，并复用进程内共享缓存。

        Args:
            scale: 输出像素 / 设计像素。

        Returns:
            (round(height × scale), round(width × scale), 4) uint8 RGBA 只读数组。

        Raises:
            ValueError: scale 不是正的有限数，或素材源无法解码。
        """
        from stockchart._raster import rasterize_source

        return rasterize_source(
            self.source,
            self.source_type,
            self.width,
            self.height,
            scale,
            digest=self._source_digest(),
        )


@dataclass(slots=True, frozen=True)
class LegRender:
    """一条腿在指定倍率下的栅格化绘制结果。

    Attributes:
        source: 生成该图像的不可变素材。
        image: 目标倍率下的 uint8 RGBA 像素。
        scale: 输出像素 / 设计像素。
    """

    source: Leg
    image: NDArray[np.uint8]
    scale: float

    def __post_init__(self) -> None:
        if not math.isfinite(self.scale) or self.scale <= 0:
            raise ValueError(f"LegRender.scale 须为正的有限数，得到 {self.scale!r}")
        if self.image.ndim != 3 or self.image.shape[2] != 4 or self.image.dtype != np.uint8:
            raise ValueError("LegRender.image 须为 uint8 RGBA")
        expected = (
            max(1, round(self.source.height * self.scale)),
            max(1, round(self.source.width * self.scale)),
        )
        if self.image.shape[:2] != expected:
            raise ValueError(f"LegRender.image 尺寸须为 {expected[1]}×{expected[0]}")
