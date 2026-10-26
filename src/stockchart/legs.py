"""L0 素材层：腿部素材的数据结构。"""

from dataclasses import dataclass
from typing import Literal

import numpy as np
from numpy.typing import NDArray


@dataclass(slots=True, frozen=True)
class Leg:
    """一条腿部素材：RGBA 像素与定位元数据。

    宽高、足底中心、足宽等元数据一律使用**设计像素**（腿高 720 的坐标系）；
    图像可能比设计尺寸更密（`pixels_per_unit` 描述这份关系），高分辨率素材
    因此不需要改任何上层坐标。

    Attributes:
        image: (H, W, 4) uint8；脚在图像底端、素材正放。
        width: 设计像素宽。
        height: 设计像素高。
        foot_center_x: 足底中心在设计坐标系里的 x，放置对齐的锚点。
        foot_width: 足底宽度（设计像素）。
        pixels_per_unit: 图像像素 / 设计像素。1 表示图像即设计尺寸；
            2 表示图像是设计尺寸的两倍密（渲染时可直接降采样）。
        leg_id: 内置素材编号（如 "leg_03"）；外部素材为 None。
        pair_id: 所属配对编号（如 "pair_02"）；外部素材为 None。
        side: "left" / "right"；外部素材为 None。
    """

    image: NDArray[np.uint8]
    width: int
    height: int
    foot_center_x: int
    foot_width: int
    pixels_per_unit: float = 1.0
    leg_id: str | None = None
    pair_id: str | None = None
    side: Literal["left", "right"] | None = None
