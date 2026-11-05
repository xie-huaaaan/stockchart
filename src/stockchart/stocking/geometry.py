"""腿形几何：宽度剖面与透视坐标。

只描述腿本身的形状（每行的横向归一化坐标、圆柱透视下的表面坐标），
不涉及织物纹理与光影；织物与光影都复用这里的计算，保证透视一致。
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray


def column_profile(alpha: NDArray[np.float64]) -> NDArray[np.float64]:
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


def curve_dip(
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


def surface_abs_x(
    u: NDArray[np.float64],
    alpha: NDArray[np.float64],
    perspective: float,
) -> NDArray[np.float64]:
    """把屏幕归一化坐标映射到圆柱表面的横向绝对坐标。

    0 保持屏幕坐标（图案均匀），1 使用 arcsin 映射（越靠两侧越密）；
    中间值线性混合，便于调节压缩强度。

    Args:
        u: (H, W) 横向归一化坐标。
        alpha: (H, W) 腿的 alpha 覆盖。
        perspective: 压缩强度（0–1）。

    Returns:
        (H, W) 图案使用的横向绝对坐标（像素）。
    """
    half_w = np.where(alpha > 0.05, 1, 0).sum(axis=1) / 2.0
    if perspective <= 0.0:
        surface_u = u
    else:
        surface_u = (1.0 - perspective) * u + perspective * np.arcsin(np.clip(u, -1.0, 1.0))
    return surface_u * half_w[:, np.newaxis]
