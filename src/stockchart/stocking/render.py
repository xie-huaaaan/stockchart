"""丝袜渲染算法：render_stocking 的实现。

所有坐标以素材像素为单位；坐标原点在图像左上角，y 轴向下。
渲染分三步：
  1. 计算腿的形状（alpha mask）与宽度剖面；
  2. 按 Fabric 种类生成 RGBA 纹理层；
  3. 叠加 Shading 光影，绘制上沿（TopEdge），合成到腿素材上。
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import numpy as np
from numpy.typing import NDArray

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
    Striped,
    StockingStyle,
    Welt,
)

if TYPE_CHECKING:
    from stockchart.legs import Leg


# ---------------------------------------------------------------------------
# 公开入口
# ---------------------------------------------------------------------------


def render_stocking(
    leg: "Leg",
    style: StockingStyle,
    height_px: int,
    *,
    seed: int | None = None,
) -> "Leg":
    """给腿穿丝袜：从脚端向上覆盖 height_px 像素。

    Args:
        leg: 待渲染的腿素材。
        style: 丝袜样式，可从 STYLES 预设取得。
        height_px: 丝袜上沿到脚端的像素数。小于等于 0 时返回原图（裸腿）；
            不小于 leg.height 时整腿全盖。
        seed: 纹理类随机效果的随机源。

    Returns:
        新的 Leg：像素已替换，元数据与原素材一致。
    """
    from stockchart.legs import Leg as LegClass

    if height_px <= 0:
        return leg

    height_px = min(height_px, leg.height)
    rng = np.random.default_rng(seed if seed is not None else 0)

    H, W = leg.height, leg.width
    src = leg.image.astype(np.float64) / 255.0  # (H, W, 4) float64 [0,1]

    # 腿的 alpha mask（0/1 float）
    alpha_mask = src[..., 3]  # (H, W)

    # 渲染区域：图像底部 height_px 行（脚在底部）
    y_start = H - height_px  # 袜口顶端所在行（含）

    # 每行腿的宽度剖面：用于圆柱透视压缩
    col_profile = _column_profile(alpha_mask)  # (H, W) float，横向归一化坐标

    # 环形线条（横纹、袜口、蕾丝）的透视下弯量：中线最大、两侧缘为 0
    dip = _curve_dip(col_profile, alpha_mask, style.shading.curve)

    # Lace 波形只计算一次，供图案裁剪与上沿绘制共用（保证相位一致）
    wave = _lace_wave(style.top, y_start, dip, W, H, rng) \
        if isinstance(style.top, Lace) else None

    # 上沿条带下沿（每列）：袜身图案从这条线起算，条带直接覆盖在皮肤上。
    # Welt 为条带底沿弧线；Lace 为波浪边缘；Bare / Fade 为袜口弧线本身。
    if isinstance(style.top, Welt):
        row = min(y_start + int(style.top.height), H - 1)
        origin_col = y_start + style.top.height + dip[row]          # (W,)
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
        style.fabric, src, alpha_mask, col_profile, y_start, H, W,
        rng, dip, pattern_offset,
    )

    # 织物沿条带下沿逐列裁剪：图案与上沿边缘处处贴合（Lace 沿波浪无缺口）
    ys_grid = np.arange(H, dtype=np.float64)[:, np.newaxis]      # (H, 1)
    fabric_layer[ys_grid < origin_col[np.newaxis, :]] = 0.0
    top_arc = y_start + dip                                      # (H, W) 袜口弧线

    # Fade：渐隐沿弧线自袜口顶端向下 length 像素内完成（顶端透明，底端全显）
    fade_ramp: NDArray[np.float64] | None = None
    if isinstance(style.top, Fade):
        fade_ramp = np.clip(
            (ys_grid - top_arc) / max(style.top.length, 1.0), 0.0, 1.0
        )
        fabric_layer[..., 3] *= fade_ramp

    # 叠加光影（同样沿弧线裁剪，避免袜口弧线之上出现裸腿阴影）
    shading_layer = _render_shading(
        style.shading, src, alpha_mask, col_profile, y_start, H, W
    )
    shading_layer[ys_grid < top_arc] = 0.0
    if fade_ramp is not None:
        # 渐隐区中阴影与高光同步变淡，避免"袜子已消失、阴影仍在"的灰雾
        shading_layer[..., 3] *= fade_ramp
        shading_layer[..., 2] *= fade_ramp

    # 合成：将腿皮肤与袜子融合（光影后置，使上沿条带同样受光）
    result = _composite(src, fabric_layer, alpha_mask, y_start)

    # 绘制上沿
    result = _render_top_edge(
        result, style.top, style.fabric, style.shading,
        alpha_mask, col_profile, y_start, H, W, rng, dip, wave
    )

    # 应用光影：在条带绘制之后，袜口/蕾丝与袜身统一受光
    result = _apply_shading(result, shading_layer)

    # 膝盖褶皱等素材内部墨线增强：以"织物压痕"的方式补画到袜子上
    result = _boost_ink_lines(
        result, src, alpha_mask, col_profile, style.fabric,
        style.shading, fabric_layer, ys_grid, top_arc, y_start,
    )

    out = (np.clip(result, 0.0, 1.0) * 255.0).astype(np.uint8)

    from dataclasses import replace
    return replace(leg, image=out)


# ---------------------------------------------------------------------------
# 素材墨线（膝盖褶皱等）增强
# ---------------------------------------------------------------------------

_LUM_WEIGHTS = np.array([0.299, 0.587, 0.114])


def _luminance(rgb: NDArray[np.float64]) -> NDArray[np.float64]:
    """RGB (..., 3) → 亮度 (...)。"""
    return rgb @ _LUM_WEIGHTS


def _ink_mask(
    src: NDArray[np.float64],
    alpha: NDArray[np.float64],
) -> NDArray[np.float64]:
    """检测素材内部的手绘线条（膝盖褶皱等），返回 [0,1] 软掩码。

    以肤色亮度的 90 分位为基准，亮度低于基准 0.05 开始、0.18 达到全强度；
    排除 alpha 边缘约 3px 环带（轮廓线不参与，避免与侧缘阴影叠加），
    并做轻微模糊保持手绘感。
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

    # 排除轮廓：对腿 mask 做约 3px 腐蚀
    leg_u8 = (alpha > 0.05).astype(np.uint8) * 255
    interior = np.asarray(
        Image.fromarray(leg_u8).filter(ImageFilter.MinFilter(7))
    ).astype(np.float64) / 255.0
    ink *= interior

    # 轻微模糊
    ink_img = Image.fromarray((ink * 255).astype(np.uint8))
    ink = np.asarray(ink_img.filter(ImageFilter.GaussianBlur(0.8))).astype(
        np.float64
    ) / 255.0
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
) -> NDArray[np.float64]:
    """把素材自带的内部墨线以织物褶痕的形式补画到袜子上。

    线条颜色跟随袜色：深色织物上用 screen 提亮为冷灰线（动漫黑丝的画法），
    浅色织物上按原线条深度比 multiply 压暗。强度由 Shading.ink 控制，
    并按局部织物不透明度加权——裸腿处不增强（皮肤本来的线已在）。
    """
    if sh.ink <= 0:
        return img

    ink = _ink_mask(src, alpha)
    if not (ink > 0.01).any():
        return img

    H, W = alpha.shape
    # 增强只发生在袜子区域内，且按织物覆盖率加权
    coverage = fabric_layer[..., 3]
    if isinstance(fabric, Fishnet):
        # 网孔直接透出皮肤线，只对底袜部分增强，避免碎线
        if fabric.underlay is not None:
            coverage = _fabric_plain(
                fabric.underlay, src, alpha, u, y0, H, W
            )[..., 3]
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
    screen_c = 1.0 - (1.0 - current) * (1.0 - shadow_rgb)   # 深色织物：提亮为冷灰线
    mult_c = current * f_local                               # 浅色织物：压暗

    boosted = screen_c * darkness + mult_c * (1.0 - darkness)
    img[..., :3] = current * (1.0 - w) + boosted * w
    return img


# ---------------------------------------------------------------------------
# 辅助：列坐标剖面
# ---------------------------------------------------------------------------


def _column_profile(alpha: NDArray[np.float64]) -> NDArray[np.float64]:
    """为每个像素计算横向归一化坐标 u（−1 左缘，0 中线，1 右缘）。

    用每行的 alpha 覆盖范围动态估计腿宽，保证在腿宽变化时（脚踝/大腿）
    u 坐标始终贴合当前截面。
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
    """环形线条的透视下弯量（像素，正值向下）。

    圆柱在略微俯视时，横向环绕线呈弧线：腿中线处下垂最多、两侧缘为 0，
    下垂量与该行腿宽（局部半径）成正比。curve 为 0 时返回全零。
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
    """蕾丝波浪下沿的每列 y 坐标及波形参数 (wave_bot, scallop, amplitude, phase)。

    wave_bot 在 (y0 + height ± 振幅) 之间起伏，计入条带下沿所在行的弧线
    下弯量；振幅约为 scallop 的 15%（使扇贝圆缓）。
    """
    scallop = max(top.scallop, 20.0)
    amplitude = min(scallop * 0.15, top.height * 0.25)
    phase = rng.uniform(0, scallop)
    dip_bot = dip[min(y0 + int(top.height), H - 1)] if dip is not None else np.zeros(W)
    wave_bot = (y0 + top.height) + dip_bot + amplitude * np.sin(
        2 * math.pi * (np.arange(W, dtype=np.float64) + phase) / scallop
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
    """生成 (H, W, 4) float64 的袜身 RGBA 层，y_start 以上行全透明。

    dip 为环形图案（横纹、网格横线、印花行）的透视下弯量 (H, W)。
    pattern_offset 为上沿条带高度：图案相位从条带下沿起算（是否可见由
    render_stocking 中的逐列裁剪决定）。
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
    elif isinstance(fabric, Dotted):
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
    y0: int, H: int, W: int,
) -> NDArray[np.float64]:
    """纯色袜：opacity 随圆柱曲率和腿截面宽度变化。"""
    layer = np.zeros((H, W, 4), dtype=np.float64)
    rgb = color_rgb(f.color)  # (3,)
    base_a = f.opacity * color_alpha(f.color)

    # 圆柱 cos 衰减：|u| 接近 1 时是侧面，"透过"更多织物 → 更不透明
    cos_u = np.sqrt(np.maximum(1.0 - u**2, 0.0))  # (H, W)

    # rim：侧缘不透明度提升
    rim_boost = 1.0 - cos_u                         # 0 中线，1 极侧缘
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
    """对每个 (y, x) 位置返回 RGB (H,W,3) 和 opacity (H,W)。

    条带边界做约 1.2px 的亚像素软化，避免逐列相位取整产生阶梯锯齿。
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
    y0: int, H: int, W: int,
    dip: NDArray[np.float64] | None = None,
    pattern_offset: float = 0.0,
) -> NDArray[np.float64]:
    """横条纹袜：条纹相位从上沿条带下沿起算，沿弧线下弯。

    条带覆盖区的清除由 render_stocking 的逐列裁剪完成。
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
    y0: int, H: int, W: int,
) -> NDArray[np.float64]:
    """竖罗纹：用 cos 函数在 u 方向产生明暗交替的条纹。"""
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
    """在 (abs_x, ys) 坐标系中计算网线的 alpha（0 网孔，1 网线）。"""
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
    y0: int, H: int, W: int,
    rng: np.random.Generator,
    dip: NDArray[np.float64] | None = None,
) -> NDArray[np.float64]:
    """网袜：网线不透明、网孔透明（可叠底袜），横向网线沿弧线下弯。

    条带覆盖区的清除由 render_stocking 的逐列裁剪完成。
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
    """生成印花图案的 alpha（1 在图案内，0 在图案外）。"""
    H, W = abs_x.shape

    if layout == "grid":
        # 错位网格：偶数行偏移半个间距
        row_idx = np.floor(ys / spacing).astype(int)
        col_base = np.floor(abs_x / spacing).astype(int)
        offset = (row_idx % 2) * (spacing / 2)
        cx = (np.floor((abs_x - offset) / spacing) + 0.5) * spacing + offset
        cy = (row_idx + 0.5) * spacing
        dx = abs_x - cx
        dy = ys - cy
    else:  # scatter
        cell = spacing
        gi = np.floor(abs_x / cell).astype(int)
        gj = np.floor(ys / cell).astype(int)
        seed_arr = ((gi * 1000003 + gj * 7919) & 0xFFFFFF).astype(np.uint32)
        rand_x = ((seed_arr * np.uint32(0x5DEECE6D) + np.uint32(11)) & np.uint32(0xFFFFFF)).astype(np.float64) / float(0xFFFFFF) - 0.5
        rand_y = ((seed_arr * np.uint32(0xDEADBEEF) + np.uint32(0x12345)) & np.uint32(0xFFFFFF)).astype(np.float64) / float(0xFFFFFF) - 0.5
        cx = (gi + 0.5 + rand_x * 0.6) * cell
        cy = (gj + 0.5 + rand_y * 0.6) * cell
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
        val = (nx**2 + ny**2 - 1.0)**3 - nx**2 * ny**3
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
    y0: int, H: int, W: int,
    rng: np.random.Generator,
    dip: NDArray[np.float64] | None = None,
    pattern_offset: float = 0.0,
) -> NDArray[np.float64]:
    """印花袜：底袜 + 图案叠加；图案行沿弧线下弯，相位从条带下沿起算。"""
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
    y0: int, H: int, W: int,
) -> NDArray[np.float64]:
    """生成 (H, W, 4) 光影覆盖层。

    使用正片叠底（multiply）模式：颜色越深遮越暗，白色 (1,1,1) 不影响。
    高光使用屏幕（screen）模式叠加。
    """
    layer = np.ones((H, W, 4), dtype=np.float64)
    layer[..., 3] = 0.0  # 默认全透

    if sh.rim_shadow <= 0 and sh.highlight <= 0:
        return layer

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
    # 阴影 alpha 放在 R 通道用作权重（合成时单独处理）
    # 用 (H, W, 2) 分别传阴影和高光 alpha，这里打包进 G=hl_a
    layer[..., 3] = shadow_a
    # 把高光 alpha 打包进 B 通道临时存储，合成时提取
    layer[..., 2] = hl_a  # 约定：B 通道存高光 alpha（合成函数负责解包）

    layer[:y0] = 0.0
    layer[alpha < 0.05] = 0.0
    return layer


# ---------------------------------------------------------------------------
# 合成
# ---------------------------------------------------------------------------


def _alpha_over(
    dst: NDArray[np.float64], src_: NDArray[np.float64]
) -> NDArray[np.float64]:
    """Porter-Duff 'A over B'（src_ 在上）。"""
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
    """将腿皮肤与袜子纹理合成为 RGBA（光影由 _apply_shading 后置应用）。"""
    result = src_leg.copy()

    fa = fabric[..., 3:4]   # 袜子 alpha (H,W,1)
    frgb = fabric[..., :3]  # 袜子 RGB

    leg_rgb = src_leg[..., :3]
    blended_rgb = frgb * fa + leg_rgb * (1.0 - fa)
    blended_rgb = np.clip(blended_rgb, 0.0, 1.0)

    H, W = src_leg.shape[:2]
    mask = np.zeros((H, W, 1), dtype=np.float64)
    mask[y0:] = 1.0

    result[..., :3] = blended_rgb * mask + leg_rgb * (1.0 - mask)
    return result


def _apply_shading(
    img: NDArray[np.float64],
    shading: NDArray[np.float64],
) -> NDArray[np.float64]:
    """对合成结果应用光影：边缘阴影正片叠底、竖向高光 screen。

    在上沿条带绘制之后调用，使袜口/蕾丝同样受光。
    shading[..., 3] 为阴影 alpha，[..., 2] 为高光 alpha。
    """
    sh_a = shading[..., 3:4]
    hl_a = shading[..., 2:3]
    sh_rgb = shading[..., :3]

    # 正片叠底阴影：shadow_rgb 通常偏冷，乘在当前颜色上
    mul = img[..., :3] * sh_rgb
    img[..., :3] = img[..., :3] * (1.0 - sh_a) + mul * sh_a

    # screen 高光（白色）：提亮
    img[..., :3] = img[..., :3] + (1.0 - img[..., :3]) * hl_a
    return img


# ---------------------------------------------------------------------------
# 上沿绘制
# ---------------------------------------------------------------------------


def _render_top_edge(
    img: NDArray[np.float64],
    top: "Bare | Welt | Lace | Fade",
    fabric: Fabric,
    sh: Shading,
    alpha: NDArray[np.float64],
    u: NDArray[np.float64],
    y0: int,
    H: int, W: int,
    rng: np.random.Generator,
    dip: NDArray[np.float64] | None = None,
    wave: tuple[NDArray[np.float64], float, float, float] | None = None,
) -> NDArray[np.float64]:
    """在图像上原地绘制上沿效果，返回修改后的图像。

    Fade 的渐隐已在织物 alpha 中实现，此处无需再画。
    dip 为环形线条的透视下弯量 (H, W)，可为 None（不弯）。
    wave 为 Lace 的 (wave_bot, scallop, amplitude, phase)，由 render_stocking 预计算。
    """
    if isinstance(top, Bare):
        img = _draw_edge_line(img, alpha, _edge_base(y0, W, dip), sh, rng,
                              color=(0.1, 0.1, 0.1))
    elif isinstance(top, Welt):
        img = _draw_welt(img, fabric, alpha, y0, H, W, top, sh, rng, dip)
    elif isinstance(top, Lace):
        assert wave is not None
        img = _draw_lace(img, fabric, alpha, y0, H, W, top, sh, rng, dip, wave)
    return img


def _edge_base(
    y0: int, W: int, dip: NDArray[np.float64] | None,
) -> NDArray[np.float64]:
    """上沿边线各列的基准 y：y0 加上该行的下弯量。"""
    if dip is None:
        return np.full(W, float(y0))
    row = dip[min(max(y0, 0), dip.shape[0] - 1)]
    return y0 + row


def _fabric_main_color(fabric: Fabric) -> NDArray[np.float64]:
    """取袜身的主色（RGB [0,1]）。"""
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


def _draw_edge_line(
    img: NDArray[np.float64],
    alpha: NDArray[np.float64],
    y_base: NDArray[np.float64],
    sh: Shading,
    rng: np.random.Generator,
    color: tuple[float, float, float] = (0.1, 0.1, 0.1),
) -> NDArray[np.float64]:
    """沿基准曲线 y_base 画一条手绘边线（逐列 ±wobble 抖动，约 2px 粗）。"""
    H, W = img.shape[0], img.shape[1]
    color_arr = np.array(color, dtype=np.float64)
    wobble = np.round(
        rng.normal(0, max(sh.wobble, 0.01), size=W)
    ).astype(int)
    for x in range(W):
        yb = int(round(y_base[x]))
        for dy in range(-1, 2):
            yy = yb + wobble[x] + dy
            if 0 <= yy < H and alpha[yy, x] > 0.05:
                t = 0.65 if dy == 0 else 0.25
                img[yy, x, :3] = (1.0 - t) * img[yy, x, :3] + t * color_arr
    return img


def _draw_welt(
    img: NDArray[np.float64],
    fabric: Fabric,
    alpha: NDArray[np.float64],
    y0: int, H: int, W: int,
    top: Welt,
    sh: Shading,
    rng: np.random.Generator,
    dip: NDArray[np.float64] | None = None,
) -> NDArray[np.float64]:
    """松紧袜口：袜口顶端对齐 y0，加厚条带从 y0 向下延伸 height 像素，
    上下边沿跟随弧线下弯。"""
    h = int(top.height)

    main_rgb = _fabric_main_color(fabric)
    if top.color is not None:
        welt_rgb = color_rgb(top.color)
    else:
        # 加深主色约 30%
        welt_rgb = main_rgb * 0.7

    welt_a = top.opacity if top.opacity is not None else 1.0

    dip2 = dip if dip is not None else np.zeros((H, W))
    ys = np.arange(H, dtype=np.float64)[:, np.newaxis]

    top_arc = y0 + dip2          # 条带上沿（弧线）
    bot_arc = y0 + h + dip2      # 条带下沿（弧线）

    band = (ys >= top_arc) & (ys < bot_arc) & (alpha > 0.05)
    img[band, :3] = img[band, :3] * (1.0 - welt_a) + welt_rgb * welt_a

    # 勒痕：条带上沿之上一条细暗线
    if top.pinch > 0:
        pinch_y = np.floor(top_arc).astype(int) - 1  # (H, W)
        pinch = (ys == pinch_y) & (alpha > 0.05)
        img[pinch, :3] *= 1.0 - top.pinch * 0.3

    img = _draw_edge_line(img, alpha, _edge_base(y0, W, dip), sh, rng,
                          color=tuple(welt_rgb))  # type: ignore[arg-type]
    return img


def _draw_lace(
    img: NDArray[np.float64],
    fabric: Fabric,
    alpha: NDArray[np.float64],
    y0: int, H: int, W: int,
    top: Lace,
    sh: Shading,
    rng: np.random.Generator,
    dip: NDArray[np.float64] | None,
    wave: tuple[NDArray[np.float64], float, float, float],
) -> NDArray[np.float64]:
    """蕾丝边：半透明带直接覆盖在皮肤上，孔点透出其下的皮肤，
    沿波浪下沿画细边线勾勒扇贝轮廓。

    wave 为 render_stocking 预计算的 (wave_bot, scallop, amplitude, phase)，
    与织物图案的逐列裁剪共用同一波形。
    """
    if top.color is not None:
        lace_rgb = color_rgb(top.color)
    else:
        lace_rgb = _fabric_main_color(fabric)

    wave_bot, scallop, amplitude, phase = wave

    t = top.opacity
    y_mat = np.arange(H, dtype=np.float64)[:, np.newaxis]  # (H, 1)

    # 下沿的亚像素软混合权重
    soft_dist = y_mat - (wave_bot[np.newaxis, :] - 0.5)
    weight = np.clip(1.0 - soft_dist / 1.5 + 1.0 / 3.0, 0.0, 1.0)

    # 上边界：随袜口弧线 y0 + dip；且只在腿内
    dip2 = dip if dip is not None else np.zeros((H, W))
    in_zone = (y_mat >= y0 + dip2) & (alpha > 0.05)

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
                np.maximum(hole_map[y0w:y1w, x0w:x1w], disc,
                           out=hole_map[y0w:y1w, x0w:x1w])
            k += 1

    eff_t = weight * in_zone * t
    img[..., :3] = (
        img[..., :3] * (1.0 - eff_t[..., np.newaxis])
        + lace_rgb * eff_t[..., np.newaxis]
    )

    # 孔点加深（镂空阴影感），软边圆盘
    img[..., :3] *= (1.0 - hole_map * 0.5)[..., np.newaxis]

    # 波浪下沿细边线：勾勒扇贝轮廓（蕾丝色加深）
    img = _draw_edge_line(img, alpha, wave_bot, sh, rng,
                          color=tuple(lace_rgb * 0.55))  # type: ignore[arg-type]

    # 袜口顶端画一条手绘边线
    img = _draw_edge_line(img, alpha, _edge_base(y0, W, dip), sh, rng,
                          color=tuple(lace_rgb * 0.8))  # type: ignore[arg-type]
    return img
