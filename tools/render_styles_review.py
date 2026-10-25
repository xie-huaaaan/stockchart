"""样式评审图生成：为每个内置预设输出单张成品图 + 一张汇总对比图。

用法：uv run python tools/render_styles_review.py
输出：out/styles/<key>.png 与 out/styles_all.png
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from stockchart import STYLES, Leg, LegLibrary, render_stocking

ROOT = Path(__file__).parent.parent
OUT = ROOT / "out"

# 每个预设用哪条腿渲染（循环取用，增加多样性）
LEG_IDS = ["leg_03", "leg_09", "leg_15", "leg_21", "leg_01"]

# 丝袜高度（腿高的比例）
FILL = 0.82

BG = (245, 242, 240, 255)  # 暖白背景


def compose(leg: Leg, key: str, scale: int = 1) -> Image.Image:
    """渲染一条穿袜的腿并放到带标签的画布上。"""
    styled = render_stocking(leg, STYLES[key], int(leg.height * FILL), seed=42)
    img = Image.fromarray(styled.image)
    bg = Image.new("RGBA", img.size, BG)
    bg.alpha_composite(img)
    if scale > 1:
        bg = bg.resize((bg.width * scale, bg.height * scale), Image.LANCZOS)

    label_h = 28
    canvas = Image.new("RGBA", (bg.width, bg.height + label_h), BG)
    canvas.alpha_composite(bg, (0, 0))
    draw = ImageDraw.Draw(canvas)
    draw.text((8, bg.height + 6), key, fill=(60, 55, 50))
    return canvas.convert("RGB")


def main() -> None:
    out_dir = OUT / "styles"
    out_dir.mkdir(parents=True, exist_ok=True)

    lib = LegLibrary(seed=7)
    keys = list(STYLES.keys())

    singles: dict[str, Image.Image] = {}
    for i, key in enumerate(keys):
        leg = lib.get(LEG_IDS[i % len(LEG_IDS)])
        singles[key] = compose(leg, key)
        singles[key].save(out_dir / f"{key}.png")
        print(f"  {key}.png")

    # 汇总对比图：网格排列
    cols = 5
    rows = (len(keys) + cols - 1) // cols
    cell_w = max(im.width for im in singles.values()) + 12
    cell_h = max(im.height for im in singles.values()) + 12
    sheet = Image.new("RGB", (cols * cell_w + 12, rows * cell_h + 12), (230, 228, 225))
    for i, key in enumerate(keys):
        x = 12 + (i % cols) * cell_w
        y = 12 + (i // cols) * cell_h
        sheet.paste(singles[key], (x, y))
    sheet.save(OUT / "styles_all.png")
    print(f"\n{len(keys)} presets → {out_dir}/  +  styles_all.png")


if __name__ == "__main__":
    main()
