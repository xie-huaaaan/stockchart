"""袜区裁剪与图案查表的几何、透明度和可复现约束。"""

import numpy as np

from stockchart import Fishnet, Plain, Stripe, Striped
from stockchart.stocking.fabric import render_fabric
from stockchart.stocking.geometry import column_profile, curve_dip
from stockchart.stocking.patterns import motif_mask, stripe_pixels


def test_cropping_preserves_stretch_and_fishnet_phase() -> None:
    src = np.ones((120, 60, 4), dtype=np.float32)
    src[..., 3] = 0
    src[:50, 2:58, 3] = 1
    src[50:, 18:42, 3] = 1
    alpha = src[..., 3]
    profile = column_profile(alpha)
    dip = curve_dip(profile, alpha, 0.2)
    plain = Plain(color=(30, 30, 30), stretch=0.8)
    for fabric in (plain, Fishnet(color=(20, 20, 20), underlay=plain)):
        full = render_fabric(fabric, src, alpha, profile, 0, 120, 60, np.random.default_rng(3), dip)
        cropped = render_fabric(
            fabric, src, alpha, profile, 75, 120, 60, np.random.default_rng(3), dip
        )
        assert not cropped[:75].any()
        np.testing.assert_allclose(cropped[75:], full[75:], atol=1e-7)


def test_stripe_lookup_is_periodic_and_retains_alpha() -> None:
    style = Striped(stripes=(Stripe((240, 20, 30), 6, 0.25), Stripe((20, 30, 240), 10, 0.75)))
    rows = np.array([[2.0, 8.0, 18.0, 24.0]], dtype=np.float32)
    pixels = stripe_pixels(style, rows)
    np.testing.assert_allclose(pixels[0, :2], pixels[0, 2:], atol=1e-6)
    np.testing.assert_allclose(pixels[0, :, 3], [0.25, 0.75, 0.25, 0.75], atol=1e-6)
    assert pixels[0, 0, 0] > pixels[0, 0, 2]
    assert pixels[0, 1, 2] > pixels[0, 1, 0]


def test_motif_lookup_preserves_orientation_and_scale() -> None:
    x = np.array([[0, 0.8, 0.8, 0, 3]], dtype=np.float32)
    y = np.array([[0, -0.8, 0.8, 2, 0]], dtype=np.float32)
    for shape in ("heart", "star"):
        first = motif_mask(x, y, 1, shape)
        np.testing.assert_array_equal(first, motif_mask(x * 8, y * 8, 8, shape))
        assert first[0, 0] == 1
        assert first[0, 3] == first[0, 4] == 0
    heart = motif_mask(x, y, 1, "heart")
    assert heart[0, 1] == 1
    assert heart[0, 2] == 0
