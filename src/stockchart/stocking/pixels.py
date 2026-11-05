"""渲染内部的浮点数组类型；生产路径使用 float32，兼容开发工具的 float64。"""

import numpy as np
from numpy.typing import NDArray

type FloatArray = NDArray[np.float32] | NDArray[np.float64]
