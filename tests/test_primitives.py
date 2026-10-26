"""L1 渲染原语测试：Canvas、draw_text / measure_text、sketch_line / sketch_axis。"""

from pathlib import Path

import numpy as np
import pytest
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
from stockchart.text import wrap_text

BG: Color = (250, 248, 243)


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
        # 逐字符回退的布局契约：整串宽度 = 各字符宽度之和
        assert measure_text("wwww", size_px=30) == pytest.approx(4 * measure_text("w", size_px=30))
        assert measure_text("脱粉量", size_px=30) > 0

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
