# L0 — leg assets

← [API index](index.md) · Related: [L1 rendering primitives](rendering.md)

## L0 assets

```python
@dataclass(slots=True, frozen=True)
class Leg:
    """A leg asset: positioning metadata + a transparent SVG source (or RGBA pixels).

    Width, height, foot center, foot width, and all other metadata use
    **design pixels** (the coordinate system where a leg is 720 tall).
    Built-in assets carry `svg`: `image` is only a design-size layout preview,
    and rendering re-rasterizes at the target scale. External PNG assets have
    no `svg`; their `image` is the original bitmap.

    Attributes:
        image: (H, W, 4) uint8; the foot is at the bottom of the image and the
            asset is upright. Built-in assets are at design size; external
            assets are at the PNG's native size.
        width: width in design pixels.
        height: height in design pixels.
        foot_center_x: x of the foot-sole center in the design coordinate
            system; the anchor for placement alignment.
        foot_width: foot-sole width (design pixels).
        pixels_per_unit: `image` pixels / design pixels. 1 for built-in
            assets; external bitmaps may be >1.
        leg_id: built-in asset id (e.g. "leg_03"); None for external assets.
        pair_id: the owning pair id (e.g. "pair_02"); None for external assets.
        side: "left" / "right"; None for external assets.
        svg: built-in transparent SVG source; None for external assets.
            Rasterized at the target scale during rendering.

    Methods:
        raster_at(pixels_per_unit): rasterize `svg` at the target density,
            caching the result on the Leg. First call on a built-in asset
            takes about 85 ms (rendered at 4x, then downscaled); afterwards
            the cache is reused. External assets without `svg` raise
            ValueError.
        at_density(pixels_per_unit): return a Leg directly drawable at that
            density; returns self when the density already matches. Used
            internally by `render_stocking(scale=)`.
    """

    image: np.ndarray
    width: int
    height: int
    foot_center_x: int
    foot_width: int
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
        """seed also serves as the default random source for subsequent automatic leg selection."""

    def get(self, leg_id: str) -> Leg:
        """Fetch a leg by id, e.g. get("leg_03")."""

    def pair(self, pair_id: str) -> tuple[Leg, Leg]:
        """Fetch a pair of legs, returning (left leg, right leg)."""

    def alternate(self, n: int) -> list[Leg]:
        """Select n legs in left, right, left, right ... order.

        Which pairs are used is pseudo-random by seed and avoids repeats
        where possible; beyond 13 pairs, selection continues reusing
        already-used assets.
        """

    def sample_pairs(self, n: int) -> list[tuple[Leg, Leg]]:
        """Select n complete pairs (for paired layouts); selection rules same as alternate."""
```

```python
def load_leg(
    png: str | Path,
    *,
    foot_center_x: int | None = None,
    foot_width: int | None = None,
) -> Leg:
    """Load a custom leg asset from a PNG; usable exactly like built-in assets (id fields are None).

    Args:
        png: path to a PNG with an alpha channel; the foot must be at the
            bottom of the image (same orientation as built-in assets).
        foot_center_x: x coordinate of the foot-sole center. Defaults to an
            automatic estimate from the alpha centroid of the bottom rows.
        foot_width: foot-sole width. Defaults to an automatic estimate from
            the alpha coverage width at the bottom.

    Returns:
        A Leg instance for the custom asset, passable directly to every
        layer's interfaces; `svg` is None and `pixels_per_unit` is 1
        (no multi-resolution detection).
    """
```
