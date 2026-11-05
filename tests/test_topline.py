# 白盒测试：检查 bar/mirror_bar 的内部柱记录与布局结果
# pyright: reportPrivateUsage=false

"""L4 一行出图测试：映射规则、成对选腿、图例、数值标签与镜像。

与 L2/L3 层重复的断言（间距数学、样式循环、配对细节）只保留在
test_plot_layout.py；此处只测 L4 独有的映射与选项透传。
"""

from typing import Any, cast

import numpy as np
import pytest
from tests.test_data import FakeFrame

from stockchart import STYLES, ChartOptions, bar, mirror_bar


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
        # 全零数据：柱子全裸，轴范围退化为 0–1
        q = bar([0.0, 0.0, 0.0], seed=1)
        assert all(b.height_px == 0 for b in q._bars)
        assert q._y_axis is not None and q._y_axis.scale.domain == (0.0, 1.0)

    def test_mixed_compressed_into_band(self) -> None:
        extent = 720
        p = bar([-10.0, 0.0, 5.0, 30.0], seed=1)
        hs = [b.height_px for b in p._bars]
        assert all(0.1 * extent - 1 <= h <= 0.85 * extent + 1 for h in hs)
        # 单调：值越大丝袜越高
        assert hs == sorted(hs)
        # 0 值带一段丝袜（不为 0）
        assert hs[1] > 0

    def test_all_negative_monotonic(self) -> None:
        p = bar([-30.0, -10.0, -5.0], seed=1)
        hs = [b.height_px for b in p._bars]
        assert hs == sorted(hs)

    def test_all_negative_equal_uses_min_fill(self) -> None:
        p = bar([-5.0, -5.0], seed=1)
        hs = [b.height_px for b in p._bars]
        assert hs == pytest.approx([0.1 * 720, 0.1 * 720])

    def test_invalid_params_raise(self) -> None:
        with pytest.raises(ValueError):
            bar([1.0], max_fill=0)
        with pytest.raises(ValueError):
            bar([1.0], max_fill=1.01)
        with pytest.raises(ValueError):
            bar([-1.0, 1.0], min_fill=-0.1)
        with pytest.raises(ValueError):
            bar([-1.0, 1.0], min_fill=0.9, max_fill=0.8)
        with pytest.raises(ValueError):
            bar([1.0], height_px=0)
        with pytest.raises(ValueError):
            bar([1.0], width_px=0)
        with pytest.raises(ValueError):
            bar([1.0], cycle="bad")  # type: ignore[arg-type]
        with pytest.raises(ValueError):
            mirror_bar([1.0, -1.0], mode="bad")  # type: ignore[arg-type]
        with pytest.raises(ValueError):
            mirror_bar([1.0], max_abs_fill=0)
        with pytest.raises(ValueError):
            mirror_bar([1.0], max_abs_fill=1.01)
        with pytest.raises(ValueError):
            mirror_bar([1.0], height_px=0)

    def test_max_fill_upper_bound_is_inclusive(self) -> None:
        p = bar([1.0], max_fill=1.0, seed=1)
        assert p._bars[0].height_px == pytest.approx(720)

    def test_height_px_auto_and_override(self) -> None:
        p = bar([1.0], seed=1)
        assert p._bars[0].height_px == pytest.approx(0.85 * 720)
        assert p._layout().y_up_len == pytest.approx(792)
        q = bar([1.0], height_px=900, seed=1)
        assert q._layout().y_up_len == pytest.approx(900)

    def test_empty_and_ragged_data_raise(self) -> None:
        with pytest.raises(ValueError):
            bar([])
        with pytest.raises(ValueError):
            bar([[1.0, 2.0], []])
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

    def test_single_series_group_takes_left_leg_of_fresh_pairs(self) -> None:
        p = bar([1.0, 2.0, 3.0], paired="group", seed=1)
        legs = [b.leg for b in p._bars]
        assert [leg.side for leg in legs] == ["left", "left", "left"]
        assert len({leg.pair_id for leg in legs}) == 3

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

    def test_1d_group_cycle_keeps_first_style(self) -> None:
        p = bar([1.0, 2.0, 3.0], style=["black_tights", "white_tights"], cycle="group", seed=1)
        assert all(b.style is STYLES["black_tights"] for b in p._bars)

    def test_sequence_cycle_rejects_series_labels(self) -> None:
        with pytest.raises(ValueError):
            bar([[1.0, 2.0]], series_labels=["甲", "乙"], cycle="sequence", seed=1)

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

    def test_value_labels_bounded_width(self) -> None:
        # 数值标签不参与布局，宽度必须有界：6 位有效数字、大数自动科学计数法，
        # 且不得输出 0.1+0.2 这类最短往返噪声
        p = bar([1234567.0, 0.123456789, 0.1 + 0.2], value_labels=True, seed=1)
        assert [b.value_label for b in p._bars] == ["1.23457e+06", "0.123457", "0.3"]

    def test_title_and_axis_present(self) -> None:
        p = bar([1.0, 2.0], title="标题", seed=1)
        assert p._title is not None and p._title.text == "标题"
        assert p._y_axis is not None

    def test_render_smoke(self) -> None:
        """L4 端到端：标题 / 标签 / 图例 / 数值标签组合渲染不报错且出墨迹。"""
        p = bar(
            [[3.0, 5.0]],
            labels=["一月"],
            series_labels=["甲", "乙"],
            title="冒烟",
            value_labels=True,
            seed=1,
        )
        canvas = p.render(scale=1)
        assert canvas.width_px > 0 and canvas.height_px > 0
        arr = canvas.to_numpy()
        bg = np.array((250, 248, 243), dtype=int)
        assert (np.abs(arr[:, :, :3].astype(int) - bg).sum(axis=2) > 30).any()


class TestDataInference:
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
        # 用布局高度比较，避免渲染（渲染路径由 test_render_smoke 覆盖）
        h_pos = mirror_bar([5.0], seed=1)._layout().final_h
        h_neg = mirror_bar([5.0, -5.0], seed=1)._layout().final_h
        assert h_neg > h_pos

    def test_value_labels_on_data_side(self) -> None:
        p = mirror_bar([5.0, -3.0], value_labels=True, seed=1)
        up, down = p._bars
        assert up.value_label == "5"
        assert down.value_label == "-3"

    def test_deterministic(self) -> None:
        """同 seed 的选腿与柱记录一致。

        像素级确定性由 L2 的 BarPlot 用例与 render_stocking 的 seed 用例覆盖，
        这里只保证 L4 的选腿计划可复现。
        """

        def plan() -> list[tuple[str, str, float]]:
            p = mirror_bar([4.0, -2.0, 3.0], labels=["甲", "乙", "丙"], seed=9)
            return [(b.leg.leg_id or "", b.side, b.height_px) for b in p._bars]

        assert plan() == plan()
