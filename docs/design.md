# Design Notes

Status: all layers L0–L4 are implemented and visually reviewed; this file records the design decisions and the rendering-algorithm approach behind them. Full parameters and presets for stocking styles: see the API reference, [Stocking styles](api/rendering.md).

## Target Look

The original hand-made reference image (skin-toned legs with dark-gray stockings; kept out of the repository, now under the gitignored `dist/`): each bar is a skin-toned leg wearing a dark-gray stocking; the stocking is pulled up from the sole to the height corresponding to the data value, and skin shows above it. The library's scope is broader than this image: it is meant to be a creative toolkit of leg assets, of which bar charts (including grouped ones) are just the first application layered on top.

## Name

- Project and package name: `stockchart` (`import stockchart`). Published on PyPI (currently 0.1.1). `stockplot` and `stockings` are unrelated packages that happen to share the theme.

## Assets

The hand-made source bitmaps (`row1.png`, `row2.png`, `row3.png`, `sample.jpg`) are no longer part of the repository — they live in the gitignored `dist/` next to the super-resolution masters. The library ships transparent SVGs with derived ink preprocessing data (see "Assets and Output" below). Historical dimensions of the row images:

| File | Size | Legs | Pairs |
| --- | --- | --- | --- |
| row1.png | 3607×720 | 6 | 3 |
| row2.png | 3880×720 | 10 | 5 |
| row3.png | 3277×720 | 10 | 5 |

- Each leg runs from the top of the thigh to the ankle, cropped flat at both ends; all legs are 720px tall and 145–183px wide.
- Skin tone is roughly RGB(253, 234, 228), with hand-drawn outlines and a few semi-transparent pixels at the edges; there are no shadows.
- A few small stray specks left over from hand-crafting appear within each row (e.g. at x≈780 in row1); these are removed by an area threshold.
- Within a pair the two legs sit very close together, while the gap between pairs is clearly larger; in left-to-right order, each pair has the left leg on the left and the right leg on the right.
- Splitting method: connected-component labeling on the alpha channel → filter specks by area → sort by x → pair adjacent legs two by two. The output also includes a numbered preview image for the user to verify.

## Mapping Data to Stocking Height (Two Top-Level Branches)

- The mapping happens only at the top layer (`bar` / `mirror_bar`); everything below works in design pixels (see "Assets and Output"). The data value corresponding to the baseline defaults to 0 and is adjustable.
- **Bar-area height** `height_px` is a pixel height above the baseline, not a ratio, and excludes title, labels, legend, or other edge areas. It is a `ChartOptions` passthrough; when omitted it uses the tallest selected leg's design height plus 10% headroom (792 for the 720 built-ins). `width_px` is the analogous plot-area width; both reach `BarPlot` and axis drawing. L2's `BarPlot(extent_up=)` still defaults to `DEFAULT_Y_EXTENT` (792); L4 no longer uses `y_extent`.
- All bars share the **smallest design height among the selected legs** as the reference height, so no leg is clipped; built-in legs have equal heights, so bars remain directly comparable.
- Branch A (`bar`, everything upward):
  - No negative values: `height = v / max × max_fill × reference height` (`max_fill` defaults to 0.85, range (0, 1]); a value of 0 means a bare leg;
  - With negative values: the whole value range is linearly compressed into `[min_fill, max_fill]` (defaults 0.1 / 0.85). A leg at value 0 then carries a band of stocking and the y-axis 0 tick hangs somewhere in the middle of the stocking — a deliberate trade-off to fully preserve size ordering;
  - All-zero data: all bare legs; all-negative data follows the same rule, with larger values meaning higher stockings. When all negative values are equal there is no ordering to preserve, so every leg uses `min_fill`.
- Branch B (`mirror_bar`, mirrored positive/negative): ratio = `max_abs_fill` (default 0.85, range (0, 1]) × reference height / max|v|; positive values draw the upper leg, negative values draw the flipped lower leg (foot against the baseline), and 0 counts as +0. `mode="single"` draws only the data side; `mode="both"` draws both sides with a bare leg on the other. Space below is reserved only when needed (single with negative values, or both). By default x labels are not anchored to the baseline but to a point below **the lowest point of all content** (including downward legs and the y axis extending downward); the `pos` parameter can pin them against the baseline above or below instead ("auto" automatically picks the side without legs). The y-axis trunk line extends downward with the negative ticks, and the arrowhead stays at the very top; if a tick maps above `extent_up`, the top of the canvas expands to keep the trunk and tick number inside.
- Stocking-height mapping and leg layout are two separate layers, so they can be tested independently. Full signatures: [API reference](api/index.md).

## Stocking Rendering (Implemented)

Goal: an anime-style flat-coloring look that fits the assets — "the way anime draws stockings" — not realistic fabric rendering. The assets' characteristics dictate the basic strategy: skin is nearly a flat color (no shadows), gray hand-drawn outlines, a few crease lines at the knee, and legs drawn only down to the ankle. Everything is generated with numpy math; no bitmap assets are used.

Structure: `StockingStyle = Fabric + TopEdge + Shading`, three independently combinable parts; 19 presets, see the API reference.

### Rendering Pipeline (render_stocking)

1. **Column profile** `column_profile`: per row, estimate the leg width from the alpha coverage, yielding a normalized transverse coordinate u ∈ [−1, 1] — every "wrapped around the leg" effect is parameterized by u;
2. **Curve dip** `curve_dip`: `dip = curve × half-width × (1 − u²)` — viewed slightly from above, horizontal wrapping lines (stripes, the welt, lace, mesh rows) form arcs that sag at the center and rise relatively at the sides, with the dip proportional to the local leg width;
3. **Fabric layer** `render_fabric`: generate RGBA per Fabric kind; the pattern phase is counted from the bottom edge of the top-edge band;
4. **Per-column clipping**: the fabric is clipped column by column along the bottom edge of the top-edge band (the Welt band's bottom arc / the Lace scallop edge), so the pattern hugs the band's edge everywhere with no gaps;
5. **Fade**: within `length` pixels measured downward from the top of the stocking, the fabric alpha ramps up linearly;
6. **Fabric compositing**: the stocking color is blended with the skin by the fabric alpha (rim/stretch modulate the opacity);
7. **Top-edge drawing**: the Welt is an opaque band (double-layer fabric) / Lace is a 0.85 semi-transparent band with soft scallop edges + darkened hole dots + a scallop edge line; the band is drawn directly over the skin (the band *is* the fabric of that region);
8. **Shading applied afterwards** `apply_lighting`: the rim shadow (multiply blending) and the vertical highlight (screen blending) are applied uniformly after the top-edge band is drawn, so the welt and the fabric receive light continuously. Bare skin above the welt participates in the same shading at the `Shading.skin` strength (default 0.5; 0 means shading affects only the stocking — the old look) and uses a warm-tinted `skin_shadow_color` — a cold purple shadow looks dirty on skin. Within the fade's transition zone, shading cross-fades from full stocking strength to the skin strength, avoiding a shadow discontinuity at the welt; bare legs (height 0) are also lit when skin>0, so all legs in the same chart receive light consistently;
9. **Ink-line boost** `boost_ink_lines`: detect the hand-drawn lines inside the asset (knee crease lines) and redraw them onto the stocking as "fabric indentation" — on dark fabric they are brightened to cold-gray lines with `shadow_color` via screen blending; on light fabric they are darkened in proportion to the original line depth. Strength = `Shading.ink` × local fabric coverage. Coverage and color include the body, welt and lace; bare skin is excluded, and fishnet without an underlay receives the boost only on its top edge, not in the mesh area;
10. **Native scale** `scale`: when >1, the whole pipeline runs in a pixel space scaled by `scale` — the asset is resampled with premultiplied alpha and bicubic interpolation, every pixel length in the style is multiplied by `scale`, and fabric / top edge / shading are regenerated at that resolution. So zoomed output shows real fabric detail (not a chunky upscaled bitmap); bitmaps are composited 1:1 in device pixels. The asset's own resolution is the only remaining limit (see "Assets and Output" below).

### Design Trade-offs (From Review Iterations)

- **Perspective compression of stripes/ribbing/fishnet/prints**: patterns are generated in the leg's "unwrapped surface coordinates", blending screen coordinate `u` with cylindrical arc length `arcsin(u)` by `perspective` (0 = uniform, 1 = full cylinder, default 0.8), so they naturally densify toward the sides; band boundaries get about 1.2px of sub-pixel softening to avoid stairstepping from per-column phase rounding;
- **Relationship between the top edge and the fabric**: an earlier attempt filled the quiet zone with plain fabric in the dominant color, which blurred into a wide band of the same color as the lace. The correct model is that the band *is* the fabric, drawn directly over the skin, with the pattern phase starting from the band's bottom edge;
- **Lace semi-transparency (0.85)**: what shows through the openwork fabric is skin (the pattern gives way there), and the hole dots are expressed by darkening rather than reducing opacity (decided in user review);
- **Shading must come after the top edge**: if you light before drawing the band, the band's flat color looks like a sticker. The highlight's screen formula was once written incorrectly as an identity operation; fixed;
- **Boundaries of the ink-line boost**: exclude a 3px ring along the alpha edge (outlines must not stack with the rim shadow), use a soft threshold + slight blur to keep the hand-drawn feel, and use multiplicative darkening so it adapts to any stocking color;
- **Top-edge line wobble must be low-frequency**: the welt/lace edge lines once sampled noise independently per column, so adjacent columns jumped by 1–2px and the result read as "glitches" rather than hand-drawn (measured: 36 of 65 columns jumped). Replaced with a random walk over white noise smoothed twice — the amplitude is still `wobble`, with a 20–40px wavelength; the edge lines and band boundaries were also switched to coverage-based blending (1px soft transition), removing stairsteps from per-column rounding on diagonal stretches.

### Performance

Textures are generated directly at the output density; normalized pixels and intermediate layers use float32. SVG rasters, leg profiles, and rim-shadow geometry are shared across library instances with byte-limited caches; shared original pixels are read-only. Fabric compositing touches only the stocking region, and top edges are drawn in a narrow band. Stocking and skin share one lighting geometry calculation and blend directly into the image, without two full shadow layers.

The package ships 2x ink-strength and local-depth maps in `src/stockchart/_precomputed/` (about 1MiB for all 26 legs), generated by `tools/prepare_asset_data.py` under the artwork's ARR license. Each file records the SVG SHA-256, algorithm version, and preprocessing density. Missing or outdated data is extracted from the asset once and cached in memory. Other output densities resize the precomputed maps with bilinear interpolation, which can slightly change fine-line thickness. Runtime blending touches only detected ink pixels covered by fabric; fishnet without an underlay skips the stage. Measurements and remaining work are recorded in [TODO](../TODO.md).

## Fonts

No fonts are bundled. Fonts are specified through a `FontSpec`: a family name, a font file path, or a candidate list of both (they may be mixed), in priority order; `font=None` uses the platform default chain (`defaults.DEFAULT_FONT_FAMILIES`, favoring handwriting/Kai faces: Windows: `楷体`, `华文行楷`, `Ink Free`, `Segoe Print`; macOS: `Kaiti SC`, `Bradley Hand`, `Marker Felt`; Linux: `Noto Serif CJK`, `WenQuanYi`, `Noto Sans CJK`). This path never touches matplotlib's font configuration, so none of its caching/configuration issues apply.

Glyph resolution is per code point: the first font in the candidate stack that has the glyph wins; if none does, the system's per-code-point fallback takes over (skia `FontMgr.matchFamilyStyleCharacter`, win=DirectWrite / mac=CoreText / linux=FontConfig); if that fails too, a stroked placeholder box is drawn instead of raising.

Drawing is implemented by the `src/stockchart/text/` package: each line is split into segments by font, and each segment is shaped through skia.textlayout (HarfBuzz + ICU inside) — kerning, ligatures (fi and other Latin ligatures unrelated to CJK), intra-segment RTL, and composite emoji are all handled correctly; full bidi reordering across segments is not supported yet (a known boundary). Layout and drawing share one TextLayout cache, so repeated measurement never re-shapes.

Multi-line text: hard splits at `\n`, then greedy soft wrapping by pixel width (preferring breaks after whitespace/punctuation, CJK breaking per character), with a U+2026 ellipsis on the last line when `max_lines` is exceeded. Measurements use real font metrics (a mixed-font text block takes the largest ascent/descent); the line-height factors such as `DEFAULT_TITLE_LINE_FACTOR` mean **natural line height × factor**, and layout reserves space from those real metrics.

## Layout and Grouping

- Spacing: `bar_gap` is the gap between the **edges** of adjacent legs (default 28; leg widths vary 145–183, so spacing by edges looks visually even), and `group_gap` is the group spacing (default 120); the two are independent. The group spacing was increased after review to make group boundaries more obvious.
- Leg-picking strategy: `LegLibrary.alternate(n, paired=...)` takes legs along each column in the order "left, right, left, right…"; the asset pair is chosen pseudo-randomly by `seed`, preferring no repeats. With `paired=True`, adjacent legs form a pair (left, right); otherwise every leg comes from a different pair. Single-leg assets are used only when pairing is not requested.
- **Four top-level `paired` strategies**: `"auto"` (default) uses `"none"` for a single series and `"global"` for multiple series; `"group"` takes complete pairs independently within each group — series 0 and 1 share a pair, series 2 starts the next pair, and for an odd series count the extra right leg of the last pair is discarded; `"global"` takes pairs continuously across the whole chart, so a pair may span groups; `"none"` draws every leg from a different pair. For a single series, `"group"` literally takes the left leg of a fresh pair for each group. Multi-series defaults to `"global"` to avoid two same-side legs meeting at a group boundary. L3's `add_bars` / `add_grouped_bars` accept the same parameter.
- **Style cycling**: the batch methods accept a list for `style`, and the `cycle` parameter decides how it cycles. "group" cycles by **position within the group** (bar i in a group uses `styles[i % len]`) — when the list length equals the series count this is the conventional "one style per series" behavior, where each series keeps one style across the whole chart for the best readability; "sequence" cycles by **the draw order of all bars** (group 0 bar 0, group 0 bar 1, group 1 bar 0, …), which for one-dimensional data is "one style per bar". The L4 default "auto": "sequence" for 1-D, "group" for 2-D — in 1-D data each group has only one bar, so group cycling would degenerate into every bar sharing one style, hence not the default. If the list is longer the extra styles go unused; if shorter it repeats periodically (the caller's responsibility). The explicit `legs` / `pairs` parameters must match the data length and do not participate in cycling (cycling is palette semantics and belongs to styles only).
- **x label anchoring**: by default ("content") labels are drawn below the lowest point of all content (including downward legs and the y axis extending downward), decoupled from the baseline; with nothing below, they naturally sit just under the baseline. "auto" hugs the baseline and picks the side without bars — mirror charts often leave one side completely empty (e.g. above all-negative data), and labels beside the baseline are closer and more readable than ones hanging under the lowest leg; when both sides have legs it falls back to "content". You can also force a baseline side with "above" / "below" (overlap is the caller's problem if that side has legs). L4's `mirror_bar` defaults to "auto", `bar` to "content". L4's adaptive width counts each group's label width into the group width, so at default widths labels do not overlap.
- **Automatic tilting of overly long x labels**: `add_x_labels(rotation="auto")` first measures horizontally whether adjacent labels collide; if they do, it tries 45°/60°/75°/90° in order and takes the first angle without overlap. Canvas height below (or above the baseline) is increased by the rotated bounding box, and the sides are padded for any overhang past the plot area, so text is never clipped. Pass `rotation=0` to disable auto-tilting, or a fixed angle to always tilt. This is the standard approach for dense ticks in mainstream plotting libraries (matplotlib / seaborn): keep the full text rather than truncate it or widen the canvas indefinitely. L4 can override the default through `ChartOptions`'s `x_label_rotation`.
- **Title and axis names**: `add_title` by default centers horizontally above the **plot area** (the range the bars occupy); `align="left"` aligns to the plot area's left edge. If the title is wider than the canvas, the canvas is widened symmetrically — no wrapping, no clipping. `add_x_axis_name` centers the x-axis name below the x labels (above a bottom legend); `add_y_axis_name` writes it to the left of the tick numbers, vertically centered over the y axis's full vertical extent — CJK text is set vertically character by character, while Latin letters/digits are rotated 90° as a whole and read bottom-to-top. A name longer than the trunk continues in additional columns/lines instead of overflowing. Font sizes: title 52, axis names 30 (ticks 26 / x labels 30). L4's `title` / `xlabel` / `ylabel` map directly onto these three methods.

## Legend

Series naming goes through the legend uniformly (mainstream-library practice; series are distinguished by texture and left/right leg, and without a legend more than 2 series becomes unreadable). x labels stay one layer per group — no second layer of series names; two-layer labels belong to "hierarchical categories" (sub-labels under group labels), which is a separate feature to add later if needed.

- The marker is a **fabric texture swatch**: a flat 44px square generated directly from the style, with small corner radii and a thin outline. It retains the fabric pattern, colors, and opacity and caches the result; no complete leg is rendered or cropped. Swatches omit skin lighting, ink lines, and top-edge decoration. In paired mode they still use the series' style; left/right information comes from the chart itself.
- Each entry = swatch + series name. Default position: horizontally centered between the title and the plot area; `loc="bottom"` puts it at the very bottom (below the x labels). `ncol` fixes the number of entries per row; by default automatic — one row if it fits, otherwise wrapped by width.
- **Automatic wrapping of overly long legend labels**: when a single label is wider than the available line width, it wraps by character/word into multiple lines (up to 3; if it still does not fit, the last line gets an ellipsis). When `ncol` is given, labels wrap into equal-width columns and each row is centered as a whole; a short last row may therefore not line up with the columns above. The swatch is vertically centered against the multi-line text block, and the row height grows accordingly.
- The legend's height is automatically added to the top/bottom canvas margins; its width no longer stretches the canvas — it wraps to fit the existing width. In L4, passing `series_labels` generates the legend automatically; without it no legend is drawn (preserving the reference image's minimal single-series look).

## Readability Enhancements (Optional Parameters, Off by Default)

- **Value labels** (L4 `value_labels=True`): a handwritten value above the welt; on mirror charts the lower leg's value goes below its welt. Font size slightly smaller than the x labels. Labels align to **the leg outline's center on the welt row**, not the sole center — the leg assets themselves are tilted, so centering on the sole would visibly miss the welt. Stocking height is hard to read precisely, and this is common in infographic use. Value labels **do not take part in layout reservation** (they never change the canvas size); their width is bounded by 6-significant-digit formatting (scientific notation takes over for magnitudes of 10^6 and above, or below 10^-4).
- **y-axis grid lines** (L2 `add_y_axis(grid=True)`, L4 `bar/mirror_bar(grid=True)`): horizontal dashed lines along each tick (light warm gray, drawn beneath the legs and stockings to help align readings); the lines follow `axis_style` — straight or hand-drawn wobble. The 0 tick, which coincides with the baseline, is not drawn, to avoid doubling the x axis.

## Assets and Output (Design Pixels vs Pixel Density)

- **Design pixels are the layout coordinate system**: `Leg.width`, `height`, and `foot_center_x` use the source’s design dimensions (built-in height 720). Chart spacing, font sizes, and stocking heights use design pixels; Canvas and drawing primitives use output pixels. Style lengths remain absolute design pixels and do not scale with source height.
- **Separate sources and raster results**: frozen `Leg` holds source bytes and design geometry without creating a layout preview. `render_stocking(scale=k)` returns a `LegRender` containing only `source`, `image`, and `scale`. SVG is rasterized at the target scale; PNG uses premultiplied-alpha resampling. Fabric and top edges are generated at that density. Leg caches its source digest, libraries own indices, pairings and lazy loading, and bounded process caches share pixels, drawing commands and preprocessing.
- **Bundled assets are stored only as transparent SVG**: `tools/split_master.py` splits the 13 pairs of super-resolution master artwork the user made with Upscayl (`dist/all_up_1.png`): each leg is cut out via alpha connected components, matched one-to-one against the library's numbering by the IoU of normalized alpha masks; each leg is first stretched to **design size × 4**, then traced into a color SVG with vtracer. vtracer requires opaque input and its output is pre-filled with a full-canvas background color, so a `<clipPath>` generated from the leg's visible silhouette (blue channel below the paper background) is applied to cut the background away — the SVG is therefore transparent and can be stored in the library as the sole asset.
- **Moderate color-layer simplification**: tracing uses 6-bit color precision, a 16-pixel speckle threshold, a layer difference of 16 and a curve-length threshold of 4 pixels to reduce tiny color fragments and paths. When the original master is unavailable, `tools/simplify_assets.py` rebuilds color layers from a 4x raster of unsimplified SVGs while preserving their clipping paths; simplified output must not be used repeatedly as the next source. This round reduces the 26 assets from 31,563 to 3,043 paths. Some fine lines and color levels change; IDs, pairings and design dimensions stay unchanged.
- **Rasterizing directly at the target pixel size**: `vector.rasterize_svg` renders the SVG directly at the target pixel size. skia's SVGDOM miscalculates clipPath when the **container** is scaled (observed: shifted left / partially clipped), so the container always stays at the SVG's intrinsic size (design size) and only the canvas is scaled — vector paths (including clipping) are rasterized at the target resolution. Parsed commands are recorded as a Skia Picture and shared across output densities. Bundled commands are rebuilt from SVG if the source digest or Skia version differs, or the file is missing. Commands and raster pixels have separate bounded caches. Skia exports contiguous RGBA directly, avoiding NumPy channel reordering and copying. Scales above 4× still get true vector detail rather than an enlarged 4x bitmap.
- **Legs clipped at the master artwork's edges**: the master artwork's left and right edges may cut off legs (currently pair_04, pair_08); those pairs fall back together to the 720p row images and are re-traced from there, while the rest come from the AI master artwork. The master artwork drifts slightly relative to the design size, so every leg is stretched to design size × 4; master-sourced ink amount is roughly 80%–91% of the old 720p assets, and the 720p fallback source is 93%–97%.
- **Why we no longer trace from 720p**: at the original resolution, 1–2px thin lines and anti-aliased grays get quantized by the tracer into a few flat colors, and adjacent strokes fuse at the minimum-feature threshold (measured: ink amount 20%–55% too high, crease lines blurred into blobs). The master artwork is already upscaled 4×, so tracing it directly suffices; the bitmap high-density pipeline is retired.
- External PNG/SVG sources use `load_leg`; design dimensions come from PNG image size or the SVG viewport. There is no cropping, normalization, or orientation detection. An omitted foot anchor is estimated from bottom alpha. `LegLibrary([...])` may mix external and built-in assets and is injectable into L3/L4. Ordinary layouts use all legs, paired layouts use only complete pairs, and `DEFAULT_LEG_LIBRARY` supplies built-ins.

## Public API Layering

Five layers; full signatures and semantics in the [API reference](api/index.md):

- L0 Assets: `Leg`, `LegRender`, `DEFAULT_LEG_LIBRARY`, `LegLibrary`, `load_leg()`
- L1 Rendering primitives: `render_stocking()`, `StockingStyle` / `STYLES`, `draw_text()`, `measure_text()` / `measure_text_height()` / `wrap_text()`, `sketch_line()`, `sketch_axis()`
- L2 Free-form bar charts: `BarPlot`, `Scale`, `Canvas`
- L3 Layout helpers: `BarPlot.add_bars / add_grouped_bars / add_paired_bars`
- L4 One-line charts: `bar()`, `mirror_bar()` (the four-valued `paired` parameter controls auto, unpaired, group-paired, or globally-paired leg selection)

## Data Input and Parameter Pass-Through

- L4's `data` first goes through `normalize_data` (`functools.singledispatch`) and is normalized to `PlotData`: 1-D/2-D sequences, numpy arrays, `dict` / `Mapping` (scalar values → keys become x labels; equal-length sequence values → keys become series names and the legend is generated automatically), pandas-style table objects (recognized by their `index` / `columns` / `to_numpy()` structure, **without importing pandas**), and already-normalized `PlotData`. Custom types are registered with `register_data_type`; explicitly passed `labels` / `series_labels` override values inferred from the data.
- L4 keeps only chart-semantic parameters; `axis_style`, `background`, `grid`, `ticks`, `x_label_pos`, `x_label_rotation`, `title_align` / `title_size_px`, `axis_name_size_px`, `legend_loc` / `legend_ncol`, `bar_gap` / `group_gap`, and `font` are packed into `ChartOptions`, passed via `**options`, and routed internally to `BarPlot` / `add_*`. Unknown keys raise `TypeError` at runtime (misspelled parameters are never silently ignored). The old `bar(..., grid=True)` / `axis_style="handdrawn"` spellings still work; they just no longer appear in the signature.

## Axis Styles

- **Straight lines by default (clean)**: axes, arrowheads, ticks, and grid are drawn as straight lines without wobble. Earlier versions defaulted to hand-drawn wobble; review judged the look poor, so it became optional.
- **Hand-drawn wobble (handdrawn)**: with `axis_style="handdrawn"`, polylines are subdivided and wobbled with deterministic noise controlled by `seed`; axis lines, arrowheads, and tick marks wobble too, while grid lines use a lighter amplitude. The reference image's hand-drawn feel remains available when wanted.
- The style is set at `BarPlot` construction; L4's `bar` / `mirror_bar` pass it through `ChartOptions`'s `axis_style` key. `sketch_axis` remains a pure rendering primitive: start point + direction + length + pixel tick offsets, unaware of `Scale`; converting tick values to pixels is L2's `add_y_axis` job (including extending downward for negative values).
- Axis names are separate from the axes: `add_y_axis` only handles ticks and grid, names go through `add_y_axis_name`; the x-axis name uses `add_x_axis_name`. This way names can be written standalone even on charts with no axes (free-form layout).

## Non-Goals and Known Limitations

The following behaviors are **intentionally not supported or improved**; avoid them in practice. Ordinary Chinese/English/numeric charts are unaffected.

- **Full cross-segment bidi reordering**: when right-to-left text (e.g. Arabic) mixes with other text and falls into different font segments, segment order is not reordered (RTL *within* a segment is correct). Chart labels are dominated by Chinese, English, and digits; per-segment font control is kept instead of whole-line bidi.
- **Vertical punctuation forms in CJK vertical axis names**: punctuation in a vertical CJK axis name keeps its horizontal form; input vertical-form characters directly if needed.
- **Combining marks and emoji modifiers split across fonts**: when a base character and its modifier resolve to different fonts, they are drawn as two segments and may misalign (normal text is unaffected).
- **Empty-string titles / axis names still reserve layout space**: only when `""` is passed explicitly; omit the parameter instead.
- **Over-large legend `ncol` may overflow the canvas**: no automatic shrinking; use the default (auto) column count or a reasonable ncol.
- **Value labels do not take part in layout reservation**: the canvas size is intentionally unaffected; width is bounded by 6-significant-digit formatting, and in extreme cases labels may still overlap neighbours.
- **`LegLibrary.preview()` still uses PIL's built-in fonts**: the asset catalog image is an internal dev tool and is not unified with the skia text engine.

Packaging note: when building a standalone Windows executable (PyInstaller etc.), ship the `icudtl.dat` bundled in the skia-python wheel, otherwise line breaking/shaping may fail; running from Python directly is unaffected.

## Development Order

1. ✅ `tools/split_legs.py` splits the assets (26 legs / 13 pairs); preview images verified;
2. ✅ `LegLibrary` + `load_leg` + tests;
3. ✅ `render_stocking`: 5 Fabric kinds × 4 TopEdge kinds × Shading, 19 presets, approved in user review (review scripts `tools/render_*_review.py`, output in `out/`, not committed);
4. ✅ L1 text and lines (`Canvas`/`draw_text`/`measure_text`/`measure_text_height`/`wrap_text`/`sketch_line`/`sketch_axis`);
5. ✅ L2–L4 (`Scale`/`BarPlot`/`add_bars` family/`bar`/`mirror_bar`), review images via `tools/render_plot_review.py`; spacing, font sizes, legend sizes, tick density, value-label alignment, etc. adjusted per review feedback and approved;
6. ✅ Native render scale (`render_stocking(scale=)` + `LegRender.scale`) and transparent SVG assets (`tools/split_master.py`: master-artwork splitting → tracing → clipPath → SVG);
7. ✅ Drawing details: straight axes by default (hand-drawn optional), automatic tilting of overly long x labels, automatic wrapping of overly long legend labels, larger default group spacing;
8. ✅ Public API cleanup: `normalize_data` (`singledispatch`) supporting pandas and other data formats, L4 pass-through parameters packed into `ChartOptions`, title centered by default and x / y axis names, docs in sync;
9. ✅ Text engine rewritten on skia.textlayout segment shaping (kerning, ligatures and intra-segment RTL correct), the `font` parameter passed through to the whole chart and to individual elements, and value labels and ticks formatted with a bounded 6-significant-digit scheme.

## Settled Decisions

- The default style is `black_sheer` (black sheer); `gray_sheer` matches the reference image's color scheme; 19 presets, see the API reference;
- `max_fill` / `max_abs_fill` default to 0.85 relative to the asset design height; `height_px` defaults to the tallest selected leg's design height plus 10% headroom, and `width_px` adapts to content;
- Series naming uses the legend (fabric texture swatch markers); how a `style` list cycles is controlled by `cycle` — `group` (position within the group, the default for 2-D) / `sequence` (overall draw order, the default for 1-D); value labels and y-axis grid lines are optional and off by default;
- **Shading covers the whole leg** (`Shading.skin=0.5`): skin uses the warm-tinted `skin_shadow_color`; `0` returns to the old look where shading affects only the stocking; bare legs are lit too;
- **x label position** is controlled by `pos`: `content` (below the lowest point of all content, the default), `auto` (against the baseline, automatically picking the side without legs — `mirror_bar`'s default), `above`/`below`; overly long labels auto-tilt out of the way by default, with `rotation` fixing an angle or disabling tilting;
- **Straight axes by default** (`axis_style="clean"`); hand-drawn wobble requires explicit `axis_style="handdrawn"`;
- **Title centered by default** (52px), x-axis name horizontally centered; y-axis name 30px, CJK text vertical, all other text rotated 90°; L4's `title` / `xlabel` / `ylabel` work directly;
- **Normalized data input**: `normalize_data` + `register_data_type`; pandas is recognized by structure only and is not a runtime dependency;
- **L4 parameter layering**: chart-semantic parameters stay in the signature; pass-through parameters are packed into `ChartOptions` and received via `**options`;
- **Leg pairing**: `paired="auto"` (default; none for a single series, global for multiple series) / `"none"` / `"group"` / `"global"`; for a single series, group takes a fresh pair's left leg per group; L0's `alternate(paired=True)` provides the flat "adjacent legs form a pair" primitive;
- **No default seed**: omitting `seed` is random; the same `seed` reproduces the same result;
- **Group spacing defaults to 120** (previously 96), making group boundaries clearer;
- Output is PNG only; no SVG/PDF. SVG exists only as the storage format for the bundled leg assets; the public output is still PNG only — reasoning in "Assets and Output";
- `LegLibrary.alternate()`'s docstring now matches the implementation: even indices are left legs, odd indices are right legs (0-based).
- **Modules split by responsibility**: `plot/`, `stocking/`, and `topline/` are packages of their own, and cross-layer calls go through the public interfaces only (L4 places its legs via `BarPlot.add_columns()`, and every record type of `plot.types` is exported); `vector.py` independently prepares, caches and rasterizes SVG commands for `legs`, `library` and tooling scripts; `text/engine.py` segments by font while `text/layout.py` breaks lines by width — two dimensions, not a duplication.
