# L0 — leg assets

← [API index](index.md) · Related: [L1 rendering primitives](rendering.md) · [L2 free-form bar plot](barplot.md)

![Built-in leg catalog](../images/leg_catalog.png)

26 legs / 13 pairs; every leg is a transparent SVG. IDs and pairings are frozen once published.

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

## L0 assets

```python
@dataclass(slots=True, frozen=True)
class Leg:
    """A leg asset: positioning metadata + a transparent SVG source (or RGBA pixels).

    Width, height, foot center, and all other metadata use **design pixels**
    (the coordinate system where a leg is 720 tall). Built-in assets carry
    `svg`: `image` is only a design-size layout preview, and rendering
    re-rasterizes at the target scale. External PNG assets have no `svg`;
    their `image` is the original bitmap.

    Attributes:
        image: (H, W, 4) uint8; the foot is at the bottom of the image and the
            asset is upright. Built-in assets are at design size; external
            assets are at the PNG's native size.
        width: width in design pixels.
        height: height in design pixels.
        foot_center_x: x of the foot-sole center in the design coordinate
            system; the anchor for placement alignment.
        pixels_per_unit: `image` pixels / design pixels. 1 for built-in
            assets and external bitmaps.
        leg_id: built-in asset id (e.g. "leg_03"); None for external assets.
        pair_id: the owning pair id (e.g. "pair_02"); None for external assets.
        side: "left" / "right"; None for external assets.
        svg: built-in transparent SVG source; None for external assets.
            Rasterized at the target scale during rendering.

    Methods:
        raster_at(pixels_per_unit): rasterize `svg` directly at the target
            density, caching the result on the Leg. External assets without
            `svg` raise ValueError.
        at_density(pixels_per_unit): return a Leg directly drawable at that
            density; returns self when the density already matches. Used
            internally by `render_stocking(scale=)`.
    """

    image: np.ndarray
    width: int
    height: int
    foot_center_x: int
    pixels_per_unit: float = 1.0
    leg_id: str | None = None
    pair_id: str | None = None
    side: Literal["left", "right"] | None = None
    svg: bytes | None = None
```

```python
class LegLibrary:
    """Library of built-in leg assets (26 legs / 13 pairs; each leg is a transparent SVG)."""

    def __init__(self, *, seed: int | None = None) -> None:
        """seed is the random source for subsequent automatic leg selection; omit for a fresh random run."""

    @property
    def leg_ids(self) -> tuple[str, ...]:
        """All leg IDs in sorted order."""

    @property
    def pair_ids(self) -> tuple[str, ...]:
        """All pair IDs in sorted order."""

    def get(self, leg_id: str) -> Leg:
        """Fetch a leg by id, e.g. get("leg_03")."""

    def pair(self, pair_id: str) -> tuple[Leg, Leg]:
        """Fetch a pair of legs, returning (left leg, right leg)."""

    def alternate(self, n: int, *, paired: bool = False) -> list[Leg]:
        """Select n legs in left, right, left, right ... order.

        With paired=False (default), every leg comes from a different asset
        pair. With paired=True, adjacent legs form a pair (left, right);
        asset pairs are pseudo-random by seed and avoid repeats where
        possible. For odd n the last pair contributes only its left leg;
        beyond 13 pairs, selection continues reusing assets.
        """

    def sample_pairs(self, n: int) -> list[tuple[Leg, Leg]]:
        """Select n complete pairs (for paired layouts); selection rules same as alternate."""

    def preview(self, *, scale: float = 0.5) -> PIL.Image.Image:
        """Build a labeled catalog image of all built-in assets, grouped by pair."""
```

```python
def load_leg(
    png: str | Path,
    *,
    foot_center_x: int | None = None,
) -> Leg:
    """Load a custom leg asset from a PNG; usable like built-in assets (id fields are None).

    Args:
        png: path to a PNG with an alpha channel; the foot must be at the
            bottom of the image (same orientation as built-in assets).
        foot_center_x: x coordinate of the foot-sole center. Defaults to an
            automatic estimate from the alpha centroid of the bottom rows.

    Returns:
        A Leg instance for the custom asset, passable directly to every
        layer's interfaces; `svg` is None and `pixels_per_unit` is 1.
    """
```
