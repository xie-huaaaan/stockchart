"""图表评审图生成：覆盖 L2–L4 的主要功能组合。

用法：uv run python tools/render_plot_review.py
输出：out/plots/ 下按编号命名的 PNG，供人工核对布局、图例、刻度与标签。
"""

from __future__ import annotations

from pathlib import Path

from stockchart import BarPlot, LegLibrary, Scale, bar, mirror_bar

ROOT = Path(__file__).parent.parent
OUT = ROOT / "out" / "plots"

LIB = LegLibrary(seed=7)


def save(plot: BarPlot, name: str, scale: float = 1.0) -> None:
    plot.save(OUT / name, scale=scale)
    print(name)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    # 01 单序列：参考图风格（灰丝、数值标签、无图例）
    save(
        bar(
            [320, 480, 250, 560, 410],
            labels=["一月", "二月", "三月", "四月", "五月"],
            title="脱粉量",
            style="gray_sheer",
            value_labels=True,
            seed=1,
        ),
        "01_bar_single.png",
    )

    # 02 分组成对（2 系列，左右腿配对 + 样式区分 + 图例）
    save(
        bar(
            [[320, 210], [450, 280], [510, 190], [260, 330]],
            labels=["1月", "2月", "3月", "4月"],
            series_labels=["本站", "隔壁站"],
            title="每月掉粉统计",
            style=["black_sheer", "white_sheer"],
            value_labels=True,
            seed=2,
        ),
        "02_bar_grouped_paired.png",
    )

    # 03 分组 3 系列（样式列表按组内位置循环 + 网格线）
    save(
        bar(
            [[300, 220, 410], [380, 260, 350], [290, 330, 450]],
            labels=["春", "夏", "秋"],
            series_labels=["棉袜", "网袜", "条纹"],
            title="三种袜子的人气度",
            style=["knit_cream", "fishnet_black", "stripe_pink_white"],
            grid=True,
            seed=3,
        ),
        "03_bar_grouped3_grid.png",
    )

    # 04 一维样式循环（每柱不同样式）
    save(
        bar(
            [200, 350, 500, 420, 280, 390, 450],
            labels=[f"第{i}名" for i in range(1, 8)],
            title="人气排行",
            style=[
                "black_sheer",
                "stripe_rainbow",
                "polka_black",
                "heart_white",
                "knit_gray",
                "fishnet_over_sheer",
                "stripe_blue_white",
            ],
            seed=4,
        ),
        "04_bar_style_cycle.png",
    )

    # 05 含负值（值域压缩、0 值带丝袜、y 轴 0 刻度悬在袜中）
    save(
        bar(
            [-20, 45, 0, 70, -35, 55],
            labels=["一", "二", "三", "四", "五", "六"],
            title="口碑净变化",
            value_labels=True,
            seed=5,
        ),
        "05_bar_negative.png",
    )

    # 06 镜像 single（正负镜像 + 轴下延 + x 标签锚定最低点）
    save(
        mirror_bar(
            [4.2, -2.8, 6.1, -5.5, 3.3, -1.2, 5.0],
            labels=["一", "二", "三", "四", "五", "六", "日"],
            title="每日好评率波动",
            style="gray_sheer",
            value_labels=True,
            seed=6,
        ),
        "06_mirror_single.png",
    )

    # 06b 镜像全正：没有朝下腿，x 标签自动贴到基线上方（无腿一侧）
    save(
        mirror_bar(
            [4.2, 2.8, 6.1, 5.5, 3.3],
            labels=["周一", "周二", "周三", "周四", "周五"],
            title="全正数据：标签在上",
            style="black_sheer",
            value_labels=True,
            seed=61,
        ),
        "06b_mirror_label_above.png",
    )

    # 07 镜像 both（数据侧穿袜、对侧裸腿）
    save(
        mirror_bar(
            [3.0, -4.5, 2.2, -1.5],
            labels=["甲", "乙", "丙", "丁"],
            mode="both",
            title="收支镜像",
            style="stripe_blue_white",
            seed=7,
        ),
        "07_mirror_both.png",
    )

    # 08 图例底部（覆盖 series_labels 生成的顶部图例）
    p8 = bar(
        [[100, 200, 150], [220, 180, 260]],
        labels=["A 组", "B 组"],
        series_labels=["系列一", "系列二", "系列三"],
        title="图例在底部",
        style=["black_tights", "white_tights", "stripe_black_white"],
        seed=8,
    )
    styles8 = ["black_tights", "white_tights", "stripe_black_white"]
    p8.add_legend(list(zip(["系列一", "系列二", "系列三"], styles8, strict=True)), loc="bottom")
    save(p8, "08_legend_bottom.png")

    # 09 L2 自由模式：手工 add_bar + 手动 Scale 配轴
    lib = LIB
    plot = BarPlot(1800, seed=9)
    plot.add_title("自由模式：任意位置贴腿")
    xs = [200.0, 600.0, 1000.0, 1400.0]
    for i, x in enumerate(xs):
        leg = lib.get(f"leg_{i * 5 + 1:02d}")
        plot.add_bar(x, 720 * (0.3 + 0.15 * i), leg, style="black_sheer")
    plot.add_bar(1650, 400, lib.get("leg_26"), style="fishnet_black", side="down")
    # 有一根朝下腿时默认锚定会退到最低点之下，这里显式贴基线写标签
    plot.add_x_labels(["A", "B", "C", "D"], xs=xs, pos="below")
    plot.add_y_axis(Scale((0, 720), (0, 760)), label="自定义", grid=True)
    plot.add_legend([("黑丝", "black_sheer"), ("网袜", "fishnet_black")])
    save(plot, "09_l2_free.png")

    # 10 成对镜像（2 系列分组数据 + 镜像）
    save(
        mirror_bar(
            [[3.5, -2.0], [-1.5, 4.0], [2.0, -3.5]],
            labels=["一", "二", "三"],
            series_labels=["收入", "支出"],
            title="分组镜像",
            style=["black_sheer", "heart_white"],
            seed=10,
        ),
        "10_mirror_grouped.png",
    )

    # 11 过长的 x 标签：固定宽度下自动倾斜避让
    p11 = BarPlot(1200, seed=11)
    xs11 = [150.0, 450.0, 750.0, 1050.0]
    long_labels = [
        "超长的第一个月份标签",
        "超长的第二个月份标签",
        "超长的第三个月份标签",
        "超长的第四个月份标签",
    ]
    for i, x in enumerate(xs11):
        p11.add_bar(x, 300 + 60 * i, LIB.get(f"leg_{i * 4 + 1:02d}"), style="gray_sheer")
    p11.add_x_labels(long_labels, xs=xs11)
    p11.add_y_axis(Scale((0, 600), (0, 760)), label="数量")
    p11.add_title("长 x 标签自动倾斜")
    save(p11, "11_long_x_labels.png")

    # 12 过长的图例标签：自动换行（最多三行，仍放不下则省略）
    save(
        bar(
            [[3, 4], [5, 2], [4, 6]],
            labels=["一月", "二月", "三月"],
            series_labels=[
                "一个非常非常非常非常非常非常非常非常非常非常非常非常非常长的系列名称"
                "（后半段继续很长很长很长很长很长很长很长很长）",
                "另一个同样很长但略短一些的系列名称",
            ],
            title="长图例标签自动换行",
            style=["black_sheer", "white_sheer"],
            seed=12,
        ),
        "12_long_legend.png",
    )

    # 13 手绘风坐标轴（默认 clean，仅显式开启时抖动）
    save(
        bar(
            [320, 480, 250, 560, 410],
            labels=["一月", "二月", "三月", "四月", "五月"],
            title="手绘风坐标轴（可选）",
            style="gray_sheer",
            value_labels=True,
            axis_style="handdrawn",
            seed=13,
        ),
        "13_axis_handdrawn.png",
    )


if __name__ == "__main__":
    main()
