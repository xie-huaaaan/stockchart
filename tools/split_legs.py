"""720p 原始素材切分脚本：从 assets/row1~3.png 提取各条腿，供参考与兜底。

库内素材现在是透明 SVG（`tools/split_master.py` 生成），本脚本只产出设计尺寸
位图参考，不再写进 `src/stockchart/assets/`；输出 JSON 的字段与运行时
`legs.json` 一致（不含出处的 720p 坐标）。

用法：uv run python tools/split_legs.py
输出：
  assets/legs_720/leg_01.png … leg_26.png
  assets/legs_720/legs.json
  out/preview_720.png  （带编号的预览图，供人工核对）
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

ROOT = Path(__file__).parent.parent
ASSETS_SRC = ROOT / "assets"
ASSETS_DST = ROOT / "assets" / "legs_720"

# 按面积过滤杂点的阈值（像素面积）
MIN_AREA = 2000

# 腿图像的标准高度（所有行都是这个高度）
LEG_HEIGHT = 720

# 足底估计用的行数（从底部往上）
FOOT_ROWS = 20

# 来源文件及其行号
SOURCE_FILES: list[tuple[str, int]] = [
    ("row1.png", 1),
    ("row2.png", 2),
    ("row3.png", 3),
]


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------


def extract_legs(png_path: Path, row: int) -> list[dict]:  # type: ignore[type-arg]
    """从一张行图中提取所有腿，返回元数据列表（不含编号）。"""
    img = np.asarray(Image.open(png_path).convert("RGBA"))
    alpha = img[..., 3]

    # 连通域标记，过滤杂点
    labeled, n = ndimage.label(alpha > 0)
    objects = ndimage.find_objects(labeled)
    areas = ndimage.sum(np.ones_like(labeled), labeled, range(1, n + 1))

    legs: list[dict] = []  # type: ignore[type-arg]
    for sl, area in zip(objects, areas, strict=True):
        if area < MIN_AREA:
            continue
        x0, x1 = sl[1].start, sl[1].stop
        # 裁出这条腿（全高，仅裁 x 方向）
        crop = img[:, x0:x1, :].copy()
        H, W = crop.shape[:2]

        # 足底中心：用底部 FOOT_ROWS 行的 alpha 质心
        bot_alpha = crop[H - FOOT_ROWS :, :, 3].astype(float)
        col_sum = bot_alpha.sum(0)
        total = col_sum.sum()
        if total < 1:
            foot_center_x = W // 2
        else:
            xs = np.arange(W, dtype=float)
            foot_center_x = int((col_sum * xs).sum() / total)

        legs.append(
            {
                "image": crop,
                "width": W,
                "height": H,
                "foot_center_x": foot_center_x,
                "src_row": row,
                "src_x0": x0,
            }
        )

    # 按 x 位置排序（从左到右）
    legs.sort(key=lambda d: d["src_x0"])
    return legs


def assign_pairs(legs: list[dict]) -> list[dict]:  # type: ignore[type-arg]
    """相邻两两配对：奇数索引为左腿，偶数索引为右腿（0-based：0=左，1=右，2=左…）。"""
    for i, leg in enumerate(legs):
        pair_idx = i // 2 + 1  # 1-based 配对号（相对于本行）
        leg["local_pair"] = pair_idx
        leg["side"] = "left" if i % 2 == 0 else "right"
    return legs


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------


def main() -> None:
    ASSETS_DST.mkdir(parents=True, exist_ok=True)

    all_legs: list[dict] = []  # type: ignore[type-arg]

    for fname, row in SOURCE_FILES:
        src_path = ASSETS_SRC / fname
        if not src_path.exists():
            print(f"[skip] {src_path} not found")
            continue
        legs = extract_legs(src_path, row)
        legs = assign_pairs(legs)
        all_legs.extend(legs)
        print(f"{fname}: {len(legs)} legs extracted")

    # 全局编号（leg_01 … leg_26）；配对编号在全局重新计算
    # 按 row 顺序、row 内 x 顺序排列
    all_legs.sort(key=lambda d: (d["src_row"], d["src_x0"]))

    metadata: list[dict] = []  # type: ignore[type-arg]
    for global_idx, leg in enumerate(all_legs):
        leg_id = f"leg_{global_idx + 1:02d}"
        # 同一 src_row 内相邻两两配对 → 按 local_pair 和 src_row 确定 global pair_id
        # 用 (src_row, local_pair) 唯一确定一对
        pair_key = (leg["src_row"], leg["local_pair"])
        # 首次见到这个 pair_key 就分配新的 global_pair
        if not hasattr(main, "_pair_map"):
            main._pair_map = {}  # type: ignore[attr-defined]
        if pair_key not in main._pair_map:  # type: ignore[attr-defined]
            main._pair_map[pair_key] = f"pair_{len(main._pair_map) + 1:02d}"  # type: ignore[attr-defined]
        pair_id = main._pair_map[pair_key]  # type: ignore[attr-defined]

        # 保存 PNG
        out_png = ASSETS_DST / f"{leg_id}.png"
        Image.fromarray(leg["image"]).save(out_png)

        metadata.append(
            {
                "leg_id": leg_id,
                "pair_id": pair_id,
                "side": leg["side"],
                "width": leg["width"],
                "height": leg["height"],
                "foot_center_x": leg["foot_center_x"],
            }
        )
        print(
            f"  {leg_id}  {pair_id}  {leg['side']:<5}  w={leg['width']}  "
            f"foot_cx={leg['foot_center_x']}"
        )

    # 写 JSON
    json_path = ASSETS_DST / "legs.json"
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)
    print(f"\nMetadata written → {json_path}  ({len(metadata)} legs)")

    # 预览图
    _make_preview(all_legs, metadata, ROOT / "out" / "preview_720.png")


def _make_preview(
    all_legs: list[dict],  # type: ignore[type-arg]
    metadata: list[dict],  # type: ignore[type-arg]
    out_path: Path,
) -> None:
    """生成带编号和配对色块的预览图，供人工核对。"""
    n = len(all_legs)
    if n == 0:
        return

    thumb_h = 200
    thumb_w = 80
    pad = 8
    cols = min(n, 13)
    rows = (n + cols - 1) // cols
    canvas_w = cols * (thumb_w + pad) + pad
    canvas_h = rows * (thumb_h + 40 + pad) + pad
    canvas = Image.new("RGBA", (canvas_w, canvas_h), (240, 240, 240, 255))
    draw = ImageDraw.Draw(canvas)

    pair_colors: dict[str, tuple[int, int, int]] = {}
    palette = [
        (200, 120, 120),
        (120, 180, 120),
        (120, 140, 200),
        (200, 170, 100),
        (160, 120, 200),
        (100, 190, 200),
        (200, 140, 180),
        (150, 200, 130),
        (180, 160, 100),
        (100, 150, 180),
        (210, 130, 100),
        (130, 200, 170),
        (170, 130, 210),
    ]

    for i, (leg, meta) in enumerate(zip(all_legs, metadata, strict=True)):
        col = i % cols
        ry = i // cols
        x0 = pad + col * (thumb_w + pad)
        y0 = pad + ry * (thumb_h + 40 + pad)

        pair_id = meta["pair_id"]
        if pair_id not in pair_colors:
            pair_colors[pair_id] = palette[len(pair_colors) % len(palette)]
        pc = pair_colors[pair_id]

        # 配对底色
        draw.rectangle([x0, y0, x0 + thumb_w, y0 + thumb_h + 38], fill=(*pc, 60))

        # 缩略腿图
        img = Image.fromarray(leg["image"])
        img.thumbnail((thumb_w, thumb_h))
        bg = Image.new("RGBA", img.size, (240, 240, 240, 255))
        bg.alpha_composite(img)
        canvas.paste(bg, (x0 + (thumb_w - img.width) // 2, y0))

        # 标注
        draw.text(
            (x0 + 2, y0 + thumb_h + 2),
            meta["leg_id"],
            fill=(40, 40, 40),
        )
        draw.text(
            (x0 + 2, y0 + thumb_h + 18),
            f"{meta['pair_id']} {meta['side'][0].upper()}",
            fill=(80, 40, 40),
        )

    canvas.convert("RGB").save(out_path)
    print(f"Preview  → {out_path}")


if __name__ == "__main__":
    main()
