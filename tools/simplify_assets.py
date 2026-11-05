"""用中等追踪参数重新生成现有 SVG 的色层，保留腿形裁切与编号。

原始母图不可用时，从一份未简化的 SVG 目录重建；不要反复简化上次的输出。
常规素材更新仍使用 split_master.py，两条管线共用同一套追踪参数。

用法：uv run python tools/simplify_assets.py 原始SVG目录
输出：src/stockchart/assets/leg_*.svg，以及 out/svg_simplify/ 中的对照与统计。
"""

from __future__ import annotations

import argparse
import json
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import vtracer
from PIL import Image

from split_master import ASSETS, BACKGROUND, TRACE_OPTIONS, _compose_svg
from stockchart.vector import rasterize_svg

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / "out" / "svg_simplify"
NS = {"svg": "http://www.w3.org/2000/svg"}


def simplify(source: Path, destination: Path) -> dict[str, object]:
    """在 SVG 固有分辨率追踪颜色层，输出保留原 clipPath 的透明 SVG。"""
    svg = source.read_bytes()
    root = ET.fromstring(svg)
    width, height = int(root.attrib["width"]), int(root.attrib["height"])
    clip = root.find("svg:defs/svg:clipPath/svg:path", NS)
    if clip is None:
        raise ValueError(f"{source.name} 缺少腿形裁切路径")
    before = rasterize_svg(svg, width, height)
    image = Image.fromarray(before)
    flat = Image.new("RGB", image.size, BACKGROUND)
    flat.paste(image, mask=image.getchannel("A"))
    input_path = WORK / f"{source.stem}_input.png"
    input_path.parent.mkdir(parents=True, exist_ok=True)
    flat.save(input_path)
    traced = WORK / f"{source.stem}_color.svg"
    vtracer.convert_image_to_svg_py(str(input_path), str(traced), **TRACE_OPTIONS)
    result = _compose_svg(traced.read_text(encoding="utf-8"), clip.attrib["d"], width, height)
    destination.write_text(result, encoding="utf-8")
    after = rasterize_svg(result.encode("utf-8"), width, height)
    Image.fromarray(before).save(WORK / f"{source.stem}_before.png")
    Image.fromarray(after).save(WORK / f"{source.stem}_after.png")
    # 轮廓路径保持不变，但重新追踪的抗锯齿色层可能影响边界 alpha。
    old_mask, new_mask = before[..., 3] > 128, after[..., 3] > 128
    return {
        "id": source.stem,
        "before_bytes": len(svg),
        "after_bytes": len(result.encode("utf-8")),
        "before_paths": len(root.findall(".//svg:path", NS)),
        "after_paths": result.count("<path"),
        "silhouette_iou": float((old_mask & new_mask).sum() / (old_mask | new_mask).sum()),
        "mean_rgb_delta": float(
            np.abs(before[old_mask, :3].astype(np.int16) - after[old_mask, :3]).mean()
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="未简化的 SVG 目录")
    parser.add_argument("--output", type=Path, default=ASSETS, help="输出 SVG 目录")
    args = parser.parse_args()
    if args.source.resolve() == args.output.resolve():
        parser.error("源目录与输出目录须不同，保留未简化的源以便重复生成")
    sources = sorted(args.source.glob("leg_*.svg"))
    if not sources:
        parser.error("源目录中没有 leg_*.svg")
    args.output.mkdir(parents=True, exist_ok=True)
    rows = []
    for source in sources:
        row = simplify(source, args.output / source.name)
        rows.append(row)
        print(json.dumps(row), flush=True)
    (WORK / "metrics.json").write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
