# pyright: reportPrivateUsage=false

"""墨线掩码的滤波与局部计算测试。"""

import numpy as np
import pytest
from numpy.typing import NDArray
from PIL import Image, ImageFilter

from stockchart.stocking.ink import _ink_mask, _min_filter


@pytest.mark.parametrize(("shape", "win"), [((17, 23), 3), ((31, 47), 13), ((53, 61), 25)])
def test_min_filter_matches_pillow(shape: tuple[int, int], win: int) -> None:
    rng = np.random.default_rng(120 + win)
    mask = rng.integers(0, 256, size=shape, dtype=np.uint8)

    expected = np.asarray(Image.fromarray(mask).filter(ImageFilter.MinFilter(win)))

    np.testing.assert_array_equal(_min_filter(mask, win), expected)


def test_ink_mask_active_region_matches_full_calculation() -> None:
    rng = np.random.default_rng(72)
    height, width = 180, 72
    src = np.ones((height, width, 4), dtype=np.float64)
    src[..., :3] = rng.uniform(0.86, 1.0, size=(height, width, 3))
    src[60:68, 20:53, :3] *= 0.72
    alpha = np.zeros((height, width), dtype=np.float64)
    alpha[:, 4:-5] = 1.0
    active = np.zeros((height, width), dtype=np.bool_)
    active[70:168, 10:63] = True

    full = _ink_mask(src, alpha, scale=2.0)
    cropped = _ink_mask(src, alpha, scale=2.0, active=active)

    np.testing.assert_array_equal(cropped[active], full[active])
    assert not cropped[~active].any()


def test_ink_mask_empty_active_region_is_zero() -> None:
    src = np.ones((20, 30, 4), dtype=np.float64)
    alpha = np.ones((20, 30), dtype=np.float64)
    active: NDArray[np.bool_] = np.zeros((20, 30), dtype=np.bool_)

    assert not _ink_mask(src, alpha, active=active).any()
