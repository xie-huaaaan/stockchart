# stockchart

[English](https://github.com/xie-huaaaan/stockchart/blob/main/README.md) |
[简体中文](https://github.com/xie-huaaaan/stockchart/blob/main/README.zh-CN.md)

[![PyPI](https://img.shields.io/pypi/v/stockchart)](https://pypi.org/project/stockchart/)
[![Python](https://img.shields.io/badge/python-3.12%2B-blue)](https://www.python.org/)
[![License: MPL 2.0](https://img.shields.io/badge/license-MPL--2.0-blue)](https://github.com/xie-huaaaan/stockchart/blob/main/LICENSE)

**A creative plotting library that draws data as stockings pulled up over a pair of legs.**

![A grouped stockchart: two series over three months](https://raw.githubusercontent.com/xie-huaaaan/stockchart/main/docs/images/hero.png)

`stockchart` is a playful alternative to the bar chart. Each value becomes the height of a
stocking pulled up over a leg: a larger value means more stocking, and zero is a bare leg.
It is made for infographics, slides, posters, and anywhere a chart should be memorable
rather than conventional.

- **Values → stocking height.** Grouped, paired, and positive/negative mirror charts are
  supported.
- **19 built-in styles.** Sheer, opaque tights, stripes, knit, fishnet, polka dots, hearts,
  lace trims, and more.
- **Data-science friendly.** Lists, NumPy arrays, dictionaries, and pandas
  `DataFrame`/`Series`. pandas is optional and never imported by the library itself.
- **Native high-resolution output.** Stocking textures and lighting are generated at the
  target pixel density, not upscaled from a bitmap.
- **Composable by design.** Start with one-line `bar()`; drop down to pixel-level placement
  when you need a custom layout.
- **No matplotlib.** Text and lines are rendered with Skia, including a per-character font
  fallback for Chinese, Japanese, and Korean.

## Installation

```bash
pip install stockchart
```

or with [uv](https://docs.astral.sh/uv/):

```bash
uv add stockchart
```

Requires Python 3.12 or newer. Runtime dependencies are `skia-python`, `numpy`, and
`pillow`.

## Quick start

```python
from stockchart import bar

bar(
    [[320, 210], [450, 280], [510, 190]],
    labels=["Jan", "Feb", "Mar"],
    series_labels=["This site", "Neighbor"],
    title="Monthly report",
    xlabel="Month",
    ylabel="Active users",
    style=["black_sheer", "white_sheer"],
    value_labels=True,
    seed=2,
).save("chart.png")
```

The result is the image at the top of this README. `bar()` maps the data, chooses leg
assets, lays out groups, and draws the axes. It returns a `BarPlot` that can be saved
directly or adjusted further.

A mirror chart for positive and negative values:

```python
from stockchart import mirror_bar

mirror_bar(
    [4.2, -2.8, 6.1, -5.5],
    labels=["Mon", "Tue", "Wed", "Thu"],
    title="Daily change",
    style="gray_sheer",
    value_labels=True,
).save("mirror.png")
```

## Data input

Pass the data structure you already have:

| Input | How it is interpreted |
| --- | --- |
| 1-D list / tuple / sequence | One series |
| 2-D sequence `(groups, series)` | Grouped data |
| `numpy.ndarray` | 1-D or 2-D arrays |
| `dict` of scalars | Keys become x-axis labels, one series |
| `dict` of equal-length sequences | Keys become series names and a legend is generated |
| pandas `DataFrame` | Index → x labels, columns → series names |
| pandas `Series` | Index → x labels, one series |
| `PlotData` | Already-normalized data |

For example, a DataFrame gets its labels and legend automatically:

```python
import pandas as pd
from stockchart import bar

df = pd.DataFrame(
    {"This site": [320, 450, 510], "Neighbor": [210, 280, 190]},
    index=["Jan", "Feb", "Mar"],
)
bar(df, title="Monthly report", style=["black_sheer", "white_sheer"]).save("chart.png")
```

Explicit `labels=` and `series_labels=` override anything inferred from the data. Custom
containers can be registered with `register_data_type`; see the
[data input reference](https://github.com/xie-huaaaan/stockchart/blob/main/docs/api.md).

## Stocking styles

Pass a preset name, or a list of names to cycle through styles:

```python
bar([320, 480, 250], style=["black_sheer", "white_sheer", "fishnet_black"])
```

The 19 presets cover sheer stockings, opaque tights, stripes, ribbed knit, fishnet,
polka dots, hearts, lace trims, and more. For direct control, pass a `StockingStyle`
built from `Plain`, `Striped`, `Ribbed`, `Fishnet`, or `Dotted` fabrics with a
`Bare`, `Welt`, `Lace`, or `Fade` top edge. The full style table is in the
[API reference](https://github.com/xie-huaaaan/stockchart/blob/main/docs/api.md).

## Titles, axis names, and options

```python
bar(
    [[320, 210], [450, 280], [510, 190]],
    labels=["Jan", "Feb", "Mar"],
    series_labels=["This site", "Neighbor"],
    title="Monthly report",  # centered over the plot by default
    xlabel="Month",
    ylabel="Active users",
    title_align="left",  # restore a left-aligned title
    grid=True,
    axis_style="handdrawn",
    legend_loc="bottom",
)
```

Chart-level parameters stay in the signature; lower-level options such as `grid`,
`axis_style`, `legend_loc`, `legend_ncol`, `x_label_rotation`, `bar_gap`, and `group_gap`
are passed through a typed option bag. See the
[`ChartOptions` table](https://github.com/xie-huaaaan/stockchart/blob/main/docs/api.md).

## API layers

The library is deliberately layered, so you can choose how much control you want:

| Layer | What it gives you | Entry points |
| --- | --- | --- |
| L0 assets | Leg metadata and built-in artwork | `Leg`, `LegLibrary`, `load_leg` |
| L1 primitives | One stocking, text, hand-drawn lines | `render_stocking`, `StockingStyle`, `STYLES`, `draw_text`, `sketch_*` |
| L2 free-form plot | Canvas, baseline, arbitrary leg placement | `BarPlot`, `Scale`, `Canvas` |
| L3 layout helpers | Uniform spacing and automatic leg selection | `add_bars`, `add_grouped_bars`, `add_paired_bars` |
| L4 one-liners | Data normalization and fully automatic layout | `bar`, `mirror_bar` |

For a more hands-on layout:

```python
from stockchart import BarPlot, Scale

plot = BarPlot(1200)
plot.add_bars([300, 500, 400], style="black_sheer")
plot.add_x_labels(["A", "B", "C"])
plot.add_y_axis(Scale((0, 500), (0, 760)))
plot.add_title("Free-form layout")
plot.save("chart.png")
```

## Output

`BarPlot` renders to PNG and can also return a PIL image or a NumPy array:

```python
plot.save("chart.png", scale=2)  # PNG at 2× pixel density
image = plot.to_pil()
array = plot.to_numpy()
```

`scale` controls output pixel density; stocking textures and lighting are regenerated at
that density. SVG and PDF output are intentionally not supported.

## Documentation

- [API reference](https://github.com/xie-huaaaan/stockchart/blob/main/docs/api.md) (Chinese)
- [Design notes](https://github.com/xie-huaaaan/stockchart/blob/main/docs/design.md) (Chinese)
- [中文说明](https://github.com/xie-huaaaan/stockchart/blob/main/README.zh-CN.md)

## Development

```bash
git clone https://github.com/xie-huaaaan/stockchart.git
cd stockchart
uv sync
uv run python -m pytest
uv run ruff check . && uv run ruff format .
uv run python -m pyright
```

Issues and pull requests are welcome.

## Status

`0.1.x` is an early public release. The rendering pipeline is stable, but the public API
may still change in minor releases.

## License

Copyright © 2026 xie-huaaaan.

Released under the [Mozilla Public License 2.0](https://github.com/xie-huaaaan/stockchart/blob/main/LICENSE)
(MPL-2.0). You can use `stockchart` in closed-source projects; if you modify MPL-covered
source files, those files must remain available under MPL-2.0.
