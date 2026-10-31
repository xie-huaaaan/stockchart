# 白盒测试：检查 bar/mirror_bar 的内部柱记录与布局结果
# pyright: reportPrivateUsage=false

"""L4 一行出图测试：映射规则、成对选腿、图例、数值标签与镜像。"""

from typing import Any, cast

import numpy as np
import pytest
from tests.test_data import FakeFrame

from stockchart import STYLES, ChartOptions, PlotData, bar, mirror_bar


class TestBarMapping:
    def test_non_negative_proportional(self) -> None:
        p = bar([10.0, 20.0, 40.0], seed=1)
        hs = [b.height_px for b in p._bars]
        assert hs[1] == pytest.approx(2 * hs[0])
        assert hs[2] == pytest.approx(4 * hs[0])
        assert hs[0] > 0

    def test_zero_is_bare(self) -> None:
        p = bar([0.0, 30.0], seed=1)
        assert p._bars[0].height_px == 0
        assert p._bars[1].height_px > 0

    def test_all_zero_all_bare(self) -> None:
        p = bar([0.0, 0.0, 0.0], seed=1)
        assert all(b.height_px == 0 for b in p._bars)

    def test_mixed_compressed_into_band(self) -> None:
        extent = 760
        p = bar([-10.0, 0.0, 5.0, 30.0], seed=1)
        hs = [b.height_px for b in p._bars]
        assert all(0.1 * extent - 1 <= h <= 0.8 * extent + 1 for h in hs)
        # 单调：值越大丝袜越高
        assert hs == sorted(hs)
        # 0 值带一段丝袜（不为 0）
        assert hs[1] > 0

    def test_all_negative_monotonic(self) -> None:
        p = bar([-30.0, -10.0, -5.0], seed=1)
        hs = [b.height_px for b in p._bars]
        assert hs == sorted(hs)

    def test_empty_data_raises(self) -> None:
        with pytest.raises(ValueError):
            bar([])
        with pytest.raises(ValueError):
            bar([[1.0, 2.0], []])

    def test_ragged_rows_raise(self) -> None:
        with pytest.raises(ValueError):
            bar([[1.0, 2.0], [3.0]])


class TestPairing:
    """paired 的四种策略：auto / none / group / global。"""

    def test_auto_single_series_uses_none(self) -> None:
        p = bar([1.0, 2.0, 3.0], seed=1)
        legs = [b.leg for b in p._bars]
        assert len({leg.pair_id for leg in legs}) == 3
        assert [leg.side for leg in legs] == ["left", "right", "left"]

    def test_auto_multi_series_uses_global(self) -> None:
        p = bar([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]], seed=1)
        legs = [b.leg for b in p._bars]
        assert legs[2].pair_id == legs[3].pair_id
        assert legs[3].side == "right"

    def test_auto_two_series_pairs_within_each_group(self) -> None:
        p = bar([[1.0, 2.0], [3.0, 4.0]], seed=1)
        legs = [b.leg for b in p._bars]
        assert legs[0].pair_id == legs[1].pair_id
        assert legs[2].pair_id == legs[3].pair_id

    def test_group_pairing_three_series(self) -> None:
        p = bar([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]], paired="group", seed=1)
        legs = [b.leg for b in p._bars]
        assert legs[0].pair_id == legs[1].pair_id
        assert legs[2].pair_id != legs[1].pair_id
        assert [leg.side for leg in legs[:3]] == ["left", "right", "left"]
        assert legs[3].pair_id == legs[4].pair_id
        assert legs[3].pair_id != legs[2].pair_id
        assert [leg.side for leg in legs[3:]] == ["left", "right", "left"]

    def test_global_pairing_can_span_groups(self) -> None:
        p = bar([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]], paired="global", seed=1)
        legs = [b.leg for b in p._bars]
        assert legs[0].pair_id == legs[1].pair_id
        assert legs[2].pair_id != legs[1].pair_id
        assert legs[2].pair_id == legs[3].pair_id
        assert legs[3].side == "right"
        assert legs[4].pair_id == legs[5].pair_id

    def test_none_pairing_uses_distinct_pairs(self) -> None:
        p = bar([1.0, 2.0, 3.0], paired="none", seed=1)
        legs = [b.leg for b in p._bars]
        assert len({leg.pair_id for leg in legs}) == 3
        assert [leg.side for leg in legs] == ["left", "right", "left"]

    def test_single_series_group_falls_back_to_none(self) -> None:
        p = bar([1.0, 2.0, 3.0], paired="group", seed=1)
        assert [b.leg.side for b in p._bars] == ["left", "right", "left"]

    def test_two_series_group_is_same_pair_per_group(self) -> None:
        p = bar([[1.0, 2.0], [3.0, 4.0]], paired="group", seed=1)
        legs = [b.leg for b in p._bars]
        assert legs[0].pair_id == legs[1].pair_id
        assert legs[2].pair_id == legs[3].pair_id
        assert legs[0].pair_id != legs[2].pair_id

    def test_invalid_pairing_raises(self) -> None:
        with pytest.raises(ValueError):
            bar([1.0, 2.0], paired=cast(Any, "bogus"))


class TestBarLayout:
    def test_auto_width_fits_legs(self) -> None:
        p = bar([10.0, 20.0, 30.0], seed=1)
        total = sum(b.leg.width for b in p._bars)
        assert p.width_px >= total

    def test_labels_align_centers(self) -> None:
        p = bar([10.0, 20.0], labels=["甲", "乙"], seed=1)
        assert len(p._group_centers) == 2
        assert p._x_labels is not None and p._x_labels.xs is None

    def test_labels_length_mismatch(self) -> None:
        with pytest.raises(ValueError):
            bar([1.0, 2.0], labels=["只有", "两个", "多了"])

    def test_grouped_style_cycles_by_position(self) -> None:
        p = bar(
            [[1.0, 2.0, 3.0], [2.0, 3.0, 4.0]],
            style=["black_tights", "white_tights"],
            seed=1,
        )
        bars = p._bars
        assert len(bars) == 6
        for g in range(2):
            assert bars[g * 3].style is STYLES["black_tights"]
            assert bars[g * 3 + 1].style is STYLES["white_tights"]
            assert bars[g * 3 + 2].style is STYLES["black_tights"]

    def test_1d_style_cycles_by_bar_default(self) -> None:
        """一维数据默认按柱序循环：每根柱拿到自己的样式（组内循环会退化为全同）。"""
        p = bar(
            [1.0, 2.0, 3.0, 4.0],
            style=["black_tights", "white_tights", "knit_cream"],
            seed=1,
        )
        got = [b.style for b in p._bars]
        assert got == [
            STYLES["black_tights"],
            STYLES["white_tights"],
            STYLES["knit_cream"],
            STYLES["black_tights"],
        ]

    def test_1d_group_cycle_keeps_first_style(self) -> None:
        p = bar([1.0, 2.0, 3.0], style=["black_tights", "white_tights"], cycle="group", seed=1)
        assert all(b.style is STYLES["black_tights"] for b in p._bars)

    def test_2d_sequence_cycle(self) -> None:
        p = bar(
            [[1.0, 2.0], [3.0, 4.0]],
            style=["black_tights", "white_tights", "knit_cream"],
            cycle="sequence",
            seed=1,
        )
        got = [b.style for b in p._bars]
        assert got == [
            STYLES["black_tights"],
            STYLES["white_tights"],
            STYLES["knit_cream"],
            STYLES["black_tights"],
        ]

    def test_sequence_cycle_rejects_series_labels(self) -> None:
        with pytest.raises(ValueError):
            bar([[1.0, 2.0]], series_labels=["甲", "乙"], cycle="sequence", seed=1)

    def test_paired_same_pair_per_group(self) -> None:
        p = bar([[1.0, 2.0], [3.0, 4.0]], seed=1)
        bars = p._bars
        assert bars[0].leg.pair_id == bars[1].leg.pair_id
        assert bars[0].leg.side == "left"
        assert bars[1].leg.side == "right"

    def test_series_labels_build_legend(self) -> None:
        p = bar([[1.0, 2.0]], series_labels=["男", "女"], seed=1)
        assert p._legend is not None
        assert [label for label, _ in p._legend.items] == ["男", "女"]

    def test_series_labels_rejected_on_1d(self) -> None:
        with pytest.raises(ValueError):
            bar([1.0, 2.0], series_labels=["甲"])

    def test_value_labels_written(self) -> None:
        p = bar([12.0, 34.0], value_labels=True, seed=1)
        assert [b.value_label for b in p._bars] == ["12", "34"]

    def test_title_and_axis_present(self) -> None:
        p = bar([1.0, 2.0], title="标题", seed=1)
        assert p._title is not None and p._title.text == "标题"
        assert p._y_axis is not None

    def test_render_smoke(self) -> None:
        p = bar(
            [[3.0, 5.0, 2.0], [4.0, 1.0, 6.0]],
            labels=["一月", "二月"],
            series_labels=["甲", "乙", "丙"],
            title="冒烟",
            value_labels=True,
            seed=1,
        )
        c1 = p.render()
        c2 = bar(
            [[3.0, 5.0, 2.0], [4.0, 1.0, 6.0]],
            labels=["一月", "二月"],
            series_labels=["甲", "乙", "丙"],
            title="冒烟",
            value_labels=True,
            seed=1,
        ).render()
        assert (c1.to_numpy() == c2.to_numpy()).all()


class TestDataInference:
    def test_dict_scalars_become_labels(self) -> None:
        p = bar({"一月": 3.0, "二月": 5.0}, seed=1)
        assert p._x_labels is not None
        assert p._x_labels.labels == ["一月", "二月"]

    def test_dataframe_like_infers_labels_and_legend(self) -> None:
        frame = FakeFrame(
            [[1.0, 2.0], [3.0, 4.0]],
            index=("一", "二"),
            columns=("甲", "乙"),
        )
        p = bar(frame, seed=1)
        assert p._x_labels is not None and p._x_labels.labels == ["一", "二"]
        assert p._legend is not None
        assert [label for label, _ in p._legend.items] == ["甲", "乙"]

    def test_explicit_labels_override_inferred(self) -> None:
        p = bar({"a": 1.0, "b": 2.0}, labels=["甲", "乙"], seed=1)
        assert p._x_labels is not None and p._x_labels.labels == ["甲", "乙"]

    def test_plotdata_input(self) -> None:
        data = PlotData(values=((1.0,), (2.0,)), is_1d=True, labels=("a", "b"))
        p = bar(data, seed=1)
        assert p._x_labels is not None and p._x_labels.labels == ["a", "b"]

    def test_numpy_input(self) -> None:
        p = bar(np.array([1.0, 2.0]), seed=1)
        assert len(p._bars) == 2
        assert p._x_labels is None


class TestChartOptions:
    def test_axis_style_and_grid(self) -> None:
        p = bar([1.0, 2.0], grid=True, axis_style="handdrawn", seed=1)
        assert p._axis_style == "handdrawn"
        assert p._y_axis is not None and p._y_axis.grid

    def test_background(self) -> None:
        p = bar([1.0, 2.0], background=(1, 2, 3), seed=1)
        assert p._background == (1, 2, 3)

    def test_title_and_axis_names(self) -> None:
        p = bar(
            [1.0, 2.0],
            title="标题",
            xlabel="月份",
            ylabel="人数",
            title_align="left",
            title_size_px=40,
            axis_name_size_px=20,
            seed=1,
        )
        assert p._title is not None
        assert p._title.align == "left" and p._title.size_px == 40
        assert p._x_axis_name is not None and p._x_axis_name.size_px == 20
        assert p._y_axis_name is not None and p._y_axis_name.text == "人数"

    def test_legend_options(self) -> None:
        p = bar(
            [[1.0, 2.0]],
            series_labels=["a", "b"],
            legend_loc="bottom",
            legend_ncol=2,
            seed=1,
        )
        assert p._legend is not None
        assert p._legend.loc == "bottom" and p._legend.ncol == 2

    def test_ticks_option(self) -> None:
        p = bar([1.0, 2.0], ticks=[0.0, 1.0, 2.0], seed=1)
        assert p._y_axis is not None
        assert p._y_axis.ticks == [0.0, 1.0, 2.0]

    def test_bar_gap_option(self) -> None:
        p = bar([[1.0, 2.0], [3.0, 4.0]], bar_gap=10, seed=1)
        first, second = p._bars[0], p._bars[1]
        gap = (second.x - second.leg.foot_center_x) - (
            first.x - first.leg.foot_center_x + first.leg.width
        )
        assert gap == pytest.approx(10)

    def test_group_gap_option(self) -> None:
        p = bar([[1.0], [3.0]], group_gap=200, seed=1)
        first, second = p._bars
        gap = (second.x - second.leg.foot_center_x) - (
            first.x - first.leg.foot_center_x + first.leg.width
        )
        assert gap == pytest.approx(200)

    def test_x_label_pos_option(self) -> None:
        p = mirror_bar([1.0, -1.0], labels=["甲", "乙"], x_label_pos="below", seed=1)
        layout = p._layout()
        assert layout.x_label_y is not None
        assert layout.x_label_y > layout.baseline_y

    def test_unknown_option_raises(self) -> None:
        with pytest.raises(TypeError, match="未知参数"):
            bar([1.0], **cast(ChartOptions, {"bogus": 1}))


class TestMirrorBar:
    def test_sign_decides_side(self) -> None:
        p = mirror_bar([5.0, -3.0], seed=1)
        up, down = p._bars
        assert up.side == "up" and up.height_px > 0
        assert down.side == "down" and down.height_px > 0
        assert up.height_px / down.height_px == pytest.approx(5 / 3)

    def test_zero_is_up_bare(self) -> None:
        p = mirror_bar([0.0], seed=1)
        assert p._bars[0].side == "up"
        assert p._bars[0].height_px == 0

    def test_both_mode_draws_pair(self) -> None:
        p = mirror_bar([5.0, -3.0, 0.0], mode="both", seed=1)
        bars = p._bars
        assert len(bars) == 6
        # 每值两条腿同一 x，数据侧在记录首位
        for i in range(0, 6, 2):
            assert bars[i].x == bars[i + 1].x
        # 数据侧穿袜、另一侧裸
        assert bars[0].side == "up" and bars[0].height_px > 0
        assert bars[1].height_px == 0
        assert bars[2].side == "down" and bars[2].height_px > 0
        assert bars[3].height_px == 0
        assert bars[4].side == "up" and bars[4].height_px == 0
        assert bars[5].height_px == 0

    def test_negative_axis_extends_layout(self) -> None:
        h_pos = mirror_bar([5.0], seed=1).render(scale=1).height_px
        h_neg = mirror_bar([5.0, -5.0], seed=1).render(scale=1).height_px
        assert h_neg > h_pos

    def test_value_labels_on_data_side(self) -> None:
        p = mirror_bar([5.0, -3.0], value_labels=True, seed=1)
        up, down = p._bars
        assert up.value_label == "5"
        assert down.value_label == "-3"

    def test_deterministic(self) -> None:
        a = mirror_bar([4.0, -2.0, 3.0], labels=["甲", "乙", "丙"], seed=9).render()
        b = mirror_bar([4.0, -2.0, 3.0], labels=["甲", "乙", "丙"], seed=9).render()
        assert (a.to_numpy() == b.to_numpy()).all()
