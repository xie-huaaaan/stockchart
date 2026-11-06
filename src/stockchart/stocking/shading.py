"""光影与合成：明暗层计算、与素材的混合，以及重采样。

袜身与裸皮共用一次光照几何计算，在袜口条带绘制之后按各自权重直接混色，
保证袜口与袜身受光一致，避免建立两份完整的阴影 RGBA 图层。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from stockchart.color import color_alpha, color_rgb
from stockchart.stocking.pixels import FloatArray
from stockchart.stocking.styles import Shading, StockingStyle

if TYPE_CHECKING:
    from stockchart.legs import LegRender


def alpha_over(dst: FloatArray, src_: FloatArray) -> FloatArray:
    """按 Porter-Duff 'A over B' 合成两层 RGBA。

    Args:
        dst: 下层 RGBA。
        src_: 上层 RGBA。

    Returns:
        合成后的新 RGBA 数组。
    """
    a_src = src_[..., 3:4]
    a_dst = dst[..., 3:4]
    a_out = a_src + a_dst * (1.0 - a_src)
    rgb_out = np.where(
        a_out > 1e-8,
        (src_[..., :3] * a_src + dst[..., :3] * a_dst * (1.0 - a_src)) / np.maximum(a_out, 1e-8),
        0.0,
    )
    result = np.empty_like(dst)
    result[..., :3] = rgb_out
    result[..., 3] = a_out[..., 0]
    return result


def composite(
    src_leg: FloatArray,
    fabric: FloatArray,
    alpha: FloatArray,
    y0: int,
) -> FloatArray:
    """把腿皮肤与袜身纹理合成为 RGBA。

    袜口以上保留原腿；光影由 `apply_lighting` 在后续步骤应用。

    Args:
        src_leg: (H, W, 4) 归一化腿图。
        fabric: (H, W, 4) 袜身纹理层。
        alpha: (H, W) 腿的 alpha 覆盖；本实现不读取，保留统一签名。
        y0: 袜子区域起始行。

    Returns:
        (H, W, 4) 合成结果。
    """
    result = src_leg.copy()

    rgb = result[y0:, :, :3]
    rgb += (fabric[y0:, :, :3] - rgb) * fabric[y0:, :, 3:4]
    np.clip(rgb, 0.0, 1.0, out=rgb)
    return result


def apply_lighting(
    img: FloatArray,
    sh: Shading,
    u: FloatArray,
    rim: FloatArray,
    sock_weight: FloatArray,
) -> FloatArray:
    """一次生成光照几何，并直接在 RGB 上应用袜身与裸皮的不同光照。

    Args:
        img: 原地修改的 RGBA 图像。
        sh: 共同光影参数。
        u: 横向归一化坐标。
        rim: 素材预处理得到的侧缘阴影形状。
        sock_weight: 袜身的光照权重；其余部分按 skin 强度受光。

    Returns:
        已修改的图像。
    """
    if sh.rim_shadow <= 0 and sh.highlight <= 0:
        return img
    in_leg = img[..., 3] > 0.05
    skin_weight = (1.0 - sock_weight) * sh.skin
    sock_a = rim * (sh.rim_shadow * color_alpha(sh.shadow_color))
    skin_a = rim * (sh.rim_shadow * color_alpha(sh.skin_shadow_color))
    highlight = sh.highlight * np.exp(
        -0.5 * ((u - sh.highlight_pos) / max(sh.highlight_width, 0.01)) ** 2
    )
    if sh.cel_steps >= 2:
        sock_a = np.round(sock_a * sh.cel_steps) / sh.cel_steps
        skin_a = np.round(skin_a * sh.cel_steps) / sh.cel_steps
        highlight = np.round(highlight * sh.cel_steps) / sh.cel_steps
    sock_a *= sock_weight * in_leg
    skin_a *= skin_weight * in_leg
    total = sock_a + skin_a
    correction = np.minimum(total, 1.0) / np.maximum(total, 1e-6)
    highlight *= (sock_weight + skin_weight) * in_leg
    np.clip(highlight, 0.0, 1.0, out=highlight)
    sock_color = color_rgb(sh.shadow_color)
    skin_color = color_rgb(sh.skin_shadow_color)
    for channel in range(3):
        rgb = img[..., channel]
        rgb *= (
            1.0
            - (sock_a * (1.0 - sock_color[channel]) + skin_a * (1.0 - skin_color[channel]))
            * correction
        )
        rgb += (1.0 - rgb) * highlight
    return img


def shade_bare_leg(leg: LegRender, style: StockingStyle) -> LegRender:
    """给裸腿整体打上皮肤光影（不画袜子）。

    Args:
        leg: 当前渲染密度下的腿图。
        style: 样式参数；使用 shading.skin 与暖色皮肤阴影。

    Returns:
        光照后的 Leg。
    """
    from stockchart.legs import LegRender
    from stockchart.stocking.preprocess import prepare_leg

    prepared = prepare_leg(leg)
    out = apply_lighting(
        prepared.src.copy(),
        style.shading,
        prepared.u,
        prepared.rim,
        np.zeros(leg.image.shape[:2], dtype=np.float32),
    )
    image = (np.clip(out, 0.0, 1.0) * 255.0).astype(np.uint8)
    image[..., 3] = leg.image[..., 3]
    return LegRender(leg.source, image, leg.scale)
