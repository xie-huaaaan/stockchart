# pyright: reportPrivateUsage=false

"""素材预制数据、缺失回退与跨库共享缓存的功能测试。"""

from dataclasses import replace

import numpy as np
import pytest

from stockchart import STYLES, Leg, LegLibrary, render_stocking
from stockchart._cache import ByteCache
from stockchart.stocking import preprocess


def test_bundled_ink_matches_live_extraction() -> None:
    leg = LegLibrary(seed=0).get("leg_01").at_density(2)
    digest = preprocess._source_key(leg)
    packed = preprocess._bundled_ink("leg_01", digest)
    assert packed is not None
    expected = preprocess.extract_ink(leg.image, 2)
    np.testing.assert_array_equal(packed[0], expected[0])
    np.testing.assert_array_equal(packed[1], expected[1])
    assert preprocess._bundled_ink("leg_01", b"old-svg") is None


def test_missing_data_is_extracted_once(monkeypatch: pytest.MonkeyPatch) -> None:
    image = np.empty((120, 40, 4), dtype=np.uint8)
    image[:] = [253, 234, 228, 255]
    image[65:68, 15:25, :3] = 120
    leg = Leg(image, 40, 120, 20)
    unchanged = image.copy()
    calls = 0
    original = preprocess.extract_ink

    def counted(image: np.ndarray, density: float) -> tuple[np.ndarray, np.ndarray]:
        nonlocal calls
        calls += 1
        return original(image, density)

    monkeypatch.setattr(preprocess, "_ink_cache", ByteCache[preprocess.InkPixels](1024 * 1024))
    monkeypatch.setattr(preprocess, "extract_ink", counted)
    first = render_stocking(leg, STYLES["black_sheer"], 80, seed=2)
    render_stocking(leg, STYLES["white_sheer"], 90, seed=3)
    assert calls == 1
    assert np.array_equal(unchanged, leg.image)
    assert not np.array_equal(first.image, image)

    changed = image.copy()
    changed[60:62, 15:25, :3] = 100
    render_stocking(replace(leg, image=changed), STYLES["black_sheer"], 80, seed=2)
    assert calls == 2


def test_separate_libraries_share_readonly_raster() -> None:
    left = LegLibrary().get("leg_02").at_density(2)
    right = LegLibrary().get("leg_02").at_density(2)
    assert left.image is right.image
    assert not left.image.flags.writeable
