"""直接生成图例织物小块，不渲染整条腿、皮肤光影或袜口。"""

from dataclasses import replace
from functools import lru_cache

import numpy as np
from numpy.typing import NDArray

from stockchart.defaults import DEFAULT_SWATCH_CACHE_ENTRIES
from stockchart.stocking.fabric import render_fabric
from stockchart.stocking.styles import (
    Dotted,
    Fabric,
    Fishnet,
    Plain,
    Ribbed,
    StockingStyle,
    scale_style,
)


def _flat_fabric(fabric: Fabric) -> Fabric:
    """图例使用平展织物，保留样式的颜色、尺寸与透明度。"""
    if isinstance(fabric, Plain):
        return replace(fabric, rim=0, stretch=0)
    if isinstance(fabric, Ribbed):
        return replace(fabric, perspective=0)
    if isinstance(fabric, Fishnet):
        under = replace(fabric.underlay, rim=0, stretch=0) if fabric.underlay is not None else None
        return replace(fabric, perspective=0, underlay=under)
    if isinstance(fabric, Dotted):
        return replace(fabric, perspective=0, base=replace(fabric.base, rim=0, stretch=0))
    return fabric


@lru_cache(maxsize=DEFAULT_SWATCH_CACHE_ENTRIES)
def render_swatch(style: StockingStyle, size: int, seed: int, scale: float) -> NDArray[np.uint8]:
    """生成并缓存按输出密度绘制的图例色块。"""
    pixels = max(1, round(size * scale))
    style = scale_style(style, scale)
    src = np.ones((pixels, pixels, 4), dtype=np.float32)
    src[..., :3] = np.array([253, 234, 228], np.float32) / 255.0
    alpha = src[..., 3]
    u = np.broadcast_to(np.linspace(-1, 1, pixels, dtype=np.float32), alpha.shape)
    fabric = render_fabric(
        _flat_fabric(style.fabric),
        src,
        alpha,
        u,
        0,
        pixels,
        pixels,
        np.random.default_rng(seed),
    )
    src[..., :3] += (fabric[..., :3] - src[..., :3]) * fabric[..., 3:4]
    image = (np.clip(src, 0.0, 1.0) * 255).astype(np.uint8)
    image.flags.writeable = False
    return image
