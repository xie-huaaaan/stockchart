# 白盒测试：检查 bar/mirror_bar 的内部柱记录与布局结果
# pyright: reportPrivateUsage=false

"""L4 一行出图测试：映射规则、成对选腿、图例、数值标签与镜像。"""

import pytest

from stockchart import STYLES, bar, mirror_bar


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
        assert p._title == "标题"
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
