"""重绘中英文 README 使用的全部示例图。

用法：uv run python tools/render_readme.py
输出：docs/images/ 下的 hero 与 showcase 图片。
"""

from __future__ import annotations

from pathlib import Path

from stockchart import BarPlot, bar, mirror_bar

OUT = Path(__file__).resolve().parent.parent / "docs" / "images"


def save(plot: BarPlot, name: str, *, zh: bool) -> None:
    """按 README 语言保存原生 2x 示例图。"""
    path = OUT / f"{name}{'-zh' if zh else ''}.png"
    plot.save(path, scale=2)
    print(path.relative_to(OUT.parent.parent))


def render_language(*, zh: bool) -> None:
    """使用相同数据、样式与种子生成一种语言的示例。"""
    save(
        bar(
            [[320, 210], [450, 280], [510, 190]],
            labels=["一月", "二月", "三月"] if zh else ["Jan", "Feb", "Mar"],
            series_labels=["本站", "隔壁站"] if zh else ["This site", "Neighbor"],
            title="每月活跃用户" if zh else "Monthly report",
            xlabel="月份" if zh else "Month",
            ylabel="人数" if zh else "Active users",
            style=["black_sheer", "white_sheer"],
            value_labels=True,
            seed=2,
        ),
        "hero",
        zh=zh,
    )
    save(
        bar(
            [[4, 2], [6, 5], [2, 3], [3, 1]],
            labels=["阅读", "游戏", "远足", "烘焙"]
            if zh
            else ["Reading", "Gaming", "Hiking", "Baking"],
            series_labels=["计划", "实际"] if zh else ["Planned", "Actual"],
            title="周末计划与现实" if zh else "Weekend plans vs. reality",
            ylabel="小时" if zh else "Hours",
            style=["black_sheer", "white_sheer"],
            value_labels=True,
            seed=7,
        ),
        "showcase-grouped",
        zh=zh,
    )
    save(
        bar(
            [3, 7, -2, 9, 6, -4],
            labels=["周一", "周二", "周三", "周四", "周五", "周六"]
            if zh
            else ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"],
            title="本周心情" if zh else "This week's mood",
            style="heart_white",
            value_labels=True,
            seed=4,
        ),
        "showcase-single",
        zh=zh,
    )
    save(
        bar(
            [5, 6, 7, 8, 6, 9, 4],
            labels=["肉丝", "白丝", "彩条", "针织", "网袜", "波点", "厚袜"]
            if zh
            else ["Sheer", "Lace", "Stripe", "Knit", "Fishnet", "Dots", "Tights"],
            title="每种来一条" if zh else "One of each",
            style=[
                "nude_sheer",
                "white_sheer",
                "stripe_rainbow",
                "knit_cream",
                "fishnet_black",
                "polka_black",
                "black_pantyhose",
            ],
            value_labels=True,
            seed=3,
        ),
        "showcase-styles",
        zh=zh,
    )
    save(
        mirror_bar(
            [4.2, -2.8, 6.1, -5.5, 3.4, -1.9],
            labels=["周一", "周二", "周三", "周四", "周五", "周六"]
            if zh
            else ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"],
            title="每日变化" if zh else "Daily change",
            style="gray_sheer",
            value_labels=True,
            seed=2,
        ),
        "showcase-mirror",
        zh=zh,
    )


def main() -> None:
    """生成两种语言的首页及展示图。"""
    OUT.mkdir(parents=True, exist_ok=True)
    for zh in (False, True):
        render_language(zh=zh)


if __name__ == "__main__":
    main()
