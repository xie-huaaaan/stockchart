# stockchart 公开 API 定稿

状态：分层与签名已与用户确认；丝袜样式的种类、参数与预设已与用户确认。

## 全局约定

- **坐标单位**一律是素材像素（腿素材高 720）；最终输出的放大倍数是独立的 `scale` 参数。
- **随机性**：选腿、丝袜纹理、手绘抖动全部由 `seed` 控制，同参数同 seed 渲染结果完全一致。
- **裸腿**即"丝袜高度为 0"，没有单独的开关。
- 上层只通过下层的公开接口工作：

| 层 | 职责 | 内容 |
| --- | --- | --- |
| L0 素材 | 腿素材的加载与选取 | `Leg` `LegLibrary` `load_leg` |
| L1 渲染原语 | 单个元素绘制 | `render_stocking` `StockingStyle` `STYLES` `draw_text` `sketch_line` `sketch_axis` |
| L2 自由柱状图 | 画布、基线、任意贴腿、配轴 | `Scale` `BarPlot` |
| L3 布局封装 | 统一间距、自动选腿 | `BarPlot.add_bars` 等便捷方法 |
| L4 一行出图 | 数据归一化 + 全自动布局 | `bar` `mirror_bar` |

`Canvas`、`Color` 为跨层基础对象，单列于下。

## 基础对象

```python
type Color = tuple[int, int, int] | tuple[int, int, int, int]
"""0–255，可带 alpha。"""


class Canvas:
    """最终渲染结果的载体：一块 RGBA 画布。

    通常由 `BarPlot.render()` 产生并绘制；自由绘制时也可直接构造，
    配合 L1 原语（`draw_text` / `sketch_*`）在上面作画。
    """

    def __init__(
        self,
        width_px: int,
        height_px: int,
        *,
        background: Color = DEFAULT_BACKGROUND,
    ) -> None:
        """构造空白画布并填充背景色。尺寸单位为素材像素。"""

    def save(self, path: str | Path) -> Path:
        """写出 PNG 文件。"""

    def to_pil(self) -> Image:
        """导出为 PIL Image（RGBA）。"""

    def to_numpy(self) -> np.ndarray:
        """导出为 (H, W, 4) uint8 RGBA 数组。"""
```

`BarPlot` 也提供 `save` / `to_pil` 直通方法（见 L2），保证 L4 一行能出图。

## L0 素材层

```python
@dataclass(slots=True, frozen=True)
class Leg:
    """一条腿部素材：RGBA 像素与定位元数据。

    宽高、足底中心、足宽等元数据一律使用**设计像素**（腿高 720 的坐标系），
    与图像的实际密度无关；`pixels_per_unit` 描述"图像像素 / 设计像素"。

    Attributes:
        image: (H, W, 4) uint8；脚在图像底端、素材正放。
        width: 设计像素宽。
        height: 设计像素高。
        foot_center_x: 足底中心在设计坐标系里的 x，放置对齐的锚点。
        foot_width: 足底宽度（设计像素）。
        pixels_per_unit: 图像像素 / 设计像素；1 为素材即设计尺寸，
            2 表示图像是设计尺寸的两倍密（渲染时按需降采样，不重复放大）。
        leg_id: 内置素材编号（如 "leg_03"）；外部素材为 None。
        pair_id: 所属配对编号（如 "pair_02"）；外部素材为 None。
        side: "left" / "right"；外部素材为 None。
    """

    image: np.ndarray
    width: int
    height: int
    foot_center_x: int
    foot_width: int
    pixels_per_unit: float = 1.0
    leg_id: str | None = None
    pair_id: str | None = None
    side: Literal["left", "right"] | None = None
```

```python
class LegLibrary:
    """内置腿部素材库（26 条腿 / 13 对）。"""

    def __init__(self, *, seed: int | None = None) -> None:
        """seed 同时作为后续自动选腿的默认随机源。"""

    def get(self, leg_id: str) -> Leg:
        """按编号取一条腿，如 get("leg_03")。"""

    def pair(self, pair_id: str) -> tuple[Leg, Leg]:
        """取一对腿，返回 (左腿, 右腿)。"""

    def alternate(self, n: int) -> list[Leg]:
        """按左、右、左、右……的顺序选出 n 条腿。

        具体使用哪几对素材按 seed 伪随机、优先不重复；超过 13 对后从已用素材继续复用。
        """

    def sample_pairs(self, n: int) -> list[tuple[Leg, Leg]]:
        """选出 n 对完整素材（成对布局用），选取规则同 alternate。"""
```

```python
def load_leg(
    png: str | Path,
    *,
    foot_center_x: int | None = None,
    foot_width: int | None = None,
) -> Leg:
    """从 PNG 加载自定义腿素材，用法与内置素材完全一致（编号字段为 None）。

    Args:
        png: 带透明通道的 PNG 路径；要求脚位于图像底端（与内置素材同方向）。
        foot_center_x: 足底中心 x 坐标。缺省按底部若干行的 alpha 质心自动估计。
        foot_width: 足底宽度。缺省按底部 alpha 覆盖宽度自动估计。

    Returns:
        自定义素材的 Leg 实例，可直接传入各层接口。
    """
```

## L1 渲染原语层

### 丝袜样式

袜子 = 袜身种类（`Fabric`）+ 上沿（`TopEdge`）+ 光影（`Shading`）。三者都是
`dataclass(slots=True, frozen=True, kw_only=True)`，非法参数在构造时抛 `ValueError`。
长度单位均为素材像素，指腿正面处的尺寸（两侧按圆柱透视自动压缩）。
颜色为 `Color`；带 alpha 分量时，alpha 乘到对应的 opacity 上。

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
| `Ribbed` | 竖罗纹针织 | `color`；`opacity`(1.0)；`rib_width`(6) 罗纹间距；`depth`(0.35) 明暗对比 |
| `Fishnet` | 网袜 | `color`；`cell`(14) 网眼大小；`line_width`(1.6)；`angle`(45) 45 菱形、0 方格；`underlay: Plain \| None`(None) 底下叠的一层袜 |
| `Dotted` | 印花 | `base: Plain` 底袜（必填）；`color`；`shape`("dot") `"dot"/"heart"/"star"`；`size`(3) 图案半径；`spacing`(18)；`layout`("grid") `"grid"` 错位网格 / `"scatter"` 按 seed 随机散布；`opacity`(1.0) |

罗纹、网眼、印花的横向疏密按“绕腿一圈的针数固定”处理：腿粗处稀、脚踝处密。

**上沿**

| 类 | 含义 | 字段（默认值） |
| --- | --- | --- |
| `Bare` | 平口，只有一条细边线 | 无 |
| `Welt` | 松紧袜口：一圈加厚条带 | `height`(20)；`color`(None：取袜身主色加深一档)；`opacity`(None：双层织物视为不透明)；`pinch`(0.4) 袜口上方皮肤被勒出的浅阴影，0 关闭 |
| `Lace` | 蕾丝边 | `height`(28)；`scallop`(28) 波浪周期；`color`(None：取袜身主色)；`opacity`(0.85，镂空织物透出皮肤)；`holes`(True) 孔点图案 |
| `Fade` | 连裤袜式渐隐，无明显边 | `length`(60) 渐变区长度 |

**数据高度的定义**：腿中线处袜口顶端到脚端的距离；`Lace` 按波浪平均位置；
`Fade` 的渐隐自袜口顶端向下 `length` 像素内完成（顶端透明、无边界线）。
横向线条（条纹、袜口、蕾丝、网线）均沿 `Shading.curve` 的弧线下弯，
织物顶边与上沿线条的弧形处处重合。

**上沿静区**：`Welt` / `Lace` 条带覆盖区域的袜身图案（条纹、罗纹、网格、
印花）从条带下沿起算——`Welt` 沿其底沿弧线，`Lace` 沿波浪边缘逐列贴合；
条带直接覆于皮肤之上（条带本身即该区域的织物）：`Welt` 为双层织物、
不透明；`Lace` 为镂空织物、默认 0.85 透出皮肤，孔点处更透。

**光影（所有种类共用）**

| 字段 | 默认 | 含义 |
| --- | --- | --- |
| `curve` | 0.12 | 环形线条（上沿、横纹、网格）下弯程度（略俯视），0 为直线 |
| `rim_shadow` | 0.5 | 背光侧边缘压暗程度 |
| `shadow_color` | (150, 140, 180) | 阴影的正片叠底色（偏冷的淡紫，动漫常用） |
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
"""样式参数：单个样式，或按位置循环的样式列表（循环语义见 L3/L4）。"""
```

L2 的 `add_bar` 只接受单个 `StyleLike`；L3/L4 的批量方法接受 `StyleSeq`，
默认 `DEFAULT_STOCKING_STYLE = "black_sheer"`。

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
        height_px: 丝袜上沿到脚端的像素数（素材像素）。小于等于 0 时为裸腿
            （`Shading.skin` 大于 0 时裸腿仍按皮肤光影渲染，否则原样返回）；
            不小于 leg.height 时整腿全盖。
        seed: 纹理类随机效果的随机源。
        scale: 输出倍率。>1 时在 scale 倍像素空间里生成——袜身纹理、上沿、
            光影都是该分辨率的真细节，不是把成品图放大；素材先按比例重采样。
            返回的 Leg 尺寸为素材像素 × scale，足底中心/足宽同步放大，
            图层按 1:1 贴图即可得到 scale 倍的输出。

    Returns:
        新的 Leg：像素已替换，设计坐标元数据与素材一致；`scale != 1` 时
        图像按倍率加密（`pixels_per_unit == scale`），供 1:1 贴图。

    约定：本函数是丝袜渲染算法的对外契约（算法由独立设计实现）。始终在素材
    自身坐标系内从脚端向上渲染；腿的上下翻转由上层放置时处理（翻转与渲染
    先后等价，不在此层做）。`scale` 只是把渲染空间等比例放大，几何语义不变；
    素材本身比目标更密时按需降采样（高清素材不会被重复放大）。
    """
```

```python
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
) -> None:
    """画一段文字。逐字符字体回退保证中文可显示；缺字形画"豆腐块"，不抛异常。

    font 为家族名列表或字体文件路径；缺省走内置回退链（见 docs/design.md"字体"）。
    anchor 等参数的取值细节随实现微调，语义不变。
    """


def measure_text(
    text: str,
    *,
    size_px: float,
    font: FontSpec | None = None,
) -> float:
    """测量一段文字按 `draw_text` 相同回退规则绘制后的宽度（像素）。空串为 0。"""


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
    """手绘风直线：对线段做确定性细分抖动。"""


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
) -> None:
    """手绘风坐标轴：抖动轴干线、箭头、刻度线与刻度数字。

    (x, y) 为轴起点，干线向 direction 延伸 length 像素，箭头（可选）在远端；
    ticks 为 (距起点的像素偏移, 标签文字)：刻度线垂直于干线，数字画在
    干线左侧（垂直轴）或下侧（水平轴）。
    """
```

## L2 自由柱状图

```python
@dataclass(slots=True, frozen=True)
class Scale:
    """线性比例尺：数据值 ↔ 基线上方像素。柱高与轴刻度共用同一个 Scale 即可保证一致。"""

    domain: tuple[float, float]
    range_px: tuple[float, float]
    # domain: (值下限, 值上限)；range_px: (像素下限, 像素上限)，基线为 0、向上为正。

    def to_px(self, value: float) -> float:
        """数据值 → 像素。"""

    def from_px(self, px: float) -> float:
        """像素 → 数据值。"""

    @classmethod
    def fit(cls, values: Sequence[float], extent_px: float, *, margin: float = 0.0) -> Scale:
        """构造 [min(values), max(values)] → [0, extent_px] 的比例尺，margin 两端留边。"""
```

```python
class BarPlot:
    """自由柱状图：以 X 轴为基线，腿的位置与丝袜高度全部由调用者按素材像素指定。"""

    def __init__(
        self,
        width_px: int,
        *,
        extent_up: int = DEFAULT_Y_EXTENT,
        extent_down: int = 0,
        background: Color = DEFAULT_BACKGROUND,
        seed: int | None = None,
    ) -> None:
        """构造绘图区（轴与标签的边距在内部另行留出）。

        extent_up / extent_down 为基线上、下各预留的像素高度；
        基线固定在 y = extent_down，即下方不留空间时基线贴底。
        """

    def add_bar(
        self,
        x: float,
        height_px: float,
        leg: Leg,
        *,
        style: StockingStyle | str = DEFAULT_STOCKING_STYLE,
        side: Literal["up", "down"] = "up",
        seed: int | None = None,
    ) -> BarPlot:
        """在 x 处贴一条腿：x 是足底中心的目标位置（腿宽不一，按脚对齐才均匀）。

        Args:
            height_px: 丝袜高度（素材像素）。小于等于 0 为裸腿。
            leg: 腿素材；side="down" 时素材竖直翻转、脚贴基线朝下。
            style: StockingStyle 实例或 STYLES 预设名。
        """

    def add_y_axis(
        self,
        scale: Scale,
        *,
        ticks: Sequence[float] | None = None,
        label: str | None = None,
        grid: bool = False,
    ) -> BarPlot:
        """添加 y 轴（手绘风，含刻度数字）。ticks 缺省由 scale.domain 均匀取值生成。

        刻度按 scale 映射到基线上下两侧：domain 含负值时干线向下延伸、
        下方刻度照常绘制，箭头仍在最上端。grid=True 时沿各刻度画横向
        手绘虚线（浅色，压在腿与袜之下）。
        """

    def add_x_labels(
        self,
        labels: Sequence[str],
        *,
        xs: Sequence[float] | None = None,
        pos: Literal["content", "auto", "above", "below"] = "content",
    ) -> BarPlot:
        """添加 x 轴标签。pos 决定标签写在哪儿：

        - "content"（默认）：全部内容最低点之下（含朝下腿与 y 轴向下延伸的
          部分），与基线解耦——没有下方内容时自然贴着基线下方；
        - "auto"：紧贴基线、选没有柱子的一侧（上方无腿→基线上方，下方无
          腿→基线下方，两侧都有腿→退回 "content"）；
        - "above" / "below"：强制写在基线上方 / 下方，该侧有腿时会与腿重叠。

        xs 缺省沿宽度均分；与 add_bars 系列方法配合时自动对齐组中心。
        """

    def add_title(self, text: str) -> BarPlot:
        """添加左上角标题。"""

    def add_legend(
        self,
        items: Sequence[tuple[str, StyleLike]],
        *,
        ncol: int | None = None,
        loc: Literal["top", "bottom"] = "top",
    ) -> BarPlot:
        """添加图例：每项为织物纹理色块 + 文字，色块取该样式袜身中部的织物。

        loc="top"（默认）画在标题下方、绘图区上方，"bottom" 画在最底部；
        ncol 为一行几项，缺省自动：单行放得下就单行，否则均匀换行。
        图例占据的高度自动计入布局。
        """

    def render(self, *, scale: float = DEFAULT_OUTPUT_SCALE) -> Canvas:
        """渲染。scale 为输出放大倍数（抗锯齿），不影响素材像素坐标。"""

    def save(self, path: str | Path, *, scale: float = DEFAULT_OUTPUT_SCALE) -> Path:
        """渲染并直接写出 PNG。"""

    def to_pil(self, *, scale: float = DEFAULT_OUTPUT_SCALE) -> Image:
        """渲染并直接导出 PIL Image。"""
```

## L3 布局封装

以下均为 `BarPlot` 的便捷方法：只解决"间距 + 选腿"，丝袜高度仍由调用者给像素。

```python
def add_bars(
    self,
    heights_px: Sequence[float],
    *,
    bar_gap: float = DEFAULT_BAR_GAP,
    style: StyleSeq = DEFAULT_STOCKING_STYLE,
    legs: Sequence[Leg] | None = None,
    seed: int | None = None,
) -> BarPlot:
    """单序列：统一间距从左到右排开，自动按左、右、左、右……交替选腿。

    legs 可显式指定每根柱子的素材（长度须与 heights_px 一致，不参与循环）。
    style 为列表时按柱序循环取用。
    """


def add_grouped_bars(
    self,
    heights_px: Sequence[Sequence[float]],
    *,
    bar_gap: float = DEFAULT_BAR_GAP,
    group_gap: float = DEFAULT_GROUP_GAP,
    style: StyleSeq = DEFAULT_STOCKING_STYLE,
    cycle: Literal["group", "sequence"] = "group",
    legs: Sequence[Leg] | None = None,
    seed: int | None = None,
) -> BarPlot:
    """(组数, 系列数) 的像素高度：组内用 bar_gap、组间用 group_gap，
    跨列按左、右、左、右……交替选腿。

    style 为列表时按 cycle 取用："group"（默认）按组内位置循环，组内第 i 根
    用 styles[i % len]，列表长度等于系列数时即"每系列一个样式"；"sequence"
    按全部柱子的绘制顺序循环（组 0 第 0 根、组 0 第 1 根、组 1 第 0 根……）。
    """


def add_paired_bars(
    self,
    heights_px: Sequence[tuple[float, float]],
    *,
    group_gap: float = DEFAULT_GROUP_GAP,
    style: StyleSeq = DEFAULT_STOCKING_STYLE,
    cycle: Literal["group", "sequence"] = "group",
    pairs: Sequence[tuple[Leg, Leg]] | None = None,
    seed: int | None = None,
) -> BarPlot:
    """每组恰好 2 个值：同组使用同一对素材，系列 0 左腿、系列 1 右腿。

    style 为列表时按 cycle 取用（"group" 默认：系列 0 取 styles[0]、系列 1
    取 styles[1 % len]；"sequence" 按全部柱子的绘制顺序循环）。
    pairs 缺省时自动选取不重复的素材对。
    """
```

**间距语义**：`bar_gap` / `group_gap` 均指相邻腿**边缘之间**的空隙（腿宽 144–181 不等，
按边缘留白视觉才均匀），不是足底中心距。

## L4 一行出图

```python
def bar(
    data: Sequence[float] | Sequence[Sequence[float]],
    *,
    labels: Sequence[str] | None = None,
    series_labels: Sequence[str] | None = None,
    title: str | None = None,
    style: StyleSeq = DEFAULT_STOCKING_STYLE,
    cycle: Literal["auto", "group", "sequence"] = "auto",
    paired: bool = True,
    value_labels: bool = False,
    grid: bool = False,
    max_fill: float = 0.8,
    min_fill: float = 0.1,
    y_extent: int = DEFAULT_Y_EXTENT,
    width_px: int | None = None,
    seed: int | None = None,
) -> BarPlot:
    """全朝上的柱状图：自动完成数据 → 丝袜高度映射、选腿与布局，
    返回布局完毕的 BarPlot（可直接 .save() / .render()，也可继续手工微调）。

    自动绘制手绘风 y 轴与基线；labels 传入时 x 标签自动与各组对齐；
    画布宽缺省时按腿、间距与标签宽度自适应。
    labels 传给 x 标签，series_labels 传给图例——后者区分"系列"（每组的
    第几根腿），前者区分"组"。

    Args:
        data: 一维为单序列；二维为 (组数, 系列数) 的分组数据。
        labels: 每组（无分组时每根柱）一个标签。
        series_labels: 每系列一个名字，传入即自动生成图例（marker 为各系列
            样式的织物色块）。仅二维数据可用，一维数据传入抛 ValueError。
        style: 单个样式，或样式列表——循环方式由 cycle 决定。
        cycle: 样式列表的循环方式："group" 按组内位置（组内第 i 根用
            styles[i % len]，列表长度等于系列数时即"每系列一个样式"）；
            "sequence" 按全部柱子的绘制顺序循环；"auto"（默认）一维数据
            取 "sequence"（即每根柱按顺序取样式）、二维数据取 "group"。
            二维数据下 "sequence" 与 series_labels 无法对应固定的系列样式，
            同时传入抛 ValueError。
        paired: 仅当数据恰好 2 系列时生效（默认 True）：每组使用同一对素材，
            系列 0 左腿、系列 1 右腿；其余系列数时忽略此参数。
        value_labels: True 时在袜口上方手写数值。
        grid: True 时沿 y 轴各刻度画横向手绘虚线（浅色，压在腿与袜之下）。
        max_fill: 最大值映射到 y_extent 的比例（默认 0.8）。
        min_fill: 仅当数据含负值时启用（默认 0.1），见下。
        y_extent: 基线上方预留的像素高度。
        width_px: 画布宽；缺省按腿数、间距、标签与图例自适应。

    数据 → 丝袜高度（基线对应的数据值默认 0）:
        - 全部数据为 0: 全部裸腿。
        - 无负值: height = v / max × max_fill × y_extent，0 值即裸腿。
        - 含负值: 整个值域 [min, max] 线性压缩到 [min_fill, max_fill]。
          此时 0 值的腿带一段丝袜、y 轴 0 刻度悬在丝袜中间某处——这是为完整
          保留大小关系所做的既定取舍。全负数据同规则：值越大丝袜越高。
    """


def mirror_bar(
    data: Sequence[float] | Sequence[Sequence[float]],
    *,
    mode: Literal["single", "both"] = "single",
    labels: Sequence[str] | None = None,
    series_labels: Sequence[str] | None = None,
    title: str | None = None,
    style: StyleSeq = DEFAULT_STOCKING_STYLE,
    cycle: Literal["auto", "group", "sequence"] = "auto",
    paired: bool = True,
    value_labels: bool = False,
    grid: bool = False,
    max_abs_fill: float = 0.8,
    x_label_pos: Literal["content", "auto", "above", "below"] = "auto",
    y_extent: int = DEFAULT_Y_EXTENT,
    width_px: int | None = None,
    seed: int | None = None,
) -> BarPlot:
    """正负镜像柱状图：正值画基线上方腿，负值画下方翻转腿（脚贴基线）。

    Args:
        mode: "single" 只画数据侧的腿；"both" 上下都画，数据侧穿丝袜、
            另一侧裸腿。
        labels: 每组（无分组时每根柱）一个标签。
        series_labels: 语义同 bar()。
        style: 语义同 bar()。
        cycle: 语义同 bar()。
        paired: 语义同 bar()。
        value_labels: True 时手写数值，上方腿写在袜口上方、下方腿写在袜口下方。
        grid: 语义同 bar()。
        max_abs_fill: 最大绝对值映射到 y_extent 的比例（默认 0.8）。
        x_label_pos: x 标签位置（语义见 add_x_labels 的 pos）。镜像图常有一侧
            全空，默认 "auto" 会把标签贴到没有腿的一侧的基线旁（如全负数据
            标签在基线上方）；两侧都有腿（正负混合或 mode="both"）时退回
            "content"，画在全部内容最低点之下。

    规则:
        - 比例 = max_abs_fill × y_extent / max|v|，正负同比例。
        - 0 视为 +0: "single" 下画一条朝上裸腿；"both" 下上下均画裸腿（上为数据侧）。
        - 下方空间: "single" 仅在存在负值时保留；"both" 始终保留。
    """
```

## 默认值集中定义

所有 `DEFAULT_*` 常量集中放在 `src/stockchart/defaults.py`：`DEFAULT_Y_EXTENT`（760）、
`DEFAULT_BAR_GAP`、`DEFAULT_GROUP_GAP`、`DEFAULT_OUTPUT_SCALE`、背景色、墨色、文字色、
抖动幅度、字号（刻度 / x 标签 / 标题 / 图例 / 数值标签）、图例色块尺寸与间距、
网格线颜色等。绘制代码里不自带魔法数字，调参改一处。

## 与丝袜渲染算法实现的协作边界

- `render_stocking()` 的签名与语义是硬契约：从脚端向上、`height_px <= 0` 返回裸腿、
  超过腿高全盖、`seed` 可复现、返回同尺寸新 Leg。
- `StockingStyle` 及其组成类型的字段、预设名见上文“丝袜样式”；视觉算法见
  docs/design.md“丝袜渲染”。其余各层只透传该对象。
