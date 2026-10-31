# API reference

stockchart's public API is organized in five layers (L0–L4); higher layers work only through the public interfaces of lower ones. Coordinates are design pixels, randomness is seed-controlled, and a bare leg is simply a stocking of height 0.

**Contents**

- [L0 — leg assets](leg-assets.md)
- [L1 — rendering primitives](rendering.md)
- [L2 — free-form bar plot](barplot.md)
- [L3 — layout helpers](layout.md)
- [L4 — data input](data-input.md)
- [L4 — bar() and mirror_bar()](charts.md)

## Global conventions

- **Coordinate units** are always design pixels (the design coordinate system where a leg is 720 tall); the final output magnification is a separate `scale` parameter.
- **Randomness**: leg selection, stocking textures, and hand-drawn wobble are all controlled by `seed`; the same parameters with the same seed always render identically. Omitting `seed` gives a fresh random result each run.
- **Bare leg** simply means "stocking height 0"; there is no separate switch.
- Higher layers work only through the public interfaces of lower layers:

| Layer | Responsibility | Contents |
| --- | --- | --- |
| L0 assets | Loading and selecting leg assets | `Leg` `LegLibrary` `load_leg` |
| L1 rendering primitives | Drawing individual elements | `render_stocking` `StockingStyle` `STYLES` `draw_text` `sketch_line` `sketch_axis` |
| L2 free-form bar plot | Canvas, baseline, legs placed anywhere, axes | `Scale` `BarPlot` |
| L3 layout helpers | Uniform spacing, automatic leg selection | `BarPlot.add_bars` and other convenience methods |
| L4 one-liners | Data normalization + fully automatic layout | `bar` `mirror_bar` |

`Canvas` and `Color` are cross-layer foundational objects, listed separately below.

## Core objects

```python
type Color = tuple[int, int, int] | tuple[int, int, int, int]
"""0-255, with an optional alpha channel."""


class Canvas:
    """Carrier of the final rendering result: an RGBA canvas.

    Usually produced and drawn into by `BarPlot.render()`; for free-form
    drawing it can also be constructed directly and painted on with the
    L1 primitives (`draw_text` / `sketch_*`).
    """

    def __init__(
        self,
        width_px: int,
        height_px: int,
        *,
        background: Color = DEFAULT_BACKGROUND,
    ) -> None:
        """Construct a blank canvas filled with the background color. Sizes are in design pixels."""

    def save(self, path: str | Path) -> Path:
        """Write out a PNG file."""

    def to_pil(self) -> Image:
        """Export as a PIL Image (RGBA)."""

    def to_numpy(self) -> np.ndarray:
        """Export as an (H, W, 4) uint8 RGBA array."""
```

`BarPlot` also provides `save` / `to_pil` pass-through methods (see L2), so L4 one-liners can produce output directly.
