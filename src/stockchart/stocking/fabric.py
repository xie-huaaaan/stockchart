"""织物纹理：按 Fabric 种类生成 RGBA 纹理层。

纯色、条纹、罗纹、网眼、圆点五类；纹理在输出密度之上按倍率生成再降采样，
只影响画质，不改变公开的 scale 语义。
"""

from __future__ import annotations

import math

import numpy as np
from numpy.typing import NDArray

from stockchart.color import color_alpha, color_rgb
from stockchart.stocking.geometry import surface_abs_x
from stockchart.stocking.shading import alpha_over
from stockchart.stocking.styles import (
    Dotted,
    Fabric,
    Fishnet,
    Plain,
    Ribbed,
    Striped,
)


def render_fabric(
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
        layer = fabric_plain(fabric, src, alpha, u, y_start, H, W)
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


def fabric_plain(
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

    # 将屏幕坐标映射到圆柱表面；perspective 越大，两侧图案越密。
    abs_x = surface_abs_x(u, alpha, f.perspective)

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

    abs_x = surface_abs_x(u, alpha, f.perspective)
    ys = np.arange(H, dtype=np.float64).reshape(H, 1) * np.ones((1, W))
    if dip is not None:
        ys = ys - dip

    net = _fishnet_mask(abs_x, ys, f.cell, f.line_width, f.angle)

    rgb = color_rgb(f.color)
    layer[..., :3] = rgb
    layer[..., 3] = net * color_alpha(f.color)

    # 底袜
    if f.underlay is not None:
        under = fabric_plain(f.underlay, src, alpha, u, y0, H, W)
        # 先画底袜，再把网线叠上去
        layer = alpha_over(under, layer)

    layer[:y0] = 0.0
    return layer


def dot_mask(
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
    base = fabric_plain(f.base, src, alpha, u, y0, H, W)

    abs_x = surface_abs_x(u, alpha, f.perspective)
    ys = (np.arange(H, dtype=np.float64) - y0 - pattern_offset).reshape(H, 1) * np.ones((1, W))
    if dip is not None:
        ys = ys - dip

    dot = dot_mask(abs_x, ys, f.spacing, f.size, f.layout, f.shape, rng)

    dot_layer = np.zeros((H, W, 4), dtype=np.float64)
    dot_layer[..., :3] = color_rgb(f.color)
    dot_layer[..., 3] = dot * f.opacity * color_alpha(f.color)
    dot_layer[:y0] = 0.0

    return alpha_over(base, dot_layer)
