"""生成随包分发的内置素材墨线数据。

用法：uv run python tools/prepare_asset_data.py
输出：src/stockchart/_precomputed/leg_*.npz，与素材共用 ARR 许可。
"""

from hashlib import sha256
from pathlib import Path

import numpy as np

from stockchart import LegLibrary
from stockchart.stocking.preprocess import INK_DATA_DENSITY, INK_DATA_VERSION, extract_ink

OUT = Path(__file__).resolve().parent.parent / "src" / "stockchart" / "_precomputed"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    library = LegLibrary(seed=0)
    total = 0
    for leg_id in library.leg_ids:
        leg = library.get(leg_id)
        assert leg.svg is not None
        image = leg.raster_at(INK_DATA_DENSITY)
        ink, depth = extract_ink(image, INK_DATA_DENSITY)
        path = OUT / f"{leg_id}.npz"
        np.savez_compressed(
            path,
            version=np.int32(INK_DATA_VERSION),
            source=sha256(leg.svg).hexdigest(),
            density=np.float32(INK_DATA_DENSITY),
            ink=ink,
            depth=depth,
        )
        total += path.stat().st_size
        print(f"{leg_id}: {path.stat().st_size / 1024:.1f} KiB", flush=True)
    print(f"共 {len(library.leg_ids)} 条，{total / 1024:.1f} KiB")


if __name__ == "__main__":
    main()
