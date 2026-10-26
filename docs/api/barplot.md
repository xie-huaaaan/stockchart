# L2 — free-form bar plot

← [API index](index.md) · Related: [L1 rendering primitives](rendering.md) · [L3 layout helpers](layout.md)

## L2 free-form bar plot

```python
@dataclass(slots=True, frozen=True)
class Scale:
    """Linear scale: data values <-> pixels above the baseline. Sharing one Scale between bar heights and axis ticks guarantees consistency."""

    domain: tuple[float, float]
    range_px: tuple[float, float]
    # domain: (lower value, upper value); range_px: (lower pixel, upper pixel),
    # with the baseline at 0 and positive upward.

    def to_px(self, value: float) -> float:
        """Data value -> pixels."""

    def from_px(self, px: float) -> float:
        """Pixels -> data value."""

    @classmethod
    def fit(cls, values: Sequence[float], extent_px: float, *, margin: float = 0.0) -> Scale:
        """Build a scale mapping [min(values), max(values)] -> [0, extent_px], with margin on both ends."""
```

```python
class BarPlot:
    """Free-form bar plot: with the X axis as the baseline, leg positions and stocking heights are entirely specified by the caller in design pixels."""

    def __init__(
        self,
        width_px: int,
        *,
        extent_up: int = DEFAULT_Y_EXTENT,
        extent_down: int = 0,
        background: Color = DEFAULT_BACKGROUND,
        axis_style: Literal["clean", "handdrawn"] = "clean",
        seed: int | None = None,
    ) -> None:
        """Construct the plot area (margins for axes and labels are reserved separately inside).

        extent_up / extent_down are the pixel heights reserved above and
        below the baseline; the plot area expands automatically when legs
        exceed the reserved height. `axis_style="clean"` (default) draws
        straight axes and grid lines; `"handdrawn"` uses hand-drawn wobble
        controlled by seed.
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
        """Place a leg at x: x is the target position of the foot-sole center (leg widths vary, so aligning by foot keeps spacing even).

        Args:
            height_px: stocking height (design pixels). <= 0 means a bare leg.
            leg: the leg asset; with side="down" the asset is flipped
                vertically with the foot on the baseline pointing down.
            style: a StockingStyle instance or a STYLES preset name.
        """

    def add_y_axis(
        self,
        scale: Scale,
        *,
        ticks: Sequence[float] | None = None,
        grid: bool = False,
    ) -> BarPlot:
        """Add a y axis (with tick numbers). By default ticks are generated from scale.domain at whole-number steps.

        The axis and grid styles follow the constructor's axis_style. Ticks
        are mapped through scale to both sides of the baseline: when the
        domain contains negative values the spine extends downward and
        lower ticks are drawn as usual, with the arrowhead still at the
        very top. With grid=True, horizontal dashed lines are drawn at each
        tick (light-colored, layered beneath the legs and stockings).
        Axis names are added separately via add_y_axis_name().
        """

    def add_x_labels(
        self,
        labels: Sequence[str],
        *,
        xs: Sequence[float] | None = None,
        pos: Literal["content", "auto", "above", "below"] = "content",
        rotation: float | Literal["auto"] = "auto",
    ) -> BarPlot:
        """Add x axis labels. pos decides where labels go, rotation decides whether they tilt:

        - "content" (default): below the lowest point of all content
          (including downward legs and the y axis's downward extension),
          decoupled from the baseline — with nothing below, they naturally
          sit just under the baseline;
        - "auto": flush against the baseline, on the side without bars
          (no legs above -> above the baseline, no legs below -> below the
          baseline, legs on both sides -> falls back to "content");
        - "above" / "below": forced above / below the baseline; overlapping
          legs on that side if any.

        rotation="auto" (default) tries 45/60/75/90 degrees in order when
        adjacent labels would overlap and takes the first non-overlapping
        angle; passing 0 disables rotation, and passing a fixed angle
        (0-90) always tilts by that angle. The rotation direction follows
        the label's side of the baseline automatically, and the canvas
        gains the corresponding top/bottom and left/right margins.

        xs defaults to an even spread across the width; when combined with
        the add_bars family it aligns to group centers automatically.
        """

    def add_title(
        self,
        text: str,
        *,
        align: Literal["center", "left"] = "center",
        size_px: float = DEFAULT_TITLE_SIZE,
        color: Color = DEFAULT_TEXT_COLOR,
    ) -> BarPlot:
        """Add a chart title (single line).

        By default horizontally centered above the plot area (centered on
        the range the bars occupy, not the canvas); align="left" aligns to
        the left edge of the plot area. A title wider than the canvas
        widens the canvas symmetrically — no wrapping, no clipping. The
        height the title occupies is counted into layout automatically,
        and the legend is still drawn below the title.
        """

    def add_x_axis_name(
        self,
        text: str,
        *,
        size_px: float = DEFAULT_AXIS_NAME_SIZE,
        color: Color = DEFAULT_TEXT_COLOR,
    ) -> BarPlot:
        """Add the x axis name: centered horizontally beneath the x labels (above a bottom legend).

        With no x labels it goes directly below the lowest point of the
        content. An overly long name widens the canvas — no clipping.
        """

    def add_y_axis_name(
        self,
        text: str,
        *,
        size_px: float = DEFAULT_AXIS_NAME_SIZE,
        color: Color = DEFAULT_TEXT_COLOR,
    ) -> BarPlot:
        """Add the y axis name, drawn to the left of the tick numbers.

        Chinese/Japanese/Korean characters are laid out vertically one
        character at a time (matching their writing conventions); Latin
        letters, digits, and similar text are rotated 90 degrees as a
        whole, read bottom-up. Vertically it is centered on the y axis's
        vertical extent; it occupies the left margin and does not affect
        plot-area coordinates.
        """

    def add_legend(
        self,
        items: Sequence[tuple[str, StyleLike]],
        *,
        ncol: int | None = None,
        loc: Literal["top", "bottom"] = "top",
    ) -> BarPlot:
        """Add a legend: each item is a fabric-texture swatch + text; the swatch takes the fabric from the middle of that style's stocking.

        loc="top" (default) draws below the title and above the plot area;
        "bottom" draws at the very bottom; ncol is the number of items per
        row, auto by default: one row if it fits, otherwise wrapped by
        width. When ncol is given, all columns are equally wide. A single
        label wider than the available row width is wrapped onto multiple
        lines (at most 3; if it still does not fit, the last line is
        elided); under a given ncol it wraps by column width so columns
        stay aligned. The height the legend occupies and the wrapped line
        heights are counted into layout automatically.
        """

    def render(self, *, scale: float = DEFAULT_OUTPUT_SCALE) -> Canvas:
        """Render. scale is the output pixel density and does not affect design-pixel coordinates."""

    def save(self, path: str | Path, *, scale: float = DEFAULT_OUTPUT_SCALE) -> Path:
        """Render and write out a PNG directly."""

    def to_pil(self, *, scale: float = DEFAULT_OUTPUT_SCALE) -> Image:
        """Render and export a PIL Image directly."""
```
