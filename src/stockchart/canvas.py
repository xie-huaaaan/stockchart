"""跨层基础对象：Canvas 渲染载体。

Canvas 封装一块 skia 光栅画布，负责创建、清空、导出 PNG/PIL/NumPy；
L1 绘制原语通过包内私有的 `_skia_canvas()` 在其上作画。
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import skia
from numpy.typing import NDArray
from PIL import Image as PilImage

from stockchart.color import Color, check_color
from stockchart.defaults import DEFAULT_BACKGROUND


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


class Canvas:
    """最终渲染结果的载体：一块 RGBA 画布。

    通常由 `BarPlot.render()` 产生并绘制；自由绘制时也可直接构造，然后配合
    L1 原语（`draw_text` / `sketch_*`）在上面作画。尺寸与坐标都以输出像素计，
    不涉及设计像素；需要设计像素坐标系时由上层先设置画布变换。

    Args:
        width_px: 画布宽（输出像素），须为正数。
        height_px: 画布高（输出像素），须为正数。
        background: 背景色；缺省为米白纸面。

    Raises:
        ValueError: 宽或高不是正数。
    """

    def __init__(
        self,
        width_px: int,
        height_px: int,
        *,
        background: Color = DEFAULT_BACKGROUND,
    ) -> None:
        if width_px <= 0 or height_px <= 0:
            raise ValueError(f"画布尺寸须为正数，得到 {width_px}×{height_px}")
        self._surface = skia.Surface(width_px, height_px)
        self._surface.getCanvas().clear(skia_color(background))

    @property
    def width_px(self) -> int:
        """画布宽。

        Returns:
            宽度（输出像素）。
        """
        return self._surface.width()

    @property
    def height_px(self) -> int:
        """画布高。

        Returns:
            高度（输出像素）。
        """
        return self._surface.height()

    def _skia_canvas(self) -> skia.Canvas:
        """返回底层 skia 画布，供包内绘制原语使用。

        Returns:
            当前 surface 的 skia.Canvas；调用方直接在其上绘制。
        """
        return self._surface.getCanvas()

    def save(self, path: str | Path) -> Path:
        """写出 PNG 文件。

        Args:
            path: 输出路径，父目录须已存在。

        Returns:
            实际写出的路径。
        """
        out = Path(path)
        self.to_pil().save(out)
        return out

    def to_pil(self) -> PilImage.Image:
        """导出为 PIL Image。

        Returns:
            RGBA 模式的 PIL Image。
        """
        return PilImage.fromarray(self.to_numpy(), "RGBA")

    def to_numpy(self) -> NDArray[np.uint8]:
        """导出为 NumPy 数组。

        Returns:
            (H, W, 4) uint8 RGBA 数组。
        """
        # skia 光栅缓冲是 BGRA，导出时换回 RGBA
        return self._surface.makeImageSnapshot().toarray()[:, :, [2, 1, 0, 3]]
