"""丝袜渲染子包：样式定义（styles）与渲染算法（render）。"""

from stockchart.stocking.render import render_stocking
from stockchart.stocking.styles import (
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
)

__all__ = [
    "STYLES",
    "Bare",
    "Dotted",
    "Fade",
    "Fishnet",
    "Lace",
    "Plain",
    "Ribbed",
    "Shading",
    "StockingStyle",
    "Stripe",
    "Striped",
    "StyleLike",
    "StyleSeq",
    "Welt",
    "render_stocking",
]
