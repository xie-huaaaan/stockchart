"""颜色类型与内部换算。"""

import numpy as np
from numpy.typing import NDArray

type Color = tuple[int, int, int] | tuple[int, int, int, int]
"""0–255，可带 alpha。"""


def check_color(color: Color, name: str) -> None:
    """校验颜色元组的长度与取值范围，不合法时抛 ValueError。"""
    if len(color) not in (3, 4) or any(not 0 <= c <= 255 for c in color):
        raise ValueError(f"{name} 必须是 3 或 4 个 0–255 的整数，得到 {color!r}")


def color_rgb(color: Color) -> NDArray[np.float64]:
    """取 RGB 分量，换算到 [0, 1]。"""
    return np.array(color[:3], dtype=np.float64) / 255.0


def color_alpha(color: Color) -> float:
    """取 alpha 分量，换算到 [0, 1]；三元组视为不透明。"""
    return color[3] / 255.0 if len(color) == 4 else 1.0
