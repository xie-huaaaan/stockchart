"""袜口上沿：条带、蕾丝与袜口弧线的绘制。

上沿直接覆盖在皮肤上，再由光影统一受光；蕾丝的波浪相位与图案裁剪共用
同一份计算，保证边缘处处贴合。
"""

from __future__ import annotations

import math

import numpy as np
from numpy.typing import NDArray

from stockchart.color import color_rgb
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
    Welt,
)


def lace_wave(
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
    scallop = top.scallop
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


def render_top_edge(
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
