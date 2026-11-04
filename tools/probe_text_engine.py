"""Phase 0 探针：验证新文字引擎依赖的 skia.textlayout 运行时假设。

逐项检查并把验证图落到 out/probe_text/；关键假设失败时以非零退出码结束，
用于决定 engine.py 走 Paragraph 路线还是 TextBlob 备选路线。只做只读验证
（不修改项目文件，图片输出到开发产物目录 out/）。
"""

from __future__ import annotations

import sys
import time
from collections.abc import Callable
from pathlib import Path

import numpy as np
import skia
from PIL import Image

OUT_DIR = Path(__file__).resolve().parents[1] / "out" / "probe_text"

_failures: list[str] = []


def record(name: str, ok: bool, detail: str, *, critical: bool = True) -> None:
    """记录一项检查结果；关键项失败计入失败清单。"""
    tag = "PASS" if ok else "FAIL"
    print(f"[{tag}] {name} :: {detail}")
    if critical and not ok:
        _failures.append(name)


def _build(builder: object) -> skia.textlayout.Paragraph:
    """兼容 Build/build 两种绑定命名，构造 Paragraph。"""
    if hasattr(builder, "Build"):
        return builder.Build()  # pyright: ignore[reportAttributeAccessIssue]
    return builder.build()  # pyright: ignore[reportAttributeAccessIssue]


def render_to_png(name: str, painter: Callable[[skia.Canvas], None], w: int, h: int) -> Path:
    """在白底画布上执行 painter 并保存 PNG，返回路径。"""
    surface = skia.Surface(w, h)
    canvas = surface.getCanvas()
    canvas.clear(skia.ColorWHITE)
    painter(canvas)
    path = OUT_DIR / f"{name}.png"
    surface.makeImageSnapshot().save(str(path))
    return path


def ink_bbox(path: Path) -> tuple[int, int, int, int] | None:
    """找 PNG 中非白像素的包围盒 (left, top, right, bottom)；全白返回 None。"""
    arr = np.asarray(Image.open(path).convert("L"), dtype=np.int16)
    mask = arr < 250
    if not mask.any():
        return None
    rows = np.where(mask.any(axis=1))[0]
    cols = np.where(mask.any(axis=0))[0]
    return int(cols[0]), int(rows[0]), int(cols[-1]), int(rows[-1])


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    size = 40.0

    # ---------- 基础对象与单例 ----------
    record("skia 版本", True, str(getattr(skia, "__version__", "未知")))
    tl = getattr(skia, "textlayout", None)
    record("textlayout 模块存在", tl is not None, str(type(tl)))

    try:
        uni = skia.Unicodes.ICU.Make()
        record("Unicodes.ICU.Make()", uni is not None, str(type(uni)))
    except Exception as exc:  # 探针需要吞掉一切异常并记录
        record("Unicodes.ICU.Make()", False, repr(exc))
        return 1

    mgr = skia.FontMgr.RefDefault()
    record("FontMgr.RefDefault()", mgr is not None, "默认字体管理器可用")

    provider = skia.textlayout.TypefaceFontProvider()
    fc = skia.textlayout.FontCollection()
    fc.setDefaultFontManager(provider)

    def make_paragraph(
        text: str, families: list[str], *, size_px: float, color: int
    ) -> skia.textlayout.Paragraph:
        """单字体单行 Paragraph（新引擎的段级构造方式）。"""
        ts = skia.textlayout.TextStyle()
        ts.setFontFamilies(families)
        ts.setFontSize(size_px)
        ts.setColor(color)
        ps = skia.textlayout.ParagraphStyle()
        ps.setTextStyle(ts)
        builder = skia.textlayout.ParagraphBuilder(ps, fc, uni)
        builder.pushStyle(ts)
        builder.addText(text)
        return _build(builder)

    # ---------- 字体解析 ----------
    normal = skia.FontStyle.Normal()
    latin_tf = mgr.matchFamilyStyle("Segoe UI", normal)
    cjk_tf = mgr.matchFamilyStyle("Microsoft YaHei", normal)
    kaiti_tf = mgr.matchFamilyStyle("楷体", normal)
    record(
        "系统家族解析",
        latin_tf is not None and cjk_tf is not None,
        f"Segoe UI={latin_tf is not None}, YaHei={cjk_tf is not None}, 楷体={kaiti_tf is not None}",
    )
    if latin_tf is None or cjk_tf is None:
        return 1

    latin_alias, cjk_alias = "probe_latin", "probe_cjk"
    provider.registerTypeface(latin_tf, latin_alias)
    provider.registerTypeface(cjk_tf, cjk_alias)

    # ---------- 1. 单段管线与度量语义 ----------
    p = make_paragraph("Hgjp", [latin_alias], size_px=size, color=skia.Color(30, 30, 30))
    p.layout(1e9)
    base_font = skia.Font(latin_tf, size)
    metrics = base_font.getMetrics()
    record(
        "段级 Paragraph 度量",
        p.Height > 0 and p.LongestLine > 0 and 0 < p.AlphabeticBaseline < p.Height,
        f"Height={p.Height:.2f} LongestLine={p.LongestLine:.2f} "
        f"AlphabeticBaseline={p.AlphabeticBaseline:.2f} | "
        f"字 ascent={metrics.fAscent:.2f} descent={metrics.fDescent:.2f} "
        f"measureText={base_font.measureText('Hgjp'):.2f}",
    )
    record(
        "基线语义=|ascent|+leading",
        abs(p.AlphabeticBaseline + metrics.fAscent) < 6.0,
        f"AlphabeticBaseline+ascent={p.AlphabeticBaseline + metrics.fAscent:.2f} (应≈0)",
    )

    # ---------- 2. paint 的 y 语义：段落顶部 or 基线 ----------
    path = render_to_png(
        "paint_y_semantics",
        lambda c: p.paint(c, 40, 120),
        400,
        260,
    )
    bbox = ink_bbox(path)
    if bbox is None:
        record("paint y 语义", False, "无墨迹")
    else:
        # y=top 语义：墨迹顶 ≈ 120 + (AlphabeticBaseline - capHeight) > 100
        # y=baseline 语义：墨迹顶 ≈ 120 - capHeight < 100
        ink_top = bbox[1]
        is_top = ink_top > 105
        record(
            "paint y 语义",
            True,
            f"ink_top={ink_top} → paint 的 y 是段落框{'顶部' if is_top else '基线'}",
            critical=False,
        )

    # ---------- 3. 多段共基线拼接（段级 Paragraph 定位方案的核心） ----------
    seg1 = make_paragraph("销售额", [cjk_alias], size_px=size, color=skia.Color(30, 30, 30))
    seg2 = make_paragraph("AV 2024", [latin_alias], size_px=size, color=skia.Color(30, 30, 30))
    seg1.layout(1e9)
    seg2.layout(1e9)
    baseline_y = 150.0

    def paint_segments(canvas: skia.Canvas) -> None:
        seg1.paint(canvas, 40, baseline_y - seg1.AlphabeticBaseline)
        seg2.paint(canvas, 40 + seg1.LongestLine, baseline_y - seg2.AlphabeticBaseline)

    path = render_to_png("segments_one_baseline", paint_segments, 700, 260)
    bbox = ink_bbox(path)
    total = seg1.LongestLine + seg2.LongestLine
    if bbox is None:
        record("多段共基线", False, "无墨迹")
    else:
        width = bbox[2] - bbox[0]
        # 墨迹宽应接近两段 advance 之和（字形墨迹略小于 advance 属正常）
        record(
            "多段共基线",
            0.75 * total < width < total + 10,
            f"advance 合计={total:.1f}, 墨迹宽={width}, bbox={bbox}",
        )

    # ---------- 4. kerning 是否真实生效 ----------
    naive = base_font.measureText("AVAV")
    p_avav = make_paragraph("AVAV", [latin_alias], size_px=size, color=skia.Color(30, 30, 30))
    p_avav.layout(1e9)
    shaped = p_avav.LongestLine
    record(
        "kerning 生效",
        shaped < naive - 0.5,
        f"shaped={shaped:.2f} < naive(逐字和)={naive:.2f}，差={naive - shaped:.2f}px",
    )

    # ---------- 5. 系统逐码点回退 ----------
    rare_cp = 0x20BB7  # 𠮷，CJK 扩展 B，一般字体没有
    pua_cp = 0xE003  # 私有区，系统一般也没有
    rare_tf = mgr.matchFamilyStyleCharacter("", normal, [], rare_cp)
    pua_tf = mgr.matchFamilyStyleCharacter("", normal, [], pua_cp)
    record(
        "matchFamilyStyleCharacter 罕见汉字",
        rare_tf is not None and rare_tf.unicharToGlyph(rare_cp) != 0,
        f"回退字体={rare_tf.getFamilyName() if rare_tf else None}",
    )
    record(
        "matchFamilyStyleCharacter 私有区",
        True,
        f"返回={pua_tf.getFamilyName() if pua_tf else None}（None 或无字形则走自绘豆腐）",
        critical=False,
    )
    record(
        "unicharToGlyph 覆盖检查",
        latin_tf.unicharToGlyph(0x4E00) == 0 and cjk_tf.unicharToGlyph(0x4E00) != 0,
        "Segoe UI 无'一'字形、雅黑有（逐码点解析的前提）",
    )

    # ---------- 6. 确定性 ----------
    def paint_two_builds(canvas: skia.Canvas) -> None:
        pa = make_paragraph("确定 Render", [cjk_alias], size_px=30, color=skia.Color(30, 30, 30))
        pa.layout(1e9)
        pa.paint(canvas, 30, 60 - pa.AlphabeticBaseline)

    path_a = render_to_png("determinism_a", paint_two_builds, 400, 140)
    path_b = render_to_png("determinism_b", paint_two_builds, 400, 140)
    record(
        "绘制确定性",
        path_a.read_bytes() == path_b.read_bytes(),
        "两次独立构建+绘制，PNG 字节一致",
    )

    # ---------- 7. \\n 与空文本（信息项） ----------
    p_nl = make_paragraph("第一行\n第二行", [cjk_alias], size_px=30, color=skia.Color(30, 30, 30))
    p_nl.layout(1e9)
    p_1 = make_paragraph("第一行", [cjk_alias], size_px=30, color=skia.Color(30, 30, 30))
    p_1.layout(1e9)
    record(
        "\\n 换行高度",
        p_nl.Height > 1.6 * p_1.Height,
        f"两行 Height={p_nl.Height:.1f} vs 单行={p_1.Height:.1f}",
        critical=False,
    )

    # ---------- 8. 备选路径 TextBlob.MakeFromShapedText（信息项） ----------
    try:
        blob = skia.TextBlob.MakeFromShapedText("AVAV Shaped 你", skia.Font(cjk_tf, size), True)
        path = render_to_png(
            "make_from_shaped_text",
            lambda c: c.drawTextBlob(
                blob, 20, 100, skia.Paint(AntiAlias=True, Color=skia.Color(30, 30, 30))
            ),
            500,
            180,
        )
        record("TextBlob.MakeFromShapedText", ink_bbox(path) is not None, f"bounds={blob.bounds()}")
    except Exception as exc:  # 探针需要吞掉一切异常并记录
        record("TextBlob.MakeFromShapedText", False, repr(exc), critical=False)

    # ---------- 9. 画布缩放下的绘制（plot 输出密度路径依赖它） ----------
    def paint_scaled(canvas: skia.Canvas) -> None:
        canvas.scale(2.0, 2.0)
        p.paint(canvas, 40, 120)

    path = render_to_png("canvas_scale", paint_scaled, 800, 520)
    bbox = ink_bbox(path)
    unscaled = ink_bbox(OUT_DIR / "paint_y_semantics.png")
    if bbox is None or unscaled is None:
        record("画布 scale 缩放", False, "无墨迹")
    else:
        ratio = (bbox[2] - bbox[0]) / (unscaled[2] - unscaled[0])
        record("画布 scale 缩放", 1.8 < ratio < 2.2, f"2x scale 下墨迹宽比={ratio:.2f}")

    # ---------- 10. 性能对比 ----------
    text = "销售额 1234"
    n = 200
    t0 = time.perf_counter()
    for _ in range(n):
        pq = make_paragraph(text, [cjk_alias], size_px=30, color=skia.Color(30, 30, 30))
        pq.layout(1e9)
    t_new = time.perf_counter() - t0

    surface = skia.Surface(600, 120)
    canvas = surface.getCanvas()
    paint = skia.Paint(AntiAlias=True, Color=skia.Color(30, 30, 30))
    t0 = time.perf_counter()
    for _ in range(n):
        font = skia.Font(cjk_tf, 30)  # 现状：每次绘制重建 Font
        cursor = 0.0
        for ch in text:
            canvas.drawString(ch, cursor, 60, font, paint)
            cursor += font.measureText(ch)
    t_old = time.perf_counter() - t0
    record(
        "性能对比（构建+layout vs 逐字 drawString）",
        True,
        f"新路径 {t_new * 1000 / n:.2f}ms/次 vs 现状路径 {t_old * 1000 / n:.2f}ms/次",
        critical=False,
    )

    print()
    if _failures:
        print(f"共 {len(_failures)} 项关键假设失败: {_failures}")
        return 1
    print("全部关键假设通过：engine.py 走 Paragraph 段级路线。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
