"""stockchart: draw data as stockings pulled up over legs."""

__version__ = "0.1.0.dev0"

from stockchart.canvas import Canvas
from stockchart.color import Color
from stockchart.legs import Leg
from stockchart.library import LegLibrary, load_leg
from stockchart.sketch import sketch_axis, sketch_line
from stockchart.stocking import (
    STYLES,
    Bare,
    Dotted,
    Fade,
    Fishnet,
    Lace,
    Plain,
    Ribbed,
    Shading,
    StockingStyle,
    Stripe,
    Striped,
    StyleLike,
    StyleSeq,
    Welt,
    render_stocking,
)
from stockchart.text import FontSpec, TextAnchor, draw_text, measure_text

__all__ = [
    "STYLES",
    "Bare",
    # 基础对象
    "Canvas",
    "Color",
    # L0
    "Dotted",
    "Fade",
    "Fishnet",
    "FontSpec",
    "Lace",
    "Leg",
    "LegLibrary",
    "Plain",
    "Ribbed",
    "Shading",
    "StockingStyle",
    "Stripe",
    "Striped",
    "StyleLike",
    "StyleSeq",
    "TextAnchor",
    "Welt",
    # L1 渲染原语
    "draw_text",
    "load_leg",
    "measure_text",
    "render_stocking",
    "sketch_axis",
    "sketch_line",
]
