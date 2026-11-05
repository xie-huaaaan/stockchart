"""丝袜渲染算法：render_stocking 的实现。

算法内部在目标密度的图像像素空间中计算；公开参数与元数据使用设计像素；
坐标原点在图像左上角，y 轴向下。
渲染分三步：
  1. 计算腿的形状（alpha mask）与宽度剖面；
  2. 按 Fabric 种类生成 RGBA 纹理层；
  3. 叠加 Shading 光影，绘制上沿（TopEdge），合成到腿素材上。

各步骤的实现分散在同包的 geometry / shading / fabric / ink / edge 模块，
本模块只负责把它们串起来。
"""

from __future__ import annotations

import math
from dataclasses import replace
from typing import TYPE_CHECKING

import numpy as np
from numpy.typing import NDArray

from stockchart.stocking.edge import lace_wave, render_top_edge
from stockchart.stocking.fabric import render_fabric
from stockchart.stocking.geometry import column_profile, curve_dip
from stockchart.stocking.ink import boost_ink_lines
from stockchart.stocking.shading import (
    apply_shading,
    composite,
    downsample_rendered,
    render_shading,
    resample_leg,
    shade_bare_leg,
)
from stockchart.stocking.styles import Fade, Lace, StockingStyle, Welt, scale_style

if TYPE_CHECKING:
    from stockchart.legs import Leg


# 纹理在输出密度之上再按该倍率生成，然后降采样；只影响画质，不改变公开的 scale 语义。
_SUPERSAMPLE = 2


def render_stocking(
    leg: Leg,
    style: StockingStyle,
    height_px: int,
    *,
    seed: int | None = None,
    scale: float = 1.0,
) -> Leg:
    """给腿穿丝袜：从脚端向上覆盖 height_px 像素。

    Args:
        leg: 待渲染的腿素材。
        style: 丝袜样式，可从 STYLES 预设取得。
        height_px: 丝袜上沿到脚端的像素数（设计像素）。小于等于 0 时为裸腿
            （`Shading.skin` 大于 0 时裸腿仍按皮肤光影渲染，否则原样返回）；
            不小于 leg.height 时整腿全盖。
        seed: 纹理类随机效果的随机源。
        scale: 输出倍率。>1 时在 scale 倍像素空间里生成——袜身纹理、上沿、
            光影都是该分辨率的真细节，不是把成品放大；内置矢量素材按该倍率
            重新栅格化，外部位图素材先按比例重采样。
            纹理在内部再按 2 倍生成后降采样以改善硬边抗锯齿，这不改变返回
            图像的尺寸与 `pixels_per_unit`。
            返回的 Leg 图像为「设计尺寸 × scale」像素（`pixels_per_unit == scale`），
            `width` / `height` / `foot_center_x` 等元数据仍是设计像素，
            图层按 1:1 贴图即得到 scale 倍输出。

    Returns:
        新的 Leg：图像按 scale 倍密度重绘（`pixels_per_unit == scale`），
        设计像素元数据与原素材一致。

    Raises:
        ValueError: scale 不是正的有限数。
    """
    if not math.isfinite(scale) or scale <= 0:
        raise ValueError(f"scale 须为正数，得到 {scale}")

    # 输出密度的腿图：返回尺寸、alpha 轮廓与元数据都以它为准。
    output_leg = resample_leg(leg, scale)
    if height_px <= 0 and style.shading.skin <= 0:
        return output_leg

    # 纹理在更高的密度上生成，最后缩回输出密度。
    leg = resample_leg(leg, scale * _SUPERSAMPLE)
    density = leg.pixels_per_unit
    if density != 1.0:
        style = scale_style(style, density)
        height_px = round(height_px * density)

    if height_px <= 0:
        # 裸腿也要参与皮肤光影，否则同一张图里裸腿比穿袜腿少一层受光
        return downsample_rendered(shade_bare_leg(leg, style), output_leg, scale)

    H, W = leg.image.shape[:2]
    height_px = min(height_px, H)
    rng = np.random.default_rng(seed)

    src = leg.image.astype(np.float64) / 255.0  # (H, W, 4) float64 [0,1]

    # 腿的 alpha mask（0/1 float）
    alpha_mask = src[..., 3]  # (H, W)

    # 渲染区域：图像底部 height_px 行（脚在底部）
    y_start = H - height_px  # 袜口顶端所在行（含）

    # 袜口以上没有绘制内容时保留输出密度的原像素，避免整图重采样；
    # 余量覆盖袜口边线与抖动，皮肤光影开启时整条腿都会被修改。
    margin = 3 + math.ceil(style.shading.wobble * scale / density)
    content_top = (
        0 if style.shading.skin > 0 else min(H, max(0, round(y_start * scale / density) - margin))
    )

    # 每行腿的宽度剖面：用于圆柱透视压缩
    col_profile = column_profile(alpha_mask)  # (H, W) float，横向归一化坐标

    # 环形线条（横纹、袜口、蕾丝）的透视下弯量：中线最大、两侧缘为 0
    dip = curve_dip(col_profile, alpha_mask, style.shading.curve)

    # Lace 波形只计算一次，供图案裁剪与上沿绘制共用（保证相位一致）
    wave = lace_wave(style.top, y_start, dip, W, H, rng) if isinstance(style.top, Lace) else None

    # 上沿条带下沿（每列）：袜身图案从这条线起算，条带直接覆盖在皮肤上。
    # Welt 为条带底沿弧线；Lace 为波浪边缘；Bare / Fade 为袜口弧线本身。
    if isinstance(style.top, Welt):
        row = min(y_start + int(style.top.height), H - 1)
        origin_col = y_start + style.top.height + dip[row]  # (W,)
        pattern_offset = style.top.height
    elif isinstance(style.top, Lace):
        assert wave is not None
        origin_col = wave[0]
        pattern_offset = style.top.height
    else:
        origin_col = y_start + dip[min(y_start, H - 1)]
        pattern_offset = 0.0

    # 生成袜子 RGBA 纹理 (H, W, 4)，y_start 以上行全透明
    fabric_layer = render_fabric(
        style.fabric,
        src,
        alpha_mask,
        col_profile,
        y_start,
        H,
        W,
        rng,
        dip,
        pattern_offset,
    )

    # 织物沿条带下沿逐列裁剪：图案与上沿边缘处处贴合（Lace 沿波浪无缺口）
    ys_grid = np.arange(H, dtype=np.float64)[:, np.newaxis]  # (H, 1)
    fabric_layer[ys_grid < origin_col[np.newaxis, :]] = 0.0
    top_arc = y_start + dip  # (H, W) 袜口弧线

    # Fade：渐隐沿弧线自袜口顶端向下 length 像素内完成（顶端透明，底端全显）
    fade_ramp: NDArray[np.float64] | None = None
    if isinstance(style.top, Fade):
        ramp = np.clip((ys_grid - top_arc) / max(style.top.length, 1.0), 0.0, 1.0)
        fade_ramp = ramp
        fabric_layer[..., 3] *= ramp

    # 光影：袜身用全强度与冷色阴影；袜口以上的裸皮按 Shading.skin 强度并换成
    # 暖色阴影（冷紫落在皮肤上会显脏）。两层按覆盖率加权合并后一次应用。
    shading_layer, shading_hl = render_shading(style.shading, src, alpha_mask, col_profile, 0, H, W)
    skin = style.shading.skin
    above = ys_grid < top_arc
    if fade_ramp is None:
        w_sock = np.where(above, 0.0, 1.0)
        w_skin = np.where(above, skin, 0.0)
    else:
        # 渐隐区里袜子逐渐消失：光影由 sock 全强度过渡到裸皮的 skin 强度，
        # 避免袜口处出现一条阴影断层
        w_sock = np.where(above, 0.0, fade_ramp)
        w_skin = np.where(above, 1.0, 1.0 - fade_ramp) * skin
    if skin > 0:
        skin_layer, skin_hl = render_shading(
            replace(style.shading, shadow_color=style.shading.skin_shadow_color),
            src,
            alpha_mask,
            col_profile,
            0,
            H,
            W,
        )
        a_sock = shading_layer[..., 3:4] * w_sock[..., np.newaxis]
        a_skin = skin_layer[..., 3:4] * w_skin[..., np.newaxis]
        total = np.clip(a_sock + a_skin, 0.0, 1.0)
        safe = np.maximum(a_sock + a_skin, 1e-6)
        shading_layer[..., :3] = (
            shading_layer[..., :3] * a_sock + skin_layer[..., :3] * a_skin
        ) / safe
        shading_layer[..., 3:4] = total
        shading_hl = np.clip(shading_hl * w_sock + skin_hl * w_skin, 0.0, 1.0)
    else:
        shading_layer[..., 3] *= w_sock
        shading_hl *= w_sock

    # 合成：将腿皮肤与袜子融合（光影后置，使上沿条带同样受光）
    result = composite(src, fabric_layer, alpha_mask, y_start)

    # 绘制上沿
    result = render_top_edge(
        result,
        style.top,
        style.fabric,
        style.shading,
        alpha_mask,
        col_profile,
        y_start,
        H,
        W,
        rng,
        dip,
        wave,
    )

    # 应用光影：在条带绘制之后，袜口/蕾丝与袜身统一受光
    result = apply_shading(result, shading_layer, shading_hl)

    # 膝盖褶皱等素材内部墨线增强：以"织物压痕"的方式补画到袜子上
    result = boost_ink_lines(
        result,
        src,
        alpha_mask,
        col_profile,
        style.fabric,
        style.shading,
        fabric_layer,
        ys_grid,
        top_arc,
        y_start,
        density,
    )

    out = (np.clip(result, 0.0, 1.0) * 255.0).astype(np.uint8)

    return downsample_rendered(replace(leg, image=out), output_leg, scale, content_top=content_top)
