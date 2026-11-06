"""生成随包分发的内置素材墨线数据与 Skia 矢量绘图指令。

用法：uv run python tools/prepare_asset_data.py
输出：src/stockchart/_precomputed/ 中的 NPZ、SKP 与源索引，与素材共用 ARR 许可。
"""

import json
from hashlib import sha256
from pathlib import Path

import numpy as np
import skia

from stockchart import LegLibrary
from stockchart.stocking.preprocess import INK_DATA_DENSITY, INK_DATA_VERSION, extract_ink
from stockchart.vector import _record_svg, svg_dimensions

OUT = Path(__file__).resolve().parent.parent / "src" / "stockchart" / "_precomputed"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    library = LegLibrary()
    total = 0
    sources: dict[str, str] = {}
    for leg_id in library.leg_ids:
        leg = library.get(leg_id)
        digest = sha256(leg.source).hexdigest()
        width, height = svg_dimensions(leg.source)
        picture = _record_svg(leg.source, width, height)
        picture_path = OUT / f"{leg_id}.skp"
        picture_path.write_bytes(bytes(picture.serialize()))
        sources[digest] = leg_id
        image = leg.raster_at(INK_DATA_DENSITY)
        ink, depth = extract_ink(image, INK_DATA_DENSITY)
        path = OUT / f"{leg_id}.npz"
        np.savez_compressed(
            path,
            version=np.int32(INK_DATA_VERSION),
            source=digest,
            density=np.float32(INK_DATA_DENSITY),
            ink=ink,
            depth=depth,
        )
        total += path.stat().st_size + picture_path.stat().st_size
        print(
            f"{leg_id}: 墨线 {path.stat().st_size / 1024:.1f} KiB，"
            f"指令 {picture_path.stat().st_size / 1024:.1f} KiB",
            flush=True,
        )
    (OUT / "pictures.json").write_text(
        json.dumps({"skia": skia.__version__, "sources": sources}, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"共 {len(library.leg_ids)} 条，{total / 1024:.1f} KiB")


if __name__ == "__main__":
    main()
