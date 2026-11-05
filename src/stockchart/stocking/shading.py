"""光影与合成：明暗层计算、与素材的混合，以及重采样。

光影按“袜身全强度 + 袜口以上裸皮按 skin 强度”两层计算后加权合并，
最后在袜口条带绘制之后统一应用，保证袜口与袜身受光一致。
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

import numpy as np
from numpy.typing import NDArray
from PIL import Image

from stockchart.color import color_alpha, color_rgb
from stockchart.stocking.geometry import column_profile
from stockchart.stocking.styles import Shading, StockingStyle

if TYPE_CHECKING:
    from stockchart.legs import Leg


def render_shading(
    sh: Shading,
    src: NDArray[np.float64],
    alpha: NDArray[np.float64],
    u: NDArray[np.float64],
    y0: int,
    H: int,
    W: int,
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """生成光影覆盖层。

    边缘阴影使用正片叠底（multiply），高光使用屏幕（screen）。阴影色与阴影
    强度放在 RGBA 层里，高光强度单独返回，避免复用颜色通道造成串色。

    Args:
        sh: 光影参数。
        src: (H, W, 4) 归一化腿图；本实现不读取，保留统一签名。
        alpha: (H, W) 腿的 alpha 覆盖。
        u: (H, W) 横向归一化坐标。
        y0: 袜子区域起始行。
        H: 图像高。
        W: 图像宽。

    Returns:
        `(shadow_layer, highlight)`：shadow_layer 为 (H, W, 4)，RGB 是阴影色、
        alpha 是阴影强度；highlight 为 (H, W) 的 [0, 1] 高光强度。
    """
    layer = np.zeros((H, W, 4), dtype=np.float64)
    highlight = np.zeros((H, W), dtype=np.float64)

    if sh.rim_shadow <= 0 and sh.highlight <= 0:
        return layer, highlight

    shadow_rgb = color_rgb(sh.shadow_color)
    shadow_a_base = color_alpha(sh.shadow_color)

    cos_u = np.sqrt(np.maximum(1.0 - u**2, 0.0))  # (H, W)

    # 边缘阴影：cos_u → 0 时最深
    rim = (1.0 - cos_u) ** 1.5  # 让阴影更集中于极侧缘
    shadow_a = sh.rim_shadow * shadow_a_base * rim

    # 高光：在 highlight_pos 附近的竖向高亮条
    hl_u = (u - sh.highlight_pos) / max(sh.highlight_width, 0.01)
    hl = np.exp(-0.5 * hl_u**2)  # 高斯形高光
    hl_a = sh.highlight * hl

    if sh.cel_steps >= 2:
        # 分阶：将连续阴影量化为 cel_steps + 1 阶
        steps = sh.cel_steps
        shadow_a = np.round(shadow_a * steps) / steps
        hl_a = np.round(hl_a * steps) / steps

    layer[..., :3] = shadow_rgb
    layer[..., 3] = shadow_a
    in_leg = alpha > 0.05
    layer[:y0] = 0.0
    layer[~in_leg] = 0.0
    highlight = hl_a.copy()
    highlight[:y0] = 0.0
    highlight[~in_leg] = 0.0
    return layer, highlight


def alpha_over(dst: NDArray[np.float64], src_: NDArray[np.float64]) -> NDArray[np.float64]:
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
    src_leg: NDArray[np.float64],
    fabric: NDArray[np.float64],
    alpha: NDArray[np.float64],
    y0: int,
) -> NDArray[np.float64]:
    """把腿皮肤与袜身纹理合成为 RGBA。

    袜口以上保留原腿；光影由 `apply_shading` 在后续步骤应用。

    Args:
        src_leg: (H, W, 4) 归一化腿图。
        fabric: (H, W, 4) 袜身纹理层。
        alpha: (H, W) 腿的 alpha 覆盖；本实现不读取，保留统一签名。
        y0: 袜子区域起始行。

    Returns:
        (H, W, 4) 合成结果。
    """
    result = src_leg.copy()

    fa = fabric[..., 3:4]  # 袜子 alpha (H,W,1)
    frgb = fabric[..., :3]  # 袜子 RGB

    leg_rgb = src_leg[..., :3]
    blended_rgb = frgb * fa + leg_rgb * (1.0 - fa)
    blended_rgb = np.clip(blended_rgb, 0.0, 1.0)

    H, W = src_leg.shape[:2]
    mask = np.zeros((H, W, 1), dtype=np.float64)
    mask[y0:] = 1.0

    result[..., :3] = blended_rgb * mask + leg_rgb * (1.0 - mask)
    return result


def _resize_rgba(
    image: NDArray[np.uint8],
    width: int,
    height: int,
    *,
    resample: Image.Resampling,
) -> NDArray[np.uint8]:
    """按预乘 alpha 缩放 RGBA。

    先乘 alpha 再插值，避免透明区的黑色被拉进边缘形成暗边；通道以浮点
    缩放，避免预乘后先量化到 8 位造成低透明度区域的色带。

    Args:
        image: (H, W, 4) uint8 RGBA。
        width: 目标宽。
        height: 目标高。
        resample: PIL 重采样算法。

    Returns:
        (height, width, 4) uint8 RGBA。
    """

    def resize_float(channel: NDArray[np.float64]) -> NDArray[np.float64]:
        """把单通道浮点图缩放为目标尺寸。"""
        img = Image.fromarray(channel.astype(np.float32), mode="F")
        return np.asarray(img.resize((width, height), resample), dtype=np.float64)

    src = image.astype(np.float64) / 255.0
    alpha = src[..., 3]
    premultiplied = src[..., :3] * alpha[..., np.newaxis]
    rgb = np.stack([resize_float(premultiplied[..., i]) for i in range(3)], axis=-1)
    a = resize_float(alpha)
    rgb /= np.maximum(a[..., np.newaxis], 1e-6)
    out = np.dstack([np.clip(rgb, 0.0, 1.0), np.clip(a, 0.0, 1.0)[..., np.newaxis]])
    return (out * 255).round().astype(np.uint8)


def downsample_rendered(
    leg: Leg,
    output_leg: Leg,
    density: float,
    *,
    content_top: int = 0,
) -> Leg:
    """把超采样渲染结果缩到输出密度。

    轮廓 alpha 直接沿用输出密度的腿图，避免边缘漂移；袜口以上不参与重采样。

    Args:
        leg: 当前超采样密度下的渲染结果。
        output_leg: 输出密度的参考腿图，提供尺寸与轮廓 alpha。
        density: 输出密度（像素 / 设计像素）。
        content_top: 该行以上的像素直接复制 output_leg；0 表示不保留。

    Returns:
        输出密度下的 Leg。
    """
    height, width = output_leg.image.shape[:2]
    if leg.image.shape[:2] == (height, width):
        image = leg.image.copy()
    else:
        image = _resize_rgba(leg.image, width, height, resample=Image.Resampling.LANCZOS)
    alpha = output_leg.image[..., 3]
    # 超采样 alpha 在轮廓最外侧可能已为 0，而输出密度仍有覆盖率；
    # 这些像素没有可用的织物颜色，用原腿颜色补齐，避免出现黑边。
    empty = (image[..., 3] == 0) & (alpha > 0)
    image[empty, :3] = output_leg.image[empty, :3]
    image[..., 3] = alpha
    if content_top > 0:
        image[:content_top] = output_leg.image[:content_top]
    return replace(leg, image=image, pixels_per_unit=density)


def resample_leg(leg: Leg, density: float) -> Leg:
    """把腿图重采样到指定密度，元数据仍是设计像素。

    内置矢量素材按目标密度重新栅格化；外部位图素材比目标更密时降采样，
    否则升采样。位图使用预乘 alpha 插值，避免透明边缘出现暗边。

    Args:
        leg: 原始腿素材。
        density: 目标像素 / 设计像素。

    Returns:
        图像为目标密度、`pixels_per_unit == density` 的新 Leg。
    """
    if leg.svg is not None:
        return leg.at_density(density)
    if abs(leg.pixels_per_unit - density) < 1e-9:
        return leg
    h_img, w_img = leg.image.shape[:2]
    h2 = max(1, round(h_img * density / leg.pixels_per_unit))
    w2 = max(1, round(w_img * density / leg.pixels_per_unit))

    # 降采样用 Lanczos（保细节），升采样用双三次（避免振铃）
    resample = (
        Image.Resampling.LANCZOS if density < leg.pixels_per_unit else Image.Resampling.BICUBIC
    )
    return replace(
        leg,
        image=_resize_rgba(leg.image, w2, h2, resample=resample),
        pixels_per_unit=density,
    )


def shade_bare_leg(leg: Leg, style: StockingStyle) -> Leg:
    """给裸腿整体打上皮肤光影（不画袜子）。

    Args:
        leg: 当前渲染密度下的腿图。
        style: 样式参数；使用 shading.skin 与暖色皮肤阴影。

    Returns:
        光照后的 Leg。
    """
    H, W = leg.image.shape[:2]
    src = leg.image.astype(np.float64) / 255.0
    alpha = src[..., 3]
    prof = column_profile(alpha)
    sh = style.shading
    shadow, highlight = render_shading(
        replace(sh, shadow_color=sh.skin_shadow_color), src, alpha, prof, 0, H, W
    )
    shadow[..., 3] *= sh.skin
    highlight *= sh.skin
    out = apply_shading(src.copy(), shadow, highlight)
    return replace(leg, image=(np.clip(out, 0.0, 1.0) * 255.0).astype(np.uint8))


def apply_shading(
    img: NDArray[np.float64],
    shadow: NDArray[np.float64],
    highlight: NDArray[np.float64],
) -> NDArray[np.float64]:
    """对合成结果应用光影。

    边缘阴影按正片叠底压暗，竖向高光按 screen 提亮；在上沿条带绘制之后调用，
    使袜口与蕾丝同样受光。

    Args:
        img: (H, W, 4) 归一化图像；原地修改并返回。
        shadow: (H, W, 4) 阴影层：RGB 为阴影色，alpha 为阴影强度。
        highlight: (H, W) 高光强度。

    Returns:
        修改后的图像。
    """
    sh_a = shadow[..., 3:4]
    sh_rgb = shadow[..., :3]

    # 正片叠底阴影：shadow_rgb 通常偏冷，乘在当前颜色上
    mul = img[..., :3] * sh_rgb
    img[..., :3] = img[..., :3] * (1.0 - sh_a) + mul * sh_a

    # screen 高光（白色）：提亮
    img[..., :3] = img[..., :3] + (1.0 - img[..., :3]) * highlight[..., np.newaxis]
    return img
