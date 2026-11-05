"""内置丝袜样式预设注册表。

STYLES 是只读映射，键名与取值见 docs/api.zh-CN/rendering.md；
预设本身由 styles 模块里的 dataclass 组合而成。
"""

from __future__ import annotations

from types import MappingProxyType

from stockchart.stocking.styles import (
    Bare,
    Dotted,
    Fade,
    Fishnet,
    Lace,
    Plain,
    Ribbed,
    StockingStyle,
    Stripe,
    Striped,
    Welt,
)

# ---------------------------------------------------------------------------
# STYLES 预设注册表
# ---------------------------------------------------------------------------


def _make_styles() -> dict[str, StockingStyle]:
    """构造全部内置样式预设。

    Returns:
        以 STYLES 键名到 StockingStyle 的字典。
    """
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
