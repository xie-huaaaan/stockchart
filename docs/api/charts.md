# L4 — bar() and mirror_bar()

← [API index](index.md) · Related: [L4 data input](data-input.md) · [L3 layout helpers](layout.md)

## L4 option passthrough

`bar` / `mirror_bar` keep only chart-semantic parameters; options that the current layer does not consume and that need to reach `BarPlot` or the `add_*` methods are received via `**options`. The options are defined centrally in `ChartOptions`:

```python
class ChartOptions(TypedDict, total=False):
    """Optional parameters L4 passes through to lower layers; the key names match the L2 interfaces.

    Attributes:
        axis_style: axis style, "clean" or "handdrawn".
        background: canvas background color.
        bar_gap: gap between the edges of adjacent legs within a group (design pixels).
        group_gap: gap between groups (design pixels).
        font: chart-wide default font (family name, font file path or a list of
            candidates), applied to the title, axis names, ticks, x labels, the
            legend and the value labels; None uses the platform default chain.
        grid: whether to draw the horizontal dashed lines at the y ticks.
        ticks: explicit tick values; None means they are generated automatically.
        x_label_pos: x label position strategy.
        x_label_rotation: x label rotation strategy.
        title_align: title alignment.
        title_size_px: title font size (design pixels).
        axis_name_size_px: axis name font size (design pixels).
        legend_loc: whether the legend sits at the top or at the bottom.
        legend_ncol: number of legend columns; None means it wraps automatically.
        height_px: bar area height above the baseline; None means the tallest leg's
            design height plus 10% headroom.
        width_px: plot area width; None means it is computed automatically from the
            legs, the gaps and the label widths.
    """

    axis_style: Literal["clean", "handdrawn"]
    background: Color
    bar_gap: float
    group_gap: float
    grid: bool
    ticks: Sequence[float] | None
    x_label_pos: Literal["content", "auto", "above", "below"]
    x_label_rotation: float | Literal["auto"]
    title_align: Literal["center", "left"]
    title_size_px: float
    axis_name_size_px: float
    font: FontSpec | None
    legend_loc: Literal["top", "bottom"]
    legend_ncol: int | None
    height_px: int | None
    width_px: int | None
```

| Option | Default | Goes to |
| --- | --- | --- |
| `axis_style` | `"clean"` | `BarPlot(axis_style=)` |
| `background` | `DEFAULT_BACKGROUND` | `BarPlot(background=)` |
| `bar_gap` | `DEFAULT_BAR_GAP` (28) | gap between legs within a group |
| `group_gap` | 28 for 1D / 120 for 2D | gap between groups |
| `grid` | `False` | `add_y_axis(grid=)` |
| `ticks` | `None` (automatic whole-step ticks) | `add_y_axis(ticks=)` |
| `x_label_pos` | `bar` -> `"content"`, `mirror_bar` -> `"auto"` | `add_x_labels(pos=)` |
| `x_label_rotation` | `"auto"` | `add_x_labels(rotation=)` |
| `title_align` | `"center"` | `add_title(align=)` |
| `title_size_px` | `DEFAULT_TITLE_SIZE` (52) | `add_title(size_px=)` |
| `axis_name_size_px` | `DEFAULT_AXIS_NAME_SIZE` (30) | both axis-name font sizes |
| `font` | `None` (platform default chain) | `BarPlot(font=)`, the chart-wide text font; e.g. `font=["MiSans", "Microsoft YaHei"]` or a font file path |
| `legend_loc` | `"top"` | `add_legend(loc=)` |
| `legend_ncol` | `None` (automatic) | `add_legend(ncol=)` |
| `height_px` | `None` (tallest full leg + 10% headroom) | `BarPlot(extent_up=)` / y-axis length; a smaller explicit value still expands to the full leg height |
| `width_px` | `None` (legs, gaps, labels) | `BarPlot(width_px=)` / x-axis length |

`font` is the chart-wide default font, passed through to `BarPlot(font=)`; it applies to the title, axis names, x labels, legend, tick numbers, and value labels. Its value is a `FontSpec` (family names / font file paths / a candidate list, see L1 rendering primitives); None uses the platform default chain. Unknown keys raise `TypeError` at runtime and list the available options; static typing is checked by the `TypedDict`. Older keywords such as `axis_style` / `grid` / `x_label_pos` are still accepted as before; they simply no longer appear in the function signatures.

## L4 one-liners

```python
def bar(
    data: DataInput,
    *,
    labels: Sequence[str] | None = None,
    series_labels: Sequence[str] | None = None,
    title: str | None = None,
    xlabel: str | None = None,
    ylabel: str | None = None,
    style: StyleSeq = DEFAULT_STOCKING_STYLE,
    cycle: Literal["auto", "group", "sequence"] = "auto",
    paired: Literal["auto", "none", "group", "global"] = "auto",
    value_labels: bool = False,
    max_fill: float = 0.85,
    min_fill: float = 0.1,
    seed: int | None = None,
    library: LegLibrary = DEFAULT_LEG_LIBRARY,
    **options: Unpack[ChartOptions],
) -> BarPlot:
    """All-upright bar chart: automatically performs the data to stocking height mapping, the leg selection and the layout.

    The y axis and the baseline are drawn automatically; when labels are given the
    x labels align with each group automatically; when the plot area width is
    omitted it adapts to the legs, the gaps and the label widths, and the final
    canvas ends up wider because of the axes, the labels and the title. The axes
    are straight by default; axis_style="handdrawn" switches to a hand-drawn wobble.

    Args:
        data: supports 1D/2D sequences, numpy arrays, dicts, pandas-style table
            objects and PlotData; a DataFrame's index/columns automatically become
            the x labels and the series names. See docs/api/data-input.md for the
            complete list.
        labels: one label per group (per bar when there is no grouping); by default
            the labels inferred from the data are used.
        series_labels: one name per series; providing it generates a legend
            automatically (the marker is a fabric swatch of each series' style);
            by default the series names inferred from the data are used. Only
            available for 2D data; providing it with 1D data raises ValueError.
        title: chart title, horizontally centered above the plot area by default;
            title_align="left" switches to left alignment.
        xlabel: x axis name, drawn below the x labels.
        ylabel: y axis name, to the left of the tick numbers; CJK text is set
            vertically character by character, while Latin letters and digits
            are rotated 90 degrees (see add_y_axis_name).
        style: a single style, or a list of styles — the cycling is decided by
            cycle.
        cycle: "group" cycles by the position within the group (the i-th bar of a
            group takes styles[i % len]), "sequence" cycles in the draw order of
            all the bars; "auto" (default) takes "sequence" for 1D data (each bar
            takes the styles in order) and "group" for 2D data (a length equal to
            the series count means "one style per series"). With 2D data, if
            "sequence" cannot be matched to the series styles of the legend,
            providing series_labels as well raises ValueError.
        paired: leg pairing strategy. "auto" (default) uses "none" for a single
            series and "global" for multiple series; "group" takes complete pairs
            independently within each group: series 0 and 1 share a pair (left,
            right), series 2 onwards takes the next pair (for a single series,
            each group takes the left leg of a fresh asset pair); "global" takes
            pairs continuously across the whole chart, so a pair may span groups;
            "none" selects from all legs, including unpaired assets, avoiding repeats where possible.
        value_labels: when True, the values are handwritten above the stocking
            tops (6 significant digits; scientific notation for magnitudes of 10^6
            and above, or below 10^-4; not part of layout).
        max_fill: the fraction of the asset design height the maximum value maps
            to; it must be in (0, 1] (default 0.85).
        min_fill: only enabled when the data contains negatives (default 0.1);
            see below.
        library: Library for automatic leg selection; defaults to DEFAULT_LEG_LIBRARY.
        options: optional parameters passed through to lower layers (grid,
            axis_style, legend_loc, bar_gap, height_px, width_px, etc.); see the
            ChartOptions table in docs/api/charts.md. height_px is the bar area
            height above the baseline, by default the tallest leg's design height
            plus 10% headroom; an explicit value smaller than the full leg height
            still expands to the full leg height. width_px is the plot area width,
            adaptive by default.

    Returns:
        A laid-out BarPlot with the legend/axes/title added; it can be saved
        directly with `.save()` / `.render()`, or tweaked by hand afterwards.

    Raises:
        TypeError: the data type is not supported, or options contains an unknown
            key.
        ValueError: the label count does not match, series_labels is used with 1D
            data, cycle is invalid, max_fill/min_fill/height_px/width_px are
            invalid, the style list is empty or holds an unknown preset, or the
            data content is invalid.

    Data -> stocking height (the data value at the baseline defaults to 0):
        - The reference height is the smallest design height among the legs picked
          for this chart, so that no leg is clipped at the top; the built-in assets
          are all 720.
        - All the data is 0: all legs are bare.
        - No negatives: height = v / max x max_fill x reference height, a value of 0
          means a bare leg.
        - Negatives present: the whole value range [min, max] is linearly
          compressed into [min_fill, max_fill]. In this case the leg of a 0 value
          wears a stretch of stocking and the 0 tick of the y axis floats somewhere
          in the middle of the stocking — an accepted trade-off made to fully
          preserve the ordering of the values. All-negative data follows the
          same rule: the larger the value, the higher the stocking; when all the
          values are the same negative number (there is no ordering to preserve)
          min_fill is used throughout.
    """


def mirror_bar(
    data: DataInput,
    *,
    mode: Literal["single", "both"] = "single",
    labels: Sequence[str] | None = None,
    series_labels: Sequence[str] | None = None,
    title: str | None = None,
    xlabel: str | None = None,
    ylabel: str | None = None,
    style: StyleSeq = DEFAULT_STOCKING_STYLE,
    cycle: Literal["auto", "group", "sequence"] = "auto",
    paired: Literal["auto", "none", "group", "global"] = "auto",
    value_labels: bool = False,
    max_abs_fill: float = 0.85,
    seed: int | None = None,
    library: LegLibrary = DEFAULT_LEG_LIBRARY,
    **options: Unpack[ChartOptions],
) -> BarPlot:
    """Positive/negative mirrored bar chart: positive values draw a leg above the baseline, negative values a flipped leg below it (the foot against the baseline).

    The y axis extends downward with the negative ticks.

    Args:
        data: same semantics as bar(), supports exactly the same data formats.
        mode: "single" draws only the leg on the side of the data; "both" draws on
            both sides, the data side wears a stocking, the other side is a bare
            leg.
        labels: one label per group (per bar when there is no grouping); by default
            the labels inferred from the data are used.
        series_labels: same semantics as bar().
        title: chart title, centered by default.
        xlabel: x axis name.
        ylabel: same semantics as bar().
        style: same semantics as bar().
        cycle: same semantics as bar().
        paired: same semantics as bar(); mirrored charts also default to "auto".
        value_labels: when True, the values are handwritten — above the stocking
            top for the upper legs, below it for the lower legs (6 significant
            digits; scientific notation for magnitudes of 10^6 and above, or below
            10^-4; not part of layout).
        max_abs_fill: the fraction of the asset design height the largest absolute
            value maps to; it must be in (0, 1] (default 0.85).
        library: Library for automatic leg selection; defaults to DEFAULT_LEG_LIBRARY.
        options: same semantics as bar(). height_px controls the bar area height
            above the baseline, by default the tallest leg's design height plus 10%
            headroom; width_px controls the plot area width, adaptive by default.
            An explicit height_px smaller than the full leg height still expands to
            the full leg height. x_label_pos defaults to "auto": mirrored charts
            often leave one side entirely empty, so the labels sit by the baseline
            on the side without legs (e.g. above the baseline for all-negative
            data); when both sides have legs (mixed signs or mode="both") it falls
            back to "content", drawn below the lowest point of all the content.

    Returns:
        A laid-out BarPlot with the legend/axes/title added; it can be saved
        directly with `.save()` / `.render()`, or tweaked by hand afterwards.

    Raises:
        TypeError: the data type is not supported, or options contains an unknown
            key.
        ValueError: the label count does not match, series_labels is used with 1D
            data, mode/cycle is invalid, max_abs_fill/height_px/width_px are
            invalid, the style list is empty or holds an unknown preset, or the
            data content is invalid.

    Rules:
        - The reference height is the smallest design height among the legs picked
          for this chart; the scale = max_abs_fill x reference height / max|v|, the
          same for positive and negative values.
        - 0 counts as +0: under "single" one upward bare leg is drawn; under "both"
          bare legs are drawn on both sides (the upper one is the data side).
        - Space below: "single" reserves it only when negatives exist; "both"
          always reserves it.
    """
```

Parameter checks: `max_fill` / `max_abs_fill` must be in (0, 1], `0 <= min_fill < max_fill`, explicit `height_px` / `width_px` must be positive, and `cycle` plus `mirror_bar`'s `mode` only accept the documented values. NaN / Infinity in the data raise `ValueError` during normalization.

## Centralized defaults

All `DEFAULT_*` constants are collected in `src/stockchart/defaults.py`: `DEFAULT_MAX_FILL` (0.85), `DEFAULT_MIN_FILL` (0.1), `DEFAULT_HEIGHT_HEADROOM_RATIO` (0.1, the column-area headroom ratio), `DEFAULT_Y_EXTENT` (792, the L2 column-area default), `DEFAULT_BAR_GAP` (28), `DEFAULT_GROUP_GAP` (120), `DEFAULT_OUTPUT_SCALE`, the background/ink/text colors, `DEFAULT_AXIS_STYLE` (clean), wobble amplitudes, font sizes (ticks 26 / x labels 30 / title 52 / axis names 30 / legend 28 / value labels 26), `DEFAULT_TITLE_ALIGN` (center), axis-name spacing, and line-height factors (title 1.4 / axis names 1.25 / x labels 1.35 / legend 1.25, multiplied by the font's natural line height to get the line spacing), x-label avoidance angles, legend wrap line counts and row gaps, legend swatch size and spacing, grid line colors, and the default font chain `DEFAULT_FONT_FAMILIES`, among others. Drawing code carries no magic numbers of its own; tuning means changing one place. L2's `BarPlot(extent_up=)` still defaults to `DEFAULT_Y_EXTENT` (792).

## Minimal example

```python
from stockchart import bar

bar(
    [320, 450, 510],
    labels=["Jan", "Feb", "Mar"],
    title="Monthly active users",
    value_labels=True,
    seed=2,
).save("chart.png")
```
