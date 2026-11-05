"""样式解析与选腿。

把用户给的样式写法（预设名或样式对象）归一为 StockingStyle 实例，
并按配对策略从素材库里挑腿。
"""

from __future__ import annotations

from collections.abc import Sequence

from stockchart.legs import Leg
from stockchart.library import LegLibrary
from stockchart.plot.types import Pairing, StyleCycle
from stockchart.stocking import STYLES, StockingStyle, StyleLike, StyleSeq


def check_pairing(paired: Pairing) -> None:
    """校验选腿的配对策略。

    Args:
        paired: 待校验的策略值。

    Raises:
        ValueError: 不在 "auto" / "none" / "group" / "global" 中。
    """
    if paired not in ("auto", "none", "group", "global"):
        raise ValueError(f"paired 须为 'auto'、'none'、'group' 或 'global'，得到 {paired!r}")


def check_cycle(cycle: StyleCycle) -> None:
    """校验批量样式的循环方式。

    Args:
        cycle: 待校验的循环方式。

    Raises:
        ValueError: 不在 "group" / "sequence" 中。
    """
    if cycle not in ("group", "sequence"):
        raise ValueError(f"cycle 须为 'group' 或 'sequence'，得到 {cycle!r}")


def select_legs_for_groups(sizes: Sequence[int], *, paired: Pairing, seed: int) -> list[list[Leg]]:
    """按每组腿数自动选腿。

    "auto"（默认）单系列用 "none"、多系列用 "global"；"none" 时每条腿来自
    不同素材对；"group" 时每组独立取完整对，奇数系列数舍去最后一对多出的
    右腿（单系列即每组取新素材对的左腿）；"global" 时整张图连续取对，配对
    可以跨组。

    Args:
        sizes: 每组需要的腿数；每项须为正。
        paired: 配对策略。
        seed: 选腿随机源；同一 seed 结果可复现。

    Returns:
        与 sizes 同构的 Leg 列表。

    Raises:
        ValueError: sizes 为空、含非正数，或 paired 不合法。
    """
    check_pairing(paired)
    if not sizes or any(size <= 0 for size in sizes):
        raise ValueError("每组腿数须为正数")
    lib = LegLibrary(seed=seed)
    if paired == "auto":
        paired = "global" if max(sizes) >= 2 else "none"

    if paired == "group":
        pairs_per_group = [(size + 1) // 2 for size in sizes]
        pairs = lib.sample_pairs(sum(pairs_per_group))
        result: list[list[Leg]] = []
        cursor = 0
        for size, count in zip(sizes, pairs_per_group, strict=True):
            group_pairs = pairs[cursor : cursor + count]
            cursor += count
            result.append([leg for pair in group_pairs for leg in pair][:size])
        return result

    flat = lib.alternate(sum(sizes), paired=paired == "global")
    result = []
    cursor = 0
    for size in sizes:
        result.append(flat[cursor : cursor + size])
        cursor += size
    return result


def resolve_style(style: StyleLike) -> StockingStyle:
    """把单个样式参数归一为 StockingStyle 实例。

    Args:
        style: StockingStyle 实例或 STYLES 预设名。

    Returns:
        对应的 StockingStyle 实例。

    Raises:
        ValueError: 预设名不存在。
    """
    if isinstance(style, str):
        try:
            return STYLES[style]
        except KeyError:
            raise ValueError(f"未知样式预设 {style!r}，可选：{'、'.join(STYLES)}") from None
    return style


def normalize_style_seq(style: StyleSeq) -> list[StockingStyle]:
    """把样式参数归一为非空的实例列表。

    Args:
        style: 单个样式或样式序列。

    Returns:
        StockingStyle 列表；单项输入包装成长度为 1 的列表。

    Raises:
        ValueError: 序列为空，或含未知预设名。
    """
    styles = [style] if isinstance(style, (str, StockingStyle)) else list(style)
    if not styles:
        raise ValueError("style 列表不能为空")
    return [resolve_style(s) for s in styles]


def cycle_styles(styles: Sequence[StockingStyle], n: int) -> list[StockingStyle]:
    """把样式列表按绘制顺序展开为 n 根柱各自的样式。

    Args:
        styles: 已归一化的样式列表；不能为空。
        n: 需要的样式个数。

    Returns:
        长度为 n 的列表，不足时从头循环；调用方决定切片起点。
    """
    return [styles[i % len(styles)] for i in range(n)]
