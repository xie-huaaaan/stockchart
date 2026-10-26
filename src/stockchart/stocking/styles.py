"""丝袜样式 dataclass 定义与内置预设注册表。

公开类型：StockingStyle、Fabric（Plain/Striped/Ribbed/Fishnet/Dotted）、
TopEdge（Bare/Welt/Lace/Fade）、Shading、Stripe。
预设字典：STYLES（只读映射，键见 docs/api.zh-CN/rendering.md）。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from types import MappingProxyType
from typing import Literal

from stockchart.color import Color, check_color

# ---------------------------------------------------------------------------
# Fabric 种类
# ---------------------------------------------------------------------------


@dataclass(slots=True, frozen=True, kw_only=True)
class Plain:
    """纯色袜：从极薄透肉的丝袜到完全不透明的厚袜。

    opacity 是腿正面中线处的遮盖率（0 近乎透明，1 完全不透肤色）。
    rim 控制两侧因斜向观察穿过更多织物而自然变不透明的程度。
    stretch 模拟腿越粗袜子被撑得越薄越透的视觉效果。
    """

    color: Color
    opacity: float = 0.6
    rim: float = 1.0
    stretch: float = 0.5

    def __post_init__(self) -> None:
        check_color(self.color, "Plain.color")
        for name, val in (("opacity", self.opacity), ("rim", self.rim), ("stretch", self.stretch)):
            if not 0.0 <= val <= 1.0:
                raise ValueError(f"Plain.{name} 须在 [0, 1]，得到 {val}")


@dataclass(slots=True, frozen=True)
class Stripe:
    """横条纹袜的单条条带。width 单位为素材像素（腿正面）。"""

    color: Color
    width: float
    opacity: float = 1.0

    def __post_init__(self) -> None:
        check_color(self.color, "Stripe.color")
        if self.width <= 0:
            raise ValueError(f"Stripe.width 须 > 0，得到 {self.width}")
        if not 0.0 <= self.opacity <= 1.0:
            raise ValueError(f"Stripe.opacity 须在 [0, 1]，得到 {self.opacity}")


@dataclass(slots=True, frozen=True, kw_only=True)
class Striped:
    """横条纹袜：周期性横条，从袜口往下排，腿两侧按圆柱透视自动压缩宽度。

    stripes 定义一个周期内从上到下的条带顺序。
    offset 是相位偏移（像素），正值使第一条纹从袜口向下偏移。
    """

    stripes: tuple[Stripe, ...]
    offset: float = 0.0

    def __post_init__(self) -> None:
        if not self.stripes:
            raise ValueError("Striped.stripes 不能为空")


@dataclass(slots=True, frozen=True, kw_only=True)
class Ribbed:
    """竖罗纹针织袜：竖向罗纹，越靠近腿两侧罗纹越密（透视收缩）。

    rib_width 是腿正面中线处相邻罗纹的间距（像素）。
    depth 是罗纹凹凸产生的明暗对比度（0 无纹理，1 最强对比）。
    """

    color: Color
    opacity: float = 1.0
    rib_width: float = 6.0
    depth: float = 0.35

    def __post_init__(self) -> None:
        check_color(self.color, "Ribbed.color")
        if not 0.0 <= self.opacity <= 1.0:
            raise ValueError(f"Ribbed.opacity 须在 [0, 1]，得到 {self.opacity}")
        if self.rib_width <= 0:
            raise ValueError(f"Ribbed.rib_width 须 > 0，得到 {self.rib_width}")
        if not 0.0 <= self.depth <= 1.0:
            raise ValueError(f"Ribbed.depth 须在 [0, 1]，得到 {self.depth}")


@dataclass(slots=True, frozen=True, kw_only=True)
class Fishnet:
    """网袜：斜向或方形网格，可在下面叠一层 Plain 底袜。

    cell 是网眼大小（腿正面中线处，像素）。
    angle 是网格旋转角度（度），45 为菱形，0 为方格。
    underlay 为网格下方叠的底袜；None 表示仅网格、皮肤直接透出。
    """

    color: Color
    cell: float = 14.0
    line_width: float = 1.6
    angle: float = 45.0
    underlay: Plain | None = None

    def __post_init__(self) -> None:
        check_color(self.color, "Fishnet.color")
        if self.cell <= 0:
            raise ValueError(f"Fishnet.cell 须 > 0，得到 {self.cell}")
        if self.line_width <= 0:
            raise ValueError(f"Fishnet.line_width 须 > 0，得到 {self.line_width}")


@dataclass(slots=True, frozen=True, kw_only=True)
class Dotted:
    """印花袜：在底袜上叠加规律排列或随机散布的小图案。

    shape 为图案形状；layout 为 "grid"（错位网格）或 "scatter"（由 seed 随机散布）。
    spacing 是相邻图案中心的距离（腿正面，像素）。
    """

    base: Plain
    color: Color
    shape: Literal["dot", "heart", "star"] = "dot"
    size: float = 3.0
    spacing: float = 18.0
    layout: Literal["grid", "scatter"] = "grid"
    opacity: float = 1.0

    def __post_init__(self) -> None:
        check_color(self.color, "Dotted.color")
        if self.size <= 0:
            raise ValueError(f"Dotted.size 须 > 0，得到 {self.size}")
        if self.spacing <= 0:
            raise ValueError(f"Dotted.spacing 须 > 0，得到 {self.spacing}")
        if not 0.0 <= self.opacity <= 1.0:
            raise ValueError(f"Dotted.opacity 须在 [0, 1]，得到 {self.opacity}")


type Fabric = Plain | Striped | Ribbed | Fishnet | Dotted


# ---------------------------------------------------------------------------
# TopEdge 上沿
# ---------------------------------------------------------------------------


@dataclass(slots=True, frozen=True, kw_only=True)
class Bare:
    """平口上沿：只有一条细手绘边线，无额外装饰。"""


@dataclass(slots=True, frozen=True, kw_only=True)
class Welt:
    """松紧袜口：袜口处加厚的条带，颜色略深于袜身。

    color 为 None 时取袜身主色加深一档。
    opacity 为 None 时视为不透明（1.0，双层织物）。
    pinch 是袜口上方皮肤被勒出的浅阴影线强度（0 关闭）。
    """

    height: float = 20.0
    color: Color | None = None
    opacity: float | None = None
    pinch: float = 0.4

    def __post_init__(self) -> None:
        if self.height <= 0:
            raise ValueError(f"Welt.height 须 > 0，得到 {self.height}")
        if self.color is not None:
            check_color(self.color, "Welt.color")
        if self.opacity is not None and not 0.0 <= self.opacity <= 1.0:
            raise ValueError(f"Welt.opacity 须在 [0, 1]，得到 {self.opacity}")
        if not 0.0 <= self.pinch <= 1.0:
            raise ValueError(f"Welt.pinch 须在 [0, 1]，得到 {self.pinch}")


@dataclass(slots=True, frozen=True, kw_only=True)
class Lace:
    """蕾丝边：锯齿波浪下沿，可选镂空小孔。

    scallop 是波浪周期（像素）。
    color 为 None 时取袜身主色。
    蕾丝是镂空织物，带子默认半透明（0.85），透出其下遮盖的皮肤；
    镂空感同时由 holes 的孔点图案表达。
    holes 为 True 时在蕾丝带上叠加孔点。
    """

    height: float = 28.0
    scallop: float = 28.0
    color: Color | None = None
    opacity: float = 0.85
    holes: bool = True

    def __post_init__(self) -> None:
        if self.height <= 0:
            raise ValueError(f"Lace.height 须 > 0，得到 {self.height}")
        if self.scallop <= 0:
            raise ValueError(f"Lace.scallop 须 > 0，得到 {self.scallop}")
        if self.color is not None:
            check_color(self.color, "Lace.color")
        if not 0.0 <= self.opacity <= 1.0:
            raise ValueError(f"Lace.opacity 须在 [0, 1]，得到 {self.opacity}")


@dataclass(slots=True, frozen=True, kw_only=True)
class Fade:
    """连裤袜式渐隐上沿：没有明显的边线，颜色向上逐渐消失。

    length 是渐变区的高度（像素）；数据高度取渐变区中点。
    """

    length: float = 60.0

    def __post_init__(self) -> None:
        if self.length <= 0:
            raise ValueError(f"Fade.length 须 > 0，得到 {self.length}")


type TopEdge = Bare | Welt | Lace | Fade


# ---------------------------------------------------------------------------
# Shading 光影（所有 Fabric 共用）
# ---------------------------------------------------------------------------


@dataclass(slots=True, frozen=True, kw_only=True)
class Shading:
    """丝袜的光影与立体感参数。

    curve: 横向线条（上沿、横条纹）向下弯曲的程度（0 为直线）。
    rim_shadow: 背光侧边缘压暗程度（0 关闭，1 最深）。
    shadow_color: 阴影的正片叠底色（RGBA），默认偏冷淡紫（动漫常用）。
    highlight: 竖向高光强度（0 关闭）。
    highlight_pos: 高光在腿宽方向的位置，−1 左缘、1 右缘。
    highlight_width: 高光半宽（腿半宽的比例）。
    cel_steps: 0 为平滑渐变；2 或 3 为动漫分阶色块。
    ink: 素材描边透出的强度（深色袜上渲染器自动换用更深的线色）。
    wobble: 新增线条（袜口、蕾丝边）的手绘抖动幅度（像素），由 seed 控制。
    skin: 袜口以上裸露皮肤的光影强度（相对袜子上的强度）：0 只作用于袜子
        （旧观感），1 与袜子同等，0.5 左右体积感自然。裸腿同样参与。
    skin_shadow_color: 皮肤上的阴影色。合成纤维用偏冷的 shadow_color 好看，
        但皮肤用冷紫会显脏，默认改用偏暖的肤色阴影。
    """

    curve: float = 0.12
    rim_shadow: float = 0.5
    shadow_color: Color = (150, 140, 180, 180)
    highlight: float = 0.35
    highlight_pos: float = -0.35
    highlight_width: float = 0.18
    cel_steps: int = 0
    ink: float = 1.0
    wobble: float = 0.6
    skin: float = 0.5
    skin_shadow_color: Color = (206, 168, 158, 200)

    def __post_init__(self) -> None:
        check_color(self.shadow_color, "Shading.shadow_color")
        check_color(self.skin_shadow_color, "Shading.skin_shadow_color")
        for name, val in (
            ("curve", self.curve),
            ("rim_shadow", self.rim_shadow),
            ("highlight", self.highlight),
            ("highlight_width", self.highlight_width),
            ("ink", self.ink),
            ("wobble", self.wobble),
            ("skin", self.skin),
        ):
            if val < 0.0:
                raise ValueError(f"Shading.{name} 须 >= 0，得到 {val}")
        if not -1.0 <= self.highlight_pos <= 1.0:
            raise ValueError(f"Shading.highlight_pos 须在 [−1, 1]，得到 {self.highlight_pos}")
        if self.cel_steps not in (0, 2, 3):
            raise ValueError(f"Shading.cel_steps 须为 0、2 或 3，得到 {self.cel_steps}")


# ---------------------------------------------------------------------------
# StockingStyle
# ---------------------------------------------------------------------------


@dataclass(slots=True, frozen=True, kw_only=True)
class StockingStyle:
    """丝袜样式参数集：袜身种类 + 上沿 + 光影。

    Attributes:
        fabric: 袜身种类，决定纹理与基础颜色。
        top: 上沿样式，与袜身独立，可自由组合。
        shading: 光影参数，所有袜身种类共用。
    """

    fabric: Fabric
    top: TopEdge = field(default_factory=Welt)
    shading: Shading = field(default_factory=Shading)


def scale_style(style: StockingStyle, factor: float) -> StockingStyle:
    """把样式里所有"像素长度"乘以 factor，得到同一视觉在另一分辨率下的等价样式。

    比例类参数（opacity、rim、stretch、curve、highlight_width、angle、depth、
    pinch、skin 等）保持不变；factor 为 1 时原样返回。
    """
    if factor == 1.0:
        return style

    def fabric(f: Fabric) -> Fabric:
        if isinstance(f, Striped):
            stripes = tuple(replace(s, width=s.width * factor) for s in f.stripes)
            return replace(f, stripes=stripes, offset=f.offset * factor)
        if isinstance(f, Ribbed):
            return replace(f, rib_width=f.rib_width * factor)
        if isinstance(f, Fishnet):
            under = fabric(f.underlay) if f.underlay is not None else None
            return replace(
                f, cell=f.cell * factor, line_width=f.line_width * factor, underlay=under
            )
        if isinstance(f, Dotted):
            return replace(f, base=fabric(f.base), size=f.size * factor, spacing=f.spacing * factor)
        return f

    def top(t: TopEdge) -> TopEdge:
        if isinstance(t, Welt):
            return replace(t, height=t.height * factor)
        if isinstance(t, Lace):
            return replace(t, height=t.height * factor, scallop=t.scallop * factor)
        if isinstance(t, Fade):
            return replace(t, length=t.length * factor)
        return t

    return replace(
        style,
        fabric=fabric(style.fabric),
        top=top(style.top),
        shading=replace(style.shading, wobble=style.shading.wobble * factor),
    )


# ---------------------------------------------------------------------------
# STYLES 预设注册表
# ---------------------------------------------------------------------------


def _make_styles() -> dict[str, StockingStyle]:
    """构造内置预设字典，内部调用一次后包装为只读映射。"""
    # 常用颜色常量
    _BLACK = (28, 26, 30)
    _DARK_GRAY = (80, 77, 76)
    _NUDE = (214, 170, 150)
    _WHITE = (252, 252, 255)
    _THICK_BLACK = (32, 30, 34)
    _THICK_WHITE = (248, 248, 250)

    s: dict[str, StockingStyle] = {}

    # ---- 纯色丝袜 ----
    s["black_sheer"] = StockingStyle(
        fabric=Plain(color=_BLACK, opacity=0.55),
        top=Welt(),
    )
    s["black_sheer_lace"] = StockingStyle(
        fabric=Plain(color=_BLACK, opacity=0.55),
        top=Lace(),
    )
    s["black_pantyhose"] = StockingStyle(
        fabric=Plain(color=_BLACK, opacity=0.55),
        top=Fade(),
    )
    s["gray_sheer"] = StockingStyle(
        fabric=Plain(color=_DARK_GRAY, opacity=0.6),
        top=Fade(),
    )
    s["nude_sheer"] = StockingStyle(
        fabric=Plain(color=_NUDE, opacity=0.35),
        top=Welt(),
    )
    s["white_sheer"] = StockingStyle(
        fabric=Plain(color=_WHITE, opacity=0.5),
        top=Lace(),
    )
    s["black_tights"] = StockingStyle(
        fabric=Plain(color=_THICK_BLACK, opacity=0.95),
        top=Welt(height=24),
    )
    s["white_tights"] = StockingStyle(
        fabric=Plain(color=_THICK_WHITE, opacity=0.97),
        top=Welt(height=24),
    )

    # ---- 条纹 ----
    s["stripe_blue_white"] = StockingStyle(
        fabric=Striped(
            stripes=(
                Stripe(color=(255, 255, 255), width=8),
                Stripe(color=(70, 110, 200), width=8),
            )
        ),
        top=Welt(color=(70, 110, 200)),
    )
    s["stripe_pink_white"] = StockingStyle(
        fabric=Striped(
            stripes=(
                Stripe(color=(255, 255, 255), width=8),
                Stripe(color=(240, 150, 180), width=8),
            )
        ),
        top=Welt(color=(240, 150, 180)),
    )
    s["stripe_black_white"] = StockingStyle(
        fabric=Striped(
            stripes=(
                Stripe(color=(255, 255, 255), width=12),
                Stripe(color=(30, 28, 32), width=12),
            )
        ),
        top=Welt(color=(30, 28, 32)),
    )
    s["stripe_rainbow"] = StockingStyle(
        fabric=Striped(
            stripes=(
                Stripe(color=(230, 60, 60), width=7),
                Stripe(color=(230, 130, 40), width=7),
                Stripe(color=(220, 200, 40), width=7),
                Stripe(color=(60, 180, 80), width=7),
                Stripe(color=(60, 120, 220), width=7),
                Stripe(color=(150, 70, 200), width=7),
            )
        ),
        top=Bare(),
    )
    s["stripe_sheer_black"] = StockingStyle(
        fabric=Striped(
            stripes=(
                Stripe(color=_BLACK, width=6, opacity=0.5),
                Stripe(color=_BLACK, width=6, opacity=0.9),
            )
        ),
        top=Welt(color=_BLACK),
    )

    # ---- 罗纹针织 ----
    s["knit_cream"] = StockingStyle(
        fabric=Ribbed(color=(240, 232, 215), opacity=1.0),
        top=Welt(height=30, color=(220, 212, 195)),
    )
    s["knit_gray"] = StockingStyle(
        fabric=Ribbed(color=(150, 148, 150), opacity=1.0),
        top=Welt(height=24, color=(120, 118, 120)),
    )

    # ---- 网袜 ----
    s["fishnet_black"] = StockingStyle(
        fabric=Fishnet(color=(20, 18, 22), cell=14, line_width=1.6),
        top=Welt(color=(20, 18, 22)),
    )
    s["fishnet_over_sheer"] = StockingStyle(
        fabric=Fishnet(
            color=(20, 18, 22),
            cell=14,
            line_width=1.6,
            underlay=Plain(color=_BLACK, opacity=0.4),
        ),
        top=Welt(color=(20, 18, 22)),
    )

    # ---- 印花 ----
    s["polka_black"] = StockingStyle(
        fabric=Dotted(
            base=Plain(color=_BLACK, opacity=0.55),
            color=(20, 18, 22),
            shape="dot",
            size=3,
            spacing=18,
            layout="grid",
        ),
        top=Welt(),
    )
    s["heart_white"] = StockingStyle(
        fabric=Dotted(
            base=Plain(color=_WHITE, opacity=0.5),
            color=(240, 100, 140),
            shape="heart",
            size=4,
            spacing=20,
            layout="scatter",
        ),
        top=Lace(color=(240, 100, 140)),
    )

    return s


STYLES: MappingProxyType[str, StockingStyle] = MappingProxyType(_make_styles())
"""内置预设注册表（只读），键见 docs/api.zh-CN/rendering.md。"""


# ---------------------------------------------------------------------------
# 样式参数别名（各层接口的 style 参数）
# ---------------------------------------------------------------------------


type StyleLike = StockingStyle | str
"""单个样式：StockingStyle 实例或 STYLES 键名。"""


type StyleSeq = StyleLike | Sequence[StyleLike]
"""样式参数：单个样式，或按位置循环的样式列表（循环语义见 docs/api.zh-CN/layout.md）。"""
