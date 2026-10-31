"""stockchart：把数据画成被拉起的丝袜。

公开 API 按 L0–L4 分层：腿素材、丝袜渲染、自由柱状图、布局封装与一行出图。
常用入口是 `bar()` / `mirror_bar()` 与 `render_stocking()`。
"""

__version__ = "0.1.0"

from stockchart.canvas import Canvas
from stockchart.color import Color
from stockchart.data import (
    DataInput,
    PlotData,
    normalize_data,
    register_data_type,
)
from stockchart.legs import Leg
from stockchart.library import LegLibrary, load_leg
from stockchart.plot import (
    AxisStyle,
    BarPlot,
    Pairing,
    Scale,
    TitleAlign,
    XLabelRotation,
)
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
from stockchart.topline import ChartOptions, bar, mirror_bar

__all__ = [
    "STYLES",
    "AxisStyle",
    "BarPlot",
    "Bare",
    "Canvas",
    "ChartOptions",
    "Color",
    "DataInput",
    "Dotted",
    "Fade",
    "Fishnet",
    "FontSpec",
    "Lace",
    "Leg",
    "LegLibrary",
    "Pairing",
    "Plain",
    "PlotData",
    "Ribbed",
    "Scale",
    "Shading",
    "StockingStyle",
    "Stripe",
    "Striped",
    "StyleLike",
    "StyleSeq",
    "TextAnchor",
    "TitleAlign",
    "Welt",
    "XLabelRotation",
    "bar",
    "draw_text",
    "load_leg",
    "measure_text",
    "mirror_bar",
    "normalize_data",
    "register_data_type",
    "render_stocking",
    "sketch_axis",
    "sketch_line",
]
