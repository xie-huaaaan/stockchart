"""L2 自由柱状图：比例尺与自由摆放的柱状图。

公开入口是 BarPlot（自由摆放）与 Scale（值到像素的换算）；
样式解析、布局计算与绘制实现在同包的 styles / layout / draw 模块。
types 模块的记录类型是 BarPlot 的输入输出形状，也一并导出。
"""

from __future__ import annotations

from stockchart.plot.api import BarPlot
from stockchart.plot.scale import Scale
from stockchart.plot.types import (
    AxisNameRecord,
    AxisStyle,
    BarRecord,
    BarSide,
    LegendLoc,
    LegendRecord,
    LegSpec,
    Pairing,
    PlotLayout,
    RenderInput,
    StyleCycle,
    TitleAlign,
    TitleRecord,
    XLabelPos,
    XLabelRotation,
    XLabelsRecord,
    YAxisRecord,
)

__all__ = [
    "AxisNameRecord",
    "AxisStyle",
    "BarPlot",
    "BarRecord",
    "BarSide",
    "LegSpec",
    "LegendLoc",
    "LegendRecord",
    "Pairing",
    "PlotLayout",
    "RenderInput",
    "Scale",
    "StyleCycle",
    "TitleAlign",
    "TitleRecord",
    "XLabelPos",
    "XLabelRotation",
    "XLabelsRecord",
    "YAxisRecord",
]
