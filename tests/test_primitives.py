"""L1 渲染原语测试：Canvas、draw_text / measure_text、sketch_line / sketch_axis。"""

from pathlib import Path

import numpy as np
import pytest
import skia
from numpy.typing import NDArray
from PIL import Image

from stockchart import (
    Canvas,
    Color,
    draw_text,
    measure_text,
    sketch_axis,
    sketch_line,
)
from stockchart.text import measure_text_height, wrap_text

BG: Color = (250, 248, 243)

# kerning 断言依赖 Segoe UI（Windows 自带，含 AV 对的内缩 kerning 对）
_HAS_SEGOE_UI = (
    skia.FontMgr.RefDefault().matchFamilyStyle("Segoe UI", skia.FontStyle.Normal()) is not None
)


def blank(w: int = 300, h: int = 200) -> Canvas:
    return Canvas(w, h, background=BG)


def pixels(canvas: Canvas) -> NDArray[np.uint8]:
    return canvas.to_numpy()


def ink_mask(canvas: Canvas) -> NDArray[np.bool_]:
    """与背景明显不同的像素。"""
    arr = pixels(canvas).astype(int)
    bg = np.array(BG, dtype=int)
    return np.abs(arr[:, :, :3] - bg).sum(axis=2) > 30


class TestCanvas:
    def test_shape_and_dtype(self) -> None:
        arr = pixels(blank(120, 80))
        assert arr.shape == (80, 120, 4)
        assert arr.dtype == np.uint8

    def test_background_fill(self) -> None:
        arr = pixels(blank())
        assert (arr[0, 0] == (*BG, 255)).all()
        assert (arr[-1, -1] == (*BG, 255)).all()

    def test_save_png(self, tmp_path: Path) -> None:
        path = blank().save(tmp_path / "c.png")
        assert path.exists()
        img = Image.open(path)
        assert img.size == (300, 200)

    def test_to_pil(self) -> None:
        img = blank().to_pil()
        assert img.size == (300, 200)
        assert img.mode == "RGBA"

    def test_invalid_size(self) -> None:
        with pytest.raises(ValueError):
            Canvas(0, 100)


class TestDrawText:
    def test_text_draws_pixels(self) -> None:
        c = blank()
        before = pixels(c).copy()
        draw_text(c, "脱粉 123", 20, 100, size_px=30)
        assert (pixels(c) != before).any()

    def test_deterministic(self) -> None:
        c1, c2 = blank(), blank()
        draw_text(c1, "脱粉量 12", 20, 100, size_px=30)
        draw_text(c2, "脱粉量 12", 20, 100, size_px=30)
        assert (pixels(c1) == pixels(c2)).all()

    def test_anchor_shifts_ink(self) -> None:
        left, center = blank(), blank()
        draw_text(left, "ABC", 150, 100, size_px=30, anchor=("left", "baseline"))
        draw_text(center, "ABC", 150, 100, size_px=30, anchor=("center", "baseline"))

        def centroid(c: Canvas) -> float:
            m = ink_mask(c)
            return float(np.where(m)[1].mean())

        assert centroid(center) < centroid(left)

    def test_missing_glyph_does_not_raise(self) -> None:
        c = blank()
        before = pixels(c).copy()
        draw_text(c, "A\ue003B", 20, 100, size_px=30)  # 私有区字符必无字形
        assert (pixels(c) != before).any()

    def test_empty_text_noop(self) -> None:
        c = blank()
        before = pixels(c).copy()
        draw_text(c, "", 20, 100, size_px=30)
        assert (pixels(c) == before).all()

    def test_measure_text(self) -> None:
        assert measure_text("", size_px=30) == 0.0
        assert measure_text("脱粉量", size_px=30) > 0

    @pytest.mark.skipif(not _HAS_SEGOE_UI, reason="需要 Segoe UI 字体")
    def test_measure_text_kerning(self) -> None:
        # 整串经段落整形（HarfBuzz 含 kerning），逐字测量则无 kerning：
        # AV 是经典内缩对，整串宽度必须小于逐字之和
        per_char = sum(measure_text(ch, size_px=40, font="Segoe UI") for ch in "AVAV")
        assert measure_text("AVAV", size_px=40, font="Segoe UI") < per_char

    def test_newline_draws_two_lines(self) -> None:
        def ink_span(c: Canvas) -> int:
            ys, _ = np.where(ink_mask(c))
            return int(np.ptp(ys))

        single, multi = blank(), blank()
        draw_text(single, "A", 30, 100, size_px=30)
        draw_text(multi, "A\nA", 30, 100, size_px=30)
        # \n 产生第二行：墨迹纵向跨度明显大于单行
        assert ink_span(multi) > ink_span(single)
        # 首行基线仍锚定在 y：两行块的墨迹顶部与单行一致
        top_single = int(np.where(ink_mask(single))[0].min())
        top_multi = int(np.where(ink_mask(multi))[0].min())
        assert abs(top_multi - top_single) <= 2
        # 自然行距下基线间距 = 单行块高：总墨迹跨度 ≈ 单行跨度 + 行距
        step = measure_text_height("A", size_px=30)
        assert ink_span(multi) - ink_span(single) == pytest.approx(step, abs=4)

    def test_max_width_wraps_into_multiple_lines(self) -> None:
        c = blank(120, 400)
        text = "一二三四五六七八九十" * 3
        draw_text(c, text, 10, 40, size_px=20, max_width=100)
        m = ink_mask(c)
        assert m.any()
        ys, xs = np.where(m)
        # 单行 30 个字远超 100px：纵向跨度超过两倍字号说明折成了多行
        assert int(np.ptp(ys)) > 2 * 20
        # 每行右缘不超过 x + max_width（留抗锯齿余量）
        assert int(xs.max()) <= 10 + 100 + 2

    def test_vertical_anchor_ordering(self) -> None:
        def ink_rows(c: Canvas) -> NDArray[np.int_]:
            return np.where(ink_mask(c))[0]

        tops, middles, bottoms = blank(), blank(), blank()
        draw_text(tops, "A", 30, 150, size_px=30, anchor=("left", "top"))
        draw_text(middles, "A", 30, 150, size_px=30, anchor=("left", "middle"))
        draw_text(bottoms, "A", 30, 150, size_px=30, anchor=("left", "bottom"))
        # 垂直锚参照整块：top 把块顶对到 y（墨迹全部在 y 下方），bottom 相反
        assert int(ink_rows(bottoms).min()) < int(ink_rows(middles).min())
        assert int(ink_rows(middles).min()) < int(ink_rows(tops).min())
        assert int(ink_rows(bottoms).max()) < int(ink_rows(middles).max())
        assert int(ink_rows(middles).max()) < int(ink_rows(tops).max())
        # top：块顶即 y，墨迹不会越过 y 上方；bottom：块底即 y，墨迹不会越过 y 下方
        assert int(ink_rows(tops).min()) >= 150
        assert int(ink_rows(bottoms).max()) <= 150

    @pytest.mark.parametrize(
        "anchor",
        [
            ("middle", "baseline"),  # 水平取值非法
            ("left", "center"),  # 垂直取值非法
            ("top", "top"),  # 两个都非法
        ],
    )
    def test_invalid_anchor_raises(self, anchor: tuple[str, str]) -> None:
        with pytest.raises(ValueError):
            draw_text(blank(), "A", 20, 100, size_px=30, anchor=anchor)  # type: ignore[arg-type]

    @pytest.mark.parametrize("size_px", [0, -5])
    def test_nonpositive_size_raises(self, size_px: float) -> None:
        with pytest.raises(ValueError):
            draw_text(blank(), "A", 20, 100, size_px=size_px)

    def test_empty_font_list_raises(self) -> None:
        with pytest.raises(ValueError):
            draw_text(blank(), "A", 20, 100, size_px=30, font=[])
        with pytest.raises(ValueError):
            measure_text("A", size_px=30, font=[])
        with pytest.raises(ValueError):
            measure_text_height("A", size_px=30, font=[])
        with pytest.raises(ValueError):
            wrap_text("A", max_width=100, size_px=30, font=[])

    def test_rotation_makes_text_vertical(self) -> None:
        c = blank()
        draw_text(c, "ABC", 150, 100, size_px=30, anchor=("right", "top"), rotation=-90)
        m = ink_mask(c)
        assert m.any()
        ys, xs = np.where(m)
        assert np.ptp(ys) > np.ptp(xs)  # 竖排：高度明显大于宽度

    def test_rotation_is_deterministic(self) -> None:
        c1, c2 = blank(), blank()
        for c in (c1, c2):
            draw_text(c, "脱粉量", 150, 100, size_px=30, anchor=("right", "top"), rotation=-45)
        assert (pixels(c1) == pixels(c2)).all()


class TestWrapText:
    def test_wraps_within_width(self) -> None:
        text = "一二三四五六七八九十"
        lines = wrap_text(text, max_width=60, size_px=20)
        assert len(lines) > 1
        assert "".join(lines) == text
        assert all(measure_text(line, size_px=20) <= 60 for line in lines)

    def test_max_lines_adds_ellipsis(self) -> None:
        lines = wrap_text("一" * 100, max_width=40, size_px=20, max_lines=2)
        assert len(lines) == 2
        assert lines[-1].endswith("\u2026")
        assert all(measure_text(line, size_px=20) <= 40 for line in lines)

    def test_empty_text(self) -> None:
        assert wrap_text("", max_width=100, size_px=20) == [""]


class TestSketchLine:
    def test_straight_when_no_wobble(self) -> None:
        c = blank()
        sketch_line(c, 50, 100, 250, 100, wobble=0)
        m = ink_mask(c)
        assert m[100, 50] and m[100, 250] and m[100, 150]

    def test_deterministic_by_seed(self) -> None:
        c1, c2, c3 = blank(), blank(), blank()
        sketch_line(c1, 20, 50, 280, 150, seed=7)
        sketch_line(c2, 20, 50, 280, 150, seed=7)
        sketch_line(c3, 20, 50, 280, 150, seed=8)
        assert (pixels(c1) == pixels(c2)).all()
        assert (pixels(c1) != pixels(c3)).any()

    def test_endpoints_pinned_with_wobble(self) -> None:
        c = blank()
        sketch_line(c, 50, 100, 250, 100, wobble=8, seed=3)
        m = ink_mask(c)
        assert m[100, 50] and m[100, 250]


class TestSketchAxis:
    def test_up_axis_draws_line_ticks_and_numbers(self) -> None:
        c = blank()
        before = pixels(c).copy()
        sketch_axis(
            c,
            direction="up",
            x=60,
            y=180,
            length=150,
            ticks=[(0, "0"), (75, "5"), (150, "10")],
        )
        after = pixels(c)
        assert (after != before).any()
        # 轴干线在 x=60 附近
        m = ink_mask(c)
        assert m[100, 59:62].any()

    def test_all_directions_run(self) -> None:
        for direction in ("up", "down", "right"):
            c = blank()
            sketch_axis(c, direction=direction, x=80, y=100, length=120)  # type: ignore[arg-type]
            assert ink_mask(c).any()

    def test_down_axis_without_arrow(self) -> None:
        c = blank()
        sketch_axis(c, direction="down", x=80, y=20, length=120, arrow=False)
        assert ink_mask(c).any()

    def test_deterministic(self) -> None:
        c1, c2 = blank(), blank()
        sketch_axis(c1, direction="up", x=60, y=180, length=150, seed=11)
        sketch_axis(c2, direction="up", x=60, y=180, length=150, seed=11)
        assert (pixels(c1) == pixels(c2)).all()
