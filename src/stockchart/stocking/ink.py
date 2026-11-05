"""仅在素材预处理发现的稀疏墨线上增强织物褶痕。"""

from __future__ import annotations

import numpy as np

from stockchart.color import color_rgb
from stockchart.legs import Leg
from stockchart.stocking.fabric import fabric_plain
from stockchart.stocking.pixels import FloatArray
from stockchart.stocking.preprocess import ink_pixels
from stockchart.stocking.styles import Fabric, Fishnet, Shading


def boost_ink_lines(
    img: FloatArray,
    leg: Leg,
    u: FloatArray,
    fabric: Fabric,
    sh: Shading,
    fabric_layer: FloatArray,
    top_arc: FloatArray,
    y0: int,
) -> FloatArray:
    """在有织物覆盖的墨线像素上混色，裸腿与无底袜网袜不参与增强。

    深色织物的线条提亮为冷灰色，浅色织物的线条按素材原始深浅压暗。
    """
    if sh.ink <= 0 or (isinstance(fabric, Fishnet) and fabric.underlay is None):
        return img
    pixels = ink_pixels(leg)
    ys, xs = pixels.ys, pixels.xs
    if ys.size == 0:
        return img
    coverage = fabric_layer[..., 3]
    if isinstance(fabric, Fishnet) and fabric.underlay is not None:
        height, width = img.shape[:2]
        coverage = fabric_plain(fabric.underlay, img, img[..., 3], u, y0, height, width)[..., 3]
    weight = pixels.weight * sh.ink * coverage[ys, xs]
    active = (ys >= top_arc[ys, xs]) & (weight > 0.01)
    ys, xs = ys[active], xs[active]
    if ys.size == 0:
        return img
    weight = np.clip(weight[active], 0.0, 0.85)[:, None]
    current = img[ys, xs, :3]
    fabric_lum = fabric_layer[ys, xs, :3] @ np.array([0.299, 0.587, 0.114], np.float32)
    darkness = np.clip(1.0 - fabric_lum * 2.0, 0.0, 1.0)[:, None]
    screen = 1.0 - (1.0 - current) * (1.0 - color_rgb(sh.shadow_color))
    mult = current * pixels.depth[active, None]
    boosted = screen * darkness + mult * (1.0 - darkness)
    img[ys, xs, :3] = current * (1.0 - weight) + boosted * weight
    return img
