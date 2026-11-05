"""素材几何与墨线的共享预处理；预制数据缺失时在内存中提取一次。"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from hashlib import sha256
from importlib.resources import files
from io import BytesIO

import numpy as np
from numpy.typing import NDArray
from PIL import Image, ImageFilter

from stockchart._cache import ByteCache
from stockchart.defaults import DEFAULT_INK_CACHE_ENTRIES, DEFAULT_PREPARED_CACHE_BYTES
from stockchart.legs import Leg
from stockchart.stocking.geometry import column_profile

INK_DATA_VERSION = 1
INK_DATA_DENSITY = 2.0


@dataclass(slots=True, frozen=True)
class PreparedLeg:
    """按目标密度复用的只读素材数据。

    Attributes:
        src: 归一化 RGBA 像素。
        u: 贴合每行腿宽的横向坐标。
        rim: 侧缘阴影的几何强度，不含样式参数。
    """

    src: NDArray[np.float32]
    u: NDArray[np.float32]
    rim: NDArray[np.float32]


@dataclass(slots=True, frozen=True)
class InkPixels:
    """有墨线像素的稀疏数据。

    Attributes:
        ys: 有墨线像素的行号。
        xs: 有墨线像素的列号。
        weight: 线条增强强度，范围 0 到 1。
        depth: 原始线条相对肤色的亮度，范围 0 到 1。
    """

    ys: NDArray[np.intp]
    xs: NDArray[np.intp]
    weight: NDArray[np.float32]
    depth: NDArray[np.float32]


_geometry_cache = ByteCache[PreparedLeg](DEFAULT_PREPARED_CACHE_BYTES)
_ink_cache = ByteCache[InkPixels](DEFAULT_PREPARED_CACHE_BYTES)


def _source_key(leg: Leg) -> bytes:
    """按实际矢量源或位图像素标识素材，避免编号相同但内容不同的误命中。"""
    return sha256(leg.svg if leg.svg is not None else leg.image.tobytes()).digest()


def prepare_leg(leg: Leg) -> PreparedLeg:
    """准备当前输出密度的素材数据，跨素材库实例复用且不依赖袜子样式。"""
    key = (_source_key(leg), leg.image.shape)
    cached = _geometry_cache.get(key)
    if cached is not None:
        return cached
    src = leg.image.astype(np.float32) / 255.0
    u = column_profile(src[..., 3]).astype(np.float32, copy=False)
    rim = ((1.0 - np.sqrt(np.maximum(1.0 - u * u, 0.0))) ** 1.5).astype(np.float32)
    data = PreparedLeg(src, u, rim)
    for array in (src, u, rim):
        array.flags.writeable = False
    return _geometry_cache.put(key, data, src.nbytes + u.nbytes + rim.nbytes)


def extract_ink(
    image: NDArray[np.uint8], density: float
) -> tuple[NDArray[np.uint8], NDArray[np.uint8]]:
    """提取独立于袜子样式的 8 位墨线强度和局部深浅。

    Args:
        image: 当前密度的 RGBA 素材。
        density: 每个设计像素对应的图像像素数。

    Returns:
        与素材尺寸相同的墨线强度、相对肤色亮度两张单通道图。
    """
    src = image.astype(np.float32) / 255.0
    alpha = src[..., 3]
    lum = src[..., :3] @ np.array([0.299, 0.587, 0.114], dtype=np.float32)
    covered = alpha > 0.5
    if not covered.any():
        return np.zeros(alpha.shape, np.uint8), np.full(alpha.shape, 255, np.uint8)
    skin = float(np.percentile(lum[covered], 90))
    ink = np.clip((skin - 0.05 - lum) / 0.13, 0.0, 1.0)
    win = max(3, 2 * round(3 * density) + 1)
    pad = win // 2
    mask = (alpha > 0.05).astype(np.uint8)
    mask = np.lib.stride_tricks.sliding_window_view(
        np.pad(mask, ((0, 0), (pad, pad)), mode="edge"), win, axis=1
    ).min(axis=-1)
    mask = np.lib.stride_tricks.sliding_window_view(
        np.pad(mask, ((pad, pad), (0, 0)), mode="edge"), win, axis=0
    ).min(axis=-1)
    ink_image = Image.fromarray((ink * mask * 255.0).astype(np.uint8))
    ink_u8 = np.array(ink_image.filter(ImageFilter.GaussianBlur(0.8 * density)))
    depth = (np.clip(lum / max(skin, 1e-6), 0.3, 1.0) * 255.0).round().astype(np.uint8)
    return ink_u8, depth


@lru_cache(maxsize=DEFAULT_INK_CACHE_ENTRIES)
def _bundled_ink(leg_id: str, digest: bytes) -> tuple[NDArray[np.uint8], NDArray[np.uint8]] | None:
    """加载匹配素材和算法版本的预制墨线；缺失或过期时使用现场提取路径。"""
    path = files("stockchart._precomputed").joinpath(f"{leg_id}.npz")
    if not path.is_file():
        return None
    with np.load(BytesIO(path.read_bytes()), allow_pickle=False) as data:
        if (
            int(data["version"]) != INK_DATA_VERSION
            or str(data["source"]) != digest.hex()
            or float(data["density"]) != INK_DATA_DENSITY
        ):
            return None
        return data["ink"], data["depth"]


def ink_pixels(leg: Leg) -> InkPixels:
    """返回目标密度下的稀疏墨线，只保留增强阶段实际需要的像素。"""
    digest = _source_key(leg)
    key = (digest, leg.image.shape)
    cached = _ink_cache.get(key)
    if cached is not None:
        return cached
    maps = _bundled_ink(leg.leg_id, digest) if leg.svg is not None and leg.leg_id else None
    if maps is None:
        maps = extract_ink(leg.image, leg.pixels_per_unit)
    ink, depth = maps
    height, width = leg.image.shape[:2]
    if ink.shape != (height, width):
        ink = np.array(Image.fromarray(ink).resize((width, height), Image.Resampling.BILINEAR))
        depth = np.array(Image.fromarray(depth).resize((width, height), Image.Resampling.BILINEAR))
    ys, xs = np.nonzero((ink > 2) & (leg.image[..., 3] > 12))
    weight = ink[ys, xs].astype(np.float32) / 255.0
    local_depth = depth[ys, xs].astype(np.float32) / 255.0
    data = InkPixels(ys, xs, weight, local_depth)
    return _ink_cache.put(key, data, ys.nbytes + xs.nbytes + weight.nbytes + local_depth.nbytes)
