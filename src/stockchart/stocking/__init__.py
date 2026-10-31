"""丝袜渲染子包：样式定义与渲染算法。

`styles` 提供 StockingStyle / Fabric / TopEdge / Shading 与 STYLES 预设；
`render` 提供 render_stocking()。通常从 `stockchart` 顶层导入即可。
"""

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
