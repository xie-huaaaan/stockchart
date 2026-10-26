"""把内置腿素材位图矢量化，再栅格化成高密度 PNG（没有超分母图时的退路）。

常规素材升级走 `tools/split_master.py`（直接追踪 AI 超分母图）；本脚本只用于
手头只有 720p 素材时重建 2 倍密 PNG，会覆盖同名的 `leg_XX@2x.png`。

为什么先放大再追踪：追踪器对 1–2px 的细线与抗锯齿灰阶无能为力——相邻笔画会被
最小特征阈值粘在一起，灰阶也会被量化成几块平色（实测墨量偏大 20%–55%）。先把
素材放大 4 倍，笔画间距与灰阶宽度同步拉开，追踪结果就能保住细节与线宽（墨量
误差 <5%）；栅格化时再降回目标密度。

用法：
    uv run python tools/trace_legs.py            # 默认 2 倍密度
    uv run python tools/trace_legs.py --density 3

输出：src/stockchart/assets/leg_XX@2x.png（带原图 alpha）与 legs_hires.json。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import cairosvg
import vtracer
from PIL import Image

ROOT = Path(__file__).parent.parent
ASSETS = ROOT / "src" / "stockchart" / "assets"
WORK = ROOT / "out" / "trace"
BACKGROUND = (250, 248, 243)


def trace_one(png: Path, density: int, *, pre_scale: int) -> tuple[Image.Image, dict[str, float]]:
    """返回 (目标密度的 RGBA 图, 元数据)。

    RGB 走"放大 → 追踪 → 栅格化"，alpha 直接由原图升采样，保证轮廓与原素材一致。
    """
    im = Image.open(png).convert("RGBA")
    w, h = im.size

    # 追踪需要不透明输入：垫背景色后放大
    flat = Image.new("RGB", im.size, BACKGROUND)
    flat.paste(im, (0, 0), im)
    big = flat.resize((w * pre_scale, h * pre_scale), Image.Resampling.LANCZOS)
    big_path = WORK / f"{png.stem}_pre{pre_scale}.png"
    big.save(big_path)

    svg_path = WORK / f"{png.stem}.svg"
    vtracer.convert_image_to_svg_py(
        str(big_path),
        str(svg_path),
        colormode="color",
        hierarchical="stacked",
        mode="spline",
        filter_speckle=pre_scale,
        color_precision=6,
        layer_difference=16,
        corner_threshold=60,
        length_threshold=float(pre_scale),
        max_iterations=10,
        splice_threshold=45,
        path_precision=2,
    )

    out_w, out_h = w * density, h * density
    rgb_path = WORK / f"{png.stem}_rgb.png"
    cairosvg.svg2png(
        url=str(svg_path),
        write_to=str(rgb_path),
        output_width=out_w,
        output_height=out_h,
    )
    rgb = Image.open(rgb_path).convert("RGB")

    alpha = im.getchannel("A").resize((out_w, out_h), Image.Resampling.LANCZOS)
    out = rgb.convert("RGBA")
    out.putalpha(alpha)
    meta = {"density": density, "out_width": out_w, "out_height": out_h}
    return out, meta


def main() -> None:
    parser = argparse.ArgumentParser(description="位图矢量化的高密度腿素材生成")
    parser.add_argument("--density", type=int, default=2, help="输出密度（像素/设计像素）")
    parser.add_argument("--pre-scale", type=int, default=4, help="追踪前的放大倍数")
    parser.add_argument("--only", default=None, help="只处理某条腿，如 leg_01")
    args = parser.parse_args()

    WORK.mkdir(parents=True, exist_ok=True)
    # 排除已生成的高密度文件（leg_XX@2x.png 也匹配 leg_*.png）
    sources = sorted(p for p in ASSETS.glob("leg_*.png") if "@" not in p.stem)
    if args.only:
        sources = [p for p in sources if p.stem == args.only]
    if not sources:
        raise SystemExit("没有找到源素材")

    entries: dict[str, dict[str, float]] = {}
    for png in sources:
        out, meta = trace_one(png, args.density, pre_scale=args.pre_scale)
        dest = ASSETS / f"{png.stem}@{args.density}x.png"
        out.save(dest, optimize=True)
        entries[png.stem] = meta
        size_kb = dest.stat().st_size // 1024
        print(f"{dest.name}  {meta['out_width']}x{meta['out_height']}  {size_kb}KB")

    meta_path = ASSETS / "legs_hires.json"
    if args.only and meta_path.exists():
        merged = json.loads(meta_path.read_text(encoding="utf-8"))
        merged.update(entries)
        entries = merged
    meta_path.write_text(
        json.dumps(entries, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"元数据 → {meta_path.name}（{len(entries)} 条）")


if __name__ == "__main__":
    main()
