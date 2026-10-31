# L1 — rendering primitives

← [API index](index.md) · Related: [L0 leg assets](leg-assets.md) · [L2 free-form bar plot](barplot.md)

## Stocking styles

A stocking = fabric kind (`Fabric`) + top edge (`TopEdge`) + shading (`Shading`). All three are
`dataclass(slots=True, frozen=True, kw_only=True)`; invalid parameters raise `ValueError` at construction.
Length units are design pixels and refer to dimensions at the front of the leg (the sides are compressed
automatically by cylindrical perspective). Colors are `Color`; when an alpha component is present,
it is multiplied into the corresponding opacity.

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
| `Ribbed` | Vertical ribbed knit | `color`; `opacity`(1.0); `rib_width`(6) rib spacing; `depth`(0.35) light-dark contrast |
| `Fishnet` | Fishnet stocking | `color`; `cell`(14) mesh cell size; `line_width`(1.6); `angle`(45) 45 for diamonds, 0 for a square grid; `underlay: Plain \| None`(None) a stocking layer underneath |
| `Dotted` | Printed pattern | `base: Plain` base stocking (required); `color`; `shape`("dot") `"dot"/"heart"/"star"`; `size`(3) motif radius; `spacing`(18); `layout`("grid") `"grid"` staggered grid / `"scatter"` random scatter by seed; `opacity`(1.0) |

The horizontal density of ribs, mesh, and printed patterns is handled as "a fixed number of stitches around the leg": sparser on thick thighs, denser at the ankle.

**Top edges**

| Class | Meaning | Fields (defaults) |
| --- | --- | --- |
| `Bare` | Plain cut edge, just a thin outline | none |
| `Welt` | Elastic welt: a thickened band around the top | `height`(20); `color`(None: darkens one step from the fabric's main color); `opacity`(None: two fabric layers are treated as opaque); `pinch`(0.4) the faint shadow the welt presses into the skin above it, 0 disables |
| `Lace` | Lace trim | `height`(28); `scallop`(28) wave period; `color`(None: taken from the fabric's main color); `opacity`(0.85, openwork fabric lets the skin show through); `holes`(True) hole-dot pattern |
| `Fade` | Pantyhose-style fade with no distinct edge | `length`(60) length of the gradient region |

**Definition of data height**: the distance from the top of the stocking's top edge to the tip of the foot, measured at the leg's centerline; for `Lace` it is the average position of the waves; for `Fade` the fade completes within `length` pixels below the top of the stocking (transparent at the top, no boundary line).
Horizontal lines (stripes, welts, lace, mesh lines) all curve downward along the arc of `Shading.curve`, and the arc of the fabric's top edge coincides everywhere with the top-edge lines.

**Top-edge quiet zone**: the fabric patterns (stripes, ribs, mesh, printed patterns) inside the area covered by a `Welt` / `Lace` band are counted from the bottom of the band — for `Welt` along its bottom-edge arc, for `Lace` hugging the wavy edge column by column; the band itself lies directly on the skin (the band is the fabric of that region): `Welt` is a double fabric layer, opaque; `Lace` is openwork, defaulting to 0.85 so skin shows through, and even more so at the hole dots.

**Shading (shared by all kinds)**

| Field | Default | Meaning |
| --- | --- | --- |
| `curve` | 0.12 | How much ring-shaped lines (top edge, stripes, mesh) bow downward (slight top-down view); 0 for straight lines |
| `rim_shadow` | 0.5 | How much the edges on the side away from the light are darkened |
| `shadow_color` | (150, 140, 180) | Multiply-blending color for shadows (a cool light purple, common in anime) |
| `highlight` | 0.35 | Intensity of the vertical highlight, 0 disables |
| `highlight_pos` | -0.35 | Highlight position along the leg's width, -1 left edge to 1 right edge; the light source is shared across the whole chart, so left and right legs are not mirrored |
| `highlight_width` | 0.18 | Highlight half-width (as a fraction of the leg's half-width) |
| `cel_steps` | 0 | 0 for smooth gradients; 2 or 3 for anime-style stepped color bands |
| `ink` | 1.0 | Strength with which the asset's outlines show through (automatically deepened on dark stockings) |
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

L2's `add_bar` accepts only a single `StyleLike`; the bulk methods of L3/L4 accept `StyleSeq`,
defaulting to `DEFAULT_STOCKING_STYLE = "black_sheer"`.

## render_stocking

```python
def render_stocking(
    leg: Leg,
    style: StockingStyle,
    height_px: int,
    *,
    seed: int | None = None,
    scale: float = 1.0,
) -> Leg:
    """Dress a leg in a stocking: cover upward from the tip of the foot by height_px pixels.

    Args:
        leg: the leg asset to render.
        style: the stocking style; may be taken from the STYLES presets.
        height_px: number of pixels (design pixels) from the stocking's top
            edge to the tip of the foot. When <= 0 the leg is bare (if
            `Shading.skin` > 0 the bare leg is still rendered with skin
            shading, otherwise returned as-is); when >= leg.height the
            whole leg is covered.
        seed: random source for texture-like random effects.
        scale: output scale. When >1, everything is generated in a scale-x
            pixel space — the stocking fabric texture, top edge, and shading
            are true detail at that resolution, not an upscaled finished
            image; built-in SVG assets are re-rasterized at that scale, and
            external bitmap assets are resampled proportionally.
            Textures are internally generated at 2x and then downsampled to
            improve anti-aliasing on hard edges such as fishnet and lace; the
            returned image size and `pixels_per_unit` are unchanged.
            The returned Leg's image is "design pixels x scale"
            (`pixels_per_unit == scale`) while metadata such as width, height,
            and foot center remains in design pixels; compositing layers
            1:1 yields scale-x output.

    Returns:
        A new Leg: pixels replaced, design-coordinate metadata matching the
        asset; when `scale != 1` the image is densified by the scale
        (`pixels_per_unit == scale`) for 1:1 compositing.

    Contract: this function is the outward contract of the stocking
    rendering algorithm (the algorithm itself is implemented separately).
    It always renders upward from the tip of the foot in the asset's own
    coordinate system; vertical flipping of legs is handled by upper layers
    at placement time (flipping and rendering commute, so it is not done
    in this layer). `scale` merely enlarges the rendering space
    proportionally and does not change geometric semantics; built-in SVG
    assets are rasterized at the target scale; external bitmap assets
    denser than the target are downsampled on demand (high-density assets
    are never upscaled again).
    """
```

## Text and hand-drawn lines

```python
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
) -> None:
    """Draw a piece of text. Per-character font fallback keeps Chinese renderable;
    missing glyphs are drawn as a "tofu box" instead of raising.

    font is a list of family names or a font file path; by default the
    built-in fallback chain is used (see [design notes](../design.md), "Fonts"). Details
    of anchor and other parameters may be tweaked with the implementation;
    semantics are unchanged. rotation is the clockwise rotation angle
    (degrees) around (x, y); 0 means no rotation. The text is first
    positioned by anchor, then rotated as a whole.
    """


def measure_text(
    text: str,
    *,
    size_px: float,
    font: FontSpec | None = None,
) -> float:
    """Measure the width (pixels) of text drawn with the same fallback rules as `draw_text`. 0 for the empty string."""


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
    """Hand-drawn-style straight line: deterministic subdivision wobble applied to the segment."""


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
) -> None:
    """Hand-drawn-style axis: wobbles the axis spine, arrowhead, tick marks, and tick numbers.

    (x, y) is the axis origin; the spine extends toward direction for
    length pixels, with the arrowhead (optional) at the far end; ticks is a
    sequence of (pixel offset from the origin, label text): tick marks are
    perpendicular to the spine, and numbers are drawn to the left of the
    spine (vertical axis) or below it (horizontal axis).
    """
```

## Boundary with the stocking rendering algorithm implementation

- The signature and semantics of `render_stocking()` are a hard contract: render upward from the tip of the foot, `height_px <= 0` returns a bare leg, beyond leg height covers everything, `seed` is reproducible, and it returns a new Leg whose image density is `scale` (design-coordinate metadata unchanged).
- The fields of `StockingStyle` and its component types and the preset names are in "Stocking styles" above; the visual algorithms are in [design notes](../design.md), "Stocking rendering". All other layers merely pass this object through.
