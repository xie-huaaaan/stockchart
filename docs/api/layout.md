# L3 — layout helpers

← [API index](index.md) · Related: [L2 free-form bar plot](barplot.md)

The following are all `BarPlot` convenience methods: they only solve "spacing + leg selection"; stocking heights are still given in pixels by the caller.

```python
def add_bars(
    self,
    heights_px: Sequence[float],
    *,
    bar_gap: float = DEFAULT_BAR_GAP,
    style: StyleSeq = DEFAULT_STOCKING_STYLE,
    paired: Literal["auto", "none", "group", "global"] = "auto",
    legs: Sequence[Leg] | None = None,
    seed: int | None = None,
) -> BarPlot:
    """Single series: laid out from left to right with uniform spacing, selecting legs according to the pairing policy.

    legs may explicitly specify the asset of every bar (its length must
    match heights_px, it does not participate in the cycling, and paired is
    ignored in that case). When style is a list it is cycled in bar order.
    Calling an L3 method several times continues the layout from the right
    edge of the previous content.

    Args:
        heights_px: the stocking height of each bar (design pixels).
        bar_gap: the gap between the edges of adjacent legs.
        style: a single style or a list of styles.
        paired: the leg-pairing strategy; for a single series "auto" is
            equivalent to "none".
        legs: explicitly given leg assets; None selects them automatically.
        seed: random source for the automatic leg selection; None derives it
            from the seed given at construction.

    Returns:
        self, for chaining.

    Raises:
        ValueError: heights_px is empty, the length of legs does not match,
            paired is invalid when the legs are selected automatically, or
            the style list is empty / contains an unknown preset.
    """


def add_grouped_bars(
    self,
    heights_px: Sequence[Sequence[float]],
    *,
    bar_gap: float = DEFAULT_BAR_GAP,
    group_gap: float = DEFAULT_GROUP_GAP,
    style: StyleSeq = DEFAULT_STOCKING_STYLE,
    cycle: Literal["group", "sequence"] = "group",
    paired: Literal["auto", "none", "group", "global"] = "auto",
    legs: Sequence[Leg] | None = None,
    seed: int | None = None,
) -> BarPlot:
    """Lay out a grouped bar plot from pixel heights given as (group count, series count).

    Within a group use bar_gap, between groups use group_gap; ordinary layouts
    select from all legs, while paired layouts use complete left-right pairs.

    Args:
        heights_px: a 2D height table; every row is a group and every column
            inside the group is one series.
        bar_gap: the gap between the edges of adjacent legs inside a group.
        group_gap: the gap between adjacent groups.
        style: a single style or a list of styles.
        cycle: "group" cycles by the position inside the group; "sequence"
            cycles in the draw order of all the bars.
        paired: the leg-pairing strategy; "auto" uses "none" for a single
            series and "global" for multiple series.
        legs: explicit leg assets, flattened in row-major order; None selects
            them automatically.
        seed: random source for the automatic leg selection; None derives it
            from the seed given at construction.

    Returns:
        self, for chaining.

    Raises:
        ValueError: heights_px is empty, contains an empty group, the groups
            have different series counts, the length of legs does not match,
            paired is invalid when the legs are selected automatically,
            cycle is invalid, or the style list is empty / contains an
            unknown preset.
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
    """Exactly 2 values per group: the same pair of assets is used inside a group, series 0 takes the left leg and series 1 the right leg.

    Args:
        heights_px: the (left leg height, right leg height) of every group.
        group_gap: the gap between adjacent groups.
        style: a single style or a list of styles.
        cycle: "group" cycles by the position inside the group; "sequence"
            cycles in the draw order of all the bars.
        pairs: explicit asset pairs, their length must equal the number of
            groups; None selects them automatically.
        seed: random source for the automatic pair selection; None derives it
            from the seed given at construction.

    Returns:
        self, for chaining.

    Raises:
        ValueError: heights_px is empty, some group does not have exactly 2
            values, the length/shape of pairs does not match, cycle is
            invalid, or the style list is empty / contains an unknown
            preset.
    """
```

`add_grouped_bars` requires a rectangular `heights_px` table (non-empty, same-length, non-empty groups); `add_paired_bars` requires exactly 2 values per group and exactly 2 legs per explicit pair; `cycle` only accepts "group" / "sequence". When `legs` / `pairs` are passed explicitly, `paired` is not validated.

**Spacing semantics**: `bar_gap` / `group_gap` both mean the gap between the **edges** of adjacent legs (leg widths vary from 145 to 183; spacing by edge looks visually even), not foot-sole-center distance.

## Minimal example

```python
from stockchart import BarPlot

plot = BarPlot(1200)
plot.add_grouped_bars([[300, 200], [400, 250]], style=["black_sheer", "white_sheer"])
plot.add_x_labels(["Jan", "Feb"])
plot.save("grouped.png")
```
