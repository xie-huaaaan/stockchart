"""临时导出 2x PNG，并比较 PNG/SVG 在多种样式和设计尺寸下的绘制效果。

用法：uv run python tools/render_external_asset_review.py
输出：out/external_assets/，素材及派生评审图不随包分发。
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from stockchart import (
    DEFAULT_LEG_LIBRARY,
    STYLES,
    Leg,
    LegLibrary,
    bar,
    load_leg,
    render_stocking,
)
from stockchart.stocking.styles import scale_style

OUT = Path(__file__).resolve().parent.parent / "out" / "external_assets"
LEG_IDS = ("leg_03", "leg_04", "leg_07", "leg_08", "leg_19", "leg_20")
STYLE_KEYS = (
    "black_sheer",
    "white_sheer",
    "gray_sheer",
    "stripe_rainbow",
    "knit_cream",
    "fishnet_black",
    "polka_black",
    "heart_white",
)
BG = (250, 248, 243)
INK = (58, 58, 58)


def panel(images: list[Image.Image], labels: list[str], title: str) -> Image.Image:
    """并排显示同一素材的原始输出，不缩放参与对比的像素。"""
    cell_width = max(image.width for image in images) + 28
    height = max(image.height for image in images)
    sheet = Image.new("RGB", (cell_width * len(images), height + 100), BG)
    draw = ImageDraw.Draw(sheet)
    draw.text((14, 10), title, fill=INK, font=ImageFont.load_default(size=22))
    for i, (image, label) in enumerate(zip(images, labels, strict=True)):
        x = i * cell_width
        draw.text((x + 14, 50), label, fill=INK, font=ImageFont.load_default(size=18))
        sheet.paste(image, (x + (cell_width - image.width) // 2, 90), image)
    return sheet


def overview(panels: list[Image.Image], path: Path, *, thumbnail_width: int) -> None:
    """生成带留白的样式总览；单项原尺寸对比图另外保留。"""
    thumbs = [
        image.resize(
            (thumbnail_width, round(image.height * thumbnail_width / image.width)),
            Image.Resampling.LANCZOS,
        )
        for image in panels
    ]
    cell_w = thumbnail_width + 16
    cell_h = max(image.height for image in thumbs) + 16
    sheet = Image.new("RGB", (4 * cell_w + 16, 2 * cell_h + 16), (226, 223, 216))
    for i, image in enumerate(thumbs):
        sheet.paste(image, (16 + i % 4 * cell_w, 16 + i // 4 * cell_h))
    sheet.save(path)


def export_assets() -> tuple[list[Leg], list[Leg], list[Leg]]:
    """导出原始 2x 像素，分别保留直接导入和显式指定 720 设计尺寸的 Leg。"""
    sources = [DEFAULT_LEG_LIBRARY.get(leg_id) for leg_id in LEG_IDS]
    imported: list[Leg] = []
    design_720: list[Leg] = []
    for source in sources:
        path = OUT / "png_2x" / f"{source.leg_id}.png"
        Image.fromarray(source.raster_at(2)).save(path)
        png = load_leg(
            path,
            foot_center_x=source.foot_center_x * 2,
            leg_id=source.leg_id,
            pair_id=source.pair_id,
            side=source.side,
        )
        imported.append(png)
        # PNG 字节仍是原始 2x 图；明确指定设计尺寸，避免混入样式大小差异。
        design_720.append(
            replace(
                png,
                width=source.width,
                height=source.height,
                foot_center_x=source.foot_center_x,
            )
        )
    return sources, imported, design_720


def main() -> None:
    """生成同尺寸格式对比、直接导入的单位对比和自定义库 L4 示例。"""
    for name in ("png_2x", "comparisons", "rendered"):
        (OUT / name).mkdir(parents=True, exist_ok=True)
    sources, imported, design_720 = export_assets()
    panels_2x: list[Image.Image] = []
    panels_1x: list[Image.Image] = []
    units: list[Image.Image] = []
    measurements: list[dict[str, str | float | int]] = []
    for i, key in enumerate(STYLE_KEYS):
        source = sources[i % len(sources)]
        png = design_720[i % len(sources)]
        direct = imported[i % len(sources)]
        style = STYLES[key]
        fill = 0.82
        ref_2x = render_stocking(source, style, source.height * fill, seed=42, scale=2).image
        png_2x = render_stocking(png, style, png.height * fill, seed=42, scale=2).image
        ref_1x = render_stocking(source, style, source.height * fill, seed=42).image
        png_1x = render_stocking(png, style, png.height * fill, seed=42).image
        raw = render_stocking(direct, style, direct.height * fill, seed=42).image
        adjusted = render_stocking(
            direct, scale_style(style, 2), direct.height * fill, seed=42
        ).image
        title = f"{key} / {source.leg_id}"
        for scale, ref, result, panels in (
            (2, ref_2x, png_2x, panels_2x),
            (1, ref_1x, png_1x, panels_1x),
        ):
            comparison = panel(
                [Image.fromarray(ref), Image.fromarray(result)],
                [f"SVG / scale={scale}", f"PNG 2x / scale={scale}"],
                title,
            )
            comparison.save(OUT / "comparisons" / f"{key}_{scale}x.png")
            panels.append(comparison)
            diff = np.abs(ref.astype(np.int16) - result.astype(np.int16))
            measurements.append(
                {"style": key, "output_scale": scale, "mean_abs_rgba": float(diff.mean())}
            )
        unit_panel = panel(
            [Image.fromarray(ref_2x), Image.fromarray(raw), Image.fromarray(adjusted)],
            ["SVG 720 / scale=2", "PNG 1440 / defaults", "PNG 1440 / lengths x2"],
            title,
        )
        unit_panel.save(OUT / "comparisons" / f"{key}_units.png")
        units.append(unit_panel)
        Image.fromarray(png_2x).save(OUT / "rendered" / f"{key}.png")
        print(f"{key}: PNG output {png_2x.shape[1]}x{png_2x.shape[0]}")

    overview(panels_2x, OUT / "comparison_2x.png", thumbnail_width=400)
    overview(panels_1x, OUT / "comparison_1x.png", thumbnail_width=400)
    overview(units, OUT / "import_units.png", thumbnail_width=540)
    (OUT / "measurements.json").write_text(
        json.dumps(measurements, indent=2) + "\n", encoding="utf-8"
    )
    library = LegLibrary(design_720)
    bar(
        [5, 7, 4, 8, 6, 9, 5, 8],
        labels=["透黑", "白蕾丝", "渐隐", "彩条", "针织", "网眼", "波点", "爱心"],
        title="外部 2x PNG 素材 · 720 设计尺寸",
        library=library,
        style=list(STYLE_KEYS),
        paired="none",
        value_labels=True,
        seed=42,
    ).save(OUT / "png_library_chart.png", scale=2)
    print(f"评审图 → {OUT}")


if __name__ == "__main__":
    main()
