# L3 — layout helpers

← [API index](index.md) · Related: [L2 free-form bar plot](barplot.md)

## L3 layout helpers

The following are all `BarPlot` convenience methods: they only solve "spacing + leg selection"; stocking heights are still given in pixels by the caller.

```python
def add_bars(
    self,
    heights_px: Sequence[float],
    *,
    bar_gap: float = DEFAULT_BAR_GAP,
    style: StyleSeq = DEFAULT_STOCKING_STYLE,
    legs: Sequence[Leg] | None = None,
    seed: int | None = None,
) -> BarPlot:
    """Single series: laid out left to right with uniform spacing, automatically alternating leg selection in left, right, left, right ... order.

    legs may explicitly specify the asset for each bar (its length must
    match heights_px and it does not participate in cycling). When style is
    a list, it is cycled in bar order.
    """


def add_grouped_bars(
    self,
    heights_px: Sequence[Sequence[float]],
    *,
    bar_gap: float = DEFAULT_BAR_GAP,
    group_gap: float = DEFAULT_GROUP_GAP,
    style: StyleSeq = DEFAULT_STOCKING_STYLE,
    cycle: Literal["group", "sequence"] = "group",
    legs: Sequence[Leg] | None = None,
    seed: int | None = None,
) -> BarPlot:
    """Pixel heights as (groups, series): bar_gap within a group, group_gap between groups, with legs alternated across columns in left, right, left, right ... order.

    When style is a list it is cycled according to cycle: "group" (default)
    cycles by position within the group — the i-th bar of a group uses
    styles[i % len], so a list whose length equals the series count means
    "one style per series"; "sequence" cycles in the draw order of all
    bars (group 0 bar 0, group 0 bar 1, group 1 bar 0, ...).
    """


def add_paired_bars(
    self,
    heights_px: Sequence[tuple[float, float]],
    *,
    group_gap: float = DEFAULT_GROUP_GAP,
    style: StyleSeq = DEFAULT_STOCKING_STYLE,
    cycle: Literal["group", "sequence"] = "group",
    pairs: Sequence[tuple[Leg, Leg]] | None = None,
    seed: int | None = None,
) -> BarPlot:
    """Exactly 2 values per group: each group uses the same pair of assets, series 0 the left leg and series 1 the right leg.

    When style is a list it is cycled according to cycle ("group" default:
    series 0 takes styles[0] and series 1 takes styles[1 % len];
    "sequence" cycles in the draw order of all bars).
    When pairs is omitted, non-repeating asset pairs are chosen
    automatically.
    """
```

**Spacing semantics**: `bar_gap` / `group_gap` both mean the gap between the **edges** of adjacent legs (leg widths vary from 144 to 181; spacing by edge looks visually even), not foot-sole-center distance.
