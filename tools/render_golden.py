"""黄金图基线：渲染固定场景并记录 SHA-256，用于重构前后比对。

用法：
    uv run python tools/render_golden.py           # 生成 / 更新基线
    uv run python tools/render_golden.py --check   # 重新渲染并与基线比对

基线写在 out/golden/（不进版本库）：PNG 字节依赖 skia 版本与系统字体，
换机器需重新生成。场景覆盖全部 19 个样式预设、L2–L4 的主要布局组合与文字绘制，
任何渲染算法或布局几何的改动都会让哈希变化。
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path

import numpy as np
from numpy.typing import NDArray
from PIL import Image

from stockchart import (
    STYLES,
    BarPlot,
    Canvas,
    LegLibrary,
    Scale,
    bar,
    draw_text,
    mirror_bar,
    render_stocking,
)

ROOT = Path(__file__).parent.parent
OUT = ROOT / "out" / "golden"
MANIFEST = OUT / "manifest.json"

LIB = LegLibrary(seed=7)


def _plot_image(plot: BarPlot, scale: float = 1.0) -> NDArray[np.uint8]:
    return plot.render(scale=scale).to_numpy()


def _stocking_image(style_key: str) -> NDArray[np.uint8]:
    leg = LIB.get("leg_01")
    out = render_stocking(leg, STYLES[style_key], 400, seed=7)
    return out.image


def _text_image() -> NDArray[np.uint8]:
    canvas = Canvas(520, 260, background=(250, 248, 243))
    draw_text(canvas, "脱粉量 123", 20, 60, size_px=32)
    draw_text(canvas, "竖排文字 ABC", 40, 200, size_px=28, anchor=("left", "bottom"))
    draw_text(canvas, "旋转", 300, 200, size_px=28, anchor=("right", "top"), rotation=-45)
    return canvas.to_numpy()


def _free_form_image() -> NDArray[np.uint8]:
    """L3 自由布局：add_bars / add_grouped_bars / add_paired_bars 混用。"""
    plot = BarPlot(1600, seed=21)
    plot.add_bars([200.0, 340.0, 260.0], bar_gap=24)
    plot.add_grouped_bars([[300.0, 180.0], [260.0, 340.0]], bar_gap=16, group_gap=60)
    plot.add_paired_bars([(280.0, 150.0)])
    plot.add_x_labels(["一", "二", "三"])
    plot.add_title("自由布局")
    plot.add_y_axis(Scale((0.0, 400.0), (0.0, 700.0)), grid=True)
    plot.add_y_axis_name("数量")
    return _plot_image(plot)


def _annotations_image() -> NDArray[np.uint8]:
    """标注密集场景：标题 / 轴名 / 图例 / 旋转标签 / 数值标签。"""
    plot = bar(
        [[320.0, 210.0], [450.0, 280.0]],
        labels=["超长的第一个月份标签", "超长的第二个月份标签"],
        series_labels=["本站", "隔壁站"],
        title="每月掉粉统计",
        xlabel="月份",
        ylabel="人数",
        style=["black_sheer", "white_sheer"],
        value_labels=True,
        seed=22,
    )
    plot.add_legend([("黑丝", "black_sheer"), ("白丝", "white_sheer")], loc="bottom")
    return _plot_image(plot)


def build_scenarios() -> dict[str, Callable[[], NDArray[np.uint8]]]:
    """列出全部黄金图场景。"""
    scenarios: dict[str, Callable[[], NDArray[np.uint8]]] = {
        f"style_{key}": (lambda k=key: _stocking_image(k)) for key in sorted(STYLES)
    }
    scenarios.update(
        {
            "bar_single": lambda: _plot_image(
                bar(
                    [320.0, 480.0, 250.0, 560.0, 410.0],
                    labels=["一月", "二月", "三月", "四月", "五月"],
                    title="脱粉量",
                    style="gray_sheer",
                    value_labels=True,
                    seed=1,
                )
            ),
            "bar_grouped": lambda: _plot_image(
                bar(
                    [[320.0, 210.0], [450.0, 280.0], [510.0, 190.0]],
                    labels=["1月", "2月", "3月"],
                    series_labels=["本站", "隔壁站"],
                    title="每月掉粉统计",
                    style=["black_sheer", "white_sheer"],
                    value_labels=True,
                    seed=2,
                )
            ),
            "bar_negative": lambda: _plot_image(
                bar(
                    [-20.0, 45.0, 0.0, 70.0, -35.0],
                    labels=["一", "二", "三", "四", "五"],
                    title="口碑净变化",
                    value_labels=True,
                    seed=5,
                )
            ),
            "bar_grid_handdrawn": lambda: _plot_image(
                bar(
                    [320.0, 480.0, 250.0],
                    labels=["一月", "二月", "三月"],
                    title="手绘风坐标轴",
                    style="gray_sheer",
                    axis_style="handdrawn",
                    grid=True,
                    seed=13,
                )
            ),
            "bar_scale2": lambda: _plot_image(
                bar([320.0, 480.0, 250.0], labels=["一月", "二月", "三月"], seed=23),
                scale=2.0,
            ),
            "mirror_single": lambda: _plot_image(
                mirror_bar(
                    [4.2, -2.8, 6.1, -5.5],
                    labels=["一", "二", "三", "四"],
                    title="每日好评率波动",
                    style="gray_sheer",
                    value_labels=True,
                    seed=6,
                )
            ),
            "mirror_both": lambda: _plot_image(
                mirror_bar(
                    [3.0, -4.5, 2.2, -1.5],
                    labels=["甲", "乙", "丙", "丁"],
                    mode="both",
                    title="收支镜像",
                    style="stripe_blue_white",
                    seed=7,
                )
            ),
            "l2_free_form": _free_form_image,
            "annotations": _annotations_image,
            "text": _text_image,
        }
    )
    return scenarios


def _hash(arr: NDArray[np.uint8]) -> str:
    return hashlib.sha256(arr.tobytes()).hexdigest()


def main(check: bool = False) -> int:
    scenarios = build_scenarios()
    OUT.mkdir(parents=True, exist_ok=True)

    results: dict[str, dict[str, object]] = {}
    for name, make in scenarios.items():
        arr = make()
        results[name] = {"sha256": _hash(arr), "shape": list(arr.shape)}
        if not check:
            Image.fromarray(arr, "RGBA").save(OUT / f"{name}.png")

    if check:
        if not MANIFEST.exists():
            print("✗ 找不到基线，先运行 uv run python tools/render_golden.py 生成")
            return 1
        baseline = json.loads(MANIFEST.read_text(encoding="utf-8"))["scenarios"]
        changed = [
            name
            for name, info in results.items()
            if name not in baseline or baseline[name]["sha256"] != info["sha256"]
        ]
        missing = sorted(set(baseline) - set(results))
        for name in changed:
            print(f"✗ {name} 与基线不一致")
        for name in missing:
            print(f"✗ 基线里的 {name} 已不存在")
        if changed or missing:
            print(f"\n共 {len(changed) + len(missing)} 个场景与基线不同")
            return 1
        print(f"✓ {len(results)} 个场景与基线逐字节一致")
        return 0

    MANIFEST.write_text(
        json.dumps({"count": len(results), "scenarios": results}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"✓ 已写入 {len(results)} 张黄金图与基线：{OUT}")
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main(check="--check" in sys.argv))
