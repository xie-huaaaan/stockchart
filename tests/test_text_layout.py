"""折行与块布局测试：break_lines 的切分/软折行/省略号与 layout_text 的块度量、缓存。"""

import pytest
import skia

from stockchart.text.engine import shape_line
from stockchart.text.fonts import resolve_stack
from stockchart.text.layout import break_lines, layout_text

# 微软雅黑仅 Windows 自带；涉及它的测试在缺字体的平台跳过
_HAS_YAHEI = (
    skia.FontMgr.RefDefault().matchFamilyStyle("Microsoft YaHei", skia.FontStyle.Normal())
    is not None
)


class TestBreakLines:
    def test_hard_newline_split(self) -> None:
        assert break_lines("甲\n乙\n丙", size_px=20) == ["甲", "乙", "丙"]
        # 无 max_width 也尊重 max_lines：溢出段并入末行并加省略号
        assert break_lines("甲\n乙\n丙", size_px=20, max_lines=2) == ["甲", "乙丙…"]

    def test_empty_text(self) -> None:
        assert break_lines("", size_px=20) == [""]
        assert break_lines("", size_px=20, max_width=100) == [""]

    def test_cjk_wrap_no_loss(self) -> None:
        text = "一二三四五六七八九十"
        lines = break_lines(text, size_px=20, max_width=60)
        assert len(lines) > 1
        assert "".join(lines) == text
        stack = resolve_stack(None)
        for line in lines:
            assert shape_line(line, stack, size_px=20).advance <= 60

    def test_overwide_char_still_advances(self) -> None:
        # 单字超过 max_width：折行至少前进一个字符（不卡死），复核阶段截成省略号
        lines = break_lines("一二三", size_px=100, max_width=20)
        assert len(lines) == 3
        assert all(line.endswith("\u2026") for line in lines)

    def test_english_breaks_at_spaces(self) -> None:
        text = " ".join(["hello"] * 8)
        lines = break_lines(text, size_px=20, max_width=120)
        assert len(lines) > 1
        # 断点回退保证只在空格处断开：每行由完整的 hello 组成，且无丢字
        assert all(part == "hello" for line in lines for part in line.split())
        assert " ".join(lines) == text
        stack = resolve_stack(None)
        for line in lines:
            assert shape_line(line, stack, size_px=20).advance <= 120

    def test_english_breaks_at_hyphen(self) -> None:
        text = "-".join(["abcd"] * 8)
        lines = break_lines(text, size_px=20, max_width=80)
        assert len(lines) > 1
        # 连字符是可断点：断开后行尾保留连字符，不把 abcd 切碎
        for line in lines:
            fragments = line.split("-")
            assert all(f == "abcd" for f in fragments[:-1])
            assert fragments[-1] in ("abcd", "")
        assert "".join(lines) == text

    def test_max_lines_adds_ellipsis(self) -> None:
        lines = break_lines("一" * 100, size_px=20, max_width=40, max_lines=2)
        assert len(lines) == 2
        assert lines[-1].endswith("\u2026")
        stack = resolve_stack(None)
        for line in lines:
            assert shape_line(line, stack, size_px=20).advance <= 40

    def test_max_lines_spans_hard_breaks(self) -> None:
        # 行数上限跨全部 \n 段累计：末行并入溢出文本后截断加省略号
        lines = break_lines("甲\n乙\n丙丁戊", size_px=20, max_width=60, max_lines=2)
        assert len(lines) == 2
        assert lines[0] == "甲"
        assert lines[1].startswith("乙")
        assert lines[1].endswith("\u2026")

    def test_max_lines_must_be_positive(self) -> None:
        with pytest.raises(ValueError):
            break_lines("测试", size_px=20, max_lines=0)

    def test_empty_font_candidates_raise(self) -> None:
        with pytest.raises(ValueError):
            break_lines("测试", size_px=20, font=[])
        with pytest.raises(ValueError):
            break_lines("测试", size_px=20, font=[""])


class TestWidthRecheck:
    def test_all_lines_within_max_width(self) -> None:
        # 估宽不含 kerning，最终每行以 shape_line 的真实 advance 复核
        texts = [
            "一二三四五六七八九十",
            " ".join(["hello"] * 8),
            "hello world, the quick-brown fox; jumps: over/the lazy dog",
        ]
        stack = resolve_stack(None)
        for text in texts:
            lines = break_lines(text, size_px=24, max_width=90)
            assert len(lines) > 1
            for line in lines:
                assert shape_line(line, stack, size_px=24).advance <= 90


class TestLayoutText:
    def test_single_line_metrics(self) -> None:
        layout = layout_text("测试文字", size_px=30)
        assert len(layout.lines) == 1
        line = layout.lines[0]
        assert layout.width == line.advance
        assert layout.height == line.height
        assert layout.baseline == line.baseline
        assert layout.line_step == line.height

    def test_multi_line_block_metrics(self) -> None:
        single = layout_text("甲", size_px=20)
        two = layout_text("甲\n乙", size_px=20)
        three = layout_text("甲\n乙\n丙", size_px=20)
        assert len(two.lines) == 2
        height = max(line.height for line in two.lines)
        baseline = max(line.baseline for line in two.lines)
        width = max(line.advance for line in two.lines)
        assert two.line_step == height
        assert two.baseline == baseline
        assert two.width == width
        assert two.height == two.line_step + height
        assert two.height > single.height
        height3 = max(line.height for line in three.lines)
        assert three.height == 2 * three.line_step + height3

    def test_line_height_scales_step(self) -> None:
        natural = layout_text("甲\n乙", size_px=20)
        spaced = layout_text("甲\n乙", size_px=20, line_height=2.0)
        assert spaced.line_step == 2.0 * natural.line_step
        height = max(line.height for line in spaced.lines)
        assert spaced.height == spaced.line_step + height
        assert spaced.height > natural.height

    def test_empty_text_layout(self) -> None:
        layout = layout_text("", size_px=20)
        assert len(layout.lines) == 1
        assert layout.lines[0].text == ""
        assert layout.width == 0
        assert layout.height == layout.lines[0].height
        assert layout.height > 0
        assert layout.baseline == layout.lines[0].baseline

    def test_result_is_cached(self) -> None:
        a = layout_text("缓存测试", size_px=20)
        b = layout_text("缓存测试", size_px=20)
        assert a is b
        c = layout_text("缓存测试", size_px=20, max_width=100)
        d = layout_text("缓存测试", size_px=20, max_width=100)
        assert c is d
        assert c is not a

    def test_invalid_font_propagates(self) -> None:
        with pytest.raises(ValueError):
            layout_text("测试", size_px=20, font=[])


class TestExplicitFont:
    @pytest.mark.skipif(not _HAS_YAHEI, reason="需要系统安装 Microsoft YaHei（Windows 自带）")
    def test_yahei_cjk_wrap(self) -> None:
        # 微软雅黑的汉字advance为 1 em；max_width=65 避开每行字符数的边界
        text = "甲乙丙丁戊己"
        lines = break_lines(text, size_px=20, font="Microsoft YaHei", max_width=65)
        assert lines == ["甲乙丙", "丁戊己"]
        assert "".join(lines) == text
