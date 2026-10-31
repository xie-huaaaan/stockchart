"""内置矢量素材的栅格化。

SVG 的容器尺寸必须保持固有尺寸，`clipPath` 才能正确应用；把容器缩放到其他
尺寸时 skia 会把裁切区域算错（实测左侧被裁掉）。因此渲染到目标尺寸时改为
缩放画布，让矢量路径（含裁切）按目标分辨率重新光栅化。
"""

from __future__ import annotations

import re

import numpy as np
import skia
from numpy.typing import NDArray

_SVG_SIZE = re.compile(r'<svg[^>]*\bwidth="([0-9.]+)"[^>]*\bheight="([0-9.]+)"')


def rasterize_svg(svg: bytes, width: int, height: int) -> NDArray[np.uint8]:
    """把透明 SVG 素材直接栅格化为指定像素尺寸的 RGBA 图。

    容器尺寸保持 SVG 固有尺寸，只缩放画布，以绕开 skia 在缩放容器时的
    `clipPath` 计算错误；矢量路径因此按目标分辨率重新光栅化。

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
    m = _SVG_SIZE.search(svg.decode("utf-8", errors="ignore"))
    if m is None:
        raise ValueError("SVG 根节点缺少 width/height")
    intrinsic_w, intrinsic_h = round(float(m.group(1))), round(float(m.group(2)))
    if intrinsic_w <= 0 or intrinsic_h <= 0:
        raise ValueError(f"SVG 固有尺寸须为正数，得到 {intrinsic_w}×{intrinsic_h}")

    dom = skia.SVGDOM.MakeFromStream(skia.MemoryStream(svg))
    if dom is None:
        raise ValueError("无法解析 SVG")
    surface = skia.Surface(width, height)
    with surface as canvas:
        dom.setContainerSize(skia.Size(intrinsic_w, intrinsic_h))
        canvas.scale(width / intrinsic_w, height / intrinsic_h)
        dom.render(canvas)
    # skia 的光栅缓冲是 BGRA，导出时换回 RGBA
    return surface.makeImageSnapshot().toarray()[:, :, [2, 1, 0, 3]].copy()
