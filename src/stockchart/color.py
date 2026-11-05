"""颜色类型与内部换算。

公开的 Color 是 0–255 的 RGB/RGBA 元组；内部绘制时按需拆成归一化 RGB 与
alpha，或直接转成 skia 的 ARGB 整数。所有颜色入口都应先经过 `check_color()` 校验。
"""

from typing import cast

import numpy as np
import skia
from numpy.typing import NDArray

type Color = tuple[int, int, int] | tuple[int, int, int, int]
"""0–255 的整数分量，可带 alpha；不接受浮点数或布尔值。"""


def check_color(color: Color, name: str) -> None:
    """校验颜色元组的长度、整数分量与范围。

    Args:
        color: 待校验的 RGB/RGBA 元组。
        name: 出错信息中使用的参数名，便于定位调用点。

    Raises:
        ValueError: 长度不是 3 或 4，或任一分量不是 0–255 的整数；
            浮点数与布尔值不接受。
    """
    components = cast(tuple[object, ...], color)
    if len(components) not in (3, 4) or any(
        isinstance(c, (bool, np.bool_)) or not isinstance(c, (int, np.integer)) or not 0 <= c <= 255
        for c in components
    ):
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


def skia_color(color: Color) -> int:
    """把 Color 元组转换为 skia 的 ARGB 整数。

    Args:
        color: 3 元组（RGB）或 4 元组（RGBA），分量为 0–255；3 元组视为不透明。

    Returns:
        skia 使用的 ARGB 整数。

    Raises:
        ValueError: 元组长度或分量范围不合法。
    """
    check_color(color, "color")
    a = int(color[3]) if len(color) == 4 else 255
    return skia.Color(int(color[0]), int(color[1]), int(color[2]), a)
