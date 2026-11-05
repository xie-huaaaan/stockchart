"""素材墨线增强：把膝盖褶皱等素材内部线条补画到袜身上。

以“织物压痕”的方式重建暗线，比直接提亮原素材更可控；
判定暗线需要织物的素色底，因此依赖 fabric 模块。
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from stockchart.color import color_rgb
from stockchart.stocking.fabric import fabric_plain
from stockchart.stocking.styles import Fabric, Fishnet, Shading

_LUM_WEIGHTS = np.array([0.299, 0.587, 0.114])


def _luminance(rgb: NDArray[np.float64]) -> NDArray[np.float64]:
    """按 ITU-R 601 权重把 RGB 转为亮度。

    Args:
        rgb: (..., 3) 的归一化 RGB。

    Returns:
        去掉最后一维的亮度数组。
    """
    return rgb @ _LUM_WEIGHTS


def _ink_mask(
    src: NDArray[np.float64],
    alpha: NDArray[np.float64],
    scale: float = 1.0,
) -> NDArray[np.float64]:
    """检测素材内部的手绘线条（膝盖褶皱等），返回软掩码。

    以肤色亮度的 90 分位为基准，亮度低于基准 0.05 开始、0.18 达到全强度；
    排除 alpha 边缘约 3px 环带（轮廓线不参与，避免与侧缘阴影叠加），并做
    轻微模糊保持手绘感。

    Args:
        src: (H, W, 4) 归一化腿图。
        alpha: (H, W) 腿的 alpha 覆盖。
        scale: 当前渲染密度；腐蚀窗口与模糊半径按此放大。

    Returns:
        (H, W) 的 [0, 1] 软掩码；无覆盖或无暗线时全零。
    """
    from PIL import Image, ImageFilter

    lum = _luminance(src[..., :3])
    covered = alpha > 0.5
    if not covered.any():
        return np.zeros_like(lum)
    skin_lum = float(np.percentile(lum[covered], 90))
    t_start, t_full = skin_lum - 0.05, skin_lum - 0.18
    if t_full >= t_start:
        return np.zeros_like(lum)

    ink = np.clip((t_start - lum) / (t_start - t_full), 0.0, 1.0)

    # 排除轮廓：对腿 mask 做约 3px 腐蚀（窗口随倍率放大，保持相对宽度）
    win = max(3, 2 * round(3 * scale) + 1)
    leg_u8 = (alpha > 0.05).astype(np.uint8) * 255
    interior = (
        np.asarray(Image.fromarray(leg_u8).filter(ImageFilter.MinFilter(win))).astype(np.float64)
        / 255.0
    )
    ink *= interior

    # 轻微模糊（半径同样按倍率放大）
    ink_img = Image.fromarray((ink * 255).astype(np.uint8))
    ink = (
        np.asarray(ink_img.filter(ImageFilter.GaussianBlur(0.8 * scale))).astype(np.float64) / 255.0
    )
    return ink


def boost_ink_lines(
    img: NDArray[np.float64],
    src: NDArray[np.float64],
    alpha: NDArray[np.float64],
    u: NDArray[np.float64],
    fabric: Fabric,
    sh: Shading,
    fabric_layer: NDArray[np.float64],
    ys_grid: NDArray[np.float64],
    top_arc: NDArray[np.float64],
    y0: int,
    scale: float = 1.0,
) -> NDArray[np.float64]:
    """把素材自带的内部墨线以织物褶痕的形式补画到袜子上。

    线条颜色跟随袜色：深色织物上用 screen 提亮为冷灰线（动漫黑丝的画法），
    浅色织物上按原线条深度比 multiply 压暗。强度由 `Shading.ink` 控制，并按
    局部织物不透明度加权——裸腿处不增强。

    Args:
        img: (H, W, 4) 已合成的图像；原地修改并返回。
        src: (H, W, 4) 归一化腿图，用于检测原始墨线。
        alpha: (H, W) 腿的 alpha 覆盖。
        u: (H, W) 横向归一化坐标，供底袜覆盖率计算。
        fabric: 袜身种类；渔网只增强底袜部分。
        sh: 光影参数；`ink <= 0` 时直接返回。
        fabric_layer: (H, W, 4) 袜身纹理层，用于判断织物深浅与覆盖率。
        ys_grid: (H, 1) 行坐标，用于排除袜口弧线以上的区域。
        top_arc: (H, W) 袜口弧线。
        y0: 袜子区域起始行。
        scale: 当前渲染密度；传给墨线掩码做窗口缩放。

    Returns:
        修改后的图像。
    """
    if sh.ink <= 0:
        return img

    ink = _ink_mask(src, alpha, scale)
    if not (ink > 0.01).any():
        return img

    H, W = alpha.shape
    # 增强只发生在袜子区域内，且按织物覆盖率加权
    coverage = fabric_layer[..., 3]
    if isinstance(fabric, Fishnet):
        # 网孔直接透出皮肤线，只对底袜部分增强，避免碎线
        if fabric.underlay is not None:
            coverage = fabric_plain(fabric.underlay, src, alpha, u, y0, H, W)[..., 3]
        else:
            return img

    w = ink * sh.ink * coverage
    w *= (ys_grid >= top_arc).astype(np.float64)  # 弧线之上不增强
    if not (w > 0.01).any():
        return img
    w = np.clip(w, 0.0, 0.85)[..., np.newaxis]

    # 原线条的深度比（相对肤色），用于浅色织物的压暗
    lum = _luminance(src[..., :3])
    covered = alpha > 0.5
    skin_lum = float(np.percentile(lum[covered], 90))
    f_local = np.clip(lum / max(skin_lum, 1e-6), 0.3, 1.0)[..., np.newaxis]

    current = img[..., :3]
    fab_lum = _luminance(fabric_layer[..., :3])
    darkness = np.clip(1.0 - fab_lum * 2.0, 0.0, 1.0)[..., np.newaxis]

    shadow_rgb = color_rgb(sh.shadow_color)
    screen_c = 1.0 - (1.0 - current) * (1.0 - shadow_rgb)  # 深色织物：提亮为冷灰线
    mult_c = current * f_local  # 浅色织物：压暗

    boosted = screen_c * darkness + mult_c * (1.0 - darkness)
    img[..., :3] = current * (1.0 - w) + boosted * w
    return img
