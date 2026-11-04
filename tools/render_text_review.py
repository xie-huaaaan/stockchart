"""文字引擎视觉评审图：混排、字体链、字体文件、豆腐占位、多行、折行省略号、kerning 对比。

输出到 out/plots/text_*.png，配合 tools/render_plot_review.py 的成图供视觉验收。
"""

from __future__ import annotations

from pathlib import Path

from stockchart import bar, draw_text, measure_text
from stockchart.canvas import Canvas

OUT = Path(__file__).resolve().parents[1] / "out" / "plots"

# Courier New：等宽衬线，视觉上与默认楷体链差异明显，适合验证"文件路径字体"
COURIER = Path("C:/Windows/Fonts/couri.ttf")


def main() -> None:
    """渲染全部文字专项评审图。"""
    OUT.mkdir(parents=True, exist_ok=True)

    # 1. 混排字体链：拉丁/数字走 Segoe UI，CJK 回退微软雅黑
    bar(
        [[3, 2], [5, 3], [4, 4]],
        labels=["一季度", "二季度", "三季度"],
        title="销售额 2024 Sales 报告",
        ylabel="金额 amount",
        series_labels=["薄款 sheer", "厚款 thick"],
        value_labels=True,
        font=["Segoe UI", "Microsoft YaHei"],
    ).save(str(OUT / "text_01_mixed_stack.png"))

    # 2. 字体文件路径（Courier New，可明显区分）
    if COURIER.is_file():
        bar(
            {"甲": 2, "乙": 4},
            title="Courier 字体文件渲染",
            font=COURIER,
        ).save(str(OUT / "text_02_font_file.png"))
    else:
        print(f"跳过 text_02：未找到 {COURIER}")

    # 3. 豆腐占位：私有区字符无任何字体可用，应画描边方框而非空白/异常
    bar(
        {"甲": 3, "乙": 2},
        title="缺字占位 \ue003 测试",
        labels=["正常标签", "缺字\ue004标签"],
    ).save(str(OUT / "text_03_tofu.png"))

    # 4. 标题多行（\n）
    bar(
        {"甲": 3, "乙": 5},
        title="第一行主标题\n第二行副标题说明",
    ).save(str(OUT / "text_04_multiline_title.png"))

    # 5. 图例长标签折行 + 超长省略号（第二个标签 100+ 字，三行必然放不下）
    bar(
        {"a": [1, 2], "b": [3, 1]},
        series_labels=[
            "这是一个非常长的系列名称用来测试图例的自动折行行为是否正常工作",
            "故意加长得离谱的第二个系列名称无论如何都放不进三行之内所以末行必须以省略号"
            "收尾这样才能覆盖截断路径的视觉验收而且我们还要继续把这句话写得更长一些"
            "确保远远超过三行的容量上限从而必然触发省略号截断行为供视觉检查确认",
        ],
    ).save(str(OUT / "text_05_legend_wrap.png"))

    # 6. 默认链（楷体/手写风格保持）
    bar({"甲": 3, "乙": 5, "丙": 4}, title="默认字体链风格").save(
        str(OUT / "text_06_default_chain.png")
    )

    # 7. kerning 对比：上行 HarfBuzz 整形、下行逐字绘制（旧行为）
    c = Canvas(760, 240)
    draw_text(c, "上行：整行整形（AVATAR TOYAVA）", 30, 40, size_px=22)
    draw_text(c, "AVATAR TOYAVA", 30, 110, size_px=48, font="Segoe UI")
    text = "AVATAR TOYAVA"
    cursor = 30.0
    for ch in text:  # 逐字绘制模拟旧引擎的无 kerning 间距
        draw_text(c, ch, cursor, 200, size_px=48, font="Segoe UI")
        cursor += measure_text(ch, size_px=48, font="Segoe UI")
    draw_text(c, "下行：逐字绘制（旧行为）", 430, 200, size_px=22)
    c.save(str(OUT / "text_07_kerning.png"))

    print("文字专项评审图已输出到 out/plots/")


if __name__ == "__main__":
    main()
