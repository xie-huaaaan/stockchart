# 白盒测试：直接检查 BarPlot 的内部布局几何
# pyright: reportPrivateUsage=false

"""L2 标注测试：add_y_axis / add_x_labels / add_title / add_legend。"""

import numpy as np
import pytest
from tests.test_plot_core import BG, make_leg

from stockchart import BarPlot, Scale, measure_text
from stockchart.defaults import (
    DEFAULT_AXIS_NAME_LINE_FACTOR,
    DEFAULT_LABEL_LINE_FACTOR,
    DEFAULT_LEGEND_MAX_LINES,
    DEFAULT_LEGEND_ROW_GAP,
    DEFAULT_LEGEND_SWATCH,
    DEFAULT_PLOT_LEFT_PAD,
    DEFAULT_X_LABEL_SIZE,
    DEFAULT_Y_EXTENT,
)
from stockchart.plot import _format_tick, _layout_axis_name

INK = np.array((72, 72, 72), dtype=int)

LONG_LABELS = [
    "超长的第一个月份标签",
    "超长的第二个月份标签",
    "超长的第三个月份标签",
    "超长的第四个月份标签",
]


def inked(arr: np.ndarray) -> np.ndarray:
    return np.abs(arr[:, :, :3].astype(int) - np.array(BG, dtype=int)).sum(axis=2) > 30


class TestAddYAxis:
    def test_axis_draws_line_and_ticks(self) -> None:
        p = BarPlot(600)
        p.add_bar(300, 0, make_leg())
        p.add_y_axis(Scale((0.0, 10.0), (0.0, 700.0)), ticks=[0, 5, 10])
        arr = p.render(scale=1).to_numpy()
        m = inked(arr)
        assert m.any()
        # 刻度数字在干线左侧 → 轴线 x 处左侧也有墨迹
        assert m[:, :100].any()

    def test_tiny_ticks_do_not_round_to_zero(self) -> None:
        assert _format_tick(1e-10) == "1e-10"
        assert _format_tick(0.0) == "0"
        assert _format_tick(12.0) == "12"

    def test_negative_domain_extends_below(self) -> None:
        up_only = BarPlot(600, extent_down=0)
        up_only.add_bar(300, 0, make_leg())
        up_only.add_y_axis(Scale((0.0, 10.0), (0.0, 700.0)), ticks=[0, 10])
        h_up = up_only.render(scale=1).height_px

        with_neg = BarPlot(600, extent_down=0)
        with_neg.add_bar(300, 0, make_leg())
        with_neg.add_y_axis(Scale((-10.0, 10.0), (-700.0, 700.0)), ticks=[-10, 0, 10])
        h_neg = with_neg.render(scale=1).height_px
        # 负刻度把内容向下推
        assert h_neg > h_up + 300

    def test_ticks_above_extent_expand_top(self) -> None:
        p = BarPlot(600, extent_up=100)
        p.add_y_axis(Scale((0.0, 10.0), (0.0, 300.0)), ticks=[0, 10])
        layout = p._layout()
        # 轴顶与最高刻度数字都要留在画布内
        assert layout.baseline_y - layout.y_up_len >= 0
        assert layout.baseline_y > 100

    def test_non_finite_ticks_rejected(self) -> None:
        with pytest.raises(ValueError):
            BarPlot(600).add_y_axis(Scale((0.0, 10.0), (0.0, 300.0)), ticks=[0, float("nan")])

    def test_grid_draws_under_bars(self) -> None:
        p = BarPlot(600)
        p.add_bar(300, 500, make_leg(h=720, w=300), style="black_sheer")
        p.add_y_axis(Scale((0.0, 10.0), (0.0, 700.0)), ticks=[5], grid=True)
        arr = p.render(scale=1).to_numpy()
        # 刻度 5 → y ≈ DEFAULT_Y_EXTENT - 350；网格画在腿右侧的空白区
        grid_y = DEFAULT_Y_EXTENT - 350
        zone = arr[grid_y - 20 : grid_y + 20, 550:590, :3].astype(int)
        bg = np.array(BG, dtype=int)
        assert (np.abs(zone - bg).sum(axis=2) > 20).any()


class TestAddXLabels:
    def test_labels_below_content(self) -> None:
        p = BarPlot(600, extent_up=760)
        p.add_bar(300, 300, make_leg())
        p.add_x_labels(["甲", "乙"])
        arr = p.render(scale=1).to_numpy()
        m = inked(arr)
        # 标签画在内容最低点之下：下半部分有墨迹
        assert m[arr.shape[0] - 150 :, :].any()

    def test_xs_must_match_labels(self) -> None:
        p = BarPlot(600)
        with pytest.raises(ValueError):
            p.add_x_labels(["甲", "乙"], xs=[100.0])

    def test_anchor_below_down_legs(self) -> None:
        """镜像图：x 标签锚定在朝下腿之下，而不是基线之下。"""
        p = BarPlot(600, extent_up=0, extent_down=720)
        p.add_bar(300, 100, make_leg(h=720, w=160), side="down")
        p.add_x_labels(["组"])
        arr = p.render(scale=1).to_numpy()
        m = inked(arr)
        rows = np.where(m.any(axis=1))[0]
        # 基线在 y=0 附近，下腿深达 ~720；标签必须出现在其下方
        assert rows.max() > 720

    def test_pos_above_puts_label_above_baseline(self) -> None:
        """pos="above"：标签紧贴基线上方，不占据画布底部。"""
        p = BarPlot(600, extent_up=760)
        p.add_bar(300, 200, make_leg(), side="down")
        p.add_x_labels(["甲"], pos="above")
        layout = p._layout()
        baseline = layout.baseline_y
        assert layout.x_label_y is not None
        assert layout.x_label_y < baseline

    def test_pos_below_and_auto_pick_the_legless_side(self) -> None:
        """显式 below 与 auto 都把标签贴到没有柱子的一侧。"""
        p = BarPlot(600, extent_up=760)
        p.add_bar(300, 200, make_leg())
        p.add_x_labels(["甲"], pos="below")
        below_y = p._layout().x_label_y
        assert below_y is not None
        assert below_y > p._layout().baseline_y

        # auto：只有朝上腿 → 贴在基线下方
        q = BarPlot(600, extent_up=760)
        q.add_bar(300, 200, make_leg())
        q.add_x_labels(["甲"], pos="auto")
        auto_y = q._layout().x_label_y
        assert auto_y is not None
        assert auto_y == below_y

        # auto：只有朝下腿 → 贴在基线上方
        r = BarPlot(600, extent_up=760, extent_down=720)
        r.add_bar(300, 200, make_leg(), side="down")
        r.add_x_labels(["甲"], pos="auto")
        auto_above_y = r._layout().x_label_y
        assert auto_above_y is not None
        assert auto_above_y < r._layout().baseline_y

    def test_pos_below_differs_from_content_with_down_legs(self) -> None:
        """有朝下腿时 content 会退到腿下方，below 仍贴基线（显式覆盖的用途）。"""
        p = BarPlot(600, extent_up=760, extent_down=720)
        p.add_bar(300, 200, make_leg(), side="down")
        p.add_x_labels(["甲"], pos="below")
        below_y = p._layout().x_label_y
        p.add_x_labels(["甲"])
        content_y = p._layout().x_label_y
        assert below_y is not None and content_y is not None
        assert below_y < content_y

    def test_pos_auto_falls_back_to_content_when_both_sides(self) -> None:
        p = BarPlot(600, extent_up=760, extent_down=720)
        p.add_bar(200, 200, make_leg(), side="up")
        p.add_bar(400, 200, make_leg(), side="down")
        p.add_x_labels(["甲"], pos="auto")
        layout = p._layout()
        assert layout.x_label_y is not None
        assert layout.x_label_y > layout.content_bottom

    def test_pos_invalid(self) -> None:
        p = BarPlot(600)
        with pytest.raises(ValueError):
            p.add_x_labels(["甲"], pos="middle")  # type: ignore[arg-type]


class TestXLabelRotation:
    def test_auto_rotates_when_adjacent_labels_overlap(self) -> None:
        p = BarPlot(700)
        p.add_x_labels(LONG_LABELS, xs=[100, 250, 400, 550])
        layout = p._layout()
        assert abs(layout.x_label_angle) > 0
        assert layout.x_label_height > DEFAULT_X_LABEL_SIZE * DEFAULT_LABEL_LINE_FACTOR

    def test_angle_resolution(self) -> None:
        """auto 在放得下时不旋转；rotation=0 关掉 auto；显式角度照用。"""
        fits = BarPlot(600)
        fits.add_x_labels(["甲", "乙"], xs=[150, 450])
        assert fits._layout().x_label_angle == 0

        disabled = BarPlot(700)
        disabled.add_x_labels(LONG_LABELS, xs=[100, 250, 400, 550], rotation=0)
        assert disabled._layout().x_label_angle == 0

        explicit = BarPlot(600)
        explicit.add_x_labels(["甲", "乙"], xs=[100, 300], rotation=45)
        # 标签在基线下方 → 负角
        assert explicit._layout().x_label_angle == pytest.approx(-45)

    def test_rotated_labels_get_canvas_margin(self) -> None:
        p = BarPlot(500)
        p.add_x_labels(["标签甲很长很长", "标签乙很长很长"], xs=[10, 120])
        layout = p._layout()
        # 旋转后左侧伸出绘图区，plot_left 被推开，文字不会被画布左缘裁掉
        assert layout.plot_left > 28
        arr = p.render(scale=1).to_numpy()
        cols = np.where(inked(arr).any(axis=0))[0]
        assert cols.min() > 0

    def test_vertical_label_is_centered_on_anchor(self) -> None:
        p = BarPlot(500, extent_up=200)
        x = 250.0
        p.add_x_labels(["甲"], xs=[x], pos="below", rotation=90)
        layout = p._layout()
        assert layout.x_label_y is not None
        arr = p.render(scale=1).to_numpy()
        # x 标签从 x_label_y 开始；基线箭头两翼会伸到基线下方，不纳入统计
        below = inked(arr)[int(layout.x_label_y) :]
        cols = np.where(below.any(axis=0))[0]
        center = (cols.min() + cols.max()) / 2
        assert center == pytest.approx(layout.plot_left + x, abs=6)

    def test_invalid_rotation(self) -> None:
        p = BarPlot(600)
        with pytest.raises(ValueError):
            p.add_x_labels(["甲"], rotation=120)

    def test_non_finite_xs_rejected(self) -> None:
        with pytest.raises(ValueError):
            BarPlot(600).add_x_labels(["甲"], xs=[float("nan")])


class TestAxisStyle:
    def test_default_is_clean(self) -> None:
        assert BarPlot(600)._axis_style == "clean"

    def test_handdrawn_differs_from_clean(self) -> None:
        def build(style: str) -> np.ndarray:
            p = BarPlot(500, extent_up=400, axis_style=style, seed=1)  # type: ignore[arg-type]
            p.add_bar(250, 200, make_leg())
            p.add_y_axis(Scale((0.0, 10.0), (0.0, 300.0)), ticks=[0, 10], grid=True)
            return p.render(scale=1).to_numpy()

        assert not np.array_equal(build("clean"), build("handdrawn"))

    def test_invalid_style(self) -> None:
        with pytest.raises(ValueError):
            BarPlot(600, axis_style="wavy")  # type: ignore[arg-type]


class TestTitleAndLegend:
    def test_title_alignment(self) -> None:
        centered = BarPlot(600)
        centered.add_title("测试标题")
        layout = centered._layout()
        assert centered._title is not None
        assert layout.title_x == pytest.approx(layout.plot_left + 300)

        left = BarPlot(600)
        left.add_title("测试标题", align="left")
        assert left._layout().title_x == pytest.approx(left._layout().plot_left)

    def test_title_alignment_validated(self) -> None:
        with pytest.raises(ValueError):
            BarPlot(600).add_title("标题", align="middle")  # type: ignore[arg-type]

    def test_title_size_is_recorded(self) -> None:
        p = BarPlot(600).add_title("标题", size_px=40)
        assert p._title is not None and p._title.size_px == 40

    def test_long_title_widens_canvas_without_clipping(self) -> None:
        p = BarPlot(300)
        p.add_title("很长的标题" * 20)
        layout = p._layout()
        assert p._title is not None
        text_w = measure_text(p._title.text, size_px=p._title.size_px)
        assert layout.final_w >= text_w + 2 * DEFAULT_PLOT_LEFT_PAD
        assert layout.title_x - text_w / 2 == pytest.approx(DEFAULT_PLOT_LEFT_PAD)
        arr = p.render(scale=1).to_numpy()
        cols = np.where(inked(arr).any(axis=0))[0]
        assert cols.min() > 0
        assert cols.max() < arr.shape[1] - 1

    def test_legend_adds_height_and_draws_items(self) -> None:
        base = BarPlot(600).add_bar(300, 0, make_leg()).render(scale=1).height_px
        with_legend = (
            BarPlot(600)
            .add_bar(300, 0, make_leg())
            .add_legend([("黑丝", "black_sheer"), ("白丝", "white_sheer")])
            .render(scale=1)
        )
        assert with_legend.height_px > base
        arr = with_legend.to_numpy()
        assert inked(arr)[:200, :].any()

    def test_legend_ncol_last_row_is_centered(self) -> None:
        p = BarPlot(600)
        p.add_legend(
            [("甲", "black_sheer"), ("乙", "black_sheer"), ("丙", "black_sheer")],
            ncol=2,
        )
        assert p._legend is not None
        idx_rows, row_heights, _, _ = p._legend_layout(p._legend)
        assert [len(row) for row in idx_rows] == [2, 1]
        layout = p._layout()
        arr = p.render(scale=1).to_numpy()
        last_y0 = round(layout.legend_top_y + row_heights[0] + DEFAULT_LEGEND_ROW_GAP)
        last_y1 = round(last_y0 + row_heights[1])
        xs = np.where(inked(arr)[last_y0:last_y1, :].any(axis=0))[0]
        assert xs.size > 0
        center = (xs[0] + xs[-1]) / 2
        plot_center = layout.plot_left + p.width_px / 2
        assert center == pytest.approx(plot_center, abs=6)

    def test_legend_bottom_loc(self) -> None:
        p = BarPlot(600)
        p.add_bar(300, 0, make_leg())
        p.add_legend([("系列", "black_sheer")], loc="bottom")
        arr = p.render(scale=1).to_numpy()
        m = inked(arr)
        assert m[-150:, :].any()

    def test_legend_rejects_bad_params(self) -> None:
        p = BarPlot(600)
        with pytest.raises(ValueError):
            p.add_legend([("a", "black_sheer")], ncol=0)
        with pytest.raises(ValueError):
            p.add_legend([("a", "black_sheer")], loc="middle")  # type: ignore[arg-type]

    def test_long_legend_label_wraps_to_multiple_lines(self) -> None:
        p = BarPlot(500)
        p.add_legend([("很长的系列名称" * 12, "black_sheer")])
        assert p._legend is not None
        _, row_heights, band_h, lines = p._legend_layout(p._legend)
        assert len(lines[0]) > 1
        assert row_heights[0] > DEFAULT_LEGEND_SWATCH
        assert band_h == pytest.approx(row_heights[0])

    def test_legend_label_stops_at_max_lines_with_ellipsis(self) -> None:
        p = BarPlot(300)
        p.add_legend([("超长系列" * 100, "black_sheer")])
        assert p._legend is not None
        _, _, _, lines = p._legend_layout(p._legend)
        assert len(lines[0]) == DEFAULT_LEGEND_MAX_LINES
        assert lines[0][-1].endswith("\u2026")

    def test_ncol_long_labels_fit_columns(self) -> None:
        p = BarPlot(600)
        p.add_legend(
            [(f"很长的系列名称{i}" * 8, "black_sheer") for i in range(4)],
            ncol=2,
        )
        assert p._legend is not None
        idx_rows, _, _, lines = p._legend_layout(p._legend)
        assert [len(r) for r in idx_rows] == [2, 2]
        assert all(len(line_set) > 1 for line_set in lines)


class TestAxisNames:
    def test_x_axis_name_adds_bottom_space_and_centers(self) -> None:
        base = BarPlot(600).add_bar(300, 100, make_leg())
        base_h = base._layout().final_h
        p = BarPlot(600).add_bar(300, 100, make_leg()).add_x_axis_name("月份")
        layout = p._layout()
        assert layout.x_name_y is not None
        assert layout.final_h > base_h
        assert layout.x_name_x == pytest.approx(layout.plot_left + 300)

    def test_y_axis_name_widens_left_margin(self) -> None:
        scale = Scale((0.0, 10.0), (0.0, 700.0))
        base_left = BarPlot(600).add_y_axis(scale)._layout().plot_left
        p = BarPlot(600).add_y_axis(scale).add_y_axis_name("数量")
        layout = p._layout()
        assert layout.plot_left > base_left
        assert layout.y_name_x > 0
        assert layout.baseline_y - 700 < layout.y_name_y < layout.baseline_y

    def test_axis_name_sizes(self) -> None:
        p = BarPlot(600).add_x_axis_name("月份", size_px=20).add_y_axis_name("数量", size_px=22)
        assert p._x_axis_name is not None and p._x_axis_name.size_px == 20
        assert p._y_axis_name is not None and p._y_axis_name.size_px == 22

    def test_cjk_stacks_and_latin_rotates(self) -> None:
        """中日韩文字逐字竖排，拉丁与数字整体旋转 90°。"""
        cjk = BarPlot(600).add_y_axis_name("人数")
        assert cjk._y_axis_name is not None
        assert not cjk._y_axis_name.rotate

        latin = BarPlot(600).add_y_axis_name("Users")
        assert latin._y_axis_name is not None
        assert latin._y_axis_name.rotate
        latin.render(scale=1)

    def test_long_cjk_y_axis_name_wraps_into_columns(self) -> None:
        p = BarPlot(600, extent_up=120).add_y_axis_name("非常长的纵轴名称示例")
        assert p._y_axis_name is not None
        layout = p._layout()
        columns, block_w = _layout_axis_name(p._y_axis_name, layout.y_name_span)
        assert len(columns) > 1
        assert block_w > p._y_axis_name.size_px
        cell = p._y_axis_name.size_px * DEFAULT_AXIS_NAME_LINE_FACTOR
        assert all(len(column) * cell <= layout.y_name_span + 1e-6 for column in columns)

    def test_long_latin_y_axis_name_wraps_into_lines(self) -> None:
        p = BarPlot(600, extent_up=120).add_y_axis_name("A very long vertical axis name")
        assert p._y_axis_name is not None
        layout = p._layout()
        lines, block_w = _layout_axis_name(p._y_axis_name, layout.y_name_span)
        assert len(lines) > 1
        assert block_w > p._y_axis_name.size_px
        assert all(
            measure_text(line, size_px=p._y_axis_name.size_px) <= layout.y_name_span + 1.0
            for line in lines
        )

    def test_y_axis_no_longer_takes_label(self) -> None:
        p = BarPlot(600)
        with pytest.raises(TypeError):
            p.add_y_axis(Scale((0.0, 10.0), (0.0, 700.0)), label="数量")  # type: ignore


class TestBaseline:
    def test_baseline_drawn_with_arrow(self) -> None:
        p = BarPlot(600, extent_up=760)
        p.add_bar(300, 300, make_leg())
        arr = p.render(scale=1).to_numpy()
        m = inked(arr)
        # 基线在 extent_up 附近：该行横向长墨迹
        row = m[760, :]
        assert row.sum() > 400
