# 白盒测试：直接检查 BarPlot 的内部记录（光标、组中心、柱子列表）
# pyright: reportPrivateUsage=false

"""L3 布局封装测试：间距数学、样式循环、自动选腿与组中心。"""

import itertools

import pytest
from tests.test_plot_core import make_leg

from stockchart import STYLES, BarPlot, Leg


def leg_w(w: int, side: str = "left") -> Leg:
    return make_leg(h=720, w=w)


class TestAddBars:
    def test_edge_gaps_and_centers(self) -> None:
        p = BarPlot(2000)
        p.add_bars([500.0, 300.0, 400.0], bar_gap=30)
        bars = p._bars
        assert len(bars) == 3
        # 相邻腿图像边缘之间的空隙 == bar_gap
        for a, b in itertools.pairwise(bars):
            left_a = a.x - a.leg.foot_center_x
            left_b = b.x - b.leg.foot_center_x
            assert left_b - (left_a + a.leg.width) == pytest.approx(30)
        # 组中心 = 首左缘与末右缘的中点
        first_left = bars[0].x - bars[0].leg.foot_center_x
        last_right = bars[-1].x - bars[-1].leg.foot_center_x + bars[-1].leg.width
        assert p._group_centers == [pytest.approx((first_left + last_right) / 2)]

    def test_auto_legs_alternate_sides(self) -> None:
        p = BarPlot(2000, seed=3)
        p.add_bars([100.0] * 5)
        sides = [b.leg.side for b in p._bars]
        assert sides == ["left", "right", "left", "right", "left"]

    def test_style_sequence_cycles_by_bar(self) -> None:
        p = BarPlot(2000)
        p.add_bars([100.0] * 4, style=["black_tights", "white_tights"])
        got = [b.style for b in p._bars]
        assert got == [
            STYLES["black_tights"],
            STYLES["white_tights"],
            STYLES["black_tights"],
            STYLES["white_tights"],
        ]

    def test_explicit_legs_length_mismatch(self) -> None:
        p = BarPlot(2000)
        with pytest.raises(ValueError):
            p.add_bars([100.0, 200.0], legs=[leg_w(150)])

    def test_empty_heights_raises(self) -> None:
        with pytest.raises(ValueError):
            BarPlot(2000).add_bars([])

    def test_chaining_advances_cursor(self) -> None:
        p = BarPlot(3000, seed=1)
        p.add_bars([100.0] * 2, bar_gap=20)
        first_end = p._l3_cursor
        p.add_bars([100.0] * 2, bar_gap=20)
        bars = p._bars
        # 第二段首缘与第一段末缘之间隔 group_gap
        left_3 = bars[2].x - bars[2].leg.foot_center_x
        assert left_3 - first_end == pytest.approx(96)  # DEFAULT_GROUP_GAP
        assert len(p._group_centers) == 2


class TestAddGroupedBars:
    def test_style_cycles_by_group_position(self) -> None:
        p = BarPlot(4000, seed=2)
        p.add_grouped_bars(
            [[100.0, 200.0, 300.0], [150.0, 250.0, 350.0]],
            style=["black_tights", "white_tights", "knit_cream"],
        )
        bars = p._bars
        # 每组内第 s 根用 styles[s]，跨组一致
        for g in range(2):
            for s in range(3):
                expect = [STYLES["black_tights"], STYLES["white_tights"], STYLES["knit_cream"]][s]
                assert bars[g * 3 + s].style is expect

    def test_style_sequence_cycles_across_all_bars(self) -> None:
        p = BarPlot(4000, seed=2)
        p.add_grouped_bars(
            [[100.0, 200.0], [150.0, 250.0]],
            style=["black_tights", "white_tights", "knit_cream"],
            cycle="sequence",
        )
        got = [b.style for b in p._bars]
        assert got == [
            STYLES["black_tights"],
            STYLES["white_tights"],
            STYLES["knit_cream"],
            STYLES["black_tights"],
        ]

    def test_group_gap_between_groups(self) -> None:
        p = BarPlot(4000, seed=2)
        p.add_grouped_bars([[100.0, 100.0], [100.0, 100.0]], bar_gap=10, group_gap=80)
        bars = p._bars
        # 组内空隙 10，组间 80
        assert bars[1].x - bars[1].leg.foot_center_x - (
            bars[0].x - bars[0].leg.foot_center_x + bars[0].leg.width
        ) == pytest.approx(10)
        assert bars[2].x - bars[2].leg.foot_center_x - (
            bars[1].x - bars[1].leg.foot_center_x + bars[1].leg.width
        ) == pytest.approx(80)

    def test_group_centers_per_group(self) -> None:
        p = BarPlot(4000, seed=2)
        p.add_grouped_bars([[100.0, 100.0], [100.0, 100.0]])
        assert len(p._group_centers) == 2
        # add_x_labels 无 xs 时自动对齐组中心
        p.add_x_labels(["甲", "乙"])
        assert p._x_labels is not None and p._x_labels.xs is None

    def test_explicit_legs_flattened_length(self) -> None:
        p = BarPlot(4000)
        legs = [leg_w(150) for _ in range(4)]
        with pytest.raises(ValueError):
            p.add_grouped_bars([[100.0, 100.0], [100.0, 100.0]], legs=legs[:3])
        p.add_grouped_bars([[100.0, 100.0], [100.0, 100.0]], legs=legs)
        assert len(p._bars) == 4


class TestAddPairedBars:
    def test_same_pair_per_group_left_first(self) -> None:
        p = BarPlot(2000, seed=5)
        p.add_paired_bars([(100.0, 200.0), (300.0, 400.0)])
        bars = p._bars
        assert bars[0].leg.pair_id == bars[1].leg.pair_id
        assert bars[0].leg.side == "left" and bars[1].leg.side == "right"
        # 同一组用同一对，跨组不同（素材充足时）
        assert bars[2].leg.pair_id == bars[3].leg.pair_id

    def test_style_cycles_by_series(self) -> None:
        p = BarPlot(2000, seed=5)
        p.add_paired_bars([(100.0, 200.0)], style=["black_tights", "white_tights"])
        assert p._bars[0].style is STYLES["black_tights"]
        assert p._bars[1].style is STYLES["white_tights"]

    def test_style_sequence_spans_groups(self) -> None:
        p = BarPlot(2000, seed=5)
        p.add_paired_bars(
            [(100.0, 200.0), (300.0, 400.0)],
            style=["black_tights", "white_tights", "knit_cream"],
            cycle="sequence",
        )
        got = [b.style for b in p._bars]
        assert got == [
            STYLES["black_tights"],
            STYLES["white_tights"],
            STYLES["knit_cream"],
            STYLES["black_tights"],
        ]

    def test_explicit_pairs_length_mismatch(self) -> None:
        p = BarPlot(2000)
        pair = (leg_w(150, "left"), leg_w(150, "right"))
        with pytest.raises(ValueError):
            p.add_paired_bars([(1.0, 2.0), (3.0, 4.0)], pairs=[pair])
