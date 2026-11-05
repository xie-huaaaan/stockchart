# pyright: reportPrivateUsage=false

"""基础集成测试：覆盖 L0 素材层与 L1 渲染原语。

同类断言合并在一个用例内，渲染一律用最小尺寸素材，避免拖慢整套测试。
"""

from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

import stockchart
from stockchart import (
    STYLES,
    Dotted,
    Fishnet,
    LegLibrary,
    Plain,
    Ribbed,
    StockingStyle,
    Striped,
    load_leg,
    render_stocking,
)
from stockchart.stocking.styles import Fade, Lace, Shading, Welt

# ---------------------------------------------------------------------------
# 辅助：合成一条简单的腿素材
# ---------------------------------------------------------------------------


def make_synthetic_leg(height: int = 200, width: int = 80) -> "stockchart.Leg":
    """构造一条椭圆截面腿素材，用于测试渲染。"""
    from stockchart.legs import Leg

    img = np.zeros((height, width, 4), dtype=np.uint8)
    cx = width // 2
    for y in range(height):
        half_w = int(28 + 6 * np.sin(y / height * np.pi))
        x0 = max(0, cx - half_w)
        x1 = min(width, cx + half_w)
        img[y, x0:x1, :3] = [253, 234, 228]
        img[y, x0:x1, 3] = 255

    return Leg(
        image=img,
        width=width,
        height=height,
        foot_center_x=cx,
    )


# ---------------------------------------------------------------------------
# L0：LegLibrary
# ---------------------------------------------------------------------------


class TestLegLibrary:
    def test_get_by_id(self) -> None:
        leg = LegLibrary().get("leg_01")
        assert leg.leg_id == "leg_01"
        assert leg.side == "left"
        assert leg.height == 720

    def test_unknown_id_raises(self) -> None:
        lib = LegLibrary()
        with pytest.raises(KeyError):
            lib.get("leg_99")
        with pytest.raises(KeyError):
            lib.pair("pair_99")

    def test_pair_returns_left_right(self) -> None:
        left, right = LegLibrary().pair("pair_01")
        assert left.side == "left"
        assert right.side == "right"
        assert left.pair_id == right.pair_id == "pair_01"

    def test_alternate_pattern_and_length(self) -> None:
        legs = LegLibrary(seed=42).alternate(6)
        assert len(legs) == 6
        assert [leg.side for leg in legs] == ["left", "right", "left", "right", "left", "right"]

    def test_alternate_paired_uses_same_pair(self) -> None:
        legs = LegLibrary(seed=7).alternate(6, paired=True)
        for i in range(0, len(legs), 2):
            assert legs[i].pair_id == legs[i + 1].pair_id
            assert legs[i].side == "left"
            assert legs[i + 1].side == "right"

    def test_alternate_without_pairs_uses_different_pairs(self) -> None:
        legs = LegLibrary(seed=7).alternate(6)
        assert len({leg.pair_id for leg in legs}) == 6

    def test_sample_pairs(self) -> None:
        pairs = LegLibrary(seed=42).sample_pairs(3)
        assert len(pairs) == 3
        for left, right in pairs:
            assert left.side == "left"
            assert right.side == "right"
            assert left.pair_id == right.pair_id

    def test_seed_determinism(self) -> None:
        """同 seed 的 alternate 结果相同。"""
        ids1 = [leg.leg_id for leg in LegLibrary(seed=7).alternate(4)]
        ids2 = [leg.leg_id for leg in LegLibrary(seed=7).alternate(4)]
        assert ids1 == ids2

    def test_cache_returns_same_object(self) -> None:
        lib = LegLibrary()
        assert lib.get("leg_05") is lib.get("leg_05")

    def test_ids_are_listed(self) -> None:
        lib = LegLibrary()
        assert len(lib.leg_ids) == 26
        assert lib.leg_ids[0] == "leg_01"
        assert lib.leg_ids[-1] == "leg_26"
        assert len(lib.pair_ids) == 13
        assert lib.pair_ids[0] == "pair_01"
        assert lib.pair_ids[-1] == "pair_13"
        assert "26 legs / 13 pairs" in repr(lib)

    def test_preview_returns_rgb_image(self) -> None:
        image = LegLibrary().preview(scale=0.05)
        assert image.mode == "RGB"
        assert image.width > 0
        assert image.height > 0


# ---------------------------------------------------------------------------
# L0：矢量素材与栅格化
# ---------------------------------------------------------------------------


class TestVectorAssets:
    """内置素材只存透明 SVG，渲染时按目标密度栅格化。"""

    def test_builtin_leg_has_svg_source(self) -> None:
        leg = LegLibrary().get("leg_01")
        assert leg.svg is not None
        assert leg.pixels_per_unit == 1.0
        assert leg.image.shape == (leg.height, leg.width, 4)

    def test_raster_at_target_density_is_cached(self) -> None:
        leg = LegLibrary().get("leg_01")
        img = leg.raster_at(2)
        assert img.shape == (leg.height * 2, leg.width * 2, 4)
        assert img[:, :, 3].min() == 0
        assert img[:, :, 3].max() > 250
        assert leg.raster_at(2) is img

        hi = leg.at_density(2)
        assert hi.pixels_per_unit == 2
        assert hi.image is img
        assert hi.svg is leg.svg

    def test_render_stocking_on_vector_leg(self) -> None:
        """矢量素材栅格化后可直接交给 render_stocking，尺寸与设计坐标一致。"""
        leg = LegLibrary().get("leg_01")
        out = render_stocking(leg, STYLES["black_sheer"], 200, seed=1)
        assert out.image.shape == (leg.height, leg.width, 4)
        assert out.pixels_per_unit == 1.0

    def test_external_leg_has_no_vector_source(self, tmp_path: Path) -> None:
        leg = make_synthetic_leg(720, 160)
        png_path = tmp_path / "leg.png"
        Image.fromarray(leg.image).save(png_path)
        loaded = load_leg(png_path)
        assert loaded.svg is None
        with pytest.raises(ValueError):
            loaded.raster_at(2)


# ---------------------------------------------------------------------------
# L0：load_leg
# ---------------------------------------------------------------------------


class TestLoadLeg:
    def test_from_png(self, tmp_path: Path) -> None:
        leg = make_synthetic_leg(300, 100)
        png_path = tmp_path / "test_leg.png"
        Image.fromarray(leg.image).save(png_path)

        loaded = load_leg(png_path)
        assert loaded.width == 100
        assert loaded.height == 300
        assert loaded.leg_id is None
        assert loaded.side is None

        # 足底中心可显式指定，越界报错
        assert load_leg(png_path, foot_center_x=40).foot_center_x == 40
        with pytest.raises(ValueError, match="foot_center_x"):
            load_leg(png_path, foot_center_x=100)


# ---------------------------------------------------------------------------
# L1：Leg 与 StockingStyle 参数校验
# ---------------------------------------------------------------------------


class TestLegValidation:
    def test_invalid_params_raise(self) -> None:
        img = np.zeros((10, 10, 4), dtype=np.uint8)
        with pytest.raises(ValueError):
            stockchart.Leg(image=img, width=20, height=20, foot_center_x=5)
        with pytest.raises(ValueError):
            stockchart.Leg(image=img, width=10, height=10, foot_center_x=10)
        with pytest.raises(ValueError):
            stockchart.Leg(image=img, width=10, height=10, foot_center_x=5, pixels_per_unit=0)


class TestStockingStyleValidation:
    def test_invalid_params_raise(self) -> None:
        """每个样式的参数校验都必须拦下越界值。"""
        with pytest.raises(ValueError):
            Plain(color=(0, 0, 0), opacity=1.5)
        with pytest.raises(ValueError):
            Plain(color=(300, 0, 0))  # type: ignore[arg-type]
        with pytest.raises(ValueError):
            Striped(stripes=())
        with pytest.raises(ValueError):
            Fishnet(color=(0, 0, 0), cell=-1)
        with pytest.raises(ValueError):
            Welt(height=-5)
        with pytest.raises(ValueError):
            Lace(scallop=19)
        with pytest.raises(ValueError):
            Ribbed(color=(0, 0, 0), perspective=-0.1)
        with pytest.raises(ValueError):
            Fishnet(color=(0, 0, 0), perspective=1.1)
        with pytest.raises(ValueError):
            Dotted(base=Plain(color=(0, 0, 0)), color=(0, 0, 0), perspective=1.1)
        with pytest.raises(ValueError):
            Fade(length=0)
        with pytest.raises(ValueError):
            Shading(cel_steps=5)
        with pytest.raises(ValueError):
            Shading(skin=-0.1)
        # 上界含端点
        assert Lace(scallop=20).scallop == 20


# ---------------------------------------------------------------------------
# L1：皮肤光影
# ---------------------------------------------------------------------------


class TestSkinShading:
    """皮肤光影：skin=0 不动皮肤，skin>0 时袜口以上与裸腿都受影响。"""

    def test_skin_zero_leaves_bare_leg_untouched(self) -> None:
        leg = make_synthetic_leg(720, 160)
        style = replace(STYLES["black_sheer"], shading=Shading(skin=0.0))
        out = render_stocking(leg, style, 400, seed=1)
        top = leg.height - 400
        # 袜口以上 20px 之外应与素材完全一致
        assert (out.image[: top - 20] == leg.image[: top - 20]).all()

    def test_skin_shades_bare_leg(self) -> None:
        leg = make_synthetic_leg(720, 160)
        style = replace(STYLES["black_sheer"], shading=Shading(skin=0.5))
        out = render_stocking(leg, style, 0, seed=1)
        diff = np.abs(out.image.astype(int) - leg.image.astype(int))[:, :, :3]
        # 验证受光的方向，避免依赖采样方法对边缘极值的影响。
        delta = out.image[..., :3].astype(int) - leg.image[..., :3].astype(int)
        covered = leg.image[..., 3] > 0
        assert delta[covered].min() < 0
        assert delta[covered].max() > 0
        # 左侧缘（边缘阴影）与高光带（u≈-0.35）都要变
        assert diff[:, leg.width // 2 - 32].max() > 0
        assert diff[:, leg.width // 2 - 11].max() > 0


# ---------------------------------------------------------------------------
# L1：倍率渲染
# ---------------------------------------------------------------------------


class TestRenderScale:
    """倍率渲染：在 scale 倍像素空间生成，而非放大成品图。"""

    def test_dims_and_metadata_scale(self) -> None:
        leg = make_synthetic_leg(200, 80)
        out = render_stocking(leg, STYLES["black_sheer"], 100, seed=1, scale=2)
        # 图像按倍率加密，设计坐标（供上层布局使用）保持不变
        assert out.image.shape[:2] == (400, 160)
        assert out.pixels_per_unit == 2
        assert (out.height, out.width) == (200, 80)
        assert out.foot_center_x == leg.foot_center_x

    def test_bad_scale_and_density(self) -> None:
        leg = make_synthetic_leg(200, 80)
        with pytest.raises(ValueError):
            render_stocking(leg, STYLES["black_sheer"], 100, scale=0)
        with pytest.raises(ValueError):
            render_stocking(leg, STYLES["black_sheer"], 100, scale=float("nan"))
        with pytest.raises(ValueError):
            leg.at_density(0)

    def test_scale2_matches_scale1_when_downsampled(self) -> None:
        leg = make_synthetic_leg(200, 80)
        a = render_stocking(leg, STYLES["stripe_blue_white"], 150, seed=1).image
        b = render_stocking(leg, STYLES["stripe_blue_white"], 150, seed=1, scale=2).image
        small = np.asarray(
            Image.fromarray(b).resize((leg.width, leg.height), Image.Resampling.LANCZOS)
        ).astype(int)
        diff = np.abs(small[:, :, :3] - a.astype(int)[:, :, :3])
        # 高频条纹在降采样时会有少量差异，整体应高度一致
        assert diff.mean() < 12

    def test_dense_asset_is_downsampled_not_upscaled(self) -> None:
        """2 倍密素材在 1 倍输出下应降采样，设计坐标不变。"""
        base = make_synthetic_leg(200, 80)
        hi_img = np.asarray(Image.fromarray(base.image).resize((base.width * 2, base.height * 2)))
        hi = replace(base, image=hi_img, pixels_per_unit=2.0)
        out = render_stocking(hi, STYLES["black_sheer"], 100, seed=1)
        assert out.image.shape[:2] == (200, 80)
        assert out.pixels_per_unit == 1.0
        # 2 倍输出则直接用素材本身，不再放大
        out2 = render_stocking(hi, STYLES["black_sheer"], 100, seed=1, scale=2)
        assert out2.image.shape[:2] == (400, 160)


# ---------------------------------------------------------------------------
# L1：STYLES 预设
# ---------------------------------------------------------------------------


class TestStyles:
    def test_all_preset_keys_present(self) -> None:
        expected = {
            "black_sheer",
            "black_sheer_lace",
            "black_pantyhose",
            "gray_sheer",
            "nude_sheer",
            "white_sheer",
            "black_tights",
            "white_tights",
            "stripe_blue_white",
            "stripe_pink_white",
            "stripe_black_white",
            "stripe_rainbow",
            "stripe_sheer_black",
            "knit_cream",
            "knit_gray",
            "fishnet_black",
            "fishnet_over_sheer",
            "polka_black",
            "heart_white",
        }
        assert expected <= set(STYLES.keys())


# ---------------------------------------------------------------------------
# L1：render_stocking
# ---------------------------------------------------------------------------


class TestRenderStocking:
    @pytest.fixture
    def leg(self) -> "stockchart.Leg":
        return make_synthetic_leg()

    def test_nonpositive_height_returns_original(self, leg: "stockchart.Leg") -> None:
        # skin=0 时裸腿原样返回；skin>0 会打皮肤光影（见 TestSkinShading）
        style = replace(STYLES["black_sheer"], shading=Shading(skin=0.0))
        np.testing.assert_array_equal(render_stocking(leg, style, 0).image, leg.image)
        np.testing.assert_array_equal(render_stocking(leg, style, -10).image, leg.image)

    def test_output_shape_preserved(self, leg: "stockchart.Leg") -> None:
        result = render_stocking(leg, STYLES["black_sheer"], 100, seed=0)
        assert result.image.shape == leg.image.shape
        assert result.image.dtype == np.uint8

    def test_perspective_changes_pattern(self, leg: "stockchart.Leg") -> None:
        uniform = StockingStyle(fabric=Ribbed(color=(20, 20, 20), rib_width=18, perspective=0.0))
        cylindrical = StockingStyle(
            fabric=Ribbed(color=(20, 20, 20), rib_width=18, perspective=1.0)
        )
        a = render_stocking(leg, uniform, leg.height, seed=0).image
        b = render_stocking(leg, cylindrical, leg.height, seed=0).image
        assert not np.array_equal(a, b)

    def test_seed_reproducibility(self, leg: "stockchart.Leg") -> None:
        r1 = render_stocking(leg, STYLES["black_sheer"], 150, seed=99)
        r2 = render_stocking(leg, STYLES["black_sheer"], 150, seed=99)
        np.testing.assert_array_equal(r1.image, r2.image)

    def test_different_seeds_differ(self, leg: "stockchart.Leg") -> None:
        r1 = render_stocking(leg, STYLES["black_sheer"], 150, seed=1)
        r2 = render_stocking(leg, STYLES["black_sheer"], 150, seed=2)
        # 同款式不同 seed，结果应有差异（wobble 等随机效果）
        assert not np.array_equal(r1.image, r2.image)

    def test_stocking_area_differs_from_bare(self, leg: "stockchart.Leg") -> None:
        """袜子区域的像素值应与原腿不同。"""
        height_px = 100
        result = render_stocking(leg, STYLES["black_tights"], height_px, seed=0)
        # 腿中心列，袜子区域与原图应有差异
        cx = leg.foot_center_x
        orig_mid = leg.image[leg.height - 10, cx, :3].astype(int)
        result_mid = result.image[leg.height - 10, cx, :3].astype(int)
        assert not np.array_equal(orig_mid, result_mid)

    @pytest.mark.parametrize(
        "style_key",
        [
            "black_sheer",
            "black_sheer_lace",
            "black_pantyhose",
            "stripe_blue_white",
            "knit_cream",
            "fishnet_black",
            "polka_black",
            "heart_white",
        ],
    )
    def test_all_fabric_types_run(self, leg: "stockchart.Leg", style_key: str) -> None:
        """所有 Fabric 种类都能跑完不崩溃，输出尺寸正确。"""
        result = render_stocking(leg, STYLES[style_key], 150, seed=42)
        assert result.image.shape == (leg.height, leg.width, 4)

    def test_full_cover_clips_to_leg_height(self, leg: "stockchart.Leg") -> None:
        """height_px >= leg.height 时整腿覆盖，不越界。"""
        result = render_stocking(leg, STYLES["black_sheer"], leg.height + 100, seed=0)
        assert result.image.shape == leg.image.shape

    @pytest.mark.parametrize("height_px", [0, 100, 300])
    def test_alpha_channel_unchanged(self, leg: "stockchart.Leg", height_px: int) -> None:
        """裸腿、局部穿袜与全覆盖都保留素材的半透明轮廓。"""
        image = leg.image.copy()
        rng = np.random.default_rng(42)
        image[..., 3] = np.where(
            image[..., 3] > 0, rng.integers(1, 256, size=image.shape[:2], dtype=np.uint8), 0
        )
        translucent = replace(leg, image=image)
        result = render_stocking(translucent, STYLES["black_tights"], height_px, seed=0)
        np.testing.assert_array_equal(result.image[..., 3], image[..., 3])
