"""颜色类型与内部换算。

公开的 Color 是 0–255 的 RGB/RGBA 元组；内部绘制时按需拆成归一化 RGB 与
alpha。所有颜色入口都应先经过 `check_color()` 校验。
"""

import numpy as np
from numpy.typing import NDArray

type Color = tuple[int, int, int] | tuple[int, int, int, int]
"""0–255，可带 alpha。"""


def check_color(color: Color, name: str) -> None:
    """校验颜色元组的长度与分量范围。

    Args:
        color: 待校验的 RGB/RGBA 元组。
        name: 出错信息中使用的参数名，便于定位调用点。

    Raises:
        ValueError: 长度不是 3 或 4，或任一分量不在 0–255。
    """
    if len(color) not in (3, 4) or any(not 0 <= c <= 255 for c in color):
        raise ValueError(f"{name} 必须是 3 或 4 个 0–255 的整数，得到 {color!r}")


def color_rgb(color: Color) -> NDArray[np.float64]:
    """取 RGB 分量并归一化到 [0, 1]。

    Args:
        color: RGB/RGBA 元组；alpha 被忽略。

    Returns:
        长度为 3 的 float64 数组。
    """
    return np.array(color[:3], dtype=np.float64) / 255.0


def color_alpha(color: Color) -> float:
    """取 alpha 分量并归一化到 [0, 1]。

    Args:
        color: RGB/RGBA 元组；3 元组视为完全不透明。

    Returns:
        0–1 的 alpha 值。
    """
    return color[3] / 255.0 if len(color) == 4 else 1.0
