# L4 — bar() and mirror_bar()

← [API index](index.md) · Related: [L4 data input](data-input.md) · [L3 layout helpers](layout.md)

## L4 option passthrough

`bar` / `mirror_bar` keep only chart-semantic parameters; options that the current layer does not consume and that need to reach `BarPlot` or the `add_*` methods are received via `**options`. The options are defined centrally in `ChartOptions`:

```python
class ChartOptions(TypedDict, total=False):
    """Optional parameters L4 passes through to lower layers; key names match the L2 interfaces."""

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
    legend_loc: Literal["top", "bottom"]
    legend_ncol: int | None
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
| `legend_loc` | `"top"` | `add_legend(loc=)` |
| `legend_ncol` | `None` (automatic) | `add_legend(ncol=)` |

Unknown keys raise `TypeError` at runtime and list the available options; static typing is checked by the `TypedDict`. Older keywords such as `axis_style` / `grid` / `x_label_pos` are still accepted as before; they simply no longer appear in the function signatures.

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
    max_fill: float = 0.8,
    min_fill: float = 0.1,
    y_extent: int = DEFAULT_Y_EXTENT,
    width_px: int | None = None,
    seed: int | None = None,
    **options: Unpack[ChartOptions],
) -> BarPlot:
    """An all-upward bar chart: automatically performs data -> stocking height mapping, leg selection, and layout, and returns a fully laid-out BarPlot (ready for .save() / .render(), or for further manual tweaks).

    The y axis and baseline are drawn automatically (straight by default;
    axis_style="handdrawn" switches to hand-drawn wobble). When labels are
    given, x labels align to each group automatically and tilt to avoid
    collisions when too long; when the plot-area width is omitted it adapts
    to the legs, spacing, and label widths, and the final canvas is wider
    because of axes, labels, and title. Legend labels wrap automatically when
    they exceed the plot-area width. labels feeds the x
    labels and series_labels feeds the legend — the latter distinguishes
    "series" (which leg within a group), the former distinguishes "groups".

    Args:
        data: supports 1D/2D sequences, numpy arrays, dicts, pandas-style
            table objects, and PlotData; a DataFrame's index/columns become
            the x labels and series names automatically. See [Data input](data-input.md)
            for the complete list.
        labels: one label per group (per bar when there is no grouping);
            defaults to labels inferred from the data.
        series_labels: one name per series; providing it generates a legend
            automatically (the swatches are the fabric of each series's
            style); defaults to series names inferred from the data. Only
            valid for 2D data; providing it with 1D data raises ValueError.
        title: chart title, horizontally centered above the plot area by
            default; title_align="left" switches to left-aligned.
        xlabel: x axis name, drawn below the x labels.
        ylabel: y axis name, drawn to the left of the tick numbers
            (CJK text vertical, the rest rotated).
        style: a single style, or a list of styles — cycled according to
            cycle.
        cycle: how a style list cycles: "group" cycles by position within
            the group (the i-th bar of a group uses styles[i % len], so a
            list whose length equals the series count means "one style per
            series"); "sequence" cycles in the draw order of all bars;
            "auto" (default) takes "sequence" for 1D data (i.e. each bar
            takes styles in order) and "group" for 2D data. With 2D data,
            if "sequence" cannot be matched to a fixed per-series style when
            series_labels is also given; providing both raises ValueError.
        paired: leg-pairing strategy. "auto" (default) uses "none" for a
            single series and "global" for multiple series; "group" takes
            complete pairs independently within each group: series 0 and 1
            share a pair (left, right), series 2 starts the next pair;
            "global" takes pairs continuously across the whole chart, so a
            pair may span groups; "none" draws every leg from a different
            pair. For a single series, "group" takes the left leg of a fresh
            pair for each group.
        value_labels: when True, handwritten value labels above the
            stocking tops.
        max_fill: fraction of y_extent the maximum maps to (default 0.8).
        min_fill: only enabled when the data contains negatives
            (default 0.1); see below.
        y_extent: design-pixel height reserved above the baseline for the bar
            area; excludes title, labels, legend, and other edge areas.
        width_px: plot-area width; by default adapts to the leg count,
            spacing, and label widths. The final canvas is wider because of
            axes, labels, and title.
        options: optional parameters passed through to lower layers; see
            the `ChartOptions` table (grid, axis_style, legend_loc,
            bar_gap, etc.).

    Data -> stocking height (the data value at the baseline defaults to 0):
        - All values are 0: all legs bare.
        - No negatives: height = v / max x max_fill x y_extent; a value of 0
          means a bare leg.
        - Negatives present: the entire value range [min, max] is linearly
          compressed into [min_fill, max_fill]. A value of 0 then gets a
          leg with some stocking, and the y axis's 0 tick floats somewhere
          mid-stocking — an accepted trade-off to fully preserve the
          ordering of the values. All-negative data follows the same rule:
          the larger the value, the higher the stocking. When all values
          are the same negative number there is no ordering to preserve,
          so every leg uses min_fill.
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
    max_abs_fill: float = 0.8,
    y_extent: int = DEFAULT_Y_EXTENT,
    width_px: int | None = None,
    seed: int | None = None,
    **options: Unpack[ChartOptions],
) -> BarPlot:
    """A positive/negative mirrored bar chart: positive values draw a leg above the baseline, negative values a flipped leg below it (foot against the baseline).

    Args:
        data: same semantics as bar(); supports exactly the same data
            formats.
        mode: "single" draws only the leg on the data's side; "both" draws
            on both sides — the data side wears a stocking, the other side
            is bare.
        labels: one label per group (per bar when there is no grouping);
            defaults to labels inferred from the data.
        series_labels: same semantics as bar().
        title: chart title, centered by default.
        xlabel: x axis name.
        ylabel: y axis name.
        style: same semantics as bar().
        cycle: same semantics as bar().
        paired: same semantics as bar(); mirrored charts also default to "auto".
        value_labels: when True, handwritten value labels — above the
            stocking top for upper legs, below it for lower legs.
        max_abs_fill: fraction of y_extent the largest absolute value maps
            to (default 0.8).
        y_extent: design-pixel height reserved above the baseline for the bar
            area; excludes title, labels, legend, and other edge areas.
        width_px: plot-area width; adapts by default. The final canvas is
            wider because of axes, labels, and title.
        options: same semantics as bar(). x_label_pos defaults to "auto":
            mirrored charts often leave one side entirely empty, so labels
            sit by the baseline on the side without legs (e.g. above the
            baseline for all-negative data); when both sides have legs
            (mixed signs or mode="both") it falls back to "content",
            drawn below the lowest point of all content.

    Rules:
        - Scale = max_abs_fill x y_extent / max|v|, the same for positive
          and negative.
        - 0 counts as +0: under "single" one bare leg pointing up is drawn;
          under "both" bare legs are drawn on both sides (the upper one is
          the data side).
        - Space below: "single" reserves it only when negatives exist;
          "both" always reserves it.
    """
```

Parameter checks: `max_fill` / `max_abs_fill` must be finite and positive,
`0 <= min_fill < max_fill`, `y_extent` must be positive, and `cycle` plus
`mirror_bar`'s `mode` only accept the documented values. NaN / Infinity in
the data raise `ValueError` during normalization.

## Centralized defaults

All `DEFAULT_*` constants are collected in `src/stockchart/defaults.py`: `DEFAULT_Y_EXTENT` (760),
`DEFAULT_BAR_GAP` (28), `DEFAULT_GROUP_GAP` (120), `DEFAULT_OUTPUT_SCALE`, the background/ink/text colors,
`DEFAULT_AXIS_STYLE` (clean), wobble amplitudes, font sizes (ticks 26 / x labels 30 / title 52 /
axis names 30 / legend 28 / value labels 26), `DEFAULT_TITLE_ALIGN` (center), axis-name spacing and line height,
x-label avoidance angles, legend wrap line counts and line heights, legend swatch size and spacing, grid line colors, and so on.
Drawing code carries no magic numbers of its own; tuning means changing one place.
