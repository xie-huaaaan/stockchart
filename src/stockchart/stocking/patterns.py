"""有界共享的周期条纹与标准印花查表，不缓存完整腿或随机图案。"""

from __future__ import annotations

import math
from functools import lru_cache

import numpy as np
from numpy.typing import NDArray

from stockchart.color import color_alpha, color_rgb
from stockchart.defaults import (
    DEFAULT_MOTIF_TABLE_SIZE,
    DEFAULT_PATTERN_CACHE_ENTRIES,
    DEFAULT_PATTERN_SAMPLES_PER_PIXEL,
)
from stockchart.stocking.pixels import FloatArray
from stockchart.stocking.styles import Striped


@lru_cache(maxsize=DEFAULT_PATTERN_CACHE_ENTRIES)
def _stripe_table(fabric: Striped) -> NDArray[np.float32]:
    """为一个条纹周期记录直通 RGB 与 alpha，保留原有条带软边。"""
    period = sum(stripe.width for stripe in fabric.stripes)
    samples = min(8192, max(128, math.ceil(period * DEFAULT_PATTERN_SAMPLES_PER_PIXEL)))
    phase = np.arange(samples, dtype=np.float32) * (period / samples)
    table = np.zeros((samples, 4), dtype=np.float32)
    total = np.zeros(samples, dtype=np.float32)
    soft = min(1.2, period / 8.0)
    start = 0.0
    for stripe in fabric.stripes:
        center = start + stripe.width / 2
        weight = np.clip(0.5 + (stripe.width / 2 - np.abs(phase - center)) / soft, 0.0, 1.0)
        table[:, :3] += weight[:, None] * color_rgb(stripe.color)
        table[:, 3] += weight * stripe.opacity * color_alpha(stripe.color)
        total += weight
        start += stripe.width
    table /= np.maximum(total[:, None], 1e-8)
    table.flags.writeable = False
    return table


def stripe_pixels(fabric: Striped, ys: FloatArray) -> NDArray[np.float32]:
    """按周期相位线性插值条纹表，避免逐条带扫描整片袜区。"""
    table = _stripe_table(fabric)
    period = sum(stripe.width for stripe in fabric.stripes)
    position = ((ys - fabric.offset) % period) * (len(table) / period)
    index = position.astype(np.intp)
    fraction = (position - index).astype(np.float32)[..., None]
    first = table[index % len(table)]
    return (first + (table[(index + 1) % len(table)] - first) * fraction).astype(
        np.float32, copy=False
    )


@lru_cache(maxsize=2)
def _motif_table(shape: str) -> NDArray[np.float32]:
    """记录单位尺寸的爱心或星形，范围覆盖其完整轮廓。"""
    axis = np.linspace(-1.75, 1.75, DEFAULT_MOTIF_TABLE_SIZE, dtype=np.float32)
    x, y = axis[None, :], axis[:, None]
    if shape == "heart":
        nx, ny = x / 1.2, -y / 1.2
        mask = (nx * nx + ny * ny - 1.0) ** 3 - nx * nx * ny**3 < 0
    else:
        theta = np.arctan2(y, x)
        radius = 0.4 + 0.6 * np.abs(np.cos(2.5 * theta))
        mask = x * x + y * y < radius * radius
    table = mask.astype(np.float32)
    table.flags.writeable = False
    return table


def motif_mask(dx: FloatArray, dy: FloatArray, size: float, shape: str) -> NDArray[np.float32]:
    """将各印花中心附近的坐标映射到标准形状表，保留散布坐标与种子行为。"""
    table = _motif_table(shape)
    factor = (len(table) - 1) / (3.5 * size)
    center = len(table) / 2
    xs = np.clip(dx * factor + center, 0, len(table) - 1).astype(np.intp)
    ys = np.clip(dy * factor + center, 0, len(table) - 1).astype(np.intp)
    result = table[ys, xs]
    result[(np.abs(dx) > 1.75 * size) | (np.abs(dy) > 1.75 * size)] = 0
    return result
