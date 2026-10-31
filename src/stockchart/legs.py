"""L0 素材层：腿部素材的数据结构。"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Literal

import numpy as np
from numpy.typing import NDArray

from stockchart.vector import rasterize_svg


@dataclass(slots=True, frozen=True)
class Leg:
    """一条腿部素材：定位元数据 + 矢量源（或 RGBA 像素）。

    宽高、足底中心、足宽等元数据一律使用**设计像素**（腿高 720 的坐标系）。
    内置素材带 `svg` 矢量源：`image` 只是设计尺寸的布局预览，真正渲染时由
    `render_stocking(scale=)` 按目标倍率重新栅格化；外部 PNG 素材没有矢量源，
    `image` 就是原始位图。

    Attributes:
        image: (H, W, 4) uint8；脚在图像底端、素材正放。内置素材为设计尺寸，
            外部素材为 PNG 原尺寸。
        width: 设计像素宽。
        height: 设计像素高。
        foot_center_x: 足底中心在设计坐标系里的 x，放置对齐的锚点。
        pixels_per_unit: `image` 的像素 / 设计像素。内置素材为 1（布局预览）；
            外部素材为 1。
        leg_id: 内置素材编号（如 "leg_03"）；外部素材为 None。
        pair_id: 所属配对编号（如 "pair_02"）；外部素材为 None。
        side: "left" / "right"；外部素材为 None。
        svg: 内置透明 SVG 源；外部素材为 None。渲染时按目标倍率栅格化。
    """

    image: NDArray[np.uint8]
    width: int
    height: int
    foot_center_x: int
    pixels_per_unit: float = 1.0
    leg_id: str | None = None
    pair_id: str | None = None
    side: Literal["left", "right"] | None = None
    svg: bytes | None = None
    _raster_cache: dict[tuple[int, int], NDArray[np.uint8]] = field(
        default_factory=lambda: dict[tuple[int, int], NDArray[np.uint8]](),
        repr=False,
        compare=False,
    )

    def raster_at(self, pixels_per_unit: float) -> NDArray[np.uint8]:
        """按目标密度直接把矢量源渲染成位图，结果缓存在 Leg 上。

        Args:
            pixels_per_unit: 目标像素 / 设计像素。

        Returns:
            (height × pixels_per_unit, width × pixels_per_unit, 4) uint8。

        Raises:
            ValueError: 素材没有矢量源（外部 PNG 素材）。
        """
        if self.svg is None:
            raise ValueError("该素材没有矢量源")
        w = max(1, round(self.width * pixels_per_unit))
        h = max(1, round(self.height * pixels_per_unit))
        key = (w, h)
        cached = self._raster_cache.get(key)
        if cached is None:
            cached = rasterize_svg(self.svg, w, h)
            self._raster_cache[key] = cached
        return cached

    def at_density(self, pixels_per_unit: float) -> Leg:
        """返回该密度下可直接绘制的 Leg；已有缓存时复用。

        Args:
            pixels_per_unit: 目标像素 / 设计像素。

        Returns:
            新的 Leg：`image` 为目标密度、`pixels_per_unit` 同步更新；设计
            元数据与 SVG 源保持不变。

        Raises:
            ValueError: 素材没有矢量源。
        """
        if abs(self.pixels_per_unit - pixels_per_unit) < 1e-9:
            return self
        return replace(
            self,
            image=self.raster_at(pixels_per_unit),
            pixels_per_unit=pixels_per_unit,
            _raster_cache=self._raster_cache,
        )
