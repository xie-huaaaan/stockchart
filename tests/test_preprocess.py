# pyright: reportPrivateUsage=false

"""素材预制数据、缺失回退与跨库共享缓存的功能测试。"""

from dataclasses import replace

import numpy as np
import pytest

from stockchart import STYLES, Fishnet, Leg, LegLibrary, Plain, StockingStyle, render_stocking
from stockchart._cache import ByteCache
from stockchart.stocking import preprocess
from stockchart.stocking.styles import Lace, Shading, Welt


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


def test_ink_boost_covers_top_material_independently_of_body() -> None:
    image = np.full((120, 40, 4), (253, 234, 228, 255), dtype=np.uint8)
    for row in (30, 62, 90):
        image[row : row + 3, 12:28, :3] = 100
    leg = Leg(image, 40, 120, 20)
    shading = Shading(curve=0, wobble=0, rim_shadow=0, highlight=0, skin=0, ink=0)

    for fabric in (Plain(color=(255, 255, 255)), Fishnet(color=(255, 255, 255))):
        for top in (Welt(height=24, color=(0, 0, 0)), Lace(height=24, color=(0, 0, 0))):
            style = StockingStyle(fabric=fabric, top=top, shading=shading)
            original = render_stocking(leg, style, 70, seed=1).image
            boosted = render_stocking(
                leg, replace(style, shading=replace(shading, ink=1)), 70, seed=1
            ).image
            # 深色上沿按自身颜色提亮，即使袜身是白色或没有底袜。
            assert boosted[63, 20, :3].mean() > original[63, 20, :3].mean()
            np.testing.assert_array_equal(original[:45], boosted[:45])
            np.testing.assert_array_equal(original[..., 3], boosted[..., 3])
            if isinstance(fabric, Fishnet):
                np.testing.assert_array_equal(original[85:], boosted[85:])
            else:
                assert boosted[91, 20, :3].mean() < original[91, 20, :3].mean()

    # 透明条带内部没有织物，不能仅因位于袜口以下就增强。
    transparent = StockingStyle(
        fabric=Plain(color=(0, 0, 0)),
        top=Welt(height=24, opacity=0),
        shading=shading,
    )
    off = render_stocking(leg, transparent, 70, seed=1).image
    on = render_stocking(
        leg, replace(transparent, shading=replace(shading, ink=1)), 70, seed=1
    ).image
    np.testing.assert_array_equal(off[58:68], on[58:68])
