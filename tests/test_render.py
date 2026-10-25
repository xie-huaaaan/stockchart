"""基础集成测试：覆盖 L0 素材层与 L1 渲染原语。"""

from pathlib import Path

import numpy as np
import pytest
from PIL import Image

import stockchart
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
        foot_width=40,
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

    def test_explicit_foot_params(self, tmp_path: Path) -> None:
        leg = make_synthetic_leg(200, 80)
        png_path = tmp_path / "test_leg2.png"
        Image.fromarray(leg.image).save(png_path)

        loaded = load_leg(png_path, foot_center_x=40, foot_width=30)
        assert loaded.foot_center_x == 40
        assert loaded.foot_width == 30


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
        result = render_stocking(leg, STYLES["black_sheer"], 0)
        np.testing.assert_array_equal(result.image, leg.image)

    def test_negative_height_returns_original(self, leg: "stockchart.Leg") -> None:
        result = render_stocking(leg, STYLES["black_sheer"], -10)
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
