"""L2 自由柱状图：比例尺与自由摆放的柱状图。

公开入口是 BarPlot（自由摆放）与 Scale（值到像素的换算）；
样式解析、布局计算与绘制实现在同包的 styles / layout / draw 模块。
"""

from __future__ import annotations

from stockchart.plot.api import BarPlot
from stockchart.plot.scale import Scale
from stockchart.plot.types import (
    AxisStyle,
    BarSide,
    LegendLoc,
    Pairing,
    StyleCycle,
    TitleAlign,
    XLabelPos,
    XLabelRotation,
)

__all__ = [
    "AxisStyle",
    "BarPlot",
    "BarSide",
    "LegendLoc",
    "Pairing",
    "Scale",
    "StyleCycle",
    "TitleAlign",
    "XLabelPos",
    "XLabelRotation",
]
