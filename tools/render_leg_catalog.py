"""生成内置腿素材目录图，供文档展示与人工核对。

用法：uv run python tools/render_leg_catalog.py
输出：docs/images/leg_catalog.png
"""

from __future__ import annotations

from pathlib import Path

from stockchart import LegLibrary

ROOT = Path(__file__).parent.parent


def main() -> None:
    out = ROOT / "docs" / "images" / "leg_catalog.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    image = LegLibrary().preview(scale=0.5)
    image.save(out, optimize=True)
    print(f"素材目录 → {out}  ({image.width}×{image.height})")


if __name__ == "__main__":
    main()
