"""织物纹理：按 Fabric 种类生成 RGBA 纹理层。

纯色、条纹、罗纹、网眼、圆点五类；纹理在公开的 scale 密度中直接生成。
"""

from __future__ import annotations

import math

import numpy as np

from stockchart.color import color_alpha, color_rgb
from stockchart.stocking.geometry import surface_abs_x
from stockchart.stocking.patterns import motif_mask, stripe_pixels
from stockchart.stocking.pixels import FloatArray
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
    src: FloatArray,
    alpha: FloatArray,
    u: FloatArray,
    y_start: int,
    H: int,
    W: int,
    rng: np.random.Generator,
    dip: FloatArray | None = None,
    pattern_offset: float = 0.0,
) -> FloatArray:
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
        (H, W, 4) float32 RGBA 层；仅计算袜区，袜口以上与腿外均为全透明。
    """
    if y_start >= H:
        return np.zeros((H, W, 4), dtype=np.float32)
    # 拉伸仍参考全腿最宽处，避免袜高变化导致同一位置的织物突然变薄或变厚。
    max_width = max(1.0, float((alpha > 0.05).sum(axis=1).max()))
    covered, profile = alpha[y_start:], u[y_start:]
    curvature = dip[y_start:] if dip is not None else None
    source = src[y_start:]
    rows = H - y_start
    if isinstance(fabric, Plain):
        region = fabric_plain(fabric, source, covered, profile, 0, rows, W, max_width=max_width)
    elif isinstance(fabric, Striped):
        region = _fabric_striped(
            fabric, source, covered, profile, 0, rows, W, curvature, pattern_offset
        )
    elif isinstance(fabric, Ribbed):
        region = _fabric_ribbed(fabric, source, covered, profile, 0, rows, W)
    elif isinstance(fabric, Fishnet):
        region = _fabric_fishnet(
            fabric,
            source,
            covered,
            profile,
            0,
            rows,
            W,
            rng,
            curvature,
            max_width=max_width,
            row_origin=y_start,
        )
    else:
        region = _fabric_dotted(
            fabric,
            source,
            covered,
            profile,
            0,
            rows,
            W,
            rng,
            curvature,
            pattern_offset,
            max_width=max_width,
        )

    region[covered < 0.05] = 0.0
    if y_start == 0:
        return region
    layer = np.zeros((H, W, 4), dtype=np.float32)
    layer[y_start:] = region
    return layer


def fabric_plain(
    f: Plain,
    src: FloatArray,
    alpha: FloatArray,
    u: FloatArray,
    y0: int,
    H: int,
    W: int,
    *,
    max_width: float | None = None,
) -> FloatArray:
    """生成纯色袜纹理：不透明度随圆柱曲率和腿截面宽度变化。

    Args:
        f: 纯色袜参数。
        src: 归一化腿图；本实现不读取，保留统一签名。
        alpha: (H, W) 腿的 alpha 覆盖。
        u: (H, W) 横向归一化坐标。
        y0: 袜子区域起始行。
        H: 图像高。
        W: 图像宽。
        max_width: 全腿最大宽度；区域计算时仍沿用全腿的拉伸参考。

    Returns:
        (H, W, 4) RGBA 层。
    """
    layer = np.zeros((H, W, 4), dtype=np.float32)
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
        row_w = xs.sum(axis=1, keepdims=True).astype(np.float32)  # (H,1)
        max_w = max_width if max_width is not None else np.clip(row_w.max(), 1.0, None)
        stretch_factor = 1.0 - f.stretch * (row_w / max_w - 0.5)
        stretch_factor = np.clip(stretch_factor, 0.1, 1.0)
        a_map = a_map * stretch_factor

    a_map[:y0] = 0.0

    layer[..., :3] = rgb
    layer[..., 3] = a_map
    return layer


def _fabric_striped(
    f: Striped,
    src: FloatArray,
    alpha: FloatArray,
    u: FloatArray,
    y0: int,
    H: int,
    W: int,
    dip: FloatArray | None = None,
    pattern_offset: float = 0.0,
) -> FloatArray:
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
    layer = np.zeros((H, W, 4), dtype=np.float32)
    ys_pat = np.arange(H, dtype=np.float32).reshape(H, 1) - y0 - pattern_offset
    if dip is not None:
        ys_pat = ys_pat - dip
    layer[:] = stripe_pixels(f, ys_pat)
    layer[:y0] = 0.0
    return layer


def _fabric_ribbed(
    f: Ribbed,
    src: FloatArray,
    alpha: FloatArray,
    u: FloatArray,
    y0: int,
    H: int,
    W: int,
) -> FloatArray:
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
    layer = np.zeros((H, W, 4), dtype=np.float32)
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
    W_abs: FloatArray,
    ys: FloatArray,
    cell: float,
    line_w: float,
    angle_deg: float,
) -> FloatArray:
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
    return (on_x | on_y).astype(np.float32)


def _fabric_fishnet(
    f: Fishnet,
    src: FloatArray,
    alpha: FloatArray,
    u: FloatArray,
    y0: int,
    H: int,
    W: int,
    rng: np.random.Generator,
    dip: FloatArray | None = None,
    *,
    max_width: float | None = None,
    row_origin: int = 0,
) -> FloatArray:
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
        max_width: 全腿最大宽度，供底袜拉伸使用。
        row_origin: 当前区域首行在全腿中的坐标，保持网格纵向相位。

    Returns:
        (H, W, 4) RGBA 层。
    """
    layer = np.zeros((H, W, 4), dtype=np.float32)

    abs_x = surface_abs_x(u, alpha, f.perspective)
    ys = np.arange(row_origin, row_origin + H, dtype=np.float32).reshape(H, 1)
    if dip is not None:
        ys = ys - dip

    net = _fishnet_mask(abs_x, ys, f.cell, f.line_width, f.angle)

    rgb = color_rgb(f.color)
    layer[..., :3] = rgb
    layer[..., 3] = net * color_alpha(f.color)

    # 底袜
    if f.underlay is not None:
        under = fabric_plain(f.underlay, src, alpha, u, y0, H, W, max_width=max_width)
        # 先画底袜，再把网线叠上去
        layer = alpha_over(under, layer)

    layer[:y0] = 0.0
    return layer


def dot_mask(
    abs_x: FloatArray,
    ys: FloatArray,
    spacing: float,
    size: float,
    layout: str,
    shape: str,
    rng: np.random.Generator,
) -> FloatArray:
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
        raw_x = raw_x.astype(np.float32)
        raw_y = raw_y.astype(np.float32)
        cx = (gi + 0.5) * cell + (raw_x / float(0xFFFFFF) - 0.5) * 0.6 * cell
        cy = (gj + 0.5) * cell + (raw_y / float(0xFFFFFF) - 0.5) * 0.6 * cell
        dx = abs_x - cx
        dy = ys - cy

    if shape == "dot":
        mask = (dx**2 + dy**2 < size**2).astype(np.float32)
    elif shape in ("heart", "star"):
        mask = motif_mask(dx, dy, size, shape)
    else:
        mask = np.zeros((H, W), dtype=np.float32)

    return mask


def _fabric_dotted(
    f: Dotted,
    src: FloatArray,
    alpha: FloatArray,
    u: FloatArray,
    y0: int,
    H: int,
    W: int,
    rng: np.random.Generator,
    dip: FloatArray | None = None,
    pattern_offset: float = 0.0,
    *,
    max_width: float | None = None,
) -> FloatArray:
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
        max_width: 全腿最大宽度，供底袜拉伸使用。

    Returns:
        (H, W, 4) RGBA 层。
    """
    base = fabric_plain(f.base, src, alpha, u, y0, H, W, max_width=max_width)

    abs_x = surface_abs_x(u, alpha, f.perspective)
    ys = (np.arange(H, dtype=np.float32) - y0 - pattern_offset).reshape(H, 1)
    if dip is not None:
        ys = ys - dip

    dot = dot_mask(abs_x, ys, f.spacing, f.size, f.layout, f.shape, rng)

    dot_layer = np.zeros((H, W, 4), dtype=np.float32)
    dot_layer[..., :3] = color_rgb(f.color)
    dot_layer[..., 3] = dot * f.opacity * color_alpha(f.color)
    dot_layer[:y0] = 0.0

    return alpha_over(base, dot_layer)
