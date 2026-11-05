# L1 — 渲染原语

← [API 索引](index.md) · 相关：[L0 — 腿部素材](leg-assets.md) · [L2 — 自由柱状图](barplot.md)

## 丝袜样式

袜子 = 袜身种类（`Plain` / `Striped` / `Ribbed` / `Fishnet` / `Dotted`）+ 上沿（`Bare` / `Welt` / `Lace` / `Fade`）+ 光影（`Shading`）。三者都是 `dataclass(slots=True, frozen=True, kw_only=True)`，非法参数在构造时抛 `ValueError`。长度单位均为设计像素，指腿正面处的尺寸（两侧按 `perspective` 做圆柱透视压缩，默认 0.8）。颜色为 `Color`；带 alpha 分量时，alpha 乘到对应的 opacity 上。

```python
@dataclass(slots=True, frozen=True, kw_only=True)
class StockingStyle:
    fabric: Fabric
    top: TopEdge = Welt()
    shading: Shading = Shading()


type Fabric = Plain | Striped | Ribbed | Fishnet | Dotted
type TopEdge = Bare | Welt | Lace | Fade
```

**袜身种类**

| 类 | 含义 | 字段（默认值） |
| --- | --- | --- |
| `Plain` | 纯色袜：极薄透肉 ~ 完全不透 | `color`；`opacity`(0.6) 腿正面遮盖率；`rim`(1.0) 侧缘变厚变不透的程度，0 关闭；`stretch`(0.5) 腿越粗袜子被撑得越薄越透的程度，0 关闭 |
| `Striped` | 横条纹 | `stripes: tuple[Stripe, ...]` 一个周期内从上到下的条带，`Stripe(color, width, opacity=1.0)`；`offset`(0) 相位。条纹从袜口往下排 |
| `Ribbed` | 竖罗纹针织 | `color`；`opacity`(1.0)；`rib_width`(6) 罗纹间距；`depth`(0.35) 明暗对比；`perspective`(0.8) 透视压缩 |
| `Fishnet` | 网袜 | `color`；`cell`(14) 网眼大小；`line_width`(1.6)；`angle`(45) 45 菱形、0 方格；`underlay: Plain \| None`(None) 底下叠的一层袜；`perspective`(0.8) 透视压缩 |
| `Dotted` | 印花 | `base: Plain` 底袜（必填）；`color`；`shape`("dot") `"dot"/"heart"/"star"`；`size`(3) 图案半径；`spacing`(18)；`layout`("grid") `"grid"` 错位网格 / `"scatter"` 按 seed 随机散布；`opacity`(1.0)；`perspective`(0.8) 透视压缩 |

罗纹、网眼、印花的横向疏密使用圆柱透视：`perspective=0` 为均匀间距，`1` 为完全按圆柱弧长压缩，默认 0.8。

**上沿**

| 类 | 含义 | 字段（默认值） |
| --- | --- | --- |
| `Bare` | 平口，只有一条细边线 | 无 |
| `Welt` | 松紧袜口：一圈加厚条带 | `height`(20)；`color`(None：取袜身主色加深一档)；`opacity`(None：双层织物视为不透明)；`pinch`(0.4) 袜口上方皮肤被勒出的浅阴影，0 关闭 |
| `Lace` | 蕾丝边 | `height`(28)；`scallop`(28，最小 20) 波浪周期；`color`(None：取袜身主色)；`opacity`(0.85，镂空织物透出皮肤)；`holes`(True) 孔点图案 |
| `Fade` | 连裤袜式渐隐，无明显边 | `length`(60) 渐变区长度 |

**数据高度的定义**：腿中线处袜口顶端到脚端的距离；`Lace` 按波浪平均位置；`Fade` 的渐隐自袜口顶端向下 `length` 像素内完成（顶端透明、无边界线）。横向线条（条纹、袜口、蕾丝、网线）均沿 `Shading.curve` 的弧线下弯，织物顶边与上沿线条的弧形处处重合。

**上沿静区**：`Welt` / `Lace` 条带覆盖区域的袜身图案（条纹、罗纹、网格、印花）从条带下沿起算——`Welt` 沿其底沿弧线，`Lace` 沿波浪边缘逐列贴合；条带直接覆于皮肤之上（条带本身即该区域的织物）：`Welt` 为双层织物、不透明；`Lace` 为镂空织物、默认 0.85 透出皮肤，孔点处更透。

**光影（所有种类共用）**

| 字段 | 默认 | 含义 |
| --- | --- | --- |
| `curve` | 0.12 | 环形线条（上沿、横纹、网格）下弯程度（略俯视），0 为直线 |
| `rim_shadow` | 0.5 | 背光侧边缘压暗程度 |
| `shadow_color` | (150, 140, 180, 180) | 阴影的正片叠底色（偏冷的淡紫，动漫常用） |
| `highlight` | 0.35 | 竖向高光强度，0 关闭 |
| `highlight_pos` | -0.35 | 高光在腿宽方向的位置，-1 左缘 ~ 1 右缘；全图共用光源，左右腿不镜像 |
| `highlight_width` | 0.18 | 高光半宽（腿半宽的比例） |
| `cel_steps` | 0 | 0 平滑渐变；2、3 为动漫式分阶色块 |
| `ink` | 1.0 | 素材描边透出的强度（深色袜上自动变深） |
| `wobble` | 0.6 | 新增线条（袜口、蕾丝边）的手绘抖动幅度（像素），由 seed 控制 |
| `skin` | 0.5 | 袜口以上裸露皮肤的光影强度（相对袜子上的强度）：0 只作用于袜子（旧观感），1 与袜子同等；裸腿同样参与 |
| `skin_shadow_color` | (206,168,158,200) | 皮肤上的阴影色。袜子用偏冷的 `shadow_color`，皮肤用冷紫会显脏，故单独取偏暖的肤色阴影 |

```python
STYLES: Mapping[str, StockingStyle]
"""只读预设注册表，见下表。"""
```

| 键名 | 名称 | 键名 | 名称 |
| --- | --- | --- | --- |
| `black_sheer`（默认） | 黑丝 | `stripe_blue_white` | 蓝白条纹 |
| `black_sheer_lace` | 黑丝蕾丝边 | `stripe_pink_white` | 粉白条纹 |
| `black_pantyhose` | 黑色连裤袜 | `stripe_black_white` | 黑白条纹 |
| `gray_sheer` | 灰丝（参考图配色） | `stripe_rainbow` | 彩虹条纹 |
| `nude_sheer` | 肉丝 | `stripe_sheer_black` | 黑丝暗纹 |
| `white_sheer` | 白丝（蕾丝边） | `knit_cream` | 米白针织 |
| `black_tights` | 黑色厚袜 | `knit_gray` | 灰色针织 |
| `white_tights` | 白色厚袜 | `fishnet_black` | 黑网袜 |
| `polka_black` | 黑丝波点 | `fishnet_over_sheer` | 网袜叠黑丝 |
| `heart_white` | 白丝爱心 | | |

```python
type StyleLike = StockingStyle | str
"""单个样式：StockingStyle 实例或 STYLES 键名。"""

type StyleSeq = StyleLike | Sequence[StyleLike]
"""样式参数：单个样式，或按位置循环的样式列表（循环语义见 [L3 — 布局封装](layout.md) / [L4 — bar() 与 mirror_bar()](charts.md)）。"""
```

[L2](barplot.md) 的 `add_bar` 只接受单个 `StyleLike`；L3/L4 的批量方法接受 `StyleSeq`，默认 `DEFAULT_STOCKING_STYLE = "black_sheer"`。

## render_stocking

```python
def render_stocking(
    leg: Leg,
    style: StockingStyle,
    height_px: int,
    *,
    seed: int | None = None,
    scale: float = 1.0,
) -> Leg:
    """给腿穿丝袜：从脚端向上覆盖 height_px 像素。

    Args:
        leg: 待渲染的腿素材。
        style: 丝袜样式，可从 STYLES 预设取得。
        height_px: 丝袜上沿到脚端的像素数（设计像素）。小于等于 0 时为裸腿
            （`Shading.skin` 大于 0 时裸腿仍按皮肤光影渲染，否则原样返回）；
            不小于 leg.height 时整腿全盖。
        seed: 纹理类随机效果的随机源。
        scale: 输出倍率。>1 时在 scale 倍像素空间里生成——袜身纹理、上沿、
            光影都是该分辨率的真细节，不是把成品放大；内置矢量素材按该倍率
            重新栅格化，外部位图素材先按比例重采样。
            返回的 Leg 图像为「设计尺寸 × scale」像素（`pixels_per_unit == scale`），
            `width` / `height` / `foot_center_x` 等元数据仍是设计像素，
            图层按 1:1 贴图即得到 scale 倍输出。

    Returns:
        新的 Leg：图像按 scale 倍密度重绘（`pixels_per_unit == scale`），
        设计像素元数据与原素材一致。

    Raises:
        ValueError: scale 不是正的有限数。
    """
```

## 文字与手绘线条

```python
type FontSpec = str | Path | Sequence[str | Path]
"""字体：家族名、字体文件路径，或依次尝试的候选列表（家族名与路径可混合），
候选顺序即优先级。None 用平台默认链（见 [设计说明](../design.zh-CN.md)"字体"）。"""

type TextAnchor = tuple[
    Literal["left", "center", "right"],
    Literal["top", "middle", "baseline", "bottom"],
]
"""(x, y) 锚在文字块的哪一处：垂直方向参照整块，baseline 指首行基线。"""


def draw_text(
    canvas: Canvas,
    text: str,
    x: float,
    y: float,
    *,
    size_px: float,
    color: Color = DEFAULT_TEXT_COLOR,
    font: FontSpec | None = None,
    anchor: TextAnchor = ("left", "baseline"),
    rotation: float = 0.0,
    max_width: float | None = None,
    max_lines: int | None = None,
    line_height: float | None = None,
) -> None:
    r"""画一段文字（支持 \n 与按宽折行，逐段整形含 kerning/连字）。

    Args:
        canvas: 目标画布。
        text: 待绘制文本；空串直接返回。
        x: 锚点 x（画布输出像素）。
        y: 锚点 y（画布输出像素）。
        size_px: 字号（像素），须为正数。
        color: 文字颜色（方框占位同色）。
        font: 字体候选；None 用平台默认链。
        anchor: (x, y) 对应文字块的哪一处；垂直参照整块，水平逐行生效。
        rotation: 绕 (x, y) 顺时针旋转的角度（度）。
        max_width: 每行最大宽度（像素）；None 不折行。
        max_lines: 最多行数；None 不限。
        line_height: 行距倍率；None 用自然行距。

    Raises:
        ValueError: color 不是合法的 RGB/RGBA 元组、size_px 非正、
            anchor 取值非法，或 font 候选列表为空。
    """


def measure_text(
    text: str,
    *,
    size_px: float,
    font: FontSpec | None = None,
) -> float:
    """测量文字按 draw_text 相同规则排版后的宽度（多行取最宽行）。

    Args:
        text: 待测量文本；空串返回 0。
        size_px: 字号（像素）。
        font: 字体候选；None 用平台默认链。

    Returns:
        前进宽度（像素，含 kerning/连字）。

    Raises:
        ValueError: font 候选列表为空或包含空名字。
    """


def measure_text_height(
    text: str,
    *,
    size_px: float,
    font: FontSpec | None = None,
    line_height: float | None = None,
) -> float:
    """测量文字块的真实高度（按实际解析到的字体度量，多行含行距）。

    Args:
        text: 待测量文本；空串按单空行估算。
        size_px: 字号（像素）。
        font: 字体候选；None 用平台默认链。
        line_height: 行距倍率；None 用自然行距。

    Returns:
        块高（像素）。

    Raises:
        ValueError: font 候选列表为空或包含空名字。
    """


def wrap_text(
    text: str,
    *,
    max_width: float,
    size_px: float,
    font: FontSpec | None = None,
    max_lines: int | None = None,
) -> list[str]:
    r"""按像素宽度把文本折成多行（\n 参与切分，末行可加省略号）。

    采用贪心断行，优先在空白或常见标点之后断开；中文可按字断行，英文单词
    过长时仍会断开。超过 max_lines 时末行加省略号；除单个字形本身超宽外，
    每行都不超过 max_width。

    Args:
        text: 待折行文本；空串返回 [""]。
        max_width: 每行最大宽度（像素）。
        size_px: 字号（像素）。
        font: 字体候选；None 用平台默认链。
        max_lines: 最多行数；None 表示不限。

    Returns:
        折行后的行字符串列表，至少包含一个元素。

    Raises:
        ValueError: font 候选列表为空或包含空名字。
    """


def sketch_line(
    canvas: Canvas,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    *,
    color: Color = DEFAULT_INK_COLOR,
    width_px: float = DEFAULT_STROKE_WIDTH,
    wobble: float = DEFAULT_WOBBLE,
    seed: int | None = None,
) -> None:
    """画一条手绘风直线。

    Args:
        canvas: 目标画布。
        x1: 起点 x（画布输出像素）。
        y1: 起点 y。
        x2: 终点 x。
        y2: 终点 y。
        color: 线条颜色。
        width_px: 线宽（像素）。
        wobble: 法向抖动幅度（像素）；0 为直线。
        seed: 随机源；同一 seed 结果可复现，不传则每次随机。
    """


def sketch_axis(
    canvas: Canvas,
    *,
    direction: Literal["up", "down", "right"],
    x: float,
    y: float,
    length: float,
    ticks: Sequence[tuple[float, str]] = (),
    arrow: bool = True,
    color: Color = DEFAULT_INK_COLOR,
    width_px: float = DEFAULT_STROKE_WIDTH,
    wobble: float = DEFAULT_WOBBLE,
    seed: int | None = None,
    font: FontSpec | None = None,
) -> None:
    """画一条手绘风坐标轴，可带箭头、刻度线与刻度数字。

    (x, y) 为轴起点，干线向 direction 延伸 length 像素；箭头（可选）在远端。
    垂直轴的刻度与数字在干线左侧，水平轴的在其下侧。

    Args:
        canvas: 目标画布。
        direction: "up" / "down" / "right"；决定延伸方向与刻度侧。
        x: 轴起点 x（画布输出像素）。
        y: 轴起点 y。
        length: 干线长度（像素）；<= 0 时不画箭头。
        ticks: (距起点的像素偏移, 标签文字) 序列。
        arrow: 是否在远端画箭头。
        color: 轴、刻度与文字颜色。
        width_px: 线条宽度（像素）。
        wobble: 干线抖动幅度；箭头与刻度使用其一半。
        seed: 随机源；同一 seed 结果可复现，不传则每次随机。
        font: 刻度数字字体（家族名、字体文件路径或候选列表）；None 用
            平台默认链。
    """
```

## 与丝袜渲染算法实现的协作边界

- `render_stocking()` 的签名与语义是硬契约：从脚端向上、`height_px <= 0` 返回裸腿、超过腿高全盖、`seed` 可复现、返回图像密度为 `scale` 的新 Leg（设计坐标元数据不变）。
- `StockingStyle` 及其组成类型的字段、预设名见上文“丝袜样式”；视觉算法见 [设计说明](../design.zh-CN.md)“丝袜渲染”。其余各层只透传该对象。

## 最小示例

```python
from stockchart import STYLES, LegLibrary, render_stocking

library = LegLibrary(seed=0)
rendered = render_stocking(library.get("leg_03"), STYLES["black_sheer"], 500, seed=0)
print(rendered.height, rendered.pixels_per_unit)  # 设计像素高与图像密度
```
