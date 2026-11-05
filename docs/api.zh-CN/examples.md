# 示例

← [API 索引](index.md) · 相关：[L4 — bar() 与 mirror_bar()](charts.md) · [L2 — 自由柱状图](barplot.md)

本页每段代码都可独立运行，不依赖外部数据文件；图片写到当前目录。逐段复制成 `.py` 执行即可。

## 分组柱状图

二维数据 `(组数, 系列数)` 自动变成并排的柱子，`labels` 是组名，`series_labels` 是系列名（传入即自动出图例）。

```python
from stockchart import bar

bar(
    [[320, 210], [450, 280], [510, 190]],
    labels=["一月", "二月", "三月"],
    series_labels=["本站", "隔壁站"],
    title="每月活跃用户",
    xlabel="月份",
    ylabel="人数",
    style=["black_sheer", "white_sheer"],
    value_labels=True,
    seed=2,
).save("grouped.png")
```

## 成对布局

`paired="group"` 让每组用同一对素材：系列 0 是左腿、系列 1 是右腿，看起来像一双并排的腿。

```python
from stockchart import bar

bar(
    [[320, 210], [450, 280]],
    labels=["一月", "二月"],
    series_labels=["本站", "隔壁站"],
    title="成对布局",
    paired="group",
    seed=2,
).save("paired.png")
```

## 正负镜像图

`mirror_bar()` 把正值画在基线上方、负值画在下方（脚贴基线的翻转腿）。默认只画数据侧：

```python
from stockchart import mirror_bar

mirror_bar(
    [4.2, -2.8, 6.1, -5.5],
    labels=["周一", "周二", "周三", "周四"],
    title="每日变化",
    style="gray_sheer",
    value_labels=True,
    seed=2,
).save("mirror.png")
```

`mode="both"` 两侧都画，非数据侧补一条裸腿：

```python
from stockchart import mirror_bar

mirror_bar(
    [4.2, -2.8, 6.1, -5.5],
    labels=["周一", "周二", "周三", "周四"],
    title="每日变化（双侧）",
    mode="both",
    style="gray_sheer",
    seed=2,
).save("mirror_both.png")
```

## 数值标签

`value_labels=True` 在袜口上方写出数值，统一按 6 位有效数字格式化；绝对值 ≥ 10⁶ 或 < 10⁻⁴ 时自动改用科学计数法。

```python
from stockchart import bar

bar(
    [1234567, 0.0000123, 42, 0],
    labels=["大数", "极小数", "整数", "零"],
    title="数值标签",
    value_labels=True,
    seed=2,
).save("value_labels.png")
```

## 图例与网格

图例缺省在标题下方；`legend_loc="bottom"` 挪到最底部，`legend_ncol` 指定一行几项，`grid=True` 画出横向网格线。

```python
from stockchart import bar

bar(
    [[320, 210], [450, 280]],
    labels=["一月", "二月"],
    series_labels=["本站", "隔壁站"],
    title="图例与网格",
    grid=True,
    legend_loc="bottom",
    legend_ncol=2,
    seed=2,
).save("legend.png")
```

## 指定字体

`font` 接受家族名、字体文件路径或按优先级排列的候选列表；链内都缺字形时回退系统字体，仍找不到才画方框占位。

```python
from stockchart import bar

bar(
    [320, 450, 510],
    labels=["一月", "二月", "三月"],
    title="指定字体",
    font=["MiSans", "Microsoft YaHei"],
    seed=2,
).save("font.png")
```

## 自定义样式

袜子 = 袜身（`Plain` / `Striped` / `Ribbed` / `Fishnet` / `Dotted`）+ 上沿（`Bare` / `Welt` / `Lace` / `Fade`）+ 光影（`Shading`）自由组合，三个部件都能单独调。

```python
from stockchart import Dotted, Lace, Plain, Shading, StockingStyle, bar

rose = StockingStyle(
    fabric=Dotted(
        base=Plain(color=(240, 220, 225), opacity=0.5),
        color=(200, 60, 90),
        shape="heart",
        size=4,
        spacing=20,
    ),
    top=Lace(height=30, scallop=26, color=(240, 220, 225)),
    shading=Shading(curve=0.2, highlight=0.5),
)

bar(
    [3, 5, 4, 6],
    labels=["A", "B", "C", "D"],
    title="自定义样式",
    style=rose,
    seed=1,
).save("custom_style.png")
```

## 自定义腿素材

`load_leg()` 读取带透明通道的 PNG，要求脚在图像底端；返回的 `Leg` 可以直接交给 L2 的 `add_bar()`。下面这段自带素材生成，无需外部文件。

```python
from PIL import Image, ImageDraw

from stockchart import BarPlot, Scale, load_leg

# 先生成一张示例素材：透明背景，脚在底端
image = Image.new("RGBA", (120, 400), (0, 0, 0, 0))
draw = ImageDraw.Draw(image)
draw.ellipse((25, 150, 95, 399), fill=(253, 234, 228, 255))
image.save("my_leg.png")

leg = load_leg("my_leg.png")

plot = BarPlot(600, extent_up=760)
plot.add_bar(300, 400, leg, style="white_sheer")
plot.add_y_axis(Scale((0, 400), (0, 400)))
plot.save("custom_leg.png")
```

## 自由排版

不经过 L4，直接用 L2/L3 摆放每一条腿：位置与丝袜高度都由自己给（设计像素）。

```python
from stockchart import BarPlot, Scale

plot = BarPlot(1200)
plot.add_grouped_bars([[300], [500], [400]], style="black_sheer")
plot.add_x_labels(["A", "B", "C"])
plot.add_y_axis(Scale((0, 500), (0, 500)))
plot.add_title("自由排版")
plot.save("freeform.png")
```

## 单条丝袜

`render_stocking()` 只负责给一条腿穿袜子，不涉及画布与坐标。

```python
from PIL import Image

from stockchart import STYLES, LegLibrary, render_stocking

library = LegLibrary(seed=0)
leg = library.get("leg_03")
rendered = render_stocking(leg, STYLES["black_sheer"], 500, seed=0)
Image.fromarray(rendered.image, "RGBA").save("leg.png")
```

## 文字绘制与度量

`draw_text()` 直接画在 `Canvas` 上；`measure_text()` / `measure_text_height()` / `wrap_text()` 可先量好尺寸再排版。

```python
from stockchart import Canvas, draw_text, measure_text, measure_text_height, wrap_text

canvas = Canvas(640, 260)
draw_text(canvas, "第一行\n第二行", 30, 50, size_px=36)
draw_text(
    canvas,
    "这是一段会按像素宽度自动折行的长文本，用来演示 max_width 与 max_lines 的效果。",
    30,
    140,
    size_px=24,
    max_width=560,
    max_lines=2,
)
canvas.save("text.png")

print(measure_text("每周活跃用户", size_px=30))  # 单行宽度
print(measure_text_height("第一行\n第二行", size_px=30))  # 多行高度
print(wrap_text("很长的一段文本，用来演示折行。", max_width=200, size_px=24))
```
