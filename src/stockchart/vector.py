"""内置矢量素材的栅格化。

SVG 的容器尺寸必须保持固有尺寸，`clipPath` 才能正确应用；把容器缩放到其他
尺寸时 skia 会把裁切区域算错（实测左侧被裁掉）。因此渲染到目标尺寸时改为
缩放画布，让矢量路径（含裁切）按目标分辨率重新光栅化。解析后的绘图指令
独立于输出倍率缓存；内置素材优先读取随包预制的 Skia Picture。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from hashlib import sha256
from importlib.resources import files

import numpy as np
import skia
from numpy.typing import NDArray

from stockchart._cache import ByteCache
from stockchart.defaults import DEFAULT_PICTURE_CACHE_BYTES, DEFAULT_RASTER_CACHE_BYTES

_SVG_SIZE = re.compile(rb'<svg[^>]*\bwidth="([0-9.]+)"[^>]*\bheight="([0-9.]+)"')
_raster_cache = ByteCache[NDArray[np.uint8]](DEFAULT_RASTER_CACHE_BYTES)


@dataclass(slots=True, frozen=True)
class _SvgPicture:
    """固有尺寸下的矢量绘图指令；同一份可在任意输出倍率重放。"""

    picture: skia.Picture
    width: int
    height: int


_picture_cache = ByteCache[_SvgPicture](DEFAULT_PICTURE_CACHE_BYTES)


@lru_cache(maxsize=1)
def _bundled_sources() -> dict[str, str]:
    """索引当前 Skia 版本可读取的内置指令，源摘要不匹配时仍走 SVG。"""
    path = files("stockchart._precomputed").joinpath("pictures.json")
    if not path.is_file():
        return {}
    manifest = json.loads(path.read_text(encoding="utf-8"))
    # SKP 不是跨 Skia 版本的交换格式；升级依赖后从 SVG 重建即可。
    return manifest["sources"] if manifest["skia"] == skia.__version__ else {}


def _record_svg(svg: bytes, width: int, height: int) -> skia.Picture:
    """解析一次 SVG，在固有尺寸录制裁切和矢量路径，不产生位图。"""
    dom = skia.SVGDOM.MakeFromStream(skia.MemoryStream(svg))
    if dom is None:
        raise ValueError("无法解析 SVG")
    dom.setContainerSize(skia.Size(width, height))
    recorder = skia.PictureRecorder()
    canvas = recorder.beginRecording(skia.Rect.MakeWH(width, height))
    dom.render(canvas)
    return recorder.finishRecordingAsPicture()


def _prepare_svg(svg: bytes, digest: bytes) -> _SvgPicture:
    """优先加载随包指令，缺失时录制；结果按源内容共享有界缓存。"""
    cached = _picture_cache.get(digest)
    if cached is not None:
        return cached
    m = _SVG_SIZE.search(svg)
    if m is None:
        raise ValueError("SVG 根节点缺少 width/height")
    width, height = round(float(m.group(1))), round(float(m.group(2)))
    if width <= 0 or height <= 0:
        raise ValueError(f"SVG 固有尺寸须为正数，得到 {width}×{height}")
    picture = None
    leg_id = _bundled_sources().get(digest.hex())
    if leg_id is not None:
        path = files("stockchart._precomputed").joinpath(f"{leg_id}.skp")
        if path.is_file():
            try:
                picture = skia.Picture.MakeFromData(skia.Data.MakeWithCopy(path.read_bytes()))
            except ValueError:
                # 不完整的预制文件不影响 SVG 作为素材真源的可用性。
                picture = None
    if picture is None:
        picture = _record_svg(svg, width, height)
    prepared = _SvgPicture(picture, width, height)
    # Skia 的估计不含全部间接持有的路径，另用 SVG 体积给出保守下界。
    size = max(picture.approximateBytesUsed(), len(svg) * 2)
    return _picture_cache.put(digest, prepared, size)


def rasterize_svg(svg: bytes, width: int, height: int) -> NDArray[np.uint8]:
    """把透明 SVG 素材直接栅格化为指定像素尺寸的 RGBA 图。

    容器尺寸保持 SVG 固有尺寸，只缩放画布，以绕开 skia 在缩放容器时的
    `clipPath` 计算错误；缓存的矢量绘图指令按目标分辨率重新光栅化。

    Args:
        svg: SVG 文本字节；根节点须带 width/height。
        width: 目标像素宽，须为正数。
        height: 目标像素高，须为正数。

    Returns:
        (height, width, 4) uint8 RGBA；透明区域 alpha 为 0，脚在图像底端。

    Raises:
        ValueError: 目标尺寸非正数、SVG 无法解析，或根节点缺少有效的
            width/height。
    """
    if width <= 0 or height <= 0:
        raise ValueError(f"目标尺寸须为正数，得到 {width}×{height}")
    digest = sha256(svg).digest()
    key = (digest, width, height)
    cached = _raster_cache.get(key)
    if cached is not None:
        return cached
    prepared = _prepare_svg(svg, digest)
    surface = skia.Surface(width, height)
    with surface as canvas:
        canvas.scale(width / prepared.width, height / prepared.height)
        canvas.drawPicture(prepared.picture)
    # 让 Skia 直接写入连续 RGBA，避免 NumPy 通道重排后再复制整幅图。
    image = surface.makeImageSnapshot().toarray(colorType=skia.ColorType.kRGBA_8888_ColorType)
    image.flags.writeable = False
    return _raster_cache.put(key, image, image.nbytes)
