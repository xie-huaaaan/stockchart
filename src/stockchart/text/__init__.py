"""L1 渲染原语：文字绘制与测量（skia.textlayout 段级整形引擎）。

字体解析链、折行与度量规则见 docs/design.zh-CN.md 的「字体」一节：用户
字体列表按优先级逐码点解析，栈内缺字形回退系统字体，仍无则画方框占位；
每行按字体分段后经 HarfBuzz 整形，kerning、连字与段内 RTL 正确。
"""

from stockchart.text.fonts import FontSpec
from stockchart.text.render import (
    TextAnchor,
    draw_text,
    measure_text,
    measure_text_height,
    wrap_text,
)

__all__ = [
    "FontSpec",
    "TextAnchor",
    "draw_text",
    "measure_text",
    "measure_text_height",
    "wrap_text",
]
