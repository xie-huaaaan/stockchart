"""丝袜渲染算法：render_stocking 的实现。

算法内部在目标密度的图像像素空间中计算；公开参数与元数据使用设计像素；
坐标原点在图像左上角，y 轴向下。
渲染分三步：
  1. 计算腿的形状（alpha mask）与宽度剖面；
  2. 按 Fabric 种类生成 RGBA 纹理层；
  3. 叠加 Shading 光影，绘制上沿（TopEdge），合成到腿素材上。
"""

from __future__ import annotations

import math
from dataclasses import replace
from typing import TYPE_CHECKING

import numpy as np
from numpy.typing import NDArray
from PIL import Image

from stockchart.color import color_alpha, color_rgb
from stockchart.stocking.styles import (
    Bare,
    Dotted,
    Fabric,
    Fade,
    Fishnet,
    Lace,
    Plain,
    Ribbed,
    Shading,
    StockingStyle,
    Striped,
    Welt,
    scale_style,
)

if TYPE_CHECKING:
    from stockchart.legs import Leg


# 纹理在输出密度之上再按该倍率生成，然后降采样；只影响画质，不改变公开的 scale 语义。
_SUPERSAMPLE = 2


# ---------------------------------------------------------------------------
# 公开入口
# ---------------------------------------------------------------------------


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
    output_leg = _resample_leg(leg, scale)
    if height_px <= 0 and style.shading.skin <= 0:
        return output_leg

    # 纹理在更高的密度上生成，最后缩回输出密度。
    leg = _resample_leg(leg, scale * _SUPERSAMPLE)
    density = leg.pixels_per_unit
    if density != 1.0:
        style = scale_style(style, density)
        height_px = round(height_px * density)

    if height_px <= 0:
        # 裸腿也要参与皮肤光影，否则同一张图里裸腿比穿袜腿少一层受光
        return _downsample_rendered(_shade_bare_leg(leg, style), output_leg, scale)

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
    col_profile = _column_profile(alpha_mask)  # (H, W) float，横向归一化坐标

    # 环形线条（横纹、袜口、蕾丝）的透视下弯量：中线最大、两侧缘为 0
    dip = _curve_dip(col_profile, alpha_mask, style.shading.curve)

    # Lace 波形只计算一次，供图案裁剪与上沿绘制共用（保证相位一致）
    wave = _lace_wave(style.top, y_start, dip, W, H, rng) if isinstance(style.top, Lace) else None

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
    fabric_layer = _render_fabric(
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
    shading_layer, shading_hl = _render_shading(
        style.shading, src, alpha_mask, col_profile, 0, H, W
    )
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
        skin_layer, skin_hl = _render_shading(
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
    result = _composite(src, fabric_layer, alpha_mask, y_start)

    # 绘制上沿
    result = _render_top_edge(
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
    result = _apply_shading(result, shading_layer, shading_hl)

    # 膝盖褶皱等素材内部墨线增强：以"织物压痕"的方式补画到袜子上
    result = _boost_ink_lines(
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

    return _downsample_rendered(replace(leg, image=out), output_leg, scale, content_top=content_top)


# ---------------------------------------------------------------------------
# 素材墨线（膝盖褶皱等）增强
# ---------------------------------------------------------------------------

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


def _boost_ink_lines(
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
            coverage = _fabric_plain(fabric.underlay, src, alpha, u, y0, H, W)[..., 3]
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


# ---------------------------------------------------------------------------
# 辅助：列坐标剖面
# ---------------------------------------------------------------------------


def _column_profile(alpha: NDArray[np.float64]) -> NDArray[np.float64]:
    """为每个像素计算横向归一化坐标 u（−1 左缘，0 中线，1 右缘）。

    用每行的 alpha 覆盖范围动态估计腿宽，保证腿宽变化时（脚踝/大腿）u 坐标
    始终贴合当前截面；空行保持 0。

    Args:
        alpha: (H, W) 腿的 alpha 覆盖。

    Returns:
        (H, W) 的 u 坐标数组。
    """
    H, W = alpha.shape
    u = np.zeros_like(alpha)
    xs = np.arange(W, dtype=np.float64)
    for y in range(H):
        row = alpha[y]
        covered = np.where(row > 0.05)[0]
        if covered.size == 0:
            continue
        x_left, x_right = float(covered[0]), float(covered[-1])
        width = x_right - x_left
        if width < 1.0:
            continue
        u[y] = (xs - (x_left + x_right) * 0.5) / (width * 0.5)
    return u


def _curve_dip(
    u: NDArray[np.float64],
    alpha: NDArray[np.float64],
    curve: float,
) -> NDArray[np.float64]:
    """计算环形线条的透视下弯量（像素，正值向下）。

    圆柱在略微俯视时，横向环绕线呈弧线：腿中线处下垂最多、两侧缘为 0，
    下垂量与该行腿宽（局部半径）成正比。

    Args:
        u: (H, W) 横向归一化坐标。
        alpha: (H, W) 腿的 alpha 覆盖。
        curve: 弯曲强度；<= 0 时返回全零。

    Returns:
        (H, W) 的下弯量。
    """
    if curve <= 0:
        return np.zeros_like(u)
    half_w = (alpha > 0.05).sum(axis=1, keepdims=True) / 2.0  # (H, 1)
    return curve * half_w * (1.0 - u * u)


def _lace_wave(
    top: Lace,
    y0: int,
    dip: NDArray[np.float64] | None,
    W: int,
    H: int,
    rng: np.random.Generator,
) -> tuple[NDArray[np.float64], float, float, float]:
    """计算蕾丝波浪下沿的每列 y 坐标及波形参数。

    `wave_bot` 在 `(y0 + height ± 振幅)` 之间起伏，并计入条带下沿所在行的
    弧线下弯量；振幅约为 scallop 的 15%，使扇贝形圆缓。

    Args:
        top: 蕾丝上沿参数。
        y0: 蕾丝带顶端所在行。
        dip: (H, W) 弧线下弯量；None 表示不弯。
        W: 图像宽。
        H: 图像高。
        rng: 随机源，决定波浪相位。

    Returns:
        `(wave_bot, scallop, amplitude, phase)`：每列下沿 y、周期、振幅与相位。
    """
    scallop = max(top.scallop, 20.0)
    amplitude = min(scallop * 0.15, top.height * 0.25)
    phase = rng.uniform(0, scallop)
    dip_bot = dip[min(y0 + int(top.height), H - 1)] if dip is not None else np.zeros(W)
    wave_bot = (
        (y0 + top.height)
        + dip_bot
        + amplitude * np.sin(2 * math.pi * (np.arange(W, dtype=np.float64) + phase) / scallop)
    )
    wave_bot = np.clip(wave_bot, float(y0), float(H - 1))
    return wave_bot, scallop, amplitude, phase


# ---------------------------------------------------------------------------
# 袜身纹理生成
# ---------------------------------------------------------------------------


def _render_fabric(
    fabric: Fabric,
    src: NDArray[np.float64],
    alpha: NDArray[np.float64],
    u: NDArray[np.float64],
    y_start: int,
    H: int,
    W: int,
    rng: np.random.Generator,
    dip: NDArray[np.float64] | None = None,
    pattern_offset: float = 0.0,
) -> NDArray[np.float64]:
    """生成袜身 RGBA 纹理层。

    Args:
        fabric: 袜身种类。
        src: (H, W, 4) 归一化腿图。
        alpha: (H, W) 腿的 alpha 覆盖。
        u: (H, W) 横向归一化坐标。
        y_start: 袜子区域起始行；以上行清零。
        H: 图像高。
        W: 图像宽。
        rng: 随机源，供散布类图案使用。
        dip: (H, W) 环形图案的透视下弯量；None 表示不弯。
        pattern_offset: 上沿条带高度；图案相位从条带下沿起算。

    Returns:
        (H, W, 4) float64 RGBA 层；袜口以上与腿外均为全透明。
    """
    layer = np.zeros((H, W, 4), dtype=np.float64)

    if isinstance(fabric, Plain):
        layer = _fabric_plain(fabric, src, alpha, u, y_start, H, W)
    elif isinstance(fabric, Striped):
        layer = _fabric_striped(fabric, src, alpha, u, y_start, H, W, dip, pattern_offset)
    elif isinstance(fabric, Ribbed):
        layer = _fabric_ribbed(fabric, src, alpha, u, y_start, H, W)
    elif isinstance(fabric, Fishnet):
        layer = _fabric_fishnet(fabric, src, alpha, u, y_start, H, W, rng, dip)
    else:
        layer = _fabric_dotted(fabric, src, alpha, u, y_start, H, W, rng, dip, pattern_offset)

    # 渲染区外清零
    layer[:y_start] = 0.0
    # 腿以外的像素不覆盖
    layer[alpha < 0.05] = 0.0
    return layer


def _fabric_plain(
    f: Plain,
    src: NDArray[np.float64],
    alpha: NDArray[np.float64],
    u: NDArray[np.float64],
    y0: int,
    H: int,
    W: int,
) -> NDArray[np.float64]:
    """生成纯色袜纹理：不透明度随圆柱曲率和腿截面宽度变化。

    Args:
        f: 纯色袜参数。
        src: 归一化腿图；本实现不读取，保留统一签名。
        alpha: (H, W) 腿的 alpha 覆盖。
        u: (H, W) 横向归一化坐标。
        y0: 袜子区域起始行。
        H: 图像高。
        W: 图像宽。

    Returns:
        (H, W, 4) RGBA 层。
    """
    layer = np.zeros((H, W, 4), dtype=np.float64)
    rgb = color_rgb(f.color)  # (3,)
    base_a = f.opacity * color_alpha(f.color)

    # 圆柱 cos 衰减：|u| 接近 1 时是侧面，"透过"更多织物 → 更不透明
    cos_u = np.sqrt(np.maximum(1.0 - u**2, 0.0))  # (H, W)

    # rim：侧缘不透明度提升
    rim_boost = 1.0 - cos_u  # 0 中线，1 极侧缘
    a_map = base_a + (1.0 - base_a) * rim_boost * f.rim
    a_map = np.clip(a_map, 0.0, 1.0)

    # stretch：腿宽越大越薄（用 y 方向腿宽估计）
    if f.stretch > 0:
        xs = np.where(alpha > 0.05, 1, 0)
        row_w = xs.sum(axis=1, keepdims=True).astype(np.float64)  # (H,1)
        max_w = np.clip(row_w.max(), 1.0, None)
        stretch_factor = 1.0 - f.stretch * (row_w / max_w - 0.5)
        stretch_factor = np.clip(stretch_factor, 0.1, 1.0)
        a_map = a_map * stretch_factor

    a_map[:y0] = 0.0

    layer[..., :3] = rgb
    layer[..., 3] = a_map
    return layer


def _stripe_opacity_at_y(
    fabric: Striped, ys: NDArray[np.float64]
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """按每点相对条纹周期的位置计算颜色与不透明度。

    条带边界做约 1.2px 的亚像素软化，避免逐列相位取整产生阶梯锯齿。

    Args:
        fabric: 条纹袜参数。
        ys: (H, W) 已含相位偏移与下弯量的图案坐标。

    Returns:
        `(rgb, opacity)`：均为 (H, W, ...) 的 float64 数组。
    """
    period = sum(s.width for s in fabric.stripes)
    phase = (ys - fabric.offset) % period
    soft = min(1.2, period / 8.0)

    rgb = np.zeros((*ys.shape, 3), dtype=np.float64)
    opa = np.zeros(ys.shape, dtype=np.float64)
    w_sum = np.zeros(ys.shape, dtype=np.float64)
    acc = 0.0
    for stripe in fabric.stripes:
        center = acc + stripe.width / 2.0
        # 到条带中心的距离 → 软化的隶属度（边界处与相邻条带各约 0.5）
        w = np.clip(0.5 + (stripe.width / 2.0 - np.abs(phase - center)) / soft, 0.0, 1.0)
        rgb += w[..., np.newaxis] * color_rgb(stripe.color)
        opa += w * (stripe.opacity * color_alpha(stripe.color))
        w_sum += w
        acc += stripe.width

    good = w_sum > 1e-8
    rgb[good] /= w_sum[good][..., np.newaxis]
    opa[good] /= w_sum[good]
    return rgb, opa


def _fabric_striped(
    f: Striped,
    src: NDArray[np.float64],
    alpha: NDArray[np.float64],
    u: NDArray[np.float64],
    y0: int,
    H: int,
    W: int,
    dip: NDArray[np.float64] | None = None,
    pattern_offset: float = 0.0,
) -> NDArray[np.float64]:
    """生成横条纹袜纹理，相位从袜口条带下沿起算并沿弧线下弯。

    Args:
        f: 条纹袜参数。
        src: 归一化腿图；本实现不读取，保留统一签名。
        alpha: (H, W) 腿的 alpha 覆盖。
        u: (H, W) 横向归一化坐标。
        y0: 袜子区域起始行。
        H: 图像高。
        W: 图像宽。
        dip: (H, W) 下弯量；None 表示不弯。
        pattern_offset: 上沿条带高度。

    Returns:
        (H, W, 4) RGBA 层。
    """
    layer = np.zeros((H, W, 4), dtype=np.float64)
    ys_pat = np.arange(H, dtype=np.float64).reshape(H, 1) - y0 - pattern_offset
    if dip is not None:
        ys_pat = ys_pat - dip
    rgb_map, opa_map = _stripe_opacity_at_y(f, ys_pat)
    layer[..., :3] = rgb_map
    layer[..., 3] = opa_map
    layer[:y0] = 0.0
    return layer


def _fabric_ribbed(
    f: Ribbed,
    src: NDArray[np.float64],
    alpha: NDArray[np.float64],
    u: NDArray[np.float64],
    y0: int,
    H: int,
    W: int,
) -> NDArray[np.float64]:
    """生成竖罗纹纹理：用 cos 在 u 方向产生明暗交替的条纹。

    Args:
        f: 罗纹袜参数。
        src: 归一化腿图；本实现不读取，保留统一签名。
        alpha: (H, W) 腿的 alpha 覆盖。
        u: (H, W) 横向归一化坐标。
        y0: 袜子区域起始行。
        H: 图像高。
        W: 图像宽。

    Returns:
        (H, W, 4) RGBA 层。
    """
    layer = np.zeros((H, W, 4), dtype=np.float64)
    rgb = color_rgb(f.color)

    # 将 u（-1~1）映射到腿上的绝对像素列位置，决定罗纹频率
    # 腿最宽处（大腿）的半宽作为参考宽度
    row_half_w = np.where(alpha > 0.05, 1, 0).sum(axis=1) / 2.0  # (H,)
    # 按每行半宽还原到 "腿上绝对列坐标"
    abs_x = u * row_half_w[:, np.newaxis]  # (H, W)

    # cos 罗纹：每 rib_width 像素一个周期（双倍：一凸一凹）
    wave = np.cos(abs_x * (2 * math.pi / f.rib_width))
    # 明暗对比：中心值 1，振幅 depth
    brightness = 1.0 + f.depth * wave  # 1-depth ~ 1+depth

    layer[..., :3] = rgb * brightness[..., np.newaxis]
    layer[..., 3] = f.opacity * color_alpha(f.color)
    layer[:y0] = 0.0
    return layer


def _fishnet_mask(
    W_abs: NDArray[np.float64],
    ys: NDArray[np.float64],
    cell: float,
    line_w: float,
    angle_deg: float,
) -> NDArray[np.float64]:
    """在腿面绝对坐标中计算网线覆盖率。

    Args:
        W_abs: (H, W) 腿面横向绝对坐标。
        ys: (H, W) 已含下弯量的纵向坐标。
        cell: 网眼大小（像素）。
        line_w: 网线宽度（像素）。
        angle_deg: 网格旋转角度（度）。

    Returns:
        (H, W) 的 0/1 掩码：1 为网线，0 为网孔。
    """
    a = math.radians(angle_deg)
    cos_a, sin_a = math.cos(a), math.sin(a)
    # 旋转到网格坐标
    gx = W_abs * cos_a - ys * sin_a
    gy = W_abs * sin_a + ys * cos_a
    # 每个方向上离网线中心的距离（周期归一化到 [0, 1)）
    fx = (gx % cell) / cell  # 0~1
    fy = (gy % cell) / cell
    # 离网线最近的距离（格单位）
    dx = np.minimum(fx, 1.0 - fx) * cell
    dy = np.minimum(fy, 1.0 - fy) * cell
    # 两方向任一在线宽内则属于网线
    on_x = dx < line_w / 2
    on_y = dy < line_w / 2
    return (on_x | on_y).astype(np.float64)


def _fabric_fishnet(
    f: Fishnet,
    src: NDArray[np.float64],
    alpha: NDArray[np.float64],
    u: NDArray[np.float64],
    y0: int,
    H: int,
    W: int,
    rng: np.random.Generator,
    dip: NDArray[np.float64] | None = None,
) -> NDArray[np.float64]:
    """生成网袜纹理：网线不透明、网孔透明，可叠一层底袜。

    Args:
        f: 网袜参数。
        src: (H, W, 4) 归一化腿图，用于底袜。
        alpha: (H, W) 腿的 alpha 覆盖。
        u: (H, W) 横向归一化坐标。
        y0: 袜子区域起始行。
        H: 图像高。
        W: 图像宽。
        rng: 保留统一签名；当前实现不使用随机散布。
        dip: (H, W) 下弯量；None 表示不弯。

    Returns:
        (H, W, 4) RGBA 层。
    """
    layer = np.zeros((H, W, 4), dtype=np.float64)

    row_half_w = np.where(alpha > 0.05, 1, 0).sum(axis=1) / 2.0
    abs_x = u * row_half_w[:, np.newaxis]
    ys = np.arange(H, dtype=np.float64).reshape(H, 1) * np.ones((1, W))
    if dip is not None:
        ys = ys - dip

    net = _fishnet_mask(abs_x, ys, f.cell, f.line_width, f.angle)

    rgb = color_rgb(f.color)
    layer[..., :3] = rgb
    layer[..., 3] = net * color_alpha(f.color)

    # 底袜
    if f.underlay is not None:
        under = _fabric_plain(f.underlay, src, alpha, u, y0, H, W)
        # 先画底袜，再把网线叠上去
        layer = _alpha_over(under, layer)

    layer[:y0] = 0.0
    return layer


def _dot_mask(
    abs_x: NDArray[np.float64],
    ys: NDArray[np.float64],
    spacing: float,
    size: float,
    layout: str,
    shape: str,
    rng: np.random.Generator,
) -> NDArray[np.float64]:
    """生成印花图案的 alpha 掩码。

    Args:
        abs_x: (H, W) 腿面横向绝对坐标。
        ys: (H, W) 已含下弯量的纵向坐标。
        spacing: 图案中心间距（像素）。
        size: 图案尺寸（像素）。
        layout: "grid" 为错位网格，"scatter" 为确定性随机散布。
        shape: "dot" / "heart" / "star"。
        rng: 随机源；scatter 布局用它产生整幅图的散布相位，grid 布局不使用。

    Returns:
        (H, W) 的 0/1 掩码：1 在图案内，0 在图案外。
    """
    H, W = abs_x.shape

    if layout == "grid":
        # 错位网格：偶数行偏移半个间距
        row_idx = np.floor(ys / spacing).astype(int)
        offset = (row_idx % 2) * (spacing / 2)
        cx = (np.floor((abs_x - offset) / spacing) + 0.5) * spacing + offset
        cy = (row_idx + 0.5) * spacing
        dx = abs_x - cx
        dy = ys - cy
    else:  # scatter
        cell = spacing
        gi = np.floor(abs_x / cell).astype(int)
        gj = np.floor(ys / cell).astype(int)
        # 用 seed 派生一个整幅图的盐值，使同一 seed 可复现、不同 seed 图案不同
        salt = int(rng.integers(0, 0x1000000))
        seed_arr = ((gi * 1000003 + gj * 7919 + salt) & 0xFFFFFF).astype(np.uint32)
        mask32 = np.uint32(0xFFFFFF)
        # 每格 0~1 的伪随机偏移（确定性，不依赖 rng）
        raw_x = (seed_arr * np.uint32(0x5DEECE6D) + np.uint32(11)) & mask32
        raw_y = (seed_arr * np.uint32(0xDEADBEEF) + np.uint32(0x12345)) & mask32
        raw_x = raw_x.astype(np.float64)
        raw_y = raw_y.astype(np.float64)
        cx = (gi + 0.5) * cell + (raw_x / float(0xFFFFFF) - 0.5) * 0.6 * cell
        cy = (gj + 0.5) * cell + (raw_y / float(0xFFFFFF) - 0.5) * 0.6 * cell
        dx = abs_x - cx
        dy = ys - cy

    if shape == "dot":
        dist = np.sqrt(dx**2 + dy**2)
        mask = (dist < size).astype(np.float64)
    elif shape == "heart":
        # 标准心形：用参数方程近似
        # 归一化坐标，使心形高约为 size*2
        s = size * 1.2
        nx, ny = dx / s, -dy / s  # y 轴翻转使心形尖朝下
        # 心形判别式：(x^2+y^2-1)^3 - x^2*y^3 < 0
        val = (nx**2 + ny**2 - 1.0) ** 3 - nx**2 * ny**3
        mask = (val < 0).astype(np.float64)
    elif shape == "star":
        # 五角星（极坐标近似）
        theta = np.arctan2(dy, dx)
        r = np.sqrt(dx**2 + dy**2)
        # 五角星：在 5 个角方向 r_outer，5 个凹陷方向 r_inner
        r_star = size * (0.4 + 0.6 * np.abs(np.cos(2.5 * theta)))
        mask = (r < r_star).astype(np.float64)
    else:
        mask = np.zeros((H, W), dtype=np.float64)

    return mask


def _fabric_dotted(
    f: Dotted,
    src: NDArray[np.float64],
    alpha: NDArray[np.float64],
    u: NDArray[np.float64],
    y0: int,
    H: int,
    W: int,
    rng: np.random.Generator,
    dip: NDArray[np.float64] | None = None,
    pattern_offset: float = 0.0,
) -> NDArray[np.float64]:
    """生成印花袜纹理：底袜 + 图案叠加。

    图案行沿弧线下弯，相位从袜口条带下沿起算。

    Args:
        f: 印花袜参数。
        src: (H, W, 4) 归一化腿图，用于底袜。
        alpha: (H, W) 腿的 alpha 覆盖。
        u: (H, W) 横向归一化坐标。
        y0: 袜子区域起始行。
        H: 图像高。
        W: 图像宽。
        rng: 随机源，供散布类图案使用。
        dip: (H, W) 下弯量；None 表示不弯。
        pattern_offset: 上沿条带高度。

    Returns:
        (H, W, 4) RGBA 层。
    """
    base = _fabric_plain(f.base, src, alpha, u, y0, H, W)

    row_half_w = np.where(alpha > 0.05, 1, 0).sum(axis=1) / 2.0
    abs_x = u * row_half_w[:, np.newaxis]
    ys = (np.arange(H, dtype=np.float64) - y0 - pattern_offset).reshape(H, 1) * np.ones((1, W))
    if dip is not None:
        ys = ys - dip

    dot = _dot_mask(abs_x, ys, f.spacing, f.size, f.layout, f.shape, rng)

    dot_layer = np.zeros((H, W, 4), dtype=np.float64)
    dot_layer[..., :3] = color_rgb(f.color)
    dot_layer[..., 3] = dot * f.opacity * color_alpha(f.color)
    dot_layer[:y0] = 0.0

    return _alpha_over(base, dot_layer)


# ---------------------------------------------------------------------------
# 光影层
# ---------------------------------------------------------------------------


def _render_shading(
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


# ---------------------------------------------------------------------------
# 合成
# ---------------------------------------------------------------------------


def _alpha_over(dst: NDArray[np.float64], src_: NDArray[np.float64]) -> NDArray[np.float64]:
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


def _composite(
    src_leg: NDArray[np.float64],
    fabric: NDArray[np.float64],
    alpha: NDArray[np.float64],
    y0: int,
) -> NDArray[np.float64]:
    """把腿皮肤与袜身纹理合成为 RGBA。

    袜口以上保留原腿；光影由 `_apply_shading` 在后续步骤应用。

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

    先乘 alpha 再插值，避免透明区的黑色被拉进边缘形成暗边。

    Args:
        image: (H, W, 4) uint8 RGBA。
        width: 目标宽。
        height: 目标高。
        resample: PIL 重采样算法。

    Returns:
        (height, width, 4) uint8 RGBA。
    """
    src = image.astype(np.float64) / 255.0
    alpha = src[..., 3:4]
    premultiplied = src[..., :3] * alpha
    rgb = Image.fromarray((np.clip(premultiplied, 0, 1) * 255).round().astype(np.uint8)).resize(
        (width, height), resample
    )
    a = Image.fromarray((np.clip(alpha[..., 0], 0, 1) * 255).round().astype(np.uint8)).resize(
        (width, height), resample
    )
    out = np.dstack(
        [
            np.asarray(rgb).astype(np.float64) / 255.0,
            np.asarray(a).astype(np.float64)[..., np.newaxis] / 255.0,
        ]
    )
    out[..., :3] /= np.maximum(out[..., 3:4], 1e-6)
    return (np.clip(out, 0, 1) * 255).round().astype(np.uint8)


def _downsample_rendered(
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


def _resample_leg(leg: Leg, density: float) -> Leg:
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


def _shade_bare_leg(leg: Leg, style: StockingStyle) -> Leg:
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
    prof = _column_profile(alpha)
    sh = style.shading
    shadow, highlight = _render_shading(
        replace(sh, shadow_color=sh.skin_shadow_color), src, alpha, prof, 0, H, W
    )
    shadow[..., 3] *= sh.skin
    highlight *= sh.skin
    out = _apply_shading(src.copy(), shadow, highlight)
    return replace(leg, image=(np.clip(out, 0.0, 1.0) * 255.0).astype(np.uint8))


def _apply_shading(
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


# ---------------------------------------------------------------------------
# 上沿绘制
# ---------------------------------------------------------------------------


def _render_top_edge(
    img: NDArray[np.float64],
    top: Bare | Welt | Lace | Fade,
    fabric: Fabric,
    sh: Shading,
    alpha: NDArray[np.float64],
    u: NDArray[np.float64],
    y0: int,
    H: int,
    W: int,
    rng: np.random.Generator,
    dip: NDArray[np.float64] | None = None,
    wave: tuple[NDArray[np.float64], float, float, float] | None = None,
) -> NDArray[np.float64]:
    """在图像上原地绘制上沿效果。

    Bare 画细边线，Welt 画加厚条带，Lace 画波浪蕾丝；Fade 的渐隐已在织物
    alpha 中实现，此处不额外绘制。

    Args:
        img: (H, W, 4) 归一化图像；原地修改并返回。
        top: 上沿样式。
        fabric: 袜身种类，用于取主色。
        sh: 光影参数。
        alpha: (H, W) 腿的 alpha 覆盖。
        u: (H, W) 横向归一化坐标。
        y0: 袜口顶端所在行。
        H: 图像高。
        W: 图像宽。
        rng: 随机源，供边线抖动使用。
        dip: (H, W) 下弯量；None 表示不弯。
        wave: Lace 的预计算波形；非 Lace 时为 None。

    Returns:
        修改后的图像。
    """
    if isinstance(top, Bare):
        img = _draw_edge_line(img, alpha, _edge_base(y0, W, dip), sh, rng, color=(0.1, 0.1, 0.1))
    elif isinstance(top, Welt):
        img = _draw_welt(img, fabric, alpha, y0, H, W, top, sh, rng, dip)
    elif isinstance(top, Lace):
        assert wave is not None
        img = _draw_lace(img, fabric, alpha, y0, H, W, top, sh, rng, dip, wave)
    return img


def _edge_base(
    y0: int,
    W: int,
    dip: NDArray[np.float64] | None,
) -> NDArray[np.float64]:
    """计算上沿边线各列的基准 y。

    Args:
        y0: 袜口顶端所在行。
        W: 图像宽。
        dip: (H, W) 下弯量；None 表示不弯。

    Returns:
        长度为 W 的每列基准 y。
    """
    if dip is None:
        return np.full(W, float(y0))
    row = dip[min(max(y0, 0), dip.shape[0] - 1)]
    return y0 + row


def _fabric_main_color(fabric: Fabric) -> NDArray[np.float64]:
    """取袜身的主色（归一化 RGB）。

    Args:
        fabric: 袜身种类；条纹取第一条，印花取底袜颜色。

    Returns:
        长度为 3 的 RGB 数组。
    """
    if isinstance(fabric, Plain):
        return color_rgb(fabric.color)
    if isinstance(fabric, Striped) and fabric.stripes:
        return color_rgb(fabric.stripes[0].color)
    if isinstance(fabric, Ribbed):
        return color_rgb(fabric.color)
    if isinstance(fabric, Fishnet):
        return color_rgb(fabric.color)
    if isinstance(fabric, Dotted):
        return color_rgb(fabric.base.color)
    return np.array([0.1, 0.1, 0.1])


def _soft_cover(y: NDArray[np.float64], edge: NDArray[np.float64]) -> NDArray[np.float64]:
    """计算行坐标相对软边缘的覆盖率。

    二值判定会让斜向边界形成 1px 阶梯；按覆盖率取值等价于一次简单的抗锯齿。

    Args:
        y: 行坐标数组（可含批次维）。
        edge: 边缘坐标，与 y 同形或可广播。

    Returns:
        0–1 的覆盖率：edge 以上为 0、以下为 1，边界约 1px 过渡。
    """
    return np.clip(y - edge + 0.5, 0.0, 1.0)


def _smooth_wobble(
    rng: np.random.Generator,
    n: int,
    amplitude: float,
) -> NDArray[np.float64]:
    """生成低频起伏的抖动曲线，振幅约为 ±amplitude。

    逐列独立取噪声会让边线每列各跳 1–2px，看起来是毛刺；这里对白噪声平滑
    两次再归一化，得到相邻列连续变化的缓慢漂移。

    Args:
        rng: 随机源。
        n: 采样点数（通常为图像宽）。
        amplitude: 最大绝对偏移（像素）；<= 0 或 n=0 时返回全零。

    Returns:
        长度为 n 的抖动曲线。
    """
    if amplitude <= 0 or n == 0:
        return np.zeros(n)
    raw = rng.normal(0.0, 1.0, size=n)
    width = min(9, n)
    kernel = np.ones(width) / width
    for _ in range(2):
        raw = np.convolve(raw, kernel, mode="same")
    peak = float(np.abs(raw).max())
    if peak < 1e-9:
        return np.zeros(n)
    return raw / peak * amplitude


def _draw_edge_line(
    img: NDArray[np.float64],
    alpha: NDArray[np.float64],
    y_base: NDArray[np.float64],
    sh: Shading,
    rng: np.random.Generator,
    color: tuple[float, float, float] = (0.1, 0.1, 0.1),
) -> NDArray[np.float64]:
    """沿基准曲线画一条手绘边线。

    使用低频抖动与覆盖率软笔触，线宽约 1.5px，避免斜向处的阶梯锯齿。

    Args:
        img: (H, W, 4) 归一化图像；原地修改并返回。
        alpha: (H, W) 腿的 alpha 覆盖；腿外不画。
        y_base: 每列的基准 y。
        sh: 光影参数，提供抖动幅度。
        rng: 随机源。
        color: 线色（归一化 RGB）。

    Returns:
        修改后的图像。
    """
    H, W = img.shape[0], img.shape[1]
    color_arr = np.array(color, dtype=np.float64)
    wobble = _smooth_wobble(rng, W, sh.wobble)
    rows = np.arange(H, dtype=np.float64)[:, np.newaxis]
    dist = rows - (y_base + wobble)[np.newaxis, :]
    cov = np.clip(1.0 - np.abs(dist) / 1.4, 0.0, 1.0) * (alpha > 0.05)
    t = (0.7 * cov)[..., np.newaxis]
    img[..., :3] = img[..., :3] * (1.0 - t) + color_arr * t
    return img


def _draw_welt(
    img: NDArray[np.float64],
    fabric: Fabric,
    alpha: NDArray[np.float64],
    y0: int,
    H: int,
    W: int,
    top: Welt,
    sh: Shading,
    rng: np.random.Generator,
    dip: NDArray[np.float64] | None = None,
) -> NDArray[np.float64]:
    """绘制松紧袜口条带与勒痕。

    袜口顶端对齐 y0，条带向下延伸 height 像素并随弧线下弯；颜色取
    `Welt.color` 或主色加深一档。

    Args:
        img: (H, W, 4) 归一化图像；原地修改并返回。
        fabric: 袜身种类，用于取主色。
        alpha: (H, W) 腿的 alpha 覆盖。
        y0: 袜口顶端所在行。
        H: 图像高。
        W: 图像宽。
        top: 松紧袜口参数。
        sh: 光影参数。
        rng: 随机源，供边线抖动使用。
        dip: (H, W) 下弯量；None 表示不弯。

    Returns:
        修改后的图像。
    """
    h = int(top.height)

    main_rgb = _fabric_main_color(fabric)
    welt_rgb = color_rgb(top.color) if top.color is not None else main_rgb * 0.7

    welt_a = top.opacity if top.opacity is not None else 1.0

    dip2 = dip if dip is not None else np.zeros((H, W))
    ys = np.arange(H, dtype=np.float64)[:, np.newaxis]

    top_arc = y0 + dip2  # 条带上沿（弧线）
    bot_arc = y0 + h + dip2  # 条带下沿（弧线）

    in_leg = alpha > 0.05
    band = _soft_cover(ys, top_arc) * (1.0 - _soft_cover(ys, bot_arc)) * in_leg
    t = (welt_a * band)[..., np.newaxis]
    img[..., :3] = img[..., :3] * (1.0 - t) + welt_rgb * t

    # 勒痕：条带上沿之上一条细暗线（按覆盖率软过渡，避免逐列取整出锯齿）
    if top.pinch > 0:
        line = np.clip(1.0 - np.abs(ys - (top_arc - 1.5)) / 1.4, 0.0, 1.0) * in_leg
        img[..., :3] *= (1.0 - top.pinch * 0.3 * line)[..., np.newaxis]

    img = _draw_edge_line(img, alpha, _edge_base(y0, W, dip), sh, rng, color=tuple(welt_rgb))  # type: ignore[arg-type]
    return img


def _draw_lace(
    img: NDArray[np.float64],
    fabric: Fabric,
    alpha: NDArray[np.float64],
    y0: int,
    H: int,
    W: int,
    top: Lace,
    sh: Shading,
    rng: np.random.Generator,
    dip: NDArray[np.float64] | None,
    wave: tuple[NDArray[np.float64], float, float, float],
) -> NDArray[np.float64]:
    """绘制蕾丝边。

    半透明带直接覆盖在皮肤上，孔点加深，沿波浪下沿与袜口顶端各画一条边线。

    Args:
        img: (H, W, 4) 归一化图像；原地修改并返回。
        fabric: 袜身种类，用于取主色。
        alpha: (H, W) 腿的 alpha 覆盖。
        y0: 蕾丝带顶端所在行。
        H: 图像高。
        W: 图像宽。
        top: 蕾丝参数。
        sh: 光影参数。
        rng: 随机源，供边线抖动使用。
        dip: (H, W) 下弯量；None 表示不弯。
        wave: 预计算的波形 `(wave_bot, scallop, amplitude, phase)`，与织物
            图案的逐列裁剪共用。

    Returns:
        修改后的图像。
    """
    lace_rgb = color_rgb(top.color) if top.color is not None else _fabric_main_color(fabric)

    wave_bot, scallop, _amplitude, phase = wave

    t = top.opacity
    y_mat = np.arange(H, dtype=np.float64)[:, np.newaxis]  # (H, 1)

    # 下沿的亚像素软混合权重
    soft_dist = y_mat - (wave_bot[np.newaxis, :] - 0.5)
    weight = np.clip(1.0 - soft_dist / 1.5 + 1.0 / 3.0, 0.0, 1.0)

    # 上边界：随袜口弧线 y0 + dip；且只在腿内（1px 软过渡，避免阶梯）
    dip2 = dip if dip is not None else np.zeros((H, W))
    in_zone = _soft_cover(y_mat, y0 + dip2) * (alpha > 0.05)

    # 孔点：波峰处的软圆盘，局部提高蕾丝的透明度（透出皮肤）
    hole_map = np.zeros((H, W), dtype=np.float64)
    if top.holes:
        dot_r = 2.2
        x_peak = scallop * 0.75 - phase  # sin=-1 处，波峰（带最浅）
        k = 0
        while True:
            xp = int(x_peak + k * scallop)
            if xp - 4 >= W:
                break
            if xp + 4 >= 0 and xp - 4 < W:
                xp_c = max(0, min(W - 1, xp))
                cy = (y0 + wave_bot[xp_c]) / 2.0
                y0w, y1w = max(0, int(cy) - 4), min(int(cy) + 5, H)
                x0w, x1w = max(0, xp - 4), min(xp + 5, W)
                gy, gx = np.mgrid[y0w:y1w, x0w:x1w]
                dist = np.sqrt((gy - cy) ** 2 + (gx - xp) ** 2)
                disc = np.clip(1.0 - dist / dot_r, 0.0, 1.0)
                np.maximum(hole_map[y0w:y1w, x0w:x1w], disc, out=hole_map[y0w:y1w, x0w:x1w])
            k += 1

    eff_t = weight * in_zone * t
    img[..., :3] = img[..., :3] * (1.0 - eff_t[..., np.newaxis]) + lace_rgb * eff_t[..., np.newaxis]

    # 孔点加深（镂空阴影感），软边圆盘
    img[..., :3] *= (1.0 - hole_map * 0.5)[..., np.newaxis]

    # 波浪下沿细边线：勾勒扇贝轮廓（蕾丝色加深）
    img = _draw_edge_line(img, alpha, wave_bot, sh, rng, color=tuple(lace_rgb * 0.55))  # type: ignore[arg-type]

    # 袜口顶端画一条手绘边线
    img = _draw_edge_line(img, alpha, _edge_base(y0, W, dip), sh, rng, color=tuple(lace_rgb * 0.8))  # type: ignore[arg-type]
    return img
