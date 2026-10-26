"""内置矢量素材的栅格化。

素材 SVGDOM 在固有尺寸（设计像素 × 4）下渲染时才能正确应用 `<clipPath>`；
把容器缩放到其他尺寸时 skia 会把裁切区域算错（实测左侧被裁掉）。因此这里总是
先按 SVG 的固有尺寸渲染，再用 Lanczos 缩放到目标像素尺寸。
"""

from __future__ import annotations

import re

import numpy as np
import skia
from numpy.typing import NDArray
from PIL import Image

_SVG_SIZE = re.compile(r'<svg[^>]*\bwidth="([0-9.]+)"[^>]*\bheight="([0-9.]+)"')


def rasterize_svg(svg: bytes, width: int, height: int) -> NDArray[np.uint8]:
    """把透明 SVG 素材栅格化成 width × height 的 RGBA 图。

    Args:
        svg: SVG 文本字节；根节点须带 width/height。
        width: 目标像素宽。
        height: 目标像素高。

    Returns:
        (height, width, 4) uint8，脚在底端；透明区域 alpha 为 0。
    """
    if width <= 0 or height <= 0:
        raise ValueError(f"目标尺寸须为正数，得到 {width}×{height}")
    m = _SVG_SIZE.search(svg.decode("utf-8", errors="ignore"))
    if m is None:
        raise ValueError("SVG 根节点缺少 width/height")
    intrinsic_w, intrinsic_h = round(float(m.group(1))), round(float(m.group(2)))

    dom = skia.SVGDOM.MakeFromStream(skia.MemoryStream(svg))
    if dom is None:
        raise ValueError("无法解析 SVG")
    surface = skia.Surface(intrinsic_w, intrinsic_h)
    with surface as canvas:
        dom.setContainerSize(skia.Size(intrinsic_w, intrinsic_h))
        dom.render(canvas)
    # skia 的光栅缓冲是 BGRA，导出时换回 RGBA
    arr = surface.makeImageSnapshot().toarray()[:, :, [2, 1, 0, 3]].copy()

    if (intrinsic_w, intrinsic_h) != (width, height):
        arr = np.asarray(Image.fromarray(arr).resize((width, height), Image.Resampling.LANCZOS))
    return arr
