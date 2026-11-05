# L2 — free-form bar plot

← [API index](index.md) · Related: [L1 rendering primitives](rendering.md) · [L3 layout helpers](layout.md)

```python
@dataclass(slots=True, frozen=True)
class Scale:
    """Linear scale: data values <-> pixels above the baseline.

    Sharing one Scale between bar heights and axis ticks guarantees
    consistency.

    Attributes:
        domain: (value lower bound, value upper bound); the lower bound must
            be < the upper bound.
        range_px: (pixel lower bound, pixel upper bound), measured with the
            baseline at 0 and positive upwards; negative pixels are below
            the baseline, and the lower bound must be < the upper bound.

    Raises:
        ValueError: the lower bound of domain or range_px is not less than
            its upper bound.
    """

    domain: tuple[float, float]
    range_px: tuple[float, float]

    def to_px(self, value: float) -> float:
        """Convert a data value to pixels relative to the baseline.

        Args:
            value: the data value.

        Returns:
            The corresponding pixel value; positive upwards.
        """

    def from_px(self, px: float) -> float:
        """Convert pixels relative to the baseline to a data value.

        Args:
            px: the pixel value; positive upwards.

        Returns:
            The corresponding data value.
        """

    @classmethod
    def fit(cls, values: Sequence[float], extent_px: float, *, margin: float = 0.0) -> Scale:
        """Build a scale that covers the given value range.

        Args:
            values: sequence of data values; must not be empty and must not be
                all equal.
            extent_px: the pixel height the values are mapped to; must be
                positive; range_px is (0, extent_px).
            margin: the margin ratio on both sides; each end of domain is
                expanded outward by (max - min) × margin.

        Returns:
            A new Scale.

        Raises:
            ValueError: values is empty, contains non-finite numbers, extent_px
                is not positive, margin is negative, or all values are equal.
        """
```

```python
class BarPlot:
    """Free-form bar plot: with the X axis as the baseline, leg positions and stocking heights are entirely specified by the caller in design pixels.

    `width_px` is the plot-area width; `extent_up` / `extent_down` reserve
    height above/below the baseline for legs only, excluding the title, axis
    names, tick numbers, x labels, and the legend. The space for the axes,
    the text, the legend, and the title is computed separately at render
    time, so the final canvas is usually larger than
    `width_px × (extent_up + extent_down)`; the bar area expands
    automatically when a leg is taller than the reservation.

    Args:
        width_px: plot-area width (design pixels), also the x range used by
            the legs and the coordinates.
        extent_up: design-pixel height reserved above the baseline for legs;
            excludes the title, the legend, and other edge areas.
        extent_down: design-pixel height reserved below the baseline for
            downward legs; excludes the x labels and other edge areas.
        background: canvas background color.
        axis_style: "clean" draws straight axes and grid lines; "handdrawn"
            uses hand-drawn wobble controlled by seed.
        font: the chart-wide default font (a family name, a font file path,
            or a list of candidates); it is used by the add_* methods and by
            the value labels when they do not specify a font of their own,
            None uses the platform default chain.
        seed: random source; it affects the default bar textures, the
            baseline, and the hand-drawn wobble, omitting it gives a fresh
            random result each time.

    When a leg is taller than extent_up / extent_down, the bar area expands
    upward/downward automatically; the axes, the title, the labels, and the
    legend take separate space and are not counted in these two values.

    Raises:
        ValueError: width_px is not positive, extent_up / extent_down is
            negative, or axis_style is not an allowed value.

    All add_* methods record the drawing intent and return self so that
    calls can be chained; the geometry is computed uniformly in render().
    """

    def __init__(
        self,
        width_px: int,
        *,
        extent_up: int = DEFAULT_Y_EXTENT,
        extent_down: int = 0,
        background: Color = DEFAULT_BACKGROUND,
        axis_style: Literal["clean", "handdrawn"] = "clean",
        font: FontSpec | None = None,
        seed: int | None = None,
    ) -> None: ...

    @property
    def width_px(self) -> int:
        """Plot-area width (the x range used by the legs and the coordinates).

        Returns:
            The width (design pixels); not equal to the final canvas width.
        """

    def add_bar(
        self,
        x: float,
        height_px: float,
        leg: Leg,
        *,
        style: StockingStyle | str = DEFAULT_STOCKING_STYLE,
        side: Literal["up", "down"] = "up",
        seed: int | None = None,
    ) -> BarPlot:
        """Place a leg at x.

        x is the target position of the foot-sole center: leg widths vary, so
        aligning by the foot keeps the spacing even.

        Args:
            x: the x of the foot-sole center in plot-area coordinates (design
                pixels).
            height_px: stocking height (design pixels); <= 0 means a bare leg.
                The leg itself is always drawn at its full leg.height.
            leg: the leg asset.
            style: a StockingStyle instance or a STYLES preset name.
            side: "up" attaches above the baseline; "down" flips the leg
                vertically with the foot on the baseline pointing down.
            seed: random source for the texture of this bar; when omitted it is
                derived from the seed given at construction, so the whole chart
                stays reproducible.

        Returns:
            self, for chaining.

        Raises:
            ValueError: style is an unknown preset name, side is not "up" /
                "down", or x / height_px is not a finite number.
        """

    def add_columns(
        self,
        slots: Sequence[Sequence[Sequence[LegSpec]]],
        *,
        bar_gap: float,
        slot_gap: float,
        slots_px: Sequence[float],
        lead: float,
    ) -> list[list[list[BarRecord]]]:
        """Place legs slot by slot, centered, and return the bar records shaped like the slots.

        Slot -> column -> leg spec: the columns are laid out from left to
        right (bar_gap between columns), and the legs of one column share
        the foot-sole center x (the upper and the lower legs of a mirror
        chart). Each slot occupies slots_px, and the legs are centered inside
        it; the slot center is recorded in the group-center list, so that a
        later `add_x_labels()` can align with it.

        The slot widths and the leg placement are computed by the caller --
        this method only places the legs and records the group centers, it
        does not infer the layout; use `add_bar()` to place the legs one by
        one when adaptive slot widths are not needed.

        Args:
            slots: the nested slot -> column -> leg spec structure.
            bar_gap: the gap between adjacent columns of the same slot.
            slot_gap: the gap between adjacent slots.
            slots_px: the width of each slot; the same length as slots.
            lead: the x of the left edge of the first slot.

        Returns:
            A `BarRecord` list shaped like slots.
        """

    def add_y_axis(
        self,
        scale: Scale,
        *,
        ticks: Sequence[float] | None = None,
        grid: bool = False,
        font: FontSpec | None = None,
    ) -> BarPlot:
        """Add a y axis (including the tick numbers).

        The line style of the axis and of the grid is decided by the
        constructor argument axis_style. The ticks are mapped through the scale
        to both sides of the baseline: when the domain contains negative values
        the trunk extends downward and the lower ticks are drawn as usual, with
        the arrowhead still at the very top. The axis name is added separately
        with `add_y_axis_name()`.

        Args:
            scale: the data-value-to-pixel conversion; both the tick positions
                and the downward extension come from it.
            ticks: the tick values to draw; None generates them from
                scale.domain automatically.
            grid: whether to draw horizontal dashed lines along each tick
                (layered beneath the legs and the stockings).
            font: font for the tick numbers; None inherits the chart-wide
                default.

        Returns:
            self, for chaining.

        Raises:
            ValueError: ticks contains non-finite numbers.
        """

    def add_x_labels(
        self,
        labels: Sequence[str],
        *,
        xs: Sequence[float] | None = None,
        pos: Literal["content", "auto", "above", "below"] = "content",
        rotation: float | Literal["auto"] = "auto",
        font: FontSpec | None = None,
    ) -> BarPlot:
        """Add x axis labels.

        The positioning and rotation rules:

        - "content" (default) is drawn below the lowest point of all content
          (including the downward legs and the downward extension of the y
          axis), decoupled from the baseline; with nothing below, it
          naturally sits just under the baseline.
        - "auto" hugs the baseline and picks the side without bars; when legs
          exist on both sides it falls back to "content".
        - "above" / "below" force the labels above / below the baseline, and
          they overlap the legs on that side.
        - rotation="auto" tries 45/60/75/90 degrees in turn when adjacent
          labels would overlap each other; passing 0 disables the rotation;
          passing a fixed angle (0-90) always tilts by that angle.

        Args:
            labels: the label texts.
            xs: the positions of the label anchors in plot-area coordinates
                (based on the foot-sole center); None prefers the group centers
                recorded by the `add_bars` family, otherwise the labels are
                spread evenly across the plot-area width.
            pos: the label positioning strategy.
            rotation: "auto" or a fixed angle from 0-90.
            font: label font; None inherits the chart-wide default.

        Returns:
            self, for chaining.

        Raises:
            ValueError: pos is invalid, xs and labels differ in length, xs
                contains non-finite numbers, or rotation is outside the allowed
                range.
        """

    def add_title(
        self,
        text: str,
        *,
        align: Literal["center", "left"] = "center",
        size_px: float = DEFAULT_TITLE_SIZE,
        color: Color = DEFAULT_TEXT_COLOR,
        font: FontSpec | None = None,
    ) -> BarPlot:
        """Add the chart-wide title.

        Args:
            text: the title text.
            align: "center" centers it above the plot area; "left" aligns it
                with the left edge of the plot area.
            size_px: font size (design pixels).
            color: text color.
            font: title font; None inherits the chart-wide default.

        Returns:
            self, for chaining.

        Raises:
            ValueError: align is neither "center" nor "left".
        """

    def add_x_axis_name(
        self,
        text: str,
        *,
        size_px: float = DEFAULT_AXIS_NAME_SIZE,
        color: Color = DEFAULT_TEXT_COLOR,
        font: FontSpec | None = None,
    ) -> BarPlot:
        """Add the x axis name, centered horizontally beneath the x labels (above a bottom legend).

        Args:
            text: the axis name.
            size_px: font size (design pixels).
            color: text color.
            font: axis-name font; None inherits the chart-wide default.

        Returns:
            self, for chaining.
        """

    def add_y_axis_name(
        self,
        text: str,
        *,
        size_px: float = DEFAULT_AXIS_NAME_SIZE,
        color: Color = DEFAULT_TEXT_COLOR,
        font: FontSpec | None = None,
    ) -> BarPlot:
        """Add the y axis name.

        Chinese, Japanese, and Korean characters are laid out vertically one
        character at a time; all other text is rotated 90 degrees and written
        to the left of the tick numbers; when the name is longer than the
        axis trunk it automatically continues into extra columns/lines and
        stays vertically centered on the axis trunk as a whole.

        Args:
            text: the axis name.
            size_px: font size (design pixels).
            color: text color.
            font: axis-name font; None inherits the chart-wide default.

        Returns:
            self, for chaining.
        """

    def add_legend(
        self,
        items: Sequence[tuple[str, StyleLike]],
        *,
        ncol: int | None = None,
        loc: Literal["top", "bottom"] = "top",
        font: FontSpec | None = None,
    ) -> BarPlot:
        """Add a legend.

        Each item is a genuinely rendered fabric-texture swatch + text; the
        swatch takes the fabric from the middle of that style's stocking. The
        height the legend occupies is counted into the layout automatically.

        Args:
            items: a list of (label, style); the style may be a StockingStyle
                or a preset name.
            ncol: how many items per row; None means one row if everything
                fits, otherwise it wraps by width.
            loc: "top" draws below the title and above the plot area; "bottom"
                draws at the very bottom.
            font: legend text font; None inherits the chart-wide default.

        Returns:
            self, for chaining; it returns directly when items is empty.

        Raises:
            ValueError: ncol < 1, loc is invalid, or a style preset name does
                not exist.
        """

    def render(self, *, scale: float = DEFAULT_OUTPUT_SCALE) -> Canvas:
        """Compute the layout and draw the whole chart.

        Args:
            scale: the output pixel density (1 = design size, 2 by default). It
                only affects the output resolution and the texture detail, not
                the design-pixel layout.

        Returns:
            The finished Canvas; its size is round(final_w × scale) ×
            round(final_h × scale).

        Raises:
            ValueError: scale is not a positive finite number.
        """

    def save(self, path: str | Path, *, scale: float = DEFAULT_OUTPUT_SCALE) -> Path:
        """Render and write out a PNG.

        Args:
            path: the output path; the parent directory must already exist.
            scale: the output pixel density.

        Returns:
            The path actually written.
        """

    def to_pil(self, *, scale: float = DEFAULT_OUTPUT_SCALE) -> Image:
        """Render and export a PIL Image.

        Args:
            scale: the output pixel density.

        Returns:
            A PIL Image in RGBA mode.
        """

    def to_numpy(self, *, scale: float = DEFAULT_OUTPUT_SCALE) -> np.ndarray:
        """Render and export a NumPy array.

        Args:
            scale: the output pixel density.

        Returns:
            An (H, W, 4) uint8 RGBA array, with H / W in output pixels.
        """
```

## Drawing records and layout results

`BarPlot` records *what* to draw; the geometry is computed uniformly at render
time. The types below are the shapes of its input and output: `BarRecord` /
`LegSpec` are used to place the legs, the rest are the drawing intents of the
title, the axes, the labels, and the legend; `PlotLayout` and `RenderInput` are
the product and the input of the layout stage.

```python
@dataclass(slots=True)
class BarRecord:
    """The drawing intent of one bar; the geometry is computed uniformly at render time.

    Attributes:
        x: the x of the foot-sole center in plot-area coordinates.
        height_px: stocking height (design pixels); <= 0 means a bare leg.
        leg: the leg asset.
        style: the resolved stocking style.
        side: whether the leg points up or down.
        seed: the random source of this bar's texture.
        value_label: the value label text; None means no label.
    """

    x: float
    height_px: float
    leg: Leg
    style: StockingStyle
    side: BarSide
    seed: int
    value_label: str | None = None


@dataclass(slots=True)
class LegSpec:
    """The complete drawing spec of one leg, computed by the caller and placed by `add_columns`.

    Attributes:
        leg: the leg asset.
        height_px: stocking height (design pixels).
        side: whether the leg points up or down.
        style: the resolved stocking style.
    """

    leg: Leg
    height_px: float
    side: BarSide
    style: StockingStyle


@dataclass(slots=True)
class YAxisRecord:
    """The drawing intent of the y axis; the ticks are data values, converted to pixels through the scale at drawing time.

    Attributes:
        scale: the data-value-to-pixel conversion.
        ticks: the tick values to draw.
        grid: whether to draw horizontal grid lines.
        seed: the random source of the axis and grid wobble.
        font: font for the tick numbers; None uses the platform default chain.
    """

    scale: Scale
    ticks: list[float]
    grid: bool
    seed: int
    font: FontSpec | None = None


@dataclass(slots=True)
class TitleRecord:
    """The drawing intent of the chart-wide title.

    Attributes:
        text: the title text.
        align: centered in the plot area or aligned to its left edge.
        size_px: font size (design pixels).
        color: text color.
        font: title font; None uses the platform default chain.
    """

    text: str
    align: TitleAlign = DEFAULT_TITLE_ALIGN
    size_px: float = DEFAULT_TITLE_SIZE
    color: Color = DEFAULT_TEXT_COLOR
    font: FontSpec | None = None


@dataclass(slots=True)
class AxisNameRecord:
    """The drawing intent of an axis name.

    Attributes:
        text: the axis name.
        size_px: font size (design pixels).
        color: text color.
        rotate: True rotates the whole text by 90 degrees; False lays the
            characters out one by one vertically.
        font: axis-name font; None uses the platform default chain.
    """

    text: str
    size_px: float = DEFAULT_AXIS_NAME_SIZE
    color: Color = DEFAULT_TEXT_COLOR
    rotate: bool = False
    font: FontSpec | None = None


@dataclass(slots=True)
class XLabelsRecord:
    """The drawing intent of the x labels.

    Attributes:
        labels: the label texts.
        xs: the positions of the label anchors in plot-area coordinates; None
            means they are derived from the group centers or spread evenly.
        pos: "content" / "auto" / "above" / "below".
        rotation: "auto" or a fixed angle (degrees).
        font: label font; None uses the platform default chain.
    """

    labels: list[str]
    xs: list[float] | None
    pos: XLabelPos = "content"
    rotation: XLabelRotation = "auto"
    font: FontSpec | None = None


@dataclass(slots=True)
class LegendRecord:
    """The drawing intent of the legend; the styles are normalized to instances.

    Attributes:
        items: a list of (label, style).
        ncol: the number of columns; None means it wraps by width.
        loc: "top" or "bottom".
        seed: the random source of the swatch textures.
        font: legend text font; None uses the platform default chain.
    """

    items: list[tuple[str, StockingStyle]]
    ncol: int | None
    loc: LegendLoc
    seed: int
    font: FontSpec | None = None


@dataclass(slots=True)
class PlotLayout:
    """The overall geometry of one render, all in design pixels.

    Attributes:
        final_w: the final canvas width.
        final_h: the final canvas height.
        plot_left: the canvas x of the plot area (user coordinate x=0).
        plot_right: the right edge of the plot area.
        baseline_y: the canvas y of the baseline.
        content_bottom: the lowest point of all the legs and axis content.
        axis_x: the canvas x of the y axis trunk.
        y_name_x: the canvas x of the center of the y axis name.
        y_name_y: the canvas y of the center of the y axis name.
        y_up_len: the upward length of the y axis trunk.
        y_name_span: the vertical length available to the y axis name (the
            total span of the axis trunk).
        title_x: the canvas x of the title anchor.
        title_y: the canvas y of the title anchor.
        x_name_x: the canvas x of the center of the x axis name.
        x_name_y: the canvas y of the x axis name anchor; None means there is
            no x axis name.
        legend_top_y: the canvas y of the first row of the top legend.
        x_label_y: the canvas y of the x label anchors; None means there are
            no labels.
        x_label_baseline: True anchors the labels by their bottom edge
            (they are written above the baseline).
        x_label_angle: the resolved rotation angle; a positive angle turns
            clockwise, and labels below the baseline take a negative angle.
        x_label_height: the vertical space the label block takes (the
            projected height after the rotation).
        legend_bottom_y: the canvas y of the first row of the bottom legend;
            None means there is no bottom legend.
    """

    final_w: float
    final_h: float
    plot_left: float
    plot_right: float
    baseline_y: float
    content_bottom: float
    axis_x: float = 0.0
    y_name_x: float = 0.0
    y_name_y: float = 0.0
    y_up_len: float = 0.0
    y_name_span: float = 0.0
    title_x: float = 0.0
    title_y: float = 0.0
    x_name_x: float = 0.0
    x_name_y: float | None = None
    legend_top_y: float = 0.0
    x_label_y: float | None = None
    x_label_baseline: bool = False
    x_label_angle: float = 0.0
    x_label_height: float = 0.0
    legend_bottom_y: float | None = None


@dataclass(slots=True, frozen=True)
class RenderInput:
    """Everything one render needs; the layout and the drawing share the same copy.

    Attributes:
        bars: the bar records that have been placed.
        extent_up: the height reserved above the baseline for the bars
            (design pixels).
        extent_down: the height reserved below the baseline for the bars
            (design pixels).
        width_px: the width of the plot area (design pixels).
        group_centers: the x of each group center in plot-area coordinates.
        axis_style: the axis style.
        baseline_seed: the random source of the baseline and the axes.
        font: the chart-wide default font; None uses the platform default
            chain.
        y_axis: the y axis record; None means no axis is drawn.
        y_axis_name: the y axis name record.
        x_axis_name: the x axis name record.
        x_labels: the x label record.
        title: the title record.
        legend: the legend record.
    """

    bars: list[BarRecord]
    extent_up: float
    extent_down: float
    width_px: int
    group_centers: list[float]
    axis_style: AxisStyle
    baseline_seed: int
    font: FontSpec | None
    y_axis: YAxisRecord | None
    y_axis_name: AxisNameRecord | None
    x_axis_name: AxisNameRecord | None
    x_labels: XLabelsRecord | None
    title: TitleRecord | None
    legend: LegendRecord | None
```

## Minimal example

```python
from stockchart import BarPlot, Scale

plot = BarPlot(1200)
plot.add_grouped_bars([[300], [500], [400]], style="black_sheer")
plot.add_x_labels(["A", "B", "C"])
plot.add_y_axis(Scale((0, 500), (0, 500)))
plot.add_title("Free-form layout")
plot.save("freeform.png")
```
