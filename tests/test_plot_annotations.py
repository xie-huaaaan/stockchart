"""L2 标注测试：add_y_axis / add_x_labels / add_title / add_legend。"""

import numpy as np
import pytest
from tests.test_plot_core import BG, make_leg

from stockchart import BarPlot, Scale

INK = np.array((72, 72, 72), dtype=int)


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

    def test_default_ticks_from_domain(self) -> None:
        p = BarPlot(600)
        p.add_y_axis(Scale((0.0, 8.0), (0.0, 700.0)))
        arr = p.render(scale=1).to_numpy()
        assert inked(arr).any()

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

    def test_grid_draws_under_bars(self) -> None:
        p = BarPlot(600)
        p.add_bar(300, 500, make_leg(h=720, w=300), style="black_sheer")
        p.add_y_axis(Scale((0.0, 10.0), (0.0, 700.0)), ticks=[5], grid=True)
        arr = p.render(scale=1).to_numpy()
        # 刻度 5 → y ≈ 760 - 350 = 410；网格画在腿右侧的空白区
        zone = arr[390:430, 550:590, :3].astype(int)
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


class TestTitleAndLegend:
    def test_title_at_top_left(self) -> None:
        p = BarPlot(600)
        p.add_title("测试标题")
        arr = p.render(scale=1).to_numpy()
        m = inked(arr)
        assert m[:120, :400].any()

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

    def test_legend_ncol_wraps(self) -> None:
        p = BarPlot(600)
        p.add_legend(
            [(f"系列{i}", "black_sheer") for i in range(5)],
            ncol=2,
        )
        arr = p.render(scale=1).to_numpy()
        assert inked(arr).any()

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


class TestBaseline:
    def test_baseline_drawn_with_arrow(self) -> None:
        p = BarPlot(600, extent_up=760)
        p.add_bar(300, 300, make_leg())
        arr = p.render(scale=1).to_numpy()
        m = inked(arr)
        # 基线在 extent_up 附近：该行横向长墨迹
        row = m[760, :]
        assert row.sum() > 400
