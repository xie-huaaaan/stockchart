# pyright: reportPrivateUsage=false
"""统一素材源、外部导入和混合库的公开行为。"""

from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from stockchart import (
    DEFAULT_LEG_LIBRARY,
    STYLES,
    BarPlot,
    LegLibrary,
    LegRender,
    _raster,
    bar,
    load_leg,
    mirror_bar,
    render_stocking,
)
from stockchart._cache import ByteCache


def test_svg_import_dimensions_anchor_and_lazy_loading(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "external.svg"
    path.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20.5 40.5">'
        '<rect x="6" width="8" height="40.5" fill="#c08060" fill-opacity="0.5"/></svg>'
    )
    source = load_leg(path, foot_center_x=10.25)
    assert (source.width, source.height, source.foot_center_x) == (20.5, 40.5, 10.25)
    auto = load_leg(path)
    assert 8 < auto.foot_center_x < 12
    image = auto.raster_at(2)
    assert image.shape == (81, 41, 4)
    assert image[40, 20, 3] == pytest.approx(128, abs=1)
    assert image[40, 0, 3] == 0
    with pytest.raises(FrozenInstanceError):
        source.height = 90  # type: ignore[misc]

    # 显式锚点和内置 get 均不请求任何辅助栅格。
    def unexpected(*args: object, **kwargs: object) -> np.ndarray:
        raise AssertionError("获取素材不应栅格化")

    monkeypatch.setattr(_raster, "rasterize_source", unexpected)
    load_leg(path, foot_center_x=9)
    builtin = LegLibrary().get("leg_01")
    assert builtin.height == 720
    for text in (
        '<svg width="100%" height="100%"/>',
        '<svg viewBox="0 0 0 20"/>',
        '<svg width="-2" height="30"/>',
    ):
        path.write_text(text)
        with pytest.raises(ValueError):
            load_leg(path, foot_center_x=0)


def test_png_anchor_and_render_result(tmp_path: Path) -> None:
    path = tmp_path / "external.png"
    pixels = np.zeros((60, 30, 4), np.uint8)
    pixels[20:, 8:13] = (240, 180, 140, 128)
    Image.fromarray(pixels).save(path)
    source = load_leg(path)
    assert source.foot_center_x == pytest.approx(10)
    assert load_leg(path, foot_center_x=11).foot_center_x == 11
    for scale in (0.5, 1, 2):
        result = render_stocking(source, STYLES["black_sheer"], 30, seed=0, scale=scale)
        assert isinstance(result, LegRender)
        assert result.source is source and result.scale == scale
        np.testing.assert_array_equal(result.image[..., 3], source.raster_at(scale)[..., 3])
    Image.new("RGBA", (30, 60)).save(path)
    assert load_leg(path).foot_center_x == 15


def test_mixed_library_selection_and_chart_injection() -> None:
    left, right = DEFAULT_LEG_LIBRARY.pair("pair_01")
    unnamed = replace(left, leg_id=None, pair_id=None, side=None)
    incomplete = DEFAULT_LEG_LIBRARY.get("leg_03")
    library = LegLibrary([left, right, unnamed, incomplete])
    assert library.legs == (left, right, unnamed, incomplete)
    assert library.pair_ids == ("pair_01",)
    assert library.get("leg_01") is left
    assert set(library.alternate(4, seed=0)) == set(library.legs)
    assert library.alternate(8, paired=True, seed=0) == [left, right] * 4
    library.alternate(4, seed=99)
    assert library.alternate(4, seed=8) == library.alternate(4, seed=8)
    assert library.preview(scale=0.05).width > 0
    with pytest.raises(ValueError, match="重复"):
        LegLibrary([left, left])
    with pytest.raises(ValueError, match="重复"):
        LegLibrary([left, replace(left, leg_id="other")])
    single = LegLibrary([unnamed])
    with pytest.raises(ValueError, match="完整"):
        single.sample_pairs(1)
    assert single.sample_pairs(0) == []
    with pytest.raises(KeyError):
        library.pair("pair_02")

    plot = BarPlot(500, library=single, seed=1).add_bars([20, 30])
    assert all(record.leg is unnamed for record in plot._bars)
    plot.add_bars([20], legs=[right])
    assert plot._bars[-1].leg is right
    for chart in (bar([1, 2], library=single, seed=0), mirror_bar([1, -2], library=single, seed=0)):
        assert all(record.leg is unnamed for record in chart._bars)
        assert chart.to_numpy(scale=0.1).shape[2] == 4


def test_source_raster_cache_evicts_under_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    source = DEFAULT_LEG_LIBRARY.get("leg_01")
    cache = ByteCache[np.ndarray](200)
    monkeypatch.setattr(_raster, "_cache", cache)
    first = source.raster_at(0.01)
    assert source.raster_at(0.01) is first
    source.raster_at(0.02)
    assert cache.get((source._source_digest(), "svg", 2, 7)) is None
    np.testing.assert_array_equal(first, source.raster_at(0.01))
