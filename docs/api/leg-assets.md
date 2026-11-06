# L0 — leg assets

← [API index](index.md) · Related: [L1 rendering primitives](rendering.md) · [L2 free-form bar plot](barplot.md)

![Built-in leg catalog](../images/leg_catalog.png)

26 legs / 13 pairs; every leg is a transparent SVG. IDs and pairings are frozen once published.

Bundled assets also include precomputed vector drawing commands and ink maps to reduce first-use work. Vector commands are checked against the source digest and Skia version; mismatches are rebuilt from SVG and shared within the process under a memory budget. Drawing still rasterizes at the target pixel density rather than scaling a pre-rendered bitmap.

| pair | left leg | right leg | design widths |
| --- | --- | --- | --- |
| pair_01 | leg_01 | leg_02 | 169 / 159 |
| pair_02 | leg_03 | leg_04 | 149 / 149 |
| pair_03 | leg_05 | leg_06 | 152 / 148 |
| pair_04 | leg_07 | leg_08 | 179 / 173 |
| pair_05 | leg_09 | leg_10 | 165 / 173 |
| pair_06 | leg_11 | leg_12 | 166 / 183 |
| pair_07 | leg_13 | leg_14 | 178 / 167 |
| pair_08 | leg_15 | leg_16 | 176 / 159 |
| pair_09 | leg_17 | leg_18 | 159 / 166 |
| pair_10 | leg_19 | leg_20 | 170 / 169 |
| pair_11 | leg_21 | leg_22 | 169 / 158 |
| pair_12 | leg_23 | leg_24 | 181 / 145 |
| pair_13 | leg_25 | leg_26 | 145 / 150 |

Built-in and external assets share the same Leg, rasterization, and cache pipeline. DEFAULT_LEG_LIBRARY is the built-in default; LegLibrary([...]) may mix external and selected built-in legs. Sources must be prepared in the intended orientation; no flipping, cropping, or size normalization occurs. PNG design dimensions equal its image dimensions. SVG uses absolute pixel dimensions or falls back to viewBox, deriving a missing dimension from its aspect ratio. Percentage dimensions without a usable absolute size or valid viewBox are rejected. An omitted anchor is estimated from the bottom 20 design pixels of alpha; a transparent bottom uses the horizontal center.

Welt, stripe, and mesh lengths use fixed design pixels rather than scaling with source height. External assets retain their provider’s license; bundled assets and derived data retain their ARR license.

Legs without pairing metadata remain available through `legs` and ordinary selection. `paired="none"` selects from all legs; `"group"` / `"global"` use complete left-right pairs and raise `ValueError` when none exist. For multiple series, `"auto"` means `"global"`; use `paired="none"` explicitly when the library contains only unpaired assets.

```python
@dataclass(slots=True, frozen=True)
class Leg:
    """A leg asset: immutable source bytes and geometry in design pixels.

    All geometry uses design pixels. The provider prepares the source orientation;
    the foot must be at the bottom. No orientation detection or normalization is performed.

    Args:
        source: Original PNG or SVG bytes.
        source_type: Source format.
        width: Width in design pixels.
        height: Height in design pixels.
        foot_center_x: Foot anchor x in design pixels.
        leg_id: Optional identifier within a library.
        pair_id: Optional pair identifier; participates in pairing only with side.
        side: Optional left or right side.

    Raises:
        ValueError: Empty source, invalid format, nonpositive size, or invalid foot anchor.

    Attributes:
        source: Original PNG or SVG bytes.
        source_type: Source format.
        width: Width in design pixels.
        height: Height in design pixels.
        foot_center_x: Foot anchor x in design pixels.
        leg_id: Optional leg identifier.
        pair_id: Optional pair identifier.
        side: Optional left or right side.
    """

    source: bytes
    source_type: Literal["png", "svg"]
    width: float
    height: float
    foot_center_x: float
    leg_id: str | None = None
    pair_id: str | None = None
    side: Literal["left", "right"] | None = None

    def raster_at(self, scale: float = 1.0) -> NDArray[np.uint8]:
        """Rasterize the asset at the target scale, reusing shared process caches.

        Args:
            scale: Output pixels per design pixel.

        Returns:
            A read-only (round(height × scale), round(width × scale), 4) uint8 RGBA array.

        Raises:
            ValueError: scale is not positive and finite, or the source cannot be decoded.
        """
        ...
```

```python
@dataclass(slots=True, frozen=True)
class LegRender:
    """Raster output of a leg at a particular scale.

    Attributes:
        source: The immutable source asset.
        image: RGBA uint8 pixels at the target scale.
        scale: Output pixels per design pixel.
    """

    source: Leg
    image: NDArray[np.uint8]
    scale: float
```

```python
class LegLibrary:
    """An immutable collection of built-in or external assets, rasterized on demand.

    Args:
        legs: Asset sequence; None uses built-in assets. May include legs from the default library.
        seed: Default selection seed; method-level seeds take precedence. No RNG state is retained.

    Raises:
        ValueError: Empty custom library, duplicate identifiers or sides within a pair,
            or invalid built-in metadata.
    """

    def __init__(self, legs: Sequence[Leg] | None = None, *, seed: int | None = None) -> None: ...

    @property
    def legs(self) -> tuple[Leg, ...]:
        """Return all legs in library order, including unnamed and unpaired assets.

        Returns:
            An immutable Leg tuple. Built-in sources are read on first access, without creating previews.
        """
        ...

    @property
    def leg_ids(self) -> tuple[str, ...]:
        """Return sorted nonempty leg identifiers without loading asset sources."""
        ...

    @property
    def pair_ids(self) -> tuple[str, ...]:
        """Return sorted complete-pair identifiers without loading asset sources."""
        ...

    def get(self, leg_id: str) -> Leg:
        """Fetch a leg by identifier.

        Args:
            leg_id: An existing identifier in the library.

        Returns:
            Repeated access within one library returns the same Leg instance.

        Raises:
            KeyError: The identifier does not exist.
        """
        ...

    def pair(self, pair_id: str) -> tuple[Leg, Leg]:
        """Fetch (left leg, right leg) by pair identifier.

        Args:
            pair_id: A complete-pair identifier.

        Returns:
            The corresponding left and right legs.

        Raises:
            KeyError: The pair does not exist or is incomplete.
        """
        ...

    def alternate(self, n: int, *, paired: bool = False, seed: int | None = None) -> list[Leg]:
        """Select n legs, expanding complete pairs in left-right order when paired.

        Args:
            n: Number of legs.
            paired: False shuffles all legs; True uses only complete pairs, taking the left leg for an odd final item.
            seed: Seed for this selection, independent of earlier calls; None uses the library default or fresh randomness.

        Returns:
            A list that avoids repeats while possible and cycles when more legs are requested.

        Raises:
            ValueError: n is negative, or paired selection has no complete pair.
        """
        ...

    def sample_pairs(self, n: int, *, seed: int | None = None) -> list[tuple[Leg, Leg]]:
        """Select n complete pairs using the seed for this call.

        Args:
            n: Number of pairs.
            seed: Seed for this selection; None uses the library default or fresh randomness.

        Returns:
            A list of (left, right) tuples, avoiding repeats while possible and cycling when necessary.

        Raises:
            ValueError: n is negative, or n is positive but no complete pairs exist.
        """
        ...

    def preview(self, *, scale: float = 0.5) -> Image.Image:
        """Build a catalog with complete pairs together and unpaired legs shown separately.

        Args:
            scale: Preview scale relative to design size; must be positive and finite.

        Returns:
            An RGB PIL image labeled with identifiers, pairings, and sides.

        Raises:
            ValueError: scale is not positive and finite.
        """
        ...
```

```python
def load_leg(
    path: str | Path,
    *,
    foot_center_x: float | None = None,
    leg_id: str | None = None,
    pair_id: str | None = None,
    side: Literal["left", "right"] | None = None,
) -> Leg:
    """Load an external PNG or SVG asset.

    Args:
        path: Path to a PNG or SVG file.
        foot_center_x: Foot anchor in design pixels; estimated from the bottom alpha centroid when omitted.
        leg_id: Optional identifier within a library.
        pair_id: Optional pair identifier.
        side: Optional left or right side; participates in pairing only with pair_id.

    Returns:
        An immutable Leg source using the common asset model.

    Raises:
        OSError: The file cannot be read.
        ValueError: Invalid source format, dimensions, or anchor.
    """
    ...
```

## Minimal example

```python
from stockchart import DEFAULT_LEG_LIBRARY, LegLibrary, STYLES, load_leg, render_stocking

leg = DEFAULT_LEG_LIBRARY.get("leg_03")
custom = load_leg("custom.svg", leg_id="custom")
library = LegLibrary([leg, custom])
rendered = render_stocking(custom, STYLES["black_sheer"], 200, scale=2, seed=0)
print(rendered.source.height, rendered.image.shape, rendered.scale)
```

## Practical advice for external assets

### Preparing assets

- **Match heights and margins**: use the same design height, crop range, and top/bottom margins for assets in a chart. L4 maps all data using the shortest selected asset. Mixing heights does not resize the legs automatically and can produce inconsistent body proportions, stocking coverage, and visual comparisons.
- **Prefer a 720px design height**: built-in style lengths and layout gaps currently use a height of 720 as their reference and do not normalize to external asset heights. Resize PNGs proportionally to height 720 before importing. For SVG, set the viewport `width` / `height` proportionally to height 720 while retaining the original `viewBox` and paths.
- **Keep backgrounds transparent**: use transparent PNGs or SVGs with transparent backgrounds, removing backgrounds and stray graphics outside the leg. The renderer uses alpha to identify the silhouette; white or other opaque backgrounds are treated as part of the leg.
- **Prepare orientation and bounds yourself**: place the foot at the bottom, close to the image edge. Importing does not flip, crop, or normalize assets. Coverage is measured from the bottom of the image, so excess transparent bottom padding affects alignment and coverage. Anchor estimation examines at most the bottom 20 design pixels. Pass `foot_center_x` explicitly for precise alignment, using the imported asset's design coordinates.
- **Distinguish design size from output scale**: PNG DPI metadata and names such as “@2x” do not determine density; a 1440px-high image becomes a 1440-high asset. `scale=2` doubles output pixels while preserving design sizes for layout and patterns. Setting that PNG's `scale` to 0.5 only shrinks the output; it does not change its design height to 720. A 720-high SVG rendered at `scale=2` preserves vector detail; a 720-high PNG at 2x still resamples its source outline.
- **Add pairing only when needed**: import assets directly and use `paired="none"` for multiple series without pairs. For paired layouts, give left and right assets the same `pair_id` and their respective `side`; each nonempty `leg_id` must be unique.

For example, prepare a PNG at height 720 before importing it into a library. This reduces the source resolution of larger bitmaps and leaves the original file intact:

```python
from PIL import Image
from stockchart import LegLibrary, bar, load_leg

with Image.open("source.png") as source:
    rgba = source.convert("RGBA")
    width = max(1, round(rgba.width * 720 / rgba.height))
    rgba.resize((width, 720), Image.Resampling.LANCZOS).save("leg_720.png")

leg = load_leg("leg_720.png")
library = LegLibrary([leg])
bar([3, 5, 4], library=library, paired="none", seed=2).save("custom.png", scale=2)
```

To retain a high-resolution PNG's source pixels while using a design height of 720, set the `Leg` geometry explicitly. The example below creates a new asset with `dataclasses.replace()` and leaves the PNG bytes unchanged. You must convert the width and anchor yourself; `load_leg()` does not infer this mapping:

```python
from dataclasses import replace
from stockchart import load_leg

high_res = load_leg("leg_1440.png")
factor = 720 / high_res.height
leg = replace(
    high_res,
    width=high_res.width * factor,
    height=720,
    foot_center_x=high_res.foot_center_x * factor,
)
```

Now `leg.height` is 720 while the PNG source remains 1440px high. Rendering at `scale=2` can use that resolution directly, and built-in style lengths retain their original design proportions.

Compared with importing the PNG directly and rendering at `scale=1`, the bare source pixels are identical, but stocking results differ by default: rendering the 720-high asset at 2x doubles coverage height and style lengths, whereas the 1440-high asset at 1x uses the supplied design lengths directly. Even after manually converting every length, details such as ink extraction may differ. Font sizes and gaps in complete charts also use design pixels, so equal final leg-image dimensions do not imply identical charts.

When explicitly changing `Leg.width` / `height`, scale both proportionally and convert the anchor as well. If the design aspect ratio differs from the PNG source, the image is resized independently along each axis and becomes stretched; there is no automatic aspect-ratio preservation, padding, or cropping. Texture and lighting are then computed from the distorted silhouette.

### Keeping another design height

To retain assets at height `H`, use `H / 720` as a starting point for length adjustments, then refine visually. These parameters use absolute design pixels; their defaults do not change with leg height:

| Part | Lengths to consider scaling |
| --- | --- |
| Top edge | `Welt.height`, `Lace.height` / `scallop`, `Fade.length` |
| Fabric | `Stripe.width`, `Striped.offset`, `Ribbed.rib_width` |
| Mesh and prints | `Fishnet.cell` / `line_width`, `Dotted.size` / `spacing`, and lengths in nested underlays |
| Hand-drawn wobble | `Shading.wobble` |
| Layout | `bar_gap`, `group_gap`, font sizes, and manually specified plot dimensions; L3's `extent_up` still defaults to 792, while L4 derives its default plot height from the tallest leg |

Colors, opacity, angles, perspective strength, and other ratios or dimensionless parameters do not need proportional scaling. For example, configure a 1440-high asset with pattern proportions similar to the built-in fishnet preset:

```python
from stockchart import Fishnet, StockingStyle, Welt, load_leg, render_stocking

leg = load_leg("leg_1440.png")
factor = leg.height / 720
style = StockingStyle(
    fabric=Fishnet(color=(20, 18, 22), cell=14 * factor, line_width=1.6 * factor),
    top=Welt(height=20 * factor, color=(20, 18, 22)),
)
rendered = render_stocking(leg, style, height_px=leg.height * 0.85, scale=1, seed=2)
```

A few details, including edge softening, pinch offsets, and lace dots, use fixed output pixels to control fine lines and antialiasing and currently have no public adjustment parameters. Even proportional changes to all public lengths therefore do not guarantee identical details across combinations of design height and output scale.
