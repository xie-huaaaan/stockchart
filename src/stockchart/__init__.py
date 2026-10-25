"""stockchart: draw data as stockings pulled up over legs."""

__version__ = "0.1.0.dev0"

from stockchart.color import Color
from stockchart.legs import Leg
from stockchart.library import LegLibrary, load_leg
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
    Welt,
    render_stocking,
)

__all__ = [
    # L1 渲染原语
    "STYLES",
    "Bare",
    # L0
    "Color",
    "Dotted",
    "Fade",
    "Fishnet",
    "Lace",
    "Leg",
    "LegLibrary",
    "Plain",
    "Ribbed",
    "Shading",
    "StockingStyle",
    "Stripe",
    "Striped",
    "Welt",
    "load_leg",
    "render_stocking",
]
