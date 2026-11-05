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

from stockchart.stocking.edge import lace_wave, render_top_edge
from stockchart.stocking.fabric import fabric_plain, render_fabric
from stockchart.stocking.geometry import curve_dip
from stockchart.stocking.ink import boost_ink_lines
from stockchart.stocking.pixels import FloatArray
from stockchart.stocking.preprocess import prepare_leg
from stockchart.stocking.shading import (
    apply_lighting,
    composite,
    resample_leg,
    shade_bare_leg,
)
from stockchart.stocking.styles import Fade, Fishnet, Lace, StockingStyle, Welt, scale_style

if TYPE_CHECKING:
    from stockchart.legs import Leg


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

    # 直接在输出密度生成纹理，避免额外超采样和整条腿的降采样。
    leg = resample_leg(leg, scale)
    if height_px <= 0 and style.shading.skin <= 0:
        return leg

    density = leg.pixels_per_unit
    if density != 1.0:
        style = scale_style(style, density)
        height_px = round(height_px * density)

    if height_px <= 0:
        # 裸腿也要参与皮肤光影，否则同一张图里裸腿比穿袜腿少一层受光
        return shade_bare_leg(leg, style)

    H, W = leg.image.shape[:2]
    height_px = min(height_px, H)
    rng = np.random.default_rng(seed)

    prepared = prepare_leg(leg)
    src = prepared.src

    # 腿的 alpha mask（0/1 float）
    alpha_mask = src[..., 3]  # (H, W)

    # 渲染区域：图像底部 height_px 行（脚在底部）
    y_start = H - height_px  # 袜口顶端所在行（含）

    # 每行腿的宽度剖面：用于圆柱透视压缩
    col_profile = prepared.u

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
    ys_grid = np.arange(H, dtype=np.float32)[:, np.newaxis]  # (H, 1)
    fabric_layer[ys_grid < origin_col[np.newaxis, :]] = 0.0
    top_arc = y_start + dip  # (H, W) 袜口弧线

    # Fade：渐隐沿弧线自袜口顶端向下 length 像素内完成（顶端透明，底端全显）
    fade_ramp: FloatArray | None = None
    if isinstance(style.top, Fade):
        ramp = np.clip((ys_grid - top_arc) / max(style.top.length, 1.0), 0.0, 1.0)
        fade_ramp = ramp
        fabric_layer[..., 3] *= ramp

    # 仅保留袜身权重，冷暖阴影与高光在上沿之后共用一次几何计算。
    above = ys_grid < top_arc
    w_sock = (~above).astype(np.float32) if fade_ramp is None else np.where(above, 0.0, fade_ramp)

    # 合成：将腿皮肤与袜子融合（光影后置，使上沿条带同样受光）
    result = composite(src, fabric_layer, alpha_mask, y_start)

    # 合成后复用纹理层记录实际材质：网眼只增强底袜，上沿则独立参与增强。
    if style.shading.ink > 0 and isinstance(style.fabric, Fishnet):
        if style.fabric.underlay is None:
            fabric_layer[..., 3] = 0.0
        else:
            underlay = fabric_plain(
                style.fabric.underlay, src, alpha_mask, col_profile, y_start, H, W
            )
            fabric_layer[..., 3] = underlay[..., 3]
            fabric_layer[ys_grid < origin_col[np.newaxis, :]] = 0.0
            if fade_ramp is not None:
                fabric_layer[..., 3] *= fade_ramp

    # 绘制上沿
    result = render_top_edge(
        result,
        fabric_layer if style.shading.ink > 0 else None,
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
    result = apply_lighting(result, style.shading, col_profile, prepared.rim, w_sock)

    # 膝盖褶皱等素材内部墨线增强：以"织物压痕"的方式补画到袜子上
    result = boost_ink_lines(result, leg, style.shading, fabric_layer)

    out = (np.clip(result, 0.0, 1.0) * 255.0).astype(np.uint8)
    # 织物与光影只改变 RGB，轮廓覆盖率直接保留素材像素，避免浮点量化漂移。
    out[..., 3] = leg.image[..., 3]
    return replace(leg, image=out)
