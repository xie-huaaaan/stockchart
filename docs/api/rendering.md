# L1 — rendering primitives

← [API index](index.md) · Related: [L0 leg assets](leg-assets.md) · [L2 free-form bar plot](barplot.md)

## Stocking styles

A stocking = fabric kind (`Plain` / `Striped` / `Ribbed` / `Fishnet` / `Dotted`) + top edge (`Bare` / `Welt` / `Lace` / `Fade`) + shading (`Shading`). All three are `dataclass(slots=True, frozen=True, kw_only=True)`; invalid parameters raise `ValueError` at construction. Length units are design pixels and refer to dimensions at the front of the leg (the sides are compressed by cylindrical `perspective`, default 0.8). Colors are `Color`; when an alpha component is present, it is multiplied into the corresponding opacity.

```python
@dataclass(slots=True, frozen=True, kw_only=True)
class StockingStyle:
    fabric: Fabric
    top: TopEdge = Welt()
    shading: Shading = Shading()


type Fabric = Plain | Striped | Ribbed | Fishnet | Dotted
type TopEdge = Bare | Welt | Lace | Fade
```

**Fabric kinds**

| Class | Meaning | Fields (defaults) |
| --- | --- | --- |
| `Plain` | Solid-color stocking: ultra-sheer to fully opaque | `color`; `opacity`(0.6) coverage over the front of the leg; `rim`(1.0) how much the sides thicken and turn opaque, 0 disables; `stretch`(0.5) how much the stocking stretches thinner and more sheer on thicker legs, 0 disables |
| `Striped` | Horizontal stripes | `stripes: tuple[Stripe, ...]` bands within one cycle, top to bottom, `Stripe(color, width, opacity=1.0)`; `offset`(0) phase. Stripes are laid out downward from the welt |
| `Ribbed` | Vertical ribbed knit | `color`; `opacity`(1.0); `rib_width`(6) rib spacing; `depth`(0.35) light-dark contrast; `perspective`(0.8) perspective compression |
| `Fishnet` | Fishnet stocking | `color`; `cell`(14) mesh cell size; `line_width`(1.6); `angle`(45) 45 for diamonds, 0 for a square grid; `underlay: Plain \| None`(None) a stocking layer underneath; `perspective`(0.8) perspective compression |
| `Dotted` | Printed pattern | `base: Plain` base stocking (required); `color`; `shape`("dot") `"dot"/"heart"/"star"`; `size`(3) motif radius; `spacing`(18); `layout`("grid") `"grid"` staggered grid / `"scatter"` random scatter by seed; `opacity`(1.0); `perspective`(0.8) perspective compression |

The horizontal density of ribs, mesh, and printed patterns uses cylindrical perspective: `perspective=0` is uniform, `1` is full arc-length compression; the default is 0.8.

**Top edges**

| Class | Meaning | Fields (defaults) |
| --- | --- | --- |
| `Bare` | Plain cut edge, just a thin outline | none |
| `Welt` | Elastic welt: a thickened band around the top | `height`(20); `color`(None: darkens one step from the fabric's main color); `opacity`(None: two fabric layers are treated as opaque); `pinch`(0.4) the faint shadow the welt presses into the skin above it, 0 disables |
| `Lace` | Lace trim | `height`(28); `scallop`(28, minimum 20) wave period; `color`(None: taken from the fabric's main color); `opacity`(0.85, openwork fabric lets the skin show through); `holes`(True) hole-dot pattern |
| `Fade` | Pantyhose-style fade with no distinct edge | `length`(60) length of the gradient region |

**Definition of data height**: the distance from the top of the stocking's top edge to the tip of the foot, measured at the leg's centerline; for `Lace` it is the average position of the waves; for `Fade` the fade completes within `length` pixels below the top of the stocking (transparent at the top, no boundary line). Horizontal lines (stripes, welts, lace, mesh lines) all curve downward along the arc of `Shading.curve`, and the arc of the fabric's top edge coincides everywhere with the top-edge lines.

**Top-edge quiet zone**: the fabric patterns (stripes, ribs, mesh, printed patterns) inside the area covered by a `Welt` / `Lace` band are counted from the bottom of the band — for `Welt` along its bottom-edge arc, for `Lace` hugging the wavy edge column by column; the band itself lies directly on the skin (the band is the fabric of that region): `Welt` is a double fabric layer, opaque; `Lace` is openwork, defaulting to 0.85 so skin shows through, and even more so at the hole dots.

**Shading (shared by all kinds)**

| Field | Default | Meaning |
| --- | --- | --- |
| `curve` | 0.12 | How much ring-shaped lines (top edge, stripes, mesh) bow downward (slight top-down view); 0 for straight lines |
| `rim_shadow` | 0.5 | How much the edges on the side away from the light are darkened |
| `shadow_color` | (150, 140, 180, 180) | Multiply-blending color for shadows (a cool light purple, common in anime) |
| `highlight` | 0.35 | Intensity of the vertical highlight, 0 disables |
| `highlight_pos` | -0.35 | Highlight position along the leg's width, -1 left edge to 1 right edge; the light source is shared across the whole chart, so left and right legs are not mirrored |
| `highlight_width` | 0.18 | Highlight half-width (as a fraction of the leg's half-width) |
| `cel_steps` | 0 | 0 for smooth gradients; 2 or 3 for anime-style stepped color bands |
| `ink` | 1.0 | Asset ink enhancement on the body and top edge; brightens dark fabric and darkens light fabric |
| `wobble` | 0.6 | Amplitude (pixels) of hand-drawn wobble for newly added lines (welt, lace trim), controlled by seed |
| `skin` | 0.5 | Shading intensity on the bare skin above the stocking top (relative to the intensity on the stocking): 0 applies shading only to the stocking (the old look), 1 equals the stocking's intensity; bare legs participate as well |
| `skin_shadow_color` | (206,168,158,200) | Shadow color on skin. Stockings use the cool `shadow_color`; a cool purple on skin looks dirty, so a separate warm, skin-toned shadow is used |

```python
STYLES: Mapping[str, StockingStyle]
"""Read-only registry of presets; see the table below."""
```

| Key | Name | Key | Name |
| --- | --- | --- | --- |
| `black_sheer` (default) | black sheer | `stripe_blue_white` | blue-and-white stripes |
| `black_sheer_lace` | black sheer with lace trim | `stripe_pink_white` | pink-and-white stripes |
| `black_pantyhose` | black pantyhose | `stripe_black_white` | black-and-white stripes |
| `gray_sheer` | gray sheer (reference-image colors) | `stripe_rainbow` | rainbow stripes |
| `nude_sheer` | nude sheer | `stripe_sheer_black` | black sheer with a subtle pattern |
| `white_sheer` | white sheer (with lace trim) | `knit_cream` | cream knit |
| `black_tights` | black opaque tights | `knit_gray` | gray knit |
| `white_tights` | white opaque tights | `fishnet_black` | black fishnet |
| `polka_black` | black sheer with polka dots | `fishnet_over_sheer` | fishnet over black sheer |
| `heart_white` | white sheer with hearts | | |

```python
type StyleLike = StockingStyle | str
"""A single style: a StockingStyle instance or a STYLES key."""

type StyleSeq = StyleLike | Sequence[StyleLike]
"""Style parameter: a single style, or a list of styles cycled by position (cycling semantics see L3/L4)."""
```

L2's `add_bar` accepts only a single `StyleLike`; the bulk methods of L3/L4 accept `StyleSeq`, defaulting to `DEFAULT_STOCKING_STYLE = "black_sheer"`.

## render_stocking

```python
def render_stocking(
    leg: Leg,
    style: StockingStyle,
    height_px: float,
    *,
    seed: int | None = None,
    scale: float = 1.0,
) -> LegRender:
    """Dress a leg in a stocking: cover upward from the tip of the foot by height_px pixels.

    Args:
        leg: the leg asset to render.
        style: the stocking style; may be taken from the STYLES presets.
        height_px: the number of pixels (design pixels) from the stocking's top
            edge to the tip of the foot. When <= 0 the leg is bare (if
            `Shading.skin` > 0 the bare leg is still rendered with skin
            shading, otherwise it is returned as-is); when >= leg.height the
            whole leg is covered.
        seed: the random source for texture-like random effects.
        scale: the output scale. When > 1 everything is generated in a scale-x
            pixel space — the stocking fabric texture, the top edge, and the
            shading are true detail at that resolution, not an upscaled
            finished image; built-in vector assets are re-rasterized at that
            scale, and external bitmap assets are resampled proportionally
            first.
            The LegRender image has design dimensions multiplied by scale.

    Returns:
        A separate LegRender holding the source asset, output pixels, and target scale.

    Raises:
        ValueError: `scale` is not a positive finite number.
    """
```

## Text and hand-drawn lines

```python
type FontSpec = str | Path | Sequence[str | Path]
"""Font: a family name, a font file path, or an ordered candidate list (family
names and paths may be mixed); candidate order is priority. None uses the
platform default chain (see [design notes](../design.md), "Fonts")."""

type TextAnchor = tuple[
    Literal["left", "center", "right"],
    Literal["top", "middle", "baseline", "bottom"],
]
"""Where (x, y) anchors the text block: the vertical component refers to the
whole block, and baseline means the first line's baseline."""


def draw_text(
    canvas: Canvas,
    text: str,
    x: float,
    y: float,
    *,
    size_px: float,
    color: Color = DEFAULT_TEXT_COLOR,
    font: FontSpec | None = None,
    anchor: TextAnchor = ("left", "baseline"),
    rotation: float = 0.0,
    max_width: float | None = None,
    max_lines: int | None = None,
    line_height: float | None = None,
) -> None:
    r"""Draw a piece of text (supports \n and wrapping by width, with per-segment shaping that includes kerning and ligatures).

    Args:
        canvas: the target canvas.
        text: the text to draw; the empty string returns immediately.
        x: the anchor x (canvas output pixels).
        y: the anchor y (canvas output pixels).
        size_px: the font size (pixels); it must be positive.
        color: the text color (the placeholder box uses the same color).
        font: the font candidates; None uses the platform default chain.
        anchor: which point of the text block (x, y) refers to; the vertical
            component refers to the whole block, the horizontal one applies
            per line.
        rotation: the clockwise rotation angle around (x, y) (degrees).
        max_width: the maximum width per line (pixels); None does not wrap.
        max_lines: the maximum number of lines; None means no limit.
        line_height: the line-spacing factor; None uses the natural line
            spacing.

    Raises:
        ValueError: color is not a valid RGB/RGBA tuple, size_px is not
            positive, anchor is not an allowed value, or the font candidate
            list is empty.
    """


def measure_text(
    text: str,
    *,
    size_px: float,
    font: FontSpec | None = None,
) -> float:
    """Measure the width of text laid out under the same rules as draw_text (multi-line text takes the widest line).

    Args:
        text: the text to measure; the empty string returns 0.
        size_px: the font size (pixels).
        font: the font candidates; None uses the platform default chain.

    Returns:
        The advance width (pixels, including kerning and ligatures).

    Raises:
        ValueError: the font candidate list is empty or contains an empty
            name.
    """


def measure_text_height(
    text: str,
    *,
    size_px: float,
    font: FontSpec | None = None,
    line_height: float | None = None,
) -> float:
    """Measure the real height of a text block (computed from the metrics of the fonts actually resolved; multi-line blocks include line spacing).

    Args:
        text: the text to measure; the empty string is estimated as a single
            empty line.
        size_px: the font size (pixels).
        font: the font candidates; None uses the platform default chain.
        line_height: the line-spacing factor; None uses the natural line
            spacing.

    Returns:
        The block height (pixels).

    Raises:
        ValueError: the font candidate list is empty or contains an empty
            name.
    """


def wrap_text(
    text: str,
    *,
    max_width: float,
    size_px: float,
    font: FontSpec | None = None,
    max_lines: int | None = None,
) -> list[str]:
    r"""Wrap text into multiple lines by pixel width (\n takes part in the splitting; the last line may get an ellipsis).

    Greedy line breaking is used, preferring breaks after whitespace or common
    punctuation; Chinese text can break per character, and over-long English
    words are still broken. When max_lines is exceeded the last line gets an
    ellipsis; apart from a single glyph that is itself too wide, no line
    exceeds max_width.

    Args:
        text: the text to wrap; the empty string returns [""].
        max_width: the maximum width per line (pixels).
        size_px: the font size (pixels).
        font: the font candidates; None uses the platform default chain.
        max_lines: the maximum number of lines; None means no limit.

    Returns:
        The list of wrapped line strings, with at least one element.

    Raises:
        ValueError: the font candidate list is empty or contains an empty
            name.
    """


def sketch_line(
    canvas: Canvas,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    *,
    color: Color = DEFAULT_INK_COLOR,
    width_px: float = DEFAULT_STROKE_WIDTH,
    wobble: float = DEFAULT_WOBBLE,
    seed: int | None = None,
) -> None:
    """Draw a hand-drawn-style straight line.

    Args:
        canvas: the target canvas.
        x1: the start x (canvas output pixels).
        y1: the start y.
        x2: the end x.
        y2: the end y.
        color: the line color.
        width_px: the line width (pixels).
        wobble: the wobble amplitude along the normal (pixels); 0 gives a
            straight line.
        seed: the random source; the same seed reproduces the same result,
            omitting it gives a fresh random result each time.
    """


def sketch_axis(
    canvas: Canvas,
    *,
    direction: Literal["up", "down", "right"],
    x: float,
    y: float,
    length: float,
    ticks: Sequence[tuple[float, str]] = (),
    arrow: bool = True,
    color: Color = DEFAULT_INK_COLOR,
    width_px: float = DEFAULT_STROKE_WIDTH,
    wobble: float = DEFAULT_WOBBLE,
    seed: int | None = None,
    font: FontSpec | None = None,
) -> None:
    """Draw a hand-drawn-style axis, with an optional arrowhead, tick marks, and tick numbers.

    (x, y) is the axis origin; the spine extends toward direction for length
    pixels; the arrowhead (optional) sits at the far end. The ticks and the
    numbers of a vertical axis are on the left of the spine, those of a
    horizontal axis below it.

    Args:
        canvas: the target canvas.
        direction: "up" / "down" / "right"; it decides the extension direction
            and the tick side.
        x: the axis origin x (canvas output pixels).
        y: the axis origin y.
        length: the length of the spine (pixels); <= 0 draws no arrowhead.
        ticks: a sequence of (pixel offset from the origin, label text).
        arrow: whether to draw the arrowhead at the far end.
        color: the color of the axis, the ticks, and the text.
        width_px: the line width (pixels).
        wobble: the wobble amplitude of the spine; the arrowhead and the
            ticks use half of it.
        seed: the random source; the same seed reproduces the same result,
            omitting it gives a fresh random result each time.
        font: the font for the tick numbers (a family name, a font file path,
            or a candidate list); None uses the platform default chain.
    """
```

## Boundary with the stocking rendering algorithm implementation

- The signature and semantics of `render_stocking()` are a hard contract: render upward from the tip of the foot, `height_px <= 0` returns a bare leg, beyond leg height covers everything, `seed` is reproducible, and it returns a new Leg whose image density is `scale` (design-coordinate metadata unchanged).
- The fields of `StockingStyle` and its component types and the preset names are in "Stocking styles" above; the visual algorithms are in [design notes](../design.md), "Stocking rendering". All other layers merely pass this object through.

## Minimal example

```python
from stockchart import STYLES, LegLibrary, render_stocking

library = LegLibrary(seed=0)
rendered = render_stocking(library.get("leg_03"), STYLES["black_sheer"], 500, seed=0)
print(rendered.source.height, rendered.scale)  # design height and image density
```
