# pyright: reportPrivateUsage=false

"""基础集成测试：覆盖 L0 素材层与 L1 渲染原语。"""

from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

import stockchart
import stockchart.stocking.render as render_module
from stockchart import (
    STYLES,
    Fishnet,
    LegLibrary,
    Plain,
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
    def test_all_pairs_loaded(self) -> None:
        lib = LegLibrary(seed=0)
        for i in range(1, 14):
            left, _right = lib.pair(f"pair_{i:02d}")
            assert left.pair_id == f"pair_{i:02d}"
        with pytest.raises(KeyError):
            lib.pair("pair_14")

    def test_get_by_id(self) -> None:
        lib = LegLibrary()
        leg = lib.get("leg_01")
        assert leg.leg_id == "leg_01"
        assert leg.side == "left"
        assert leg.height == 720

    def test_get_unknown_raises(self) -> None:
        lib = LegLibrary()
        with pytest.raises(KeyError):
            lib.get("leg_99")

    def test_pair_returns_left_right(self) -> None:
        lib = LegLibrary()
        left, right = lib.pair("pair_01")
        assert left.side == "left"
        assert right.side == "right"
        assert left.pair_id == "pair_01"
        assert right.pair_id == "pair_01"

    def test_pair_unknown_raises(self) -> None:
        lib = LegLibrary()
        with pytest.raises(KeyError):
            lib.pair("pair_99")

    def test_alternate_length(self) -> None:
        lib = LegLibrary(seed=42)
        legs = lib.alternate(10)
        assert len(legs) == 10

    def test_alternate_left_right_pattern(self) -> None:
        lib = LegLibrary(seed=42)
        legs = lib.alternate(6)
        for i, leg in enumerate(legs):
            expected_side = "left" if i % 2 == 0 else "right"
            assert leg.side == expected_side, f"index {i}: expected {expected_side}, got {leg.side}"

    def test_sample_pairs_length(self) -> None:
        lib = LegLibrary(seed=42)
        pairs = lib.sample_pairs(5)
        assert len(pairs) == 5
        for left, right in pairs:
            assert left.side == "left"
            assert right.side == "right"
            assert left.pair_id == right.pair_id

    def test_seed_determinism(self) -> None:
        """同 seed 的 alternate 结果相同。"""
        lib1 = LegLibrary(seed=7)
        lib2 = LegLibrary(seed=7)
        ids1 = [leg.leg_id for leg in lib1.alternate(8)]
        ids2 = [leg.leg_id for leg in lib2.alternate(8)]
        assert ids1 == ids2

    def test_cache_returns_same_object(self) -> None:
        lib = LegLibrary()
        a = lib.get("leg_05")
        b = lib.get("leg_05")
        assert a is b

    def test_ids_are_listed(self) -> None:
        lib = LegLibrary()
        assert len(lib.leg_ids) == 26
        assert lib.leg_ids[0] == "leg_01"
        assert lib.leg_ids[-1] == "leg_26"
        assert len(lib.pair_ids) == 13
        assert lib.pair_ids[0] == "pair_01"
        assert lib.pair_ids[-1] == "pair_13"
        assert "26 legs / 13 pairs" in repr(lib)

    def test_alternate_paired_uses_same_pair(self) -> None:
        legs = LegLibrary(seed=7).alternate(6, paired=True)
        for i in range(0, len(legs), 2):
            assert legs[i].pair_id == legs[i + 1].pair_id
            assert legs[i].side == "left"
            assert legs[i + 1].side == "right"

    def test_alternate_without_pairs_uses_different_pairs(self) -> None:
        legs = LegLibrary(seed=7).alternate(6)
        assert len({leg.pair_id for leg in legs[:6]}) == 6

    def test_preview_returns_rgb_image(self) -> None:
        image = LegLibrary().preview(scale=0.1)
        assert image.mode == "RGB"
        assert image.width > 0
        assert image.height > 0


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

    def test_raster_at_high_density_renders_at_target(self) -> None:
        leg = LegLibrary().get("leg_01")
        img = leg.raster_at(6)
        assert img.shape == (leg.height * 6, leg.width * 6, 4)
        assert img[:, :, 3].min() == 0
        assert img[:, :, 3].max() > 250

    def test_render_stocking_vector_scale(self) -> None:
        leg = LegLibrary().get("leg_01")
        out = render_stocking(leg, STYLES["black_sheer"], 400, seed=1, scale=2)
        assert out.image.shape == (1440, leg.width * 2, 4)
        assert out.pixels_per_unit == 2

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
    def test_from_png_returns_leg(self, tmp_path: Path) -> None:
        leg = make_synthetic_leg(300, 100)
        png_path = tmp_path / "test_leg.png"
        Image.fromarray(leg.image).save(png_path)

        loaded = load_leg(png_path)
        assert loaded.width == 100
        assert loaded.height == 300
        assert loaded.leg_id is None
        assert loaded.side is None

    def test_explicit_foot_center(self, tmp_path: Path) -> None:
        leg = make_synthetic_leg(200, 80)
        png_path = tmp_path / "test_leg2.png"
        Image.fromarray(leg.image).save(png_path)

        loaded = load_leg(png_path, foot_center_x=40)
        assert loaded.foot_center_x == 40

    def test_foot_center_out_of_range(self, tmp_path: Path) -> None:
        leg = make_synthetic_leg(200, 80)
        png_path = tmp_path / "test_leg3.png"
        Image.fromarray(leg.image).save(png_path)

        with pytest.raises(ValueError, match="foot_center_x"):
            load_leg(png_path, foot_center_x=80)


# ---------------------------------------------------------------------------
# L1：StockingStyle 参数校验
# ---------------------------------------------------------------------------


class TestStockingStyleValidation:
    def test_plain_opacity_range(self) -> None:
        with pytest.raises(ValueError):
            Plain(color=(0, 0, 0), opacity=1.5)

    def test_plain_bad_color(self) -> None:
        with pytest.raises(ValueError):
            Plain(color=(300, 0, 0))  # type: ignore[arg-type]

    def test_striped_empty_raises(self) -> None:
        with pytest.raises(ValueError):
            Striped(stripes=())

    def test_fishnet_bad_cell(self) -> None:
        with pytest.raises(ValueError):
            Fishnet(color=(0, 0, 0), cell=-1)

    def test_welt_bad_height(self) -> None:
        with pytest.raises(ValueError):
            Welt(height=-5)

    def test_lace_bad_scallop(self) -> None:
        with pytest.raises(ValueError):
            Lace(scallop=0)

    def test_fade_bad_length(self) -> None:
        with pytest.raises(ValueError):
            Fade(length=0)

    def test_shading_cel_steps_invalid(self) -> None:
        with pytest.raises(ValueError):
            Shading(cel_steps=5)

    def test_shading_skin_negative(self) -> None:
        with pytest.raises(ValueError):
            Shading(skin=-0.1)


class TestSkinShading:
    """皮肤光影：skin=0 不动皮肤，skin>0 时袜口以上与裸腿都受影响。"""

    def test_skin_zero_leaves_bare_leg_untouched(self) -> None:
        leg = make_synthetic_leg(720, 160)
        style = replace(STYLES["black_sheer"], shading=Shading(skin=0.0))
        out = render_stocking(leg, style, 400, seed=1)
        top = leg.height - 400
        # 袜口以上 20px 之外应与素材完全一致
        assert (out.image[: top - 20] == leg.image[: top - 20]).all()

    def test_skin_zero_returns_bare_leg_as_is(self) -> None:
        leg = make_synthetic_leg(720, 160)
        style = replace(STYLES["black_sheer"], shading=Shading(skin=0.0))
        out = render_stocking(leg, style, 0, seed=1)
        assert (out.image == leg.image).all()

    def test_skin_shades_bare_leg(self) -> None:
        leg = make_synthetic_leg(720, 160)
        style = replace(STYLES["black_sheer"], shading=Shading(skin=0.5))
        out = render_stocking(leg, style, 0, seed=1)
        diff = np.abs(out.image.astype(int) - leg.image.astype(int))[:, :, :3]
        assert diff.max() > 20
        # 左侧缘（边缘阴影）与高光带（u≈-0.35）都要变
        assert diff[:, leg.width // 2 - 32].max() > 0
        assert diff[:, leg.width // 2 - 11].max() > 0


class TestShadingLayers:
    def test_shadow_color_is_not_overwritten_by_highlight(self) -> None:
        from stockchart.stocking.render import _render_shading

        H, W = 20, 40
        alpha = np.ones((H, W))
        u = np.tile(np.linspace(-1.0, 1.0, W), (H, 1))
        style = Shading(
            rim_shadow=0.5,
            highlight=0.0,
            shadow_color=(150, 140, 180, 180),
        )
        shadow, highlight = _render_shading(style, np.ones((H, W, 4)), alpha, u, 0, H, W)
        # 阴影 RGB 必须保持配置的蓝色分量，不能被高光强度占用
        assert shadow[..., 2] == pytest.approx(180 / 255)
        assert not highlight.any()

    def test_dotted_scatter_depends_on_seed(self) -> None:
        from stockchart.stocking.render import _dot_mask

        H, W = 80, 80
        abs_x = np.tile(np.linspace(-30.0, 30.0, W), (H, 1))
        ys = np.arange(H, dtype=float)[:, None] * np.ones((1, W))
        a = _dot_mask(abs_x, ys, 10.0, 3.0, "scatter", "dot", np.random.default_rng(1))
        b = _dot_mask(abs_x, ys, 10.0, 3.0, "scatter", "dot", np.random.default_rng(2))
        assert not np.array_equal(a, b)


class TestRenderScale:
    """倍率渲染：在 scale 倍像素空间生成，而非放大成品图。"""

    def test_dims_and_metadata_scale(self) -> None:
        leg = make_synthetic_leg(720, 160)
        out = render_stocking(leg, STYLES["black_sheer"], 400, seed=1, scale=2)
        # 图像按倍率加密，设计坐标（供上层布局使用）保持不变
        assert out.image.shape[:2] == (1440, 320)
        assert out.pixels_per_unit == 2
        assert (out.height, out.width) == (720, 160)
        assert out.foot_center_x == leg.foot_center_x

    def test_bad_scale(self) -> None:
        leg = make_synthetic_leg(720, 160)
        with pytest.raises(ValueError):
            render_stocking(leg, STYLES["black_sheer"], 400, scale=0)
        with pytest.raises(ValueError):
            render_stocking(leg, STYLES["black_sheer"], 400, scale=float("nan"))

    def test_bad_density(self) -> None:
        leg = make_synthetic_leg(720, 160)
        with pytest.raises(ValueError):
            leg.at_density(0)

    def test_scale2_matches_scale1_when_downsampled(self) -> None:
        leg = make_synthetic_leg(720, 160)
        a = render_stocking(leg, STYLES["stripe_blue_white"], 400, seed=1).image
        b = render_stocking(leg, STYLES["stripe_blue_white"], 400, seed=1, scale=2).image
        small = np.asarray(
            Image.fromarray(b).resize((leg.width, leg.height), Image.Resampling.LANCZOS)
        ).astype(int)
        diff = np.abs(small[:, :, :3] - a.astype(int)[:, :, :3])
        # 高频条纹在降采样时会有少量差异，整体应高度一致
        assert diff.mean() < 12

    def test_internal_supersampling_is_used(self, monkeypatch: pytest.MonkeyPatch) -> None:
        leg = make_synthetic_leg(720, 160)
        style = STYLES["fishnet_black"]
        supersampled = render_stocking(leg, style, 400, seed=1).image
        monkeypatch.setattr(render_module, "_SUPERSAMPLE", 1)
        direct = render_stocking(leg, style, 400, seed=1).image
        assert supersampled.shape == direct.shape
        # 二值网线边缘经过 2× 生成再降采样后不应与直接生成完全相同
        assert not np.array_equal(supersampled, direct)

    def test_bare_leg_scale_doubles_image(self) -> None:
        leg = make_synthetic_leg(720, 160)
        out = render_stocking(leg, STYLES["black_sheer"], 0, scale=2)
        assert out.image.shape[:2] == (1440, 320)
        assert out.pixels_per_unit == 2

    def test_dense_asset_is_downsampled_not_upscaled(self) -> None:
        """2 倍密素材在 1 倍输出下应降采样，设计坐标不变。"""
        base = make_synthetic_leg(720, 160)
        hi_img = np.asarray(Image.fromarray(base.image).resize((base.width * 2, base.height * 2)))
        hi = replace(base, image=hi_img, pixels_per_unit=2.0)
        out = render_stocking(hi, STYLES["black_sheer"], 400, seed=1)
        assert out.image.shape[:2] == (720, 160)
        assert out.pixels_per_unit == 1.0
        # 2 倍输出则直接用素材本身，不再放大
        out2 = render_stocking(hi, STYLES["black_sheer"], 400, seed=1, scale=2)
        assert out2.image.shape[:2] == (1440, 320)


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

    def test_styles_immutable(self) -> None:
        with pytest.raises(TypeError):
            STYLES["new_key"] = StockingStyle(fabric=Plain(color=(0, 0, 0)))  # type: ignore[index]


# ---------------------------------------------------------------------------
# L1：render_stocking
# ---------------------------------------------------------------------------


class TestRenderStocking:
    @pytest.fixture
    def leg(self) -> "stockchart.Leg":
        return make_synthetic_leg()

    def test_zero_height_returns_original(self, leg: "stockchart.Leg") -> None:
        # skin=0 时裸腿原样返回；skin>0 会打皮肤光影（见 TestSkinShading）
        style = replace(STYLES["black_sheer"], shading=Shading(skin=0.0))
        result = render_stocking(leg, style, 0)
        np.testing.assert_array_equal(result.image, leg.image)

    def test_negative_height_returns_original(self, leg: "stockchart.Leg") -> None:
        style = replace(STYLES["black_sheer"], shading=Shading(skin=0.0))
        result = render_stocking(leg, style, -10)
        np.testing.assert_array_equal(result.image, leg.image)

    def test_output_shape_preserved(self, leg: "stockchart.Leg") -> None:
        result = render_stocking(leg, STYLES["black_sheer"], 100, seed=0)
        assert result.image.shape == leg.image.shape
        assert result.image.dtype == np.uint8

    def test_metadata_preserved(self, leg: "stockchart.Leg") -> None:
        result = render_stocking(leg, STYLES["stripe_blue_white"], 80, seed=0)
        assert result.width == leg.width
        assert result.height == leg.height
        assert result.foot_center_x == leg.foot_center_x

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

    def test_alpha_channel_unchanged(self, leg: "stockchart.Leg") -> None:
        """渲染后 alpha 通道应与原腿一致。"""
        result = render_stocking(leg, STYLES["black_tights"], 100, seed=0)
        np.testing.assert_array_equal(result.image[..., 3], leg.image[..., 3])
