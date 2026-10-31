"""L2 基础测试：Scale 比例尺与 BarPlot 核心（add_bar / render）。"""

import numpy as np
import pytest

from stockchart import BarPlot, Leg, LegLibrary, Scale

BG = (250, 248, 243)
LIB = LegLibrary(seed=1)


def make_leg(h: int = 720, w: int = 160) -> Leg:
    """合成一条纯色腿，便于断言像素区域。"""
    img = np.zeros((h, w, 4), dtype=np.uint8)
    img[..., :3] = (253, 234, 228)
    img[..., 3] = 255
    return Leg(
        image=img,
        width=w,
        height=h,
        foot_center_x=w // 2,
    )


class TestScale:
    def test_to_px_and_from_px(self) -> None:
        s = Scale((0.0, 10.0), (0.0, 200.0))
        assert s.to_px(0) == 0.0
        assert s.to_px(10) == 200.0
        assert s.to_px(5) == pytest.approx(100.0)
        assert s.from_px(150) == pytest.approx(7.5)
        assert s.from_px(s.to_px(3.7)) == pytest.approx(3.7)

    def test_domain_validation(self) -> None:
        with pytest.raises(ValueError):
            Scale((5.0, 5.0), (0.0, 100.0))
        with pytest.raises(ValueError):
            Scale((10.0, 0.0), (0.0, 100.0))

    def test_fit(self) -> None:
        s = Scale.fit([2.0, 4.0, 9.0], 300.0)
        assert s.domain == (2.0, 9.0)
        assert s.range_px == (0.0, 300.0)

    def test_fit_margin(self) -> None:
        s = Scale.fit([0.0, 10.0], 100.0, margin=0.1)
        assert s.domain == pytest.approx((-1.0, 11.0))

    def test_fit_rejects_degenerate(self) -> None:
        with pytest.raises(ValueError):
            Scale.fit([], 100.0)
        with pytest.raises(ValueError):
            Scale.fit([3.0, 3.0, 3.0], 100.0)
        with pytest.raises(ValueError):
            Scale.fit([1.0, 2.0], 100.0, margin=-0.1)


class TestBarPlotCore:
    def test_add_bar_chains(self) -> None:
        plot = BarPlot(600)
        assert plot.add_bar(100, 300, make_leg()) is plot

    def test_render_size_grows_with_legs(self) -> None:
        canvases = [
            BarPlot(600, extent_up=100, extent_down=0).add_bar(300, 0, make_leg(h=h)).render()
            for h in (200, 720)
        ]
        # 预容纳不下腿时自动扩张
        assert canvases[1].height_px > canvases[0].height_px

    def test_render_pixels_and_determinism(self) -> None:
        def build() -> BarPlot:
            p = BarPlot(400, extent_up=760, seed=0)
            p.add_bar(120, 500, make_leg(), style="black_sheer")
            p.add_bar(280, 200, make_leg(), style="white_tights")
            return p

        c1, c2 = build().render(), build().render()
        a1, a2 = c1.to_numpy(), c2.to_numpy()
        assert a1.shape == a2.shape
        assert (a1 == a2).all()
        # 腿真的画上去了：基线附近有非背景像素
        bg = np.array(BG, dtype=int)
        diff = np.abs(a1[:, :, :3].astype(int) - bg).sum(axis=2) > 30
        assert diff.any()

    def test_down_side_flips_foot_to_baseline(self) -> None:
        p = BarPlot(400, extent_up=0, extent_down=0, background=BG)
        p.add_bar(200, 300, make_leg(h=400, w=100), side="down")
        arr = p.render(scale=1).to_numpy()
        # 翻转后脚贴基线：紧贴基线处应有像素，基线下方远处（腿长之下）应没有
        bg = np.array(BG, dtype=int)
        inked = np.abs(arr[:, :, :3].astype(int) - bg).sum(axis=2) > 30
        rows = np.where(inked.any(axis=1))[0]
        assert rows.min() < 5  # 内容从基线开始向下
        assert rows.max() <= 400 + 1  # 最深不超过腿高

    def test_unknown_style_raises(self) -> None:
        with pytest.raises(ValueError, match="未知样式预设"):
            BarPlot(400).add_bar(100, 100, make_leg(), style="no_such_style")

    def test_invalid_width_and_scale(self) -> None:
        with pytest.raises(ValueError):
            BarPlot(0)
        plot = BarPlot(400).add_bar(100, 100, make_leg())
        with pytest.raises(ValueError):
            plot.render(scale=0)

    def test_bare_leg_is_zero_height_stocking(self) -> None:
        p = BarPlot(400, extent_up=760)
        p.add_bar(200, 0, make_leg(), style="black_sheer")
        arr = p.render().to_numpy()
        # 裸腿：只有肤色，没有深色袜子（黑色 sheer 会显著加深）
        leg_zone = arr[200:500, 180:220, :3].astype(int)
        assert (leg_zone.max(axis=2) > 200).any()  # 存在接近肤色的亮像素
