"""L0 素材层：腿部素材的数据结构。"""

from dataclasses import dataclass
from typing import Literal

import numpy as np
from numpy.typing import NDArray


@dataclass(slots=True, frozen=True)
class Leg:
    """一条腿部素材：RGBA 像素与定位元数据。

    Attributes:
        image: (H, W, 4) uint8；脚在图像底端、素材正放。
        width: 像素宽。
        height: 像素高。
        foot_center_x: 足底中心在图内的 x 坐标，放置对齐的锚点。
        foot_width: 足底宽度（像素）。
        leg_id: 内置素材编号（如 "leg_03"）；外部素材为 None。
        pair_id: 所属配对编号（如 "pair_02"）；外部素材为 None。
        side: "left" / "right"；外部素材为 None。
    """

    image: NDArray[np.uint8]
    width: int
    height: int
    foot_center_x: int
    foot_width: int
    leg_id: str | None = None
    pair_id: str | None = None
    side: Literal["left", "right"] | None = None
