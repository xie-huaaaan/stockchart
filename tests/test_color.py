from typing import cast

import numpy as np
import pytest

from stockchart import Canvas, Color, Plain
from stockchart.color import color_alpha, color_rgb, skia_color


def test_color_components_are_integers_in_every_rendering_path() -> None:
    for component in (10.8, 10.0, float("nan"), float("inf"), True, np.float32(10.0)):
        color = cast(Color, (component, 20, 30))
        with pytest.raises(ValueError, match="整数"):
            Plain(color=color)
        with pytest.raises(ValueError, match="整数"):
            Canvas(1, 1, background=color)

    color = cast(Color, (np.uint8(10), np.int64(20), 30, 128))
    assert skia_color(color) == skia_color((10, 20, 30, 128))
    np.testing.assert_allclose(color_rgb(color), np.array([10, 20, 30]) / 255)
    assert color_alpha(color) == 128 / 255
