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
