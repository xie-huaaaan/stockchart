# 白盒测试：L2/L4 与新文字引擎的集成（font 两级继承、真实度量联动）
# pyright: reportPrivateUsage=false

"""文字引擎集成测试：font 参数透传、全图默认继承与字体相关的布局变化。"""

import numpy as np
import pytest
import skia
from tests.test_plot_core import BG

from stockchart import BarPlot, Canvas, FontSpec, Scale, bar, sketch_axis

# Segoe UI 为 Windows 自带；度量差异断言依赖它与默认链（Windows 上楷体优先）
# 解析到不同字体，判据与 test_primitives.py 顶部一致
_HAS_SEGOE_UI = (
    skia.FontMgr.RefDefault().matchFamilyStyle("Segoe UI", skia.FontStyle.Normal()) is not None
)

SEGOE: list[str] = ["Segoe UI"]


def inked(arr: np.ndarray) -> np.ndarray:
    return np.abs(arr[:, :, :3].astype(int) - np.array(BG, dtype=int)).sum(axis=2) > 30


class TestChartOptionsFont:
    """L4 ChartOptions.font 透传：BarPlot 与各文字记录都拿到同一字体。"""

    @pytest.mark.skipif(not _HAS_SEGOE_UI, reason="需要 Segoe UI 字体")
    def test_font_option_reaches_all_records(self) -> None:
        p = bar(
            [[1.0]],
            labels=["甲"],
            series_labels=["系列"],
            title="标题",
            ylabel="人数",
            font=SEGOE,
            seed=1,
        )
        assert p._font == SEGOE
        assert p._title is not None and p._title.font == SEGOE
        assert p._y_axis is not None and p._y_axis.font == SEGOE
        assert p._y_axis_name is not None and p._y_axis_name.font == SEGOE
        assert p._x_labels is not None and p._x_labels.font == SEGOE
        assert p._legend is not None and p._legend.font == SEGOE

    @pytest.mark.skipif(not _HAS_SEGOE_UI, reason="需要 Segoe UI 字体")
    def test_font_option_renders(self) -> None:
        """透传路径全链路渲染不报错（含数值标签的全图默认字体）。"""
        p = bar(
            [1.0, 2.0],
            labels=["甲", "乙"],
            title="标题",
            value_labels=True,
            font=SEGOE,
            seed=1,
        )
        assert inked(p.render(scale=1).to_numpy()).any()


class TestBarPlotFont:
    """元素级 font 的两级继承：元素 font → 全图 font → 平台默认链。"""

    def test_elements_inherit_plot_font(self) -> None:
        p = BarPlot(600, font="楷体")
        p.add_title("标题")
        p.add_y_axis(Scale((0.0, 10.0), (0.0, 700.0)))
        p.add_y_axis_name("数量")
        p.add_x_axis_name("月份")
        p.add_x_labels(["甲"])
        p.add_legend([("系列", "black_sheer")])
        assert p._title is not None and p._title.font == "楷体"
        assert p._y_axis is not None and p._y_axis.font == "楷体"
        assert p._y_axis_name is not None and p._y_axis_name.font == "楷体"
        assert p._x_axis_name is not None and p._x_axis_name.font == "楷体"
        assert p._x_labels is not None and p._x_labels.font == "楷体"
        assert p._legend is not None and p._legend.font == "楷体"

    def test_element_font_overrides_plot_font(self) -> None:
        p = BarPlot(600, font="楷体")
        p.add_title("标题", font="Segoe UI")
        assert p._title is not None and p._title.font == "Segoe UI"
        # 未指定的元素仍继承全图默认
        p.add_y_axis_name("数量")
        assert p._y_axis_name is not None and p._y_axis_name.font == "楷体"

    def test_default_is_platform_chain(self) -> None:
        p = BarPlot(600).add_title("标题")
        assert p._title is not None and p._title.font is None


class TestFontChangesLayout:
    @pytest.mark.skipif(not _HAS_SEGOE_UI, reason="需要 Segoe UI 字体")
    def test_font_changes_axis_x(self) -> None:
        """Segoe UI 与楷体数字宽度不同：刻度数字测宽决定轴干线位置。"""

        def axis_x_of(font: FontSpec | None) -> float:
            p = BarPlot(600, font=font)
            p.add_y_axis(Scale((0.0, 10.0), (0.0, 700.0)), ticks=[0, 5, 10])
            return p._layout().axis_x

        assert axis_x_of(SEGOE) != axis_x_of(None)

    @pytest.mark.skipif(not _HAS_SEGOE_UI, reason="需要 Segoe UI 字体")
    def test_font_changes_title_placeholder(self) -> None:
        """标题占位来自实测自然行高：不同字体行高不同，画布随之变高。"""

        def final_h_of(font: FontSpec | None) -> float:
            p = BarPlot(600, font=font)
            p.add_title("mmmmmmmmmm")
            return p._layout().final_h

        assert final_h_of(SEGOE) > final_h_of(None)


class TestSketchAxisFont:
    def test_font_draws_tick_labels(self) -> None:
        c = Canvas(300, 200, background=BG)
        before = c.to_numpy().copy()
        sketch_axis(
            c,
            direction="up",
            x=60,
            y=180,
            length=150,
            ticks=[(0, "0"), (75, "5"), (150, "10")],
            seed=7,
            font=SEGOE,
        )
        arr = c.to_numpy()
        assert (arr != before).any()
        # 刻度数字在干线左侧：左缘区域有墨迹（字体不可用时优雅回退，仍有墨迹）
        assert inked(arr)[:, :59].any()
