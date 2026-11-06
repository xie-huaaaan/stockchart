"""统一的 PNG/SVG 素材栅格化与缩放缓存。"""

from __future__ import annotations

import math
from hashlib import sha256
from io import BytesIO

import numpy as np
from numpy.typing import NDArray
from PIL import Image

from stockchart._cache import ByteCache
from stockchart.defaults import DEFAULT_DECODED_CACHE_BYTES, DEFAULT_RASTER_CACHE_BYTES
from stockchart.vector import rasterize_svg

_cache = ByteCache[NDArray[np.uint8]](DEFAULT_RASTER_CACHE_BYTES)
_decoded_cache = ByteCache[NDArray[np.uint8]](DEFAULT_DECODED_CACHE_BYTES)


def _resize_rgba(image: NDArray[np.uint8], width: int, height: int) -> NDArray[np.uint8]:
    """用 Pillow 原生 RGBA 重采样，复用其内部预乘 alpha 路径。"""
    shrinking = width < image.shape[1] or height < image.shape[0]
    resample = Image.Resampling.LANCZOS if shrinking else Image.Resampling.BICUBIC
    # Pillow 在 RGBA 非最近邻缩放时内部转为预乘 RGBa，避免透明像素的底色渗入边缘。
    result = np.asarray(Image.fromarray(image).resize((width, height), resample), dtype=np.uint8)
    result.flags.writeable = False
    return result


def rasterize_source(
    source: bytes,
    source_type: str,
    design_width: float,
    design_height: float,
    scale: float,
    *,
    digest: bytes | None = None,
) -> NDArray[np.uint8]:
    """将任一素材源按设计尺寸和倍率生成 RGBA 像素。"""
    if not math.isfinite(scale) or scale <= 0:
        raise ValueError(f"scale 须为正的有限数，得到 {scale!r}")
    width = max(1, round(design_width * scale))
    height = max(1, round(design_height * scale))
    digest = sha256(source).digest() if digest is None else digest
    key = (digest, source_type, width, height)
    cached = _cache.get(key)
    if cached is not None:
        return cached

    if source_type == "svg":
        image = rasterize_svg(source, width, height)
    elif source_type == "png":
        decoded = _decoded_cache.get((digest, "png-source"))
        if decoded is None:
            with Image.open(BytesIO(source)) as opened:
                decoded = np.asarray(opened.convert("RGBA"), dtype=np.uint8).copy()
            decoded.flags.writeable = False
            _decoded_cache.put((digest, "png-source"), decoded, decoded.nbytes)
        if decoded.shape[:2] == (height, width):
            image = decoded
        else:
            image = _resize_rgba(decoded, width, height)
    else:
        raise ValueError(f"未知素材格式 {source_type!r}")

    image.flags.writeable = False
    return _cache.put(key, image, image.nbytes)
