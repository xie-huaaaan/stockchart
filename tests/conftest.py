"""测试夹具：整轮测试共用一份已栅格化的腿素材。

`LegLibrary` 的懒加载缓存是实例级的，而 `bar()` / `mirror_bar()` 每次调用都会
新建一个库，于是同一条 SVG 被反复光栅化（每条约 60ms）。这里在进程内共享
光栅化结果，把整套测试从分钟级压到秒级。

只改测试行为，不改库：光栅化是纯函数，输出按 (SVG 内容, 宽, 高) 缓存即可。
"""

from __future__ import annotations

from collections.abc import Iterator

import numpy as np
import pytest
from numpy.typing import NDArray

import stockchart.legs
import stockchart.library
import stockchart.vector


@pytest.fixture(autouse=True, scope="session")
def _shared_leg_raster_cache() -> Iterator[None]:
    """让所有素材加载路径共用同一份已光栅化的结果。"""
    original = stockchart.vector.rasterize_svg
    cache: dict[tuple[bytes, int, int], NDArray[np.uint8]] = {}

    def cached(svg: bytes, width: int, height: int) -> NDArray[np.uint8]:
        key = (svg, width, height)
        hit = cache.get(key)
        if hit is None:
            hit = original(svg, width, height)
            cache[key] = hit
        return hit

    stockchart.vector.rasterize_svg = cached
    stockchart.legs.rasterize_svg = cached
    stockchart.library.rasterize_svg = cached
    try:
        yield
    finally:
        stockchart.vector.rasterize_svg = original
        stockchart.legs.rasterize_svg = original
        stockchart.library.rasterize_svg = original
