"""L1 渲染原语：手绘风线条与坐标轴（seed 控制的确定性抖动）。"""

from __future__ import annotations

import math
import random
from collections.abc import Sequence
from typing import Literal

import skia

from stockchart.canvas import Canvas, skia_color
from stockchart.color import Color
from stockchart.defaults import (
    DEFAULT_ARROW_HALF_ANGLE_DEG,
    DEFAULT_ARROW_SIZE,
    DEFAULT_INK_COLOR,
    DEFAULT_SKETCH_SEGMENT_PX,
    DEFAULT_STROKE_WIDTH,
    DEFAULT_TICK_LABEL_GAP,
    DEFAULT_TICK_LABEL_SIZE,
    DEFAULT_TICK_SIZE,
    DEFAULT_WOBBLE,
)
from stockchart.text import TextAnchor, draw_text

type AxisDirection = Literal["up", "down", "right"]

_DIRECTION_VECTORS: dict[str, tuple[float, float]] = {
    "up": (0.0, -1.0),
    "down": (0.0, 1.0),
    "right": (1.0, 0.0),
}

# 刻度与数字所在的一侧：垂直轴朝左、水平轴朝下
_TICK_SIDE: dict[str, tuple[float, float]] = {
    "up": (-1.0, 0.0),
    "down": (-1.0, 0.0),
    "right": (0.0, 1.0),
}


def _jittered_points(
    x1: float, y1: float, x2: float, y2: float, wobble: float, rng: random.Random
) -> list[tuple[float, float]]:
    """把线段细分成中频抖动的折线点列；端点保持原位。"""
    dx, dy = x2 - x1, y2 - y1
    length = math.hypot(dx, dy)
    if length < 1e-6:
        return []
    if wobble <= 0:
        return [(x1, y1), (x2, y2)]

    n = max(3, min(64, math.ceil(length / DEFAULT_SKETCH_SEGMENT_PX) + 1))
    # 随机游走 + 两轮邻域平均，得到中频波形；逐点独立噪声会呈锯齿感
    raw = [rng.uniform(-1.0, 1.0) for _ in range(n)]
    for _ in range(2):
        raw = [(raw[max(i - 1, 0)] + raw[i] + raw[min(i + 1, n - 1)]) / 3.0 for i in range(n)]
    peak = max(abs(o) for o in raw)
    scale = wobble / peak if peak > 1e-9 else 0.0

    px, py = -dy / length, dx / length  # 单位法向
    points: list[tuple[float, float]] = []
    for i in range(n):
        t = i / (n - 1)
        bx, by = x1 + t * dx, y1 + t * dy
        if 0 < i < n - 1:
            off = raw[i] * scale
            bx, by = bx + px * off, by + py * off
        points.append((bx, by))
    return points


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
    """手绘风直线：对线段做确定性细分抖动，两端点保持原位。wobble 为 0 时画直线。"""
    rng = random.Random(seed)
    points = _jittered_points(x1, y1, x2, y2, wobble, rng)
    if not points:
        return
    path = skia.Path()
    path.moveTo(points[0][0], points[0][1])
    for px, py in points[1:]:
        path.lineTo(px, py)
    paint = skia.Paint(
        AntiAlias=True,
        Color=skia_color(color),
        Style=skia.Paint.kStroke_Style,
        StrokeWidth=width_px,
        StrokeCap=skia.Paint.kRound_Cap,
        StrokeJoin=skia.Paint.kRound_Join,
    )
    canvas.skia_canvas().drawPath(path, paint)


def sketch_axis(
    canvas: Canvas,
    *,
    direction: AxisDirection,
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
    ticks 为 (距起点的像素偏移, 标签文字)：垂直轴的刻度与数字在干线左侧，
    水平轴的在其下侧。
    """
    rng = random.Random(seed)

    def child_seed() -> int:
        return rng.getrandbits(32)

    ux, uy = _DIRECTION_VECTORS[direction]
    end_x, end_y = x + ux * length, y + uy * length
    sketch_line(
        canvas,
        x,
        y,
        end_x,
        end_y,
        color=color,
        width_px=width_px,
        wobble=wobble,
        seed=child_seed(),
    )

    if arrow and length > 0:
        angle = math.radians(DEFAULT_ARROW_HALF_ANGLE_DEG)
        size = DEFAULT_ARROW_SIZE
        # 两翼 = 反向干线分别向两侧旋开半角
        bx, by = -ux, -uy
        px_, py_ = -uy, ux
        for sign in (1.0, -1.0):
            wing_x = end_x + size * (bx * math.cos(angle) + px_ * sign * math.sin(angle))
            wing_y = end_y + size * (by * math.cos(angle) + py_ * sign * math.sin(angle))
            sketch_line(
                canvas,
                end_x,
                end_y,
                wing_x,
                wing_y,
                color=color,
                width_px=width_px,
                wobble=wobble * 0.5,
                seed=child_seed(),
            )

    sx, sy = _TICK_SIDE[direction]
    for offset, label in ticks:
        ax, ay = x + ux * offset, y + uy * offset
        tick_x, tick_y = ax + sx * DEFAULT_TICK_SIZE, ay + sy * DEFAULT_TICK_SIZE
        sketch_line(
            canvas,
            ax,
            ay,
            tick_x,
            tick_y,
            color=color,
            width_px=width_px,
            wobble=wobble * 0.5,
            seed=child_seed(),
        )
        label_anchor: TextAnchor
        if direction == "right":
            label_pos = (ax, tick_y + DEFAULT_TICK_LABEL_GAP)
            label_anchor = ("center", "top")
        else:
            label_pos = (tick_x - DEFAULT_TICK_LABEL_GAP, ay)
            label_anchor = ("right", "middle")
        draw_text(
            canvas,
            label,
            label_pos[0],
            label_pos[1],
            size_px=DEFAULT_TICK_LABEL_SIZE,
            color=color,
            anchor=label_anchor,
        )
