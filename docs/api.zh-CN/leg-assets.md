# L0 — 腿部素材

← [API 索引](index.md) · 相关：[L1 — 渲染原语](rendering.md) · [L2 — 自由柱状图](barplot.md)

![内置腿素材目录](../images/leg_catalog.png)

26 条腿 / 13 对，每条腿都是透明 SVG。编号与配对一经发布不再变动。

| pair | 左腿 | 右腿 | 设计宽度 |
| --- | --- | --- | --- |
| pair_01 | leg_01 | leg_02 | 169 / 159 |
| pair_02 | leg_03 | leg_04 | 149 / 149 |
| pair_03 | leg_05 | leg_06 | 152 / 148 |
| pair_04 | leg_07 | leg_08 | 179 / 173 |
| pair_05 | leg_09 | leg_10 | 165 / 173 |
| pair_06 | leg_11 | leg_12 | 166 / 183 |
| pair_07 | leg_13 | leg_14 | 178 / 167 |
| pair_08 | leg_15 | leg_16 | 176 / 159 |
| pair_09 | leg_17 | leg_18 | 159 / 166 |
| pair_10 | leg_19 | leg_20 | 170 / 169 |
| pair_11 | leg_21 | leg_22 | 169 / 158 |
| pair_12 | leg_23 | leg_24 | 181 / 145 |
| pair_13 | leg_25 | leg_26 | 145 / 150 |

```python
@dataclass(slots=True, frozen=True)
class Leg:
    """一条腿部素材：定位元数据 + 矢量源（或 RGBA 像素）。

    宽高、足底中心等元数据一律使用**设计像素**（腿高 720 的坐标系）。内置素材
    带 `svg` 矢量源：`image` 只是设计尺寸的布局预览，真正渲染时由
    `render_stocking(scale=)` 按目标倍率重新栅格化；外部 PNG 素材没有矢量源，
    `image` 就是原始位图。

    Attributes:
        image: (H, W, 4) uint8 RGBA；脚在图像底端、素材正放。内置素材为设计
            尺寸，外部素材为 PNG 原尺寸。
        width: 设计像素宽。
        height: 设计像素高。
        foot_center_x: 足底中心在设计坐标系里的 x，放置对齐的锚点。
        pixels_per_unit: `image` 像素 / 设计像素。内置素材为 1（布局预览），
            外部素材为 1。
        leg_id: 内置素材编号（如 "leg_03"）；外部素材为 None。
        pair_id: 所属配对编号（如 "pair_02"）；外部素材为 None。
        side: "left" / "right"；外部素材为 None。
        svg: 内置透明 SVG 源；外部素材为 None。渲染时按目标倍率栅格化。

    Raises:
        ValueError: 宽高非正、pixels_per_unit 非正、foot_center_x 越界，
            或 image 不是与设计尺寸/密度匹配的 uint8 RGBA。
    """

    image: np.ndarray
    width: int
    height: int
    foot_center_x: int
    pixels_per_unit: float = 1.0
    leg_id: str | None = None
    pair_id: str | None = None
    side: Literal["left", "right"] | None = None
    svg: bytes | None = None

    def raster_at(self, pixels_per_unit: float) -> np.ndarray:
        """按目标密度把矢量源直接渲染成位图，并缓存在当前 Leg 上。

        Args:
            pixels_per_unit: 目标像素 / 设计像素。

        Returns:
            (height × pixels_per_unit, width × pixels_per_unit, 4) uint8 RGBA。

        Raises:
            ValueError: pixels_per_unit 不是正的有限数，或素材没有矢量源。
        """

    def at_density(self, pixels_per_unit: float) -> Leg:
        """返回指定密度下可直接绘制的 Leg，已有缓存位图时复用。

        Args:
            pixels_per_unit: 目标像素 / 设计像素。

        Returns:
            新的 Leg：`image` 为目标密度、`pixels_per_unit` 同步更新；设计
            元数据与 SVG 源保持不变。

        Raises:
            ValueError: pixels_per_unit 不是正的有限数，或素材没有矢量源。
        """
```

```python
class LegLibrary:
    """内置腿部素材库（26 条腿 / 13 对）。

    所有 Leg 对象在首次访问时懒加载并缓存；反复调用 get/pair 不会重复读磁盘。
    seed 只影响自动选腿顺序，不影响素材本身。

    Args:
        seed: 后续自动选腿的随机源；不传则每次运行随机。

    Raises:
        ValueError: 打包的 legs.json 缺失或校验失败。
    """

    def __init__(self, *, seed: int | None = None) -> None: ...

    @property
    def leg_ids(self) -> tuple[str, ...]:
        """全部腿编号。

        Returns:
            按编号升序排列的 leg_id 元组。
        """

    @property
    def pair_ids(self) -> tuple[str, ...]:
        """全部配对编号。

        Returns:
            按编号升序排列的 pair_id 元组。
        """

    def get(self, leg_id: str) -> Leg:
        """按编号取一条腿（如 leg_03）。

        Args:
            leg_id: 内置腿编号，格式为 "leg_NN"。

        Returns:
            对应的 Leg 实例（懒加载）。

        Raises:
            KeyError: 编号不存在。
        """

    def pair(self, pair_id: str) -> tuple[Leg, Leg]:
        """取一对腿，返回 (左腿, 右腿)。

        Args:
            pair_id: 配对编号，格式为 "pair_NN"。

        Returns:
            (左腿, 右腿)。

        Raises:
            KeyError: 配对编号不存在。
        """

    def alternate(self, n: int, *, paired: bool = False) -> list[Leg]:
        """按左、右、左、右……的顺序选出 n 条腿。

        素材对超过 13 对后从已用素材继续复用。

        Args:
            n: 需要的腿数。
            paired: False（默认）时每条腿来自不同素材对；True 时相邻两条腿
                组成一对（左、右），素材对之间按 seed 伪随机且优先不重复。
                n 为奇数时最后一对只取左腿。

        Returns:
            长度为 n 的 Leg 列表，偶数下标为左腿，奇数下标为右腿（0-based）。

        Raises:
            ValueError: n 为负数。
        """

    def sample_pairs(self, n: int) -> list[tuple[Leg, Leg]]:
        """选出 n 对完整素材（成对布局用），选取规则同 alternate。

        Args:
            n: 需要的对数。

        Returns:
            长度为 n 的 (左腿, 右腿) 列表。

        Raises:
            ValueError: n 为负数。
        """

    def preview(self, *, scale: float = 0.5) -> PIL.Image.Image:
        """生成全部内置素材的目录图，供浏览和选型。

        按配对分组排列（每行 4 对），标注 pair_id、leg_id 与左右脚。
        这是浏览工具，不在渲染热路径；首次调用会加载全部腿素材。

        Args:
            scale: 预览图相对设计尺寸的倍率，须为正数。

        Returns:
            RGB 模式的 PIL Image。

        Raises:
            ValueError: scale 不是正的有限数。
        """
```

```python
def load_leg(
    png: str | Path,
    *,
    foot_center_x: int | None = None,
) -> Leg:
    """从 PNG 加载自定义腿素材，用法与内置素材一致（编号字段为 None）。

    Args:
        png: 带透明通道的 PNG 路径；要求脚位于图像底端（与内置素材同方向）。
        foot_center_x: 足底中心 x 坐标。缺省按底部若干行的 alpha 质心自动估计。

    Returns:
        自定义素材的 Leg 实例，可直接传入各层接口。

    Raises:
        OSError: 文件无法打开或不是可识别的图片。
        ValueError: foot_center_x 不在图像宽度范围内。
    """
```

## 最小示例

```python
from stockchart import LegLibrary

library = LegLibrary(seed=0)
leg = library.get("leg_03")  # 单条腿
left, right = library.pair("pair_02")  # 一对腿（左、右）
print(leg.width, leg.height, leg.foot_center_x)
print(library.leg_ids[:3], library.pair_ids[:3])
```
