# pyright: reportPrivateUsage=false

"""素材预制数据、缺失回退与跨库共享缓存的功能测试。"""

from dataclasses import replace
from io import BytesIO

import numpy as np
import pytest
import skia
from PIL import Image

from stockchart import (
    STYLES,
    Fishnet,
    Leg,
    LegLibrary,
    LegRender,
    Plain,
    StockingStyle,
    render_stocking,
    vector,
)
from stockchart._cache import ByteCache
from stockchart.stocking import preprocess
from stockchart.stocking.styles import Lace, Shading, Welt


def test_bundled_ink_matches_live_extraction() -> None:
    source = LegLibrary().get("leg_01")
    leg = LegRender(source, source.raster_at(2), 2)
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
    buffer = BytesIO()
    Image.fromarray(image).save(buffer, format="PNG")
    leg = Leg(buffer.getvalue(), "png", 40, 120, 20)
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
    render_stocking(leg, STYLES["black_sheer"], 80, seed=2, scale=2)
    assert calls == 1
    assert np.array_equal(unchanged, leg.raster_at())
    assert not np.array_equal(first.image, image)

    changed = image.copy()
    changed[60:62, 15:25, :3] = 100
    buffer = BytesIO()
    Image.fromarray(changed).save(buffer, format="PNG")
    render_stocking(replace(leg, source=buffer.getvalue()), STYLES["black_sheer"], 80, seed=2)
    assert calls == 2


def test_design_size_ink_is_independent_of_render_history(monkeypatch: pytest.MonkeyPatch) -> None:
    image = np.full((120, 40, 4), (253, 234, 228, 255), dtype=np.uint8)
    image[65:68, 12:28, :3] = 100
    image[90, 14:26, :3] = 80
    buffer = BytesIO()
    Image.fromarray(image).save(buffer, format="PNG")
    original = Leg(buffer.getvalue(), "png", 40, 120, 20)
    compact = replace(original, width=20, height=60, foot_center_x=10)
    style = STYLES["black_sheer"]

    monkeypatch.setattr(preprocess, "_ink_cache", ByteCache[preprocess.InkPixels](1024 * 1024))
    render_stocking(original, style, 80, seed=2)
    after_original = render_stocking(compact, style, 40, seed=2, scale=2)
    monkeypatch.setattr(preprocess, "_ink_cache", ByteCache[preprocess.InkPixels](1024 * 1024))
    independently = render_stocking(compact, style, 40, seed=2, scale=2)
    np.testing.assert_array_equal(after_original.image, independently.image)


def test_separate_libraries_share_readonly_raster() -> None:
    left = LegLibrary().get("leg_02").raster_at(2)
    right = LegLibrary().get("leg_02").raster_at(2)
    assert left is right
    assert not left.flags.writeable


def test_vector_commands_reused_across_densities(monkeypatch: pytest.MonkeyPatch) -> None:
    # 非内置 SVG 走录制回退；覆盖裁切、透明颜色、通道顺序与多倍率复用。
    svg = (
        b'<svg xmlns="http://www.w3.org/2000/svg" width="20" height="40">'
        b'<defs><clipPath id="leg"><ellipse cx="10" cy="20" rx="8" ry="19"/>'
        b'</clipPath></defs><g clip-path="url(#leg)">'
        b'<rect width="20" height="40" fill="#d09070" fill-opacity="0.6"/></g></svg>'
    )
    calls = 0
    record = vector._record_svg

    def counted(source: bytes, width: float, height: float) -> skia.Picture:
        nonlocal calls
        calls += 1
        return record(source, width, height)

    monkeypatch.setattr(vector, "_record_svg", counted)
    monkeypatch.setattr(vector, "_picture_cache", ByteCache[vector._SvgPicture](1024 * 1024))
    monkeypatch.setattr(vector, "_raster_cache", ByteCache[np.ndarray](1024 * 1024))
    for scale in (0.5, 1, 2, 6):
        width, height = round(20 * scale), round(40 * scale)
        image = vector.rasterize_svg(svg, width, height)
        dom = skia.SVGDOM.MakeFromStream(skia.MemoryStream(svg))
        assert dom is not None
        dom.setContainerSize(skia.Size(20, 40))
        surface = skia.Surface(width, height)
        canvas = surface.getCanvas()
        canvas.scale(scale, scale)
        dom.render(canvas)
        direct = surface.makeImageSnapshot().toarray(colorType=skia.ColorType.kRGBA_8888_ColorType)
        np.testing.assert_array_equal(image, direct)
        assert image.flags.c_contiguous
        assert not image.flags.writeable
    assert calls == 1
    changed = vector.rasterize_svg(svg.replace(b"#d09070", b"#809070"), 20, 40)
    assert calls == 2
    assert not np.array_equal(changed, vector.rasterize_svg(svg, 20, 40))


def test_bundled_vector_falls_back_after_skia_upgrade(monkeypatch: pytest.MonkeyPatch) -> None:
    leg = LegLibrary().get("leg_01")
    assert leg.source_type == "svg"
    manifest = vector._bundled_sources()
    digest = preprocess._source_key(leg).hex()
    assert digest in manifest
    bundled = vector.rasterize_svg(leg.source, round(leg.width * 2), round(leg.height * 2))
    monkeypatch.setattr(vector.skia, "__version__", "different-skia-version")
    vector._bundled_sources.cache_clear()
    try:
        assert not vector._bundled_sources()
        monkeypatch.setattr(vector, "_picture_cache", ByteCache[vector._SvgPicture](1024 * 1024))
        monkeypatch.setattr(vector, "_raster_cache", ByteCache[np.ndarray](8 * 1024 * 1024))
        rebuilt = vector.rasterize_svg(leg.source, round(leg.width * 2), round(leg.height * 2))
        np.testing.assert_array_equal(bundled, rebuilt)
    finally:
        vector._bundled_sources.cache_clear()


def test_ink_boost_covers_top_material_independently_of_body() -> None:
    image = np.full((120, 40, 4), (253, 234, 228, 255), dtype=np.uint8)
    for row in (30, 62, 90):
        image[row : row + 3, 12:28, :3] = 100
    buffer = BytesIO()
    Image.fromarray(image).save(buffer, format="PNG")
    leg = Leg(buffer.getvalue(), "png", 40, 120, 20)
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
