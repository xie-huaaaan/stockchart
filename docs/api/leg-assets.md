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
