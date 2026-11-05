# API reference

stockchart's public API is organized in five layers (L0–L4); higher layers work only through the public interfaces of lower ones. Coordinates are design pixels, randomness is seed-controlled, and a bare leg is simply a stocking of height 0.

## Contents

- [L0 — leg assets](leg-assets.md)
- [L1 — rendering primitives](rendering.md)
- [L2 — free-form bar plot](barplot.md): `Scale` / `BarPlot` / the drawing record types
- [L3 — layout helpers](layout.md)
- [L4 — data input](data-input.md)
- [L4 — bar() and mirror_bar()](charts.md)
- [Examples](examples.md): runnable snippets by scenario

## Global conventions

- **Coordinate units** are always design pixels (the design coordinate system where a leg is 720 tall); the final output magnification is a separate `scale` parameter.
- **Randomness**: leg selection, stocking textures, and hand-drawn wobble are all controlled by `seed`; the same parameters with the same seed always render identically. Omitting `seed` gives a fresh random result each run.
- **Bare leg** simply means "stocking height 0"; there is no separate switch.
- Higher layers work only through the public interfaces of lower layers:

| Layer | Responsibility | Contents |
| --- | --- | --- |
| L0 assets | Loading and selecting leg assets | `Leg` `LegLibrary` `load_leg` |
| L1 rendering primitives | Drawing individual elements | `render_stocking` `StockingStyle` `STYLES` `draw_text` `sketch_line` `sketch_axis` |
| L2 free-form bar plot | Canvas, baseline, legs placed anywhere, axes | `Scale` `BarPlot` `BarRecord` `LegSpec` and the other record types |
| L3 layout helpers | Uniform spacing, automatic leg selection | `BarPlot.add_bars` and other convenience methods |
| L4 one-liners | Data normalization + fully automatic layout | `bar` `mirror_bar` |

`Canvas` and `Color` are cross-layer foundational objects, listed separately below.

## Core objects

```python
type Color = tuple[int, int, int] | tuple[int, int, int, int]
"""Integer components from 0 to 255, with optional alpha; floats and booleans are rejected."""


class Canvas:
    """Carrier of the final rendering result: an RGBA canvas.

    Usually produced and drawn into by `BarPlot.render()`; for free-form drawing
    it can also be constructed directly and then painted on with the L1 primitives
    (`draw_text` / `sketch_*`). Sizes and coordinates are counted in output
    pixels and do not involve design pixels; when a design-pixel coordinate
    system is needed, the upper layer sets up the canvas transform first.

    Args:
        width_px: canvas width (output pixels); must be positive.
        height_px: canvas height (output pixels); must be positive.
        background: background color; defaults to an off-white paper tone.

    Raises:
        ValueError: the width or height is not positive.
    """

    def __init__(
        self,
        width_px: int,
        height_px: int,
        *,
        background: Color = DEFAULT_BACKGROUND,
    ) -> None: ...

    @property
    def width_px(self) -> int:
        """Canvas width.

        Returns:
            The width (output pixels).
        """

    @property
    def height_px(self) -> int:
        """Canvas height.

        Returns:
            The height (output pixels).
        """

    def save(self, path: str | Path) -> Path:
        """Write out a PNG file.

        Args:
            path: output path; the parent directory must already exist.

        Returns:
            The path actually written.
        """

    def to_pil(self) -> Image:
        """Export as a PIL Image.

        Returns:
            An RGBA-mode PIL Image.
        """

    def to_numpy(self) -> np.ndarray:
        """Export as a NumPy array.

        Returns:
            An (H, W, 4) uint8 RGBA array.
        """
```

`BarPlot` also provides `save` / `to_pil` / `to_numpy` pass-through methods (see [L2 — free-form bar plot](barplot.md)), so L4 one-liners can produce output directly.

## Type aliases

Literal aliases exported at the top level, reusable in type annotations and argument checks:

```python
type AxisStyle = Literal["clean", "handdrawn"]
"""Axis style: straight lines, or seed-controlled hand-drawn wobble."""

type Pairing = Literal["auto", "none", "group", "global"]
"""Leg-pairing strategy; see [L3 — layout helpers](layout.md) and [L4 — bar() and mirror_bar()](charts.md)."""

type TitleAlign = Literal["center", "left"]
"""Title alignment."""

type XLabelRotation = float | Literal["auto"]
"""x-label rotation: a fixed angle (0-90 degrees) or "auto" avoidance."""
```
