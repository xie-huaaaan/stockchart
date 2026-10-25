"""跨层基础对象：Canvas 渲染载体。"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import skia
from numpy.typing import NDArray
from PIL import Image as PilImage

from stockchart.color import Color, check_color
from stockchart.defaults import DEFAULT_BACKGROUND


def skia_color(color: Color) -> int:
    """Color 元组 → skia ARGB 整数。"""
    check_color(color, "color")
    a = int(color[3]) if len(color) == 4 else 255
    return skia.Color(int(color[0]), int(color[1]), int(color[2]), a)


class Canvas:
    """最终渲染结果的载体：一块 RGBA 画布。

    通常由 `BarPlot.render()` 产生并绘制；自由绘制时也可直接构造，
    配合 L1 原语（`draw_text` / `sketch_*`）在上面作画。
    """

    def __init__(
        self,
        width_px: int,
        height_px: int,
        *,
        background: Color = DEFAULT_BACKGROUND,
    ) -> None:
        """构造空白画布并填充背景色。尺寸单位为素材像素。"""
        if width_px <= 0 or height_px <= 0:
            raise ValueError(f"画布尺寸须为正数，得到 {width_px}×{height_px}")
        self._surface = skia.Surface(width_px, height_px)
        self._surface.getCanvas().clear(skia_color(background))

    @property
    def width_px(self) -> int:
        """画布宽（素材像素）。"""
        return self._surface.width()

    @property
    def height_px(self) -> int:
        """画布高（素材像素）。"""
        return self._surface.height()

    def skia_canvas(self) -> skia.Canvas:
        """返回底层 skia 画布，供包内绘制原语使用；不属于公开 API。"""
        return self._surface.getCanvas()

    def save(self, path: str | Path) -> Path:
        """写出 PNG 文件，返回写出路径。"""
        out = Path(path)
        self.to_pil().save(out)
        return out

    def to_pil(self) -> PilImage.Image:
        """导出为 PIL Image（RGBA）。"""
        return PilImage.fromarray(self.to_numpy(), "RGBA")

    def to_numpy(self) -> NDArray[np.uint8]:
        """导出为 (H, W, 4) uint8 RGBA 数组。"""
        # skia 光栅缓冲是 BGRA，导出时换回 RGBA
        return self._surface.makeImageSnapshot().toarray()[:, :, [2, 1, 0, 3]]
