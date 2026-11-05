# Examples

← [API index](index.md) · Related: [L4 — bar() and mirror_bar()](charts.md) · [L2 — free-form bar plot](barplot.md)

Every snippet below runs on its own and needs no external data files; images are written to the current directory. Copy a block into a `.py` file and run it.

## Grouped bar chart

A 2-D `(groups, series)` array becomes side-by-side legs. `labels` names the groups, `series_labels` names the series — passing them generates a legend automatically.

```python
from stockchart import bar

bar(
    [[320, 210], [450, 280], [510, 190]],
    labels=["Jan", "Feb", "Mar"],
    series_labels=["This site", "Neighbor"],
    title="Monthly active users",
    xlabel="Month",
    ylabel="Users",
    style=["black_sheer", "white_sheer"],
    value_labels=True,
    seed=2,
).save("grouped.png")
```

## Paired layout

`paired="group"` gives every group one pair of assets: series 0 is the left leg, series 1 the right one, so the group reads as a pair of legs.

```python
from stockchart import bar

bar(
    [[320, 210], [450, 280]],
    labels=["Jan", "Feb"],
    series_labels=["This site", "Neighbor"],
    title="Paired layout",
    paired="group",
    seed=2,
).save("paired.png")
```

## Mirror chart

`mirror_bar()` draws positive values above the baseline and negative ones below, as flipped legs with the foot on the baseline. By default only the data side is drawn:

```python
from stockchart import mirror_bar

mirror_bar(
    [4.2, -2.8, 6.1, -5.5],
    labels=["Mon", "Tue", "Wed", "Thu"],
    title="Daily change",
    style="gray_sheer",
    value_labels=True,
    seed=2,
).save("mirror.png")
```

`mode="both"` draws both sides; the non-data side gets a bare leg:

```python
from stockchart import mirror_bar

mirror_bar(
    [4.2, -2.8, 6.1, -5.5],
    labels=["Mon", "Tue", "Wed", "Thu"],
    title="Daily change (both sides)",
    mode="both",
    style="gray_sheer",
    seed=2,
).save("mirror_both.png")
```

## Value labels

`value_labels=True` writes the value above the stocking top. Numbers are formatted to 6 significant digits; scientific notation takes over for magnitudes of 10^6 and above, or below 10^-4.

```python
from stockchart import bar

bar(
    [1234567, 0.0000123, 42, 0],
    labels=["Large", "Tiny", "Integer", "Zero"],
    title="Value labels",
    value_labels=True,
    seed=2,
).save("value_labels.png")
```

## Legend and grid

The legend sits below the title by default; `legend_loc="bottom"` moves it to the very bottom, `legend_ncol` fixes how many items share a row, and `grid=True` draws horizontal grid lines.

```python
from stockchart import bar

bar(
    [[320, 210], [450, 280]],
    labels=["Jan", "Feb"],
    series_labels=["This site", "Neighbor"],
    title="Legend and grid",
    grid=True,
    legend_loc="bottom",
    legend_ncol=2,
    seed=2,
).save("legend.png")
```

## Choosing a font

`font` takes a family name, a font file path, or an ordered candidate list. When no candidate has the glyph, the system font is used; a boxed placeholder is drawn only if that fails too.

```python
from stockchart import bar

bar(
    [320, 450, 510],
    labels=["Jan", "Feb", "Mar"],
    title="Custom font",
    font=["MiSans", "Microsoft YaHei"],
    seed=2,
).save("font.png")
```

## Custom style

A stocking is a free combination of fabric (`Plain` / `Striped` / `Ribbed` / `Fishnet` / `Dotted`), top edge (`Bare` / `Welt` / `Lace` / `Fade`), and shading (`Shading`) — each adjustable on its own.

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
    title="Custom style",
    style=rose,
    seed=1,
).save("custom_style.png")
```

## Custom leg asset

`load_leg()` reads a PNG with an alpha channel whose foot sits at the bottom edge; the returned `Leg` can be handed straight to the L2 `add_bar()`. This snippet generates its own asset, so no external file is needed.

```python
from PIL import Image, ImageDraw

from stockchart import BarPlot, Scale, load_leg

# Build a sample asset first: transparent background, foot at the bottom
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

## Free-form layout

Skip L4 and place every leg yourself with L2/L3: both the position and the stocking height are given in design pixels.

```python
from stockchart import BarPlot, Scale

plot = BarPlot(1200)
plot.add_grouped_bars([[300], [500], [400]], style="black_sheer")
plot.add_x_labels(["A", "B", "C"])
plot.add_y_axis(Scale((0, 500), (0, 500)))
plot.add_title("Free-form layout")
plot.save("freeform.png")
```

## A single stocking

`render_stocking()` only dresses one leg; it deals with no canvas and no coordinates.

```python
from PIL import Image

from stockchart import STYLES, LegLibrary, render_stocking

library = LegLibrary(seed=0)
leg = library.get("leg_03")
rendered = render_stocking(leg, STYLES["black_sheer"], 500, seed=0)
Image.fromarray(rendered.image, "RGBA").save("leg.png")
```

## Drawing and measuring text

`draw_text()` paints onto a `Canvas`; `measure_text()` / `measure_text_height()` / `wrap_text()` let you size things before laying them out.

```python
from stockchart import Canvas, draw_text, measure_text, measure_text_height, wrap_text

canvas = Canvas(640, 260)
draw_text(canvas, "First line\nSecond line", 30, 50, size_px=36)
draw_text(
    canvas,
    "A long sentence that wraps automatically at a pixel width, showing what max_width and max_lines do.",
    30,
    140,
    size_px=24,
    max_width=560,
    max_lines=2,
)
canvas.save("text.png")

print(measure_text("Weekly active users", size_px=30))  # single-line width
print(measure_text_height("First line\nSecond line", size_px=30))  # multi-line height
print(wrap_text("A long sentence that wraps, for demo purposes.", max_width=200, size_px=24))
```
