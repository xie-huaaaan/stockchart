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
    Striped,
    Stripe,
    StockingStyle,
    Welt,
    render_stocking,
)

__all__ = [
    "Color",
    "Leg",
    # L0
    "LegLibrary",
    "load_leg",
    # L1 styles
    "StockingStyle",
    "Plain",
    "Striped",
    "Stripe",
    "Ribbed",
    "Fishnet",
    "Dotted",
    "Bare",
    "Welt",
    "Lace",
    "Fade",
    "Shading",
    "STYLES",
    # L1 render
    "render_stocking",
]
