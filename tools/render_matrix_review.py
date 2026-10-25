"""矩阵评审图：所有袜身种类 × 所有上沿的完整组合。

5 种 Fabric（Plain/Striped/Ribbed/Fishnet/Dotted）× 4 种 TopEdge（Bare/Welt/Lace/Fade），
共 20 格。行标签为袜身，列标签为上沿。

用法：uv run python tools/render_matrix_review.py
输出：out/matrix/<fabric>__<top>.png（20 张）与 out/matrix_all.png（带行列标签的总表）
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from stockchart import (
    Bare,
    Dotted,
    Fade,
    Fishnet,
    Lace,
    LegLibrary,
    Plain,
    Ribbed,
    Shading,
    StockingStyle,
    Striped,
    Stripe,
    Welt,
    render_stocking,
)

ROOT = Path(__file__).parent.parent
OUT = ROOT / "out"

FILL = 0.82
BG = (245, 242, 240, 255)
LEG_ID = "leg_03"  # 全表用同一条腿，突出样式本身的差异

# 每种 Fabric 一个代表参数化
FABRICS: dict[str, object] = {
    "plain_black": Plain(color=(28, 26, 30), opacity=0.55),
    "stripe_blue": Striped(stripes=(
        Stripe(color=(255, 255, 255), width=8),
        Stripe(color=(70, 110, 200), width=8),
    )),
    "ribbed_cream": Ribbed(color=(240, 232, 215)),
    "fishnet": Fishnet(color=(20, 18, 22)),
    "dotted_polka": Dotted(
        base=Plain(color=(28, 26, 30), opacity=0.55),
        color=(10, 10, 12),
        shape="dot",
    ),
}

TOPS: dict[str, object] = {
    "bare": Bare(),
    "welt": Welt(),
    "lace": Lace(),
    "fade": Fade(),
}


def main() -> None:
    out_dir = OUT / "matrix"
    out_dir.mkdir(parents=True, exist_ok=True)

    lib = LegLibrary(seed=7)
    leg = lib.get(LEG_ID)
    height_px = int(leg.height * FILL)

    label_w, label_h = 110, 26
    pad = 6

    cells: dict[tuple[str, str], Image.Image] = {}
    for fkey, fabric in FABRICS.items():
        for tkey, top in TOPS.items():
            style = StockingStyle(fabric=fabric, top=top)  # type: ignore[arg-type]
            styled = render_stocking(leg, style, height_px, seed=42)
            img = Image.fromarray(styled.image)
            bg = Image.new("RGBA", img.size, BG)
            bg.alpha_composite(img)
            cell = bg.convert("RGB")
            cells[(fkey, tkey)] = cell
            cell.save(out_dir / f"{fkey}__{tkey}.png")

    # 总表：首列为 Fabric 标签，首行为 TopEdge 标签
    cell_w = max(im.width for im in cells.values())
    cell_h = max(im.height for im in cells.values())
    n_f, n_t = len(FABRICS), len(TOPS)
    sheet = Image.new(
        "RGB",
        (label_w + n_t * (cell_w + pad) + pad, label_h + n_f * (cell_h + pad) + pad),
        (225, 222, 218),
    )
    draw = ImageDraw.Draw(sheet)
    for j, tkey in enumerate(TOPS):
        draw.text(
            (label_w + j * (cell_w + pad) + cell_w // 2 - 10, 4),
            tkey,
            fill=(50, 45, 40),
        )
    for i, fkey in enumerate(FABRICS):
        y = label_h + i * (cell_h + pad)
        draw.text((6, y + cell_h // 2 - 6), fkey, fill=(50, 45, 40))
        for j, tkey in enumerate(TOPS):
            x = label_w + j * (cell_w + pad)
            sheet.paste(cells[(fkey, tkey)], (x, y))

    sheet.save(OUT / "matrix_all.png")
    print(f"{len(cells)} combinations → {out_dir}/  +  matrix_all.png")


if __name__ == "__main__":
    main()
