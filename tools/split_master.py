"""把超分母图切分成内置矢量腿素材（透明 SVG）。

母图是用户用 Upscayl 放大后的拼版（若干行、每行若干对腿），腿的顺序与库内编号
无关，靠形状匹配（归一化 alpha 掩膜的 IoU）自动认领编号。AI 超分会带来轻微的
尺寸漂移，因此每条腿先拉伸到**设计尺寸 × 4**再追踪，保证布局、间距、足底锚点
与设计坐标一致。

vtracer 需要不透明输入，它的 stacked 输出会先铺一块满画布底色，所以追踪结果本身
不带透明背景。这里用腿身可见轮廓（蓝色通道低于纸底）生成 `<clipPath>`，把追踪
内容裁成腿形；alpha 的半透明软边不会变成不透明浅边。SVG 因此是透明的，可作为
唯一素材存进库，调用时按目标高度栅格化。

用法：
    uv run python tools/split_master.py dist/all_up_1.png
    uv run python tools/split_master.py dist/all_up_1.png --only leg_01

输出：src/stockchart/assets/leg_XX.svg（26 个）以及 out/preview_svg.png 预览图。
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import numpy as np
import vtracer
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage
from scipy.optimize import linear_sum_assignment

from stockchart.vector import rasterize_svg

# 用户的超分母图本来就有上亿像素，超过 Pillow 的默认防炸限制
Image.MAX_IMAGE_PIXELS = None

ROOT = Path(__file__).parent.parent
ASSETS = ROOT / "src" / "stockchart" / "assets"
WORK = ROOT / "out" / "svg_trace"
SIG = 64  # 形状匹配用的归一化掩膜尺寸
BACKGROUND = (250, 248, 243)  # 追踪需要不透明输入，用画纸色垫底
SVG_SCALE = 4  # SVG 素材的固有倍率（设计像素 × 4）
CLIP_BLUE = 242  # 腿形裁切：蓝色通道低于此值才是腿身；纸底/白色软边都会被排除
ROW_DIR = ROOT / "dist"  # 720p 原始行图（row1~3.png）所在目录

# 母图左右边缘截断了这两对腿，回退到 720p 行图重新追踪。
# 坐标是旧版 720p 素材的出处，只属于素材管线，不进运行时元数据。
FALLBACK_CROPS: dict[str, tuple[int, int, int]] = {
    "leg_07": (2, 0, 179),
    "leg_08": (2, 189, 362),
    "leg_15": (2, 3091, 3267),
    "leg_16": (2, 3271, 3430),
}
TRACE_OPTIONS: dict[str, object] = {
    "colormode": "color",
    "hierarchical": "stacked",
    "mode": "spline",
    "filter_speckle": 4,
    "color_precision": 8,
    "layer_difference": 8,
    "corner_threshold": 60,
    "length_threshold": 2.0,
    "max_iterations": 10,
    "splice_threshold": 45,
    "path_precision": 2,
}


def _components(im: Image.Image) -> list[tuple[int, int, int, int]]:
    """按 alpha 连通域找出每一条腿的包围盒，按行带、再按 x 排序。"""
    a = np.asarray(im.convert("RGBA"))[:, :, 3] > 128
    lab, _ = ndimage.label(a)
    boxes: list[tuple[int, int, int, int]] = []
    for sl in ndimage.find_objects(lab):
        if sl is None:
            continue
        x0, y0 = sl[1].start, sl[0].start
        w, h = sl[1].stop - x0, sl[0].stop - y0
        if w > 40 and h > 40:
            boxes.append((x0, y0, x0 + w, y0 + h))
    boxes.sort(key=lambda b: (b[1] // 1000, b[0]))
    return boxes


def _signature(mask: np.ndarray) -> np.ndarray:
    img = Image.fromarray((mask * 255).astype(np.uint8)).resize(
        (SIG, SIG), Image.Resampling.LANCZOS
    )
    return np.asarray(img).astype(np.float32) / 255.0


def _reference_alpha(leg_id: str, width: int, height: int) -> np.ndarray:
    """库内现成素材的 alpha 掩膜；优先 SVG，迁移期回退到 PNG。"""
    svg_path = ASSETS / f"{leg_id}.svg"
    if svg_path.is_file():
        return rasterize_svg(svg_path.read_bytes(), width, height)[:, :, 3] > 128
    with Image.open(ASSETS / f"{leg_id}.png") as src:
        return np.asarray(src.convert("RGBA"))[:, :, 3] > 128


def _match(
    boxes: list[tuple[int, int, int, int]], im: Image.Image, meta: list[dict[str, object]]
) -> dict[int, str]:
    """母图腿 → 库内编号（一对一的最优匹配）。"""
    a = np.asarray(im.convert("RGBA"))[:, :, 3] > 128
    sigs = [_signature(a[y0:y1, x0:x1]) for x0, y0, x1, y1 in boxes]
    lib_sigs: list[np.ndarray] = []
    for e in meta:
        m = _reference_alpha(str(e["leg_id"]), int(e["width"]), int(e["height"]))
        ys, xs = np.where(m)
        lib_sigs.append(_signature(m[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1]))

    iou = np.zeros((len(sigs), len(lib_sigs)), np.float32)
    for i, s in enumerate(sigs):
        for j, t in enumerate(lib_sigs):
            iou[i, j] = np.minimum(s, t).sum() / max(np.maximum(s, t).sum(), 1e-6)
    rows, cols = linear_sum_assignment(-iou)
    return {int(i): str(meta[int(j)]["leg_id"]) for i, j in zip(rows, cols, strict=True)}


def _clip_polygon(norm: Image.Image, *, step: int = 2) -> str:
    """由腿身颜色生成逐行左右边界的闭合多边形（SVG path 的 d）。

    不用 alpha：母图 alpha 的外缘有一圈半透明软边，二值化后会把纸色带成不透明
    浅边；腿身蓝色通道明显低于纸底色，用颜色边界裁切更贴近可见轮廓。
    """
    b = np.asarray(norm.convert("RGB"))[:, :, 2]
    mask = ndimage.binary_fill_holes(b < CLIP_BLUE)
    lab, n = ndimage.label(mask)
    if n == 0:
        raise ValueError("没有找到腿身")
    sizes = ndimage.sum(mask, lab, range(1, n + 1))
    a = lab == (1 + int(np.argmax(sizes)))
    _, w = a.shape
    ys = np.where(a.any(axis=1))[0]
    left = np.array([np.argmax(a[y]) for y in ys], dtype=np.float64)
    right = np.array([w - 1 - np.argmax(a[y][::-1]) for y in ys], dtype=np.float64)

    def smooth(v: np.ndarray) -> np.ndarray:
        k = np.ones(7) / 7
        return np.convolve(np.pad(v, 3, mode="edge"), k, mode="valid")

    left, right = smooth(left), smooth(right)
    right = np.maximum(right, left)
    idx = list(range(0, len(ys), step))
    if idx[-1] != len(ys) - 1:
        idx.append(len(ys) - 1)
    pts = [(left[i], ys[i]) for i in idx] + [(right[i], ys[i]) for i in reversed(idx)]
    return "M " + " L ".join(f"{x:.1f} {y:.1f}" for x, y in pts) + " Z"


def _compose_svg(color_text: str, clip_d: str, w: int, h: int) -> str:
    """把彩色追踪结果包进腿形 clipPath，得到透明 SVG。"""
    paths = re.findall(r"<path[^>]*>", color_text)
    if not paths:
        raise ValueError("追踪结果没有 path")
    return (
        '<svg version="1.1" xmlns="http://www.w3.org/2000/svg" '
        f'width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
        '<defs><clipPath id="legclip" clipPathUnits="userSpaceOnUse">'
        f'<path d="{clip_d}"/></clipPath></defs>'
        '<g clip-path="url(#legclip)">' + "".join(paths) + "</g></svg>"
    )


def _original_crop(leg_id: str, height: int, rows: dict[int, Image.Image]) -> Image.Image:
    """从 720p 原始行图裁出整条腿；母图贴边、腿形被截断时用它兜底。"""
    try:
        row, x0, x1 = FALLBACK_CROPS[leg_id]
    except KeyError:
        raise ValueError(f"{leg_id} 没有 720p 兜底坐标") from None
    if row not in rows:
        path = ROW_DIR / f"row{row}.png"
        if not path.is_file():
            raise FileNotFoundError(f"缺少 720p 兜底素材 {path}")
        with Image.open(path) as source:
            rows[row] = source.convert("RGBA")
    return rows[row].crop((x0, 0, x1, height))


def _ink(im: Image.Image) -> float:
    """墨量：线越密越深越大，用于和原素材比对线宽。"""
    a = np.asarray(im.convert("RGBA")).astype(np.float32)
    mask = a[:, :, 3] > 128
    lum = 0.299 * a[:, :, 0] + 0.587 * a[:, :, 1] + 0.114 * a[:, :, 2]
    return float(((238 - lum) / (238 - 156)).clip(0, 1)[mask].mean())


def _preview(legs: list[tuple[str, str, Image.Image]], out_path: Path) -> None:
    """带编号与配对标签的预览图，供人工核对。"""
    scale = 0.5
    pad, pair_gap, top, bottom = 12, 26, 20, 18
    try:
        font = ImageFont.truetype("arial.ttf", 13)
    except OSError:
        font = ImageFont.load_default()
    meta = {e["leg_id"]: e for e in json.loads((ASSETS / "legs.json").read_text(encoding="utf-8"))}
    bands = [
        [legs[i : i + 2] for i in range(0, 6, 2)],
        [legs[i : i + 2] for i in range(6, 16, 2)],
        [legs[i : i + 2] for i in range(16, 26, 2)],
    ]
    th = round(720 * scale)
    row_h = top + th + bottom + pad
    widths = []
    for pairs in bands:
        w = pad
        for pair in pairs:
            w += (
                sum(round(im.width * scale) for _, _, im in pair) + pad * (len(pair) - 1) + pair_gap
            )
        widths.append(w)
    canvas = Image.new("RGB", (max(widths) + pad, row_h * len(bands) + pad), BACKGROUND)
    draw = ImageDraw.Draw(canvas)
    y = pad
    for pairs in bands:
        x = pad
        for pair in pairs:
            pw = sum(round(im.width * scale) for _, _, im in pair) + pad * (len(pair) - 1)
            pair_id = str(meta[pair[0][0]]["pair_id"])
            draw.text((x + pw // 2 - 18, y), pair_id, fill=(150, 110, 110), font=font)
            xx = x
            for lid, side, im in pair:
                tw = round(im.width * scale)
                thumb = im.resize((tw, th), Image.Resampling.LANCZOS)
                canvas.paste(thumb, (xx, y + top), thumb)
                label = f"{lid} {side[0].upper()}"
                draw.text(
                    (xx + (tw - draw.textlength(label, font=font)) // 2, y + top + th + 3),
                    label,
                    fill=(70, 70, 70),
                    font=font,
                )
                xx += tw + pad
            x += pw + pair_gap
        y += row_h
    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="切分超分母图并生成透明 SVG 素材")
    parser.add_argument("master", help="超分母图路径，如 dist/all_up_1.png")
    parser.add_argument("--only", default=None, help="只处理某条腿，如 leg_01")
    args = parser.parse_args()

    WORK.mkdir(parents=True, exist_ok=True)
    im = Image.open(args.master).convert("RGBA")
    meta: list[dict[str, object]] = json.loads((ASSETS / "legs.json").read_text(encoding="utf-8"))
    by_id = {str(e["leg_id"]): e for e in meta}

    boxes = _components(im)
    mapping = _match(boxes, im, meta)
    missing = sorted(set(by_id) - set(mapping.values()))
    print(f"母图腿数 {len(boxes)}，匹配 {len(mapping)}，库内未出现的腿：{missing or '无'}")

    # 左右贴边的腿可能被截断（如 leg_07 左侧）；同一对一起回退到 720p 原始行图。
    # 兜底坐标在 FALLBACK_CROPS 中，行图从 dist/ 读取。
    # 上下贴边不判断：腿本来就在大腿/脚踝处切断，不是母图裁切。
    clipped_pairs = {
        str(by_id[leg_id]["pair_id"])
        for i, leg_id in mapping.items()
        if boxes[i][0] <= 2 or boxes[i][2] >= im.width - 2
    }
    if clipped_pairs:
        print(f"母图贴边，改用原始 720p：{', '.join(sorted(clipped_pairs))}")
    rows: dict[int, Image.Image] = {}

    preview_items: list[tuple[str, str, Image.Image]] = []
    for i, leg_id in sorted(mapping.items(), key=lambda kv: kv[1]):
        if args.only and leg_id != args.only:
            continue
        x0, y0, x1, y1 = boxes[i]
        entry = by_id[leg_id]
        w, h = int(entry["width"]), int(entry["height"])
        w4, h4 = w * SVG_SCALE, h * SVG_SCALE
        from_row = str(entry["pair_id"]) in clipped_pairs
        if from_row and leg_id not in FALLBACK_CROPS:
            print(f"  {leg_id} 贴边但没有 720p 兜底坐标，仍用母图裁切")
            from_row = False
        crop = _original_crop(leg_id, h, rows) if from_row else im.crop((x0, y0, x1, y1))

        # 追踪输入：垫画纸色、拉伸到设计尺寸 × 4
        flat = Image.new("RGB", crop.size, BACKGROUND)
        flat.paste(crop, (0, 0), crop)
        norm = flat.resize((w4, h4), Image.Resampling.LANCZOS)
        norm_png = WORK / f"{leg_id}_norm.png"
        norm.save(norm_png)
        color_svg = WORK / f"{leg_id}_color.svg"
        vtracer.convert_image_to_svg_py(str(norm_png), str(color_svg), **TRACE_OPTIONS)

        # 透明背景：腿身的可见轮廓
        svg_text = _compose_svg(
            color_svg.read_text(encoding="utf-8"),
            _clip_polygon(norm),
            w4,
            h4,
        )
        dest = ASSETS / f"{leg_id}.svg"
        dest.write_text(svg_text, encoding="utf-8")

        # 自检：按 2 倍目标高度栅格化，对比轮廓与墨量
        rendered = rasterize_svg(svg_text.encode("utf-8"), w * 2, h * 2)
        got = rendered[:, :, 3] > 128
        ref = (
            np.asarray(crop.getchannel("A").resize((w * 2, h * 2), Image.Resampling.LANCZOS)) > 128
        )
        iou = np.minimum(got, ref).sum() / np.maximum(got, ref).sum()
        ink_note = ""
        old_png = ASSETS / f"{leg_id}.png"
        if old_png.is_file():
            with Image.open(old_png) as old:
                small = Image.fromarray(rendered).resize((w, h), Image.Resampling.LANCZOS)
                ink_note = f"  墨量={_ink(small) / _ink(old):.0%}"
        print(
            f"  {leg_id}  {x1 - x0}x{y1 - y0} → {w4}x{h4}  "
            f"SVG {dest.stat().st_size // 1024}KB  轮廓IoU={iou:.3f}{ink_note}"
            f"{'  原始720p' if from_row else ''}"
        )
        if not args.only:
            preview_items.append(
                (
                    leg_id,
                    "left" if entry["side"] == "left" else "right",
                    Image.fromarray(rendered),
                )
            )

    if not args.only and len(preview_items) == len(meta):
        preview_items.sort(key=lambda item: item[0])
        _preview(preview_items, ROOT / "out" / "preview_svg.png")
        print("预览图 → out/preview_svg.png")
    print(f"SVG 素材 → {ASSETS}（{len(mapping) if not args.only else 1} 个）")


if __name__ == "__main__":
    main()
