"""记录纹理优化的原尺寸样张与热渲染耗时，并生成前后对比图。

用法：uv run python tools/render_texture_review.py --label before
另一个源码版本可用 --source-root 指向其 src；--compare 合并 before / roi / after。
产物写入 out/fabric_optimization/。
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from dataclasses import replace
from pathlib import Path
from statistics import median
from time import perf_counter

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "out" / "fabric_optimization"
CASES = (
    ("black_sheer", "leg_03", 0.25),
    ("white_sheer", "leg_04", 0.82),
    ("stripe_rainbow", "leg_07", 0.55),
    ("stripe_blue_white", "leg_08", 0.82),
    ("knit_cream", "leg_19", 0.55),
    ("fishnet_over_sheer", "leg_20", 0.82),
    ("polka_black", "leg_03", 0.55),
    ("heart_white", "leg_04", 0.82),
    ("star_custom", "leg_09", 0.82),
)


def record(label: str) -> None:
    """保存样张，并在预热后测量单腿和 L3/L4 绘制，不计 PNG 编码。"""
    from stockchart import DEFAULT_LEG_LIBRARY, STYLES, BarPlot, Dotted, bar, render_stocking

    folder = OUT / label
    folder.mkdir(parents=True, exist_ok=True)
    measurements: dict[str, float] = {}
    styles = dict(STYLES)
    heart = styles["heart_white"]
    assert isinstance(heart.fabric, Dotted)
    styles["star_custom"] = replace(
        heart, fabric=replace(heart.fabric, shape="star", layout="grid")
    )
    for key, leg_id, fill in CASES:
        leg = DEFAULT_LEG_LIBRARY.get(leg_id)
        for scale in (1, 2):
            rendered = render_stocking(leg, styles[key], leg.height * fill, seed=42, scale=scale)
            name = f"{key}_{scale}x"
            Image.fromarray(rendered.image).save(folder / f"{name}.png")
            times = []
            for _ in range(7):
                start = perf_counter()
                render_stocking(leg, styles[key], leg.height * fill, seed=42, scale=scale)
                times.append((perf_counter() - start) * 1000)
            measurements[name] = round(median(times), 2)

    chart_styles = [styles[case[0]] for case in CASES[:8]]
    plot = BarPlot(2200, seed=42)
    plot.add_bars([180, 580, 400, 590, 400, 590, 400, 590], style=chart_styles)
    chart = bar([2, 8, 5, 8, 5, 8, 5, 8], style=chart_styles, seed=42)
    for name, example in (("l3", plot), ("l4", chart)):
        example.to_pil(scale=2).save(folder / f"{name}.png")
        times = []
        for _ in range(5):
            start = perf_counter()
            example.render(scale=2)
            times.append((perf_counter() - start) * 1000)
        measurements[name] = round(median(times), 2)
    (folder / "timings.json").write_text(
        json.dumps(measurements, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({label: measurements}, indent=2))


def compare() -> None:
    """左侧旧算法、中间袜区计算、右侧查表；保留原尺寸单项供细看。"""
    versions = ("before", "roi", "after")
    thumbs: list[Image.Image] = []
    font = ImageFont.load_default(size=20)
    changes: dict[str, float] = {}
    for key, _leg, _fill in CASES:
        name = f"{key}_2x"
        images = [Image.open(OUT / version / f"{name}.png").convert("RGBA") for version in versions]
        cell_w = max(image.width for image in images) + 24
        sheet = Image.new("RGB", (3 * cell_w, images[0].height + 100), (250, 248, 243))
        draw = ImageDraw.Draw(sheet)
        draw.text((12, 8), key, fill=(50, 50, 50), font=font)
        for i, (version, image) in enumerate(zip(versions, images, strict=True)):
            draw.text((i * cell_w + 12, 45), version, fill=(50, 50, 50), font=font)
            sheet.paste(image, (i * cell_w + 12, 90), image)
        sheet.save(OUT / f"compare_{key}.png")
        thumbs.append(
            sheet.resize((510, round(sheet.height * 510 / sheet.width)), Image.Resampling.LANCZOS)
        )
        a, b = np.array(images[0]), np.array(images[-1])
        changes[key] = float(np.abs(a.astype(np.int16) - b.astype(np.int16)).mean())
    row_h = max(image.height for image in thumbs) + 16
    overview = Image.new(
        "RGB", (4 * 526 + 16, ((len(thumbs) + 3) // 4) * row_h + 16), (226, 223, 216)
    )
    for i, image in enumerate(thumbs):
        overview.paste(image, (16 + i % 4 * 526, 16 + i // 4 * row_h))
    overview.save(OUT / "comparison.png")
    print(json.dumps({"mean_abs_rgba": changes}, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--label", default="after")
    parser.add_argument("--compare", action="store_true")
    parser.add_argument(
        "--analytic", action="store_true", help="仅裁剪袜区，使用旧版解析纹理作中间对照"
    )
    args = parser.parse_args()
    if args.source_root:
        sys.path.insert(0, str(args.source_root.resolve()))
    if args.analytic:
        from stockchart.stocking import fabric

        spec = importlib.util.spec_from_file_location(
            "fabric_reference", OUT / "before" / "src" / "stockchart" / "stocking" / "fabric.py"
        )
        assert spec is not None and spec.loader is not None
        reference = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(reference)

        def analytic_stripes(style: object, rows: np.ndarray) -> np.ndarray:
            rgb, alpha = reference._stripe_opacity_at_y(style, rows)
            return np.dstack([rgb, alpha])

        fabric.stripe_pixels = analytic_stripes
        fabric.dot_mask = reference.dot_mask
    if args.compare:
        compare()
    else:
        record(args.label)


if __name__ == "__main__":
    main()
