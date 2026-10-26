"""把超分母图切分成高密度腿素材，并保留一套 SVG 母图。

母图是用户用 Upscayl 放大后的拼版（若干行、每行若干对腿），腿的顺序与库内编号
无关，靠形状匹配（归一化 alpha 掩膜的 IoU）自动认领编号。AI 超分会带来轻微的
尺寸漂移，因此每条腿都按**设计尺寸 × 密度**重新拉伸，保证布局、间距、足底锚点
与原有素材一致。

默认流程是"裁剪 → 追踪为 SVG 母图 → 按目标密度栅格化"：SVG 用母图原分辨率
追踪，viewBox 保持裁剪坐标，width/height 写成设计尺寸 × SVG_SCALE，并用
preserveAspectRatio="none" 完成设计长宽比拉伸。这样 SVG 本身就是可再次
栅格化的母图，目标密度只影响输出 PNG。alpha 取母图裁剪的 alpha（与追踪内容
同源，避免旧轮廓裁掉母图外描边）。

用法：
    uv run python tools/split_master.py dist/all_up_1.png --density 2
    uv run python tools/split_master.py dist/all_up_1.png --no-svg  # 只做位图缩放

输出：src/stockchart/assets/leg_XX@Nx.png、dist/leg_svg/leg_XX.svg，
      并把结果并入 legs_hires.json。母图里缺的腿保持原有条目不动。
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import cairosvg
import numpy as np
import vtracer
from PIL import Image
from scipy import ndimage
from scipy.optimize import linear_sum_assignment

# 用户的超分母图本来就有上亿像素，超过 Pillow 的默认防炸限制
Image.MAX_IMAGE_PIXELS = None

ROOT = Path(__file__).parent.parent
ASSETS = ROOT / "src" / "stockchart" / "assets"
SIG = 64  # 形状匹配用的归一化掩膜尺寸
BACKGROUND = (250, 248, 243)  # 追踪需要不透明输入，用画纸色垫底
SVG_SCALE = 4.0  # SVG 母图的设计倍率，与输出密度无关
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


def _match(
    boxes: list[tuple[int, int, int, int]], im: Image.Image, meta: list[dict[str, object]]
) -> dict[int, str]:
    """母图腿 → 库内编号（一对一的最优匹配）。"""
    a = np.asarray(im.convert("RGBA"))[:, :, 3] > 128
    sigs = [_signature(a[y0:y1, x0:x1]) for x0, y0, x1, y1 in boxes]
    lib_sigs: list[np.ndarray] = []
    for e in meta:
        with Image.open(ASSETS / f"{e['leg_id']}.png") as src:
            r = np.asarray(src.convert("RGBA"))
        m = r[:, :, 3] > 128
        ys, xs = np.where(m)
        lib_sigs.append(_signature(m[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1]))

    iou = np.zeros((len(sigs), len(lib_sigs)), np.float32)
    for i, s in enumerate(sigs):
        for j, t in enumerate(lib_sigs):
            iou[i, j] = np.minimum(s, t).sum() / max(np.maximum(s, t).sum(), 1e-6)
    rows, cols = linear_sum_assignment(-iou)
    return {int(i): str(meta[int(j)]["leg_id"]) for i, j in zip(rows, cols, strict=True)}


def _stretch_svg(svg_path: Path, crop_size: tuple[int, int], design_size: tuple[int, int]) -> None:
    """把 SVG 的显示尺寸改成设计空间，通过 viewBox 拉伸到设计长宽比。"""
    text = svg_path.read_text(encoding="utf-8")
    m = re.search(r"<svg[^>]*>", text)
    if m is None:
        raise ValueError(f"{svg_path} 不是合法的 SVG")
    w_out = round(design_size[0] * SVG_SCALE)
    h_out = round(design_size[1] * SVG_SCALE)
    tag = (
        '<svg version="1.1" xmlns="http://www.w3.org/2000/svg" '
        f'width="{w_out}" height="{h_out}" '
        f'viewBox="0 0 {crop_size[0]} {crop_size[1]}" preserveAspectRatio="none">'
    )
    svg_path.write_text(text[: m.start()] + tag + text[m.end() :], encoding="utf-8")


def _ink(im: Image.Image) -> float:
    """墨量：线越密越深越大，用于和原素材比对线宽。"""
    a = np.asarray(im.convert("RGBA")).astype(np.float32)
    mask = a[:, :, 3] > 128
    lum = 0.299 * a[:, :, 0] + 0.587 * a[:, :, 1] + 0.114 * a[:, :, 2]
    return float(((238 - lum) / (238 - 156)).clip(0, 1)[mask].mean())


def _trace(crop: Image.Image, svg_path: Path, design_size: tuple[int, int]) -> None:
    """把母图裁剪追踪成设计空间的 SVG 母图。"""
    flat = Image.new("RGB", crop.size, BACKGROUND)
    flat.paste(crop, (0, 0), crop)
    flat_path = svg_path.with_suffix(".flat.png")
    flat.save(flat_path)
    try:
        vtracer.convert_image_to_svg_py(str(flat_path), str(svg_path), **TRACE_OPTIONS)
    finally:
        flat_path.unlink(missing_ok=True)
    _stretch_svg(svg_path, crop.size, design_size)


def main() -> None:
    parser = argparse.ArgumentParser(description="切分超分母图并替换高密度素材")
    parser.add_argument("master", help="超分母图路径，如 dist/all_up_1.png")
    parser.add_argument("--density", type=int, default=2, help="输出密度（像素/设计像素）")
    parser.add_argument("--svg-dir", default="dist/leg_svg", help="SVG 母图输出目录")
    parser.add_argument(
        "--no-svg", action="store_true", help="跳过矢量化，直接把裁剪缩放到目标尺寸"
    )
    args = parser.parse_args()

    im = Image.open(args.master).convert("RGBA")
    meta: list[dict[str, object]] = json.loads((ASSETS / "legs.json").read_text(encoding="utf-8"))
    by_id = {str(e["leg_id"]): e for e in meta}
    svg_dir = None if args.no_svg else Path(args.svg_dir)
    if svg_dir is not None:
        svg_dir.mkdir(parents=True, exist_ok=True)

    boxes = _components(im)
    mapping = _match(boxes, im, meta)
    missing = sorted(set(by_id) - set(mapping.values()))
    print(f"母图腿数 {len(boxes)}，匹配 {len(mapping)}，库内未出现的腿：{missing or '无'}")

    entries: dict[str, dict[str, float]] = {}
    for i, leg_id in sorted(mapping.items(), key=lambda kv: kv[1]):
        x0, y0, x1, y1 = boxes[i]
        entry = by_id[leg_id]
        w, h = int(entry["width"]), int(entry["height"])
        w_out, h_out = w * args.density, h * args.density
        crop = im.crop((x0, y0, x1, y1))
        dest = ASSETS / f"{leg_id}@{args.density}x.png"

        if svg_dir is None:
            crop.resize((w_out, h_out), Image.Resampling.LANCZOS).save(dest, optimize=True)
            svg_note = "位图"
        else:
            svg_path = svg_dir / f"{leg_id}.svg"
            _trace(crop, svg_path, (w, h))
            tmp_png = svg_dir / f"{leg_id}.tmp.png"
            cairosvg.svg2png(
                url=str(svg_path),
                write_to=str(tmp_png),
                output_width=w_out,
                output_height=h_out,
            )
            with Image.open(tmp_png) as raster:
                if raster.size != (w_out, h_out):
                    raise RuntimeError(f"{leg_id}: SVG 栅格化尺寸 {raster.size} ≠ {(w_out, h_out)}")
                if raster.mode == "RGBA" and raster.getchannel("A").getextrema()[0] < 255:
                    raise RuntimeError(f"{leg_id}: SVG 栅格化后仍有透明像素")
                rgb = raster.convert("RGB")
            alpha = crop.getchannel("A").resize((w_out, h_out), Image.Resampling.LANCZOS)
            out = rgb.convert("RGBA")
            out.putalpha(alpha)
            out.save(dest, optimize=True)
            tmp_png.unlink(missing_ok=True)
            svg_note = f"SVG {svg_path.stat().st_size // 1024}KB"

        with Image.open(dest) as saved:
            got = np.asarray(saved.convert("RGBA").resize((w, h), Image.Resampling.LANCZOS))
            ink_ratio = _ink(saved.resize((w, h), Image.Resampling.LANCZOS))
        got_a = got[:, :, 3] > 128
        with Image.open(ASSETS / f"{leg_id}.png") as src:
            ref = np.asarray(src.convert("RGBA"))
            ink_ref = _ink(src)
        ref_a = ref[:, :, 3] > 128
        iou = np.minimum(got_a, ref_a).sum() / np.maximum(got_a, ref_a).sum()
        ink_ratio /= ink_ref
        entries[leg_id] = {
            "density": float(args.density),
            "out_width": float(w_out),
            "out_height": float(h_out),
        }
        print(
            f"  {leg_id}  {x1 - x0}x{y1 - y0} → {w_out}x{h_out}  {svg_note}  "
            f"轮廓IoU={iou:.3f}  墨量={ink_ratio:.0%}  {dest.stat().st_size // 1024}KB"
        )

    meta_path = ASSETS / "legs_hires.json"
    existing: dict[str, dict[str, float]] = {}
    if meta_path.exists():
        existing = json.loads(meta_path.read_text(encoding="utf-8"))
    existing.update(entries)
    meta_path.write_text(
        json.dumps(existing, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"元数据 → {meta_path.name}（{len(existing)} 条，其中本次 {len(entries)} 条）")
    if svg_dir is not None:
        print(f"SVG 母图 → {svg_dir}（{len(entries)} 个）")


if __name__ == "__main__":
    main()
