"""L0 素材层：LegLibrary 与 load_leg。"""

from __future__ import annotations

import json
import random
import re
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import Literal, cast

import numpy as np
from numpy.typing import NDArray
from PIL import Image, ImageDraw, ImageFont

from stockchart.defaults import DEFAULT_BACKGROUND
from stockchart.legs import Leg
from stockchart.vector import rasterize_svg

# ---------------------------------------------------------------------------
# load_leg：从外部 PNG 加载自定义腿素材
# ---------------------------------------------------------------------------


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
    """
    with Image.open(png) as source:
        img = np.asarray(source.convert("RGBA"))
    H, W = img.shape[:2]

    est_cx = _estimate_foot_center(img)
    return Leg(
        image=img,
        width=W,
        height=H,
        foot_center_x=foot_center_x if foot_center_x is not None else est_cx,
    )


def _estimate_foot_center(img: NDArray[np.uint8]) -> int:
    """按底部若干行的 alpha 质心估计足底中心 x。"""
    H, W = img.shape[:2]
    foot_rows = min(20, H)
    bot = img[H - foot_rows :, :, 3].astype(float)
    col_sum = bot.sum(0)
    if col_sum.sum() < 1:
        return W // 2
    xs = np.arange(W, dtype=float)
    return int((col_sum * xs).sum() / col_sum.sum())


# ---------------------------------------------------------------------------
# 元数据校验
# ---------------------------------------------------------------------------

_LEG_ID = re.compile(r"^leg_\d{2,}$")
_PAIR_ID = re.compile(r"^pair_\d{2,}$")
_META_KEYS = frozenset({"leg_id", "pair_id", "side", "width", "height", "foot_center_x"})


@dataclass(slots=True, frozen=True)
class _LegMeta:
    """legs.json 中的一条素材元数据（设计像素）。"""

    leg_id: str
    pair_id: str
    side: Literal["left", "right"]
    width: int
    height: int
    foot_center_x: int


def _parse_meta(raw: object) -> _LegMeta:
    """校验并转换单条元数据。"""
    if not isinstance(raw, dict):
        raise ValueError("应为对象")
    entry = cast("dict[str, object]", raw)

    keys = set(entry)
    missing = _META_KEYS - keys
    extra = keys - _META_KEYS
    if missing:
        raise ValueError(f"缺少字段 {sorted(missing)}")
    if extra:
        raise ValueError(f"未知字段 {sorted(extra)}")

    def text(key: str) -> str:
        value = entry[key]
        if not isinstance(value, str) or not value:
            raise ValueError(f"{key} 应为非空字符串")
        return value

    def integer(key: str) -> int:
        value = entry[key]
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError(f"{key} 应为整数")
        return value

    leg_id = text("leg_id")
    pair_id = text("pair_id")
    if not _LEG_ID.fullmatch(leg_id):
        raise ValueError(f"leg_id 格式应为 leg_NN，得到 {leg_id!r}")
    if not _PAIR_ID.fullmatch(pair_id):
        raise ValueError(f"pair_id 格式应为 pair_NN，得到 {pair_id!r}")

    side = text("side")
    if side not in ("left", "right"):
        raise ValueError(f"side 应为 'left' 或 'right'，得到 {side!r}")

    width = integer("width")
    height = integer("height")
    foot_center_x = integer("foot_center_x")
    if width <= 0 or height <= 0:
        raise ValueError(f"width/height 须为正数，得到 {width}×{height}")
    if not 0 <= foot_center_x < width:
        raise ValueError(f"foot_center_x 超出 [0, width)：{foot_center_x} / {width}")

    return _LegMeta(
        leg_id=leg_id,
        pair_id=pair_id,
        side=side,
        width=width,
        height=height,
        foot_center_x=foot_center_x,
    )


def _parse_metadata(raw: bytes) -> tuple[_LegMeta, ...]:
    """解析并校验 legs.json，返回按 leg_id 排序的元数据。"""
    try:
        data = cast("object", json.loads(raw))
    except json.JSONDecodeError as exc:
        raise ValueError(f"legs.json 不是合法 JSON：{exc}") from exc
    if not isinstance(data, list):
        raise ValueError("legs.json 顶层应为数组")

    metas: list[_LegMeta] = []
    errors: list[str] = []
    for i, item in enumerate(cast("list[object]", data)):
        try:
            metas.append(_parse_meta(item))
        except ValueError as exc:
            errors.append(f"第 {i + 1} 项：{exc}")

    seen: set[str] = set()
    for meta in metas:
        if meta.leg_id in seen:
            errors.append(f"leg_id 重复：{meta.leg_id}")
        seen.add(meta.leg_id)

    pair_sides: dict[str, dict[str, str]] = {}
    for meta in metas:
        sides = pair_sides.setdefault(meta.pair_id, {})
        if meta.side in sides:
            errors.append(
                f"{meta.pair_id} 有重复的 {meta.side} 腿：{sides[meta.side]} 与 {meta.leg_id}"
            )
        else:
            sides[meta.side] = meta.leg_id
    for pair_id, sides in sorted(pair_sides.items()):
        if "left" not in sides:
            errors.append(f"{pair_id} 缺少左腿")
        if "right" not in sides:
            errors.append(f"{pair_id} 缺少右腿")

    if errors:
        raise ValueError("legs.json 校验失败：\n" + "\n".join(f"- {e}" for e in errors))
    return tuple(sorted(metas, key=lambda meta: meta.leg_id))


# ---------------------------------------------------------------------------
# LegLibrary：内置素材库
# ---------------------------------------------------------------------------


class LegLibrary:
    """内置腿部素材库（26 条腿 / 13 对）。

    所有 Leg 对象在首次访问时懒加载并缓存；反复调用 get/pair 不会重复读磁盘。
    """

    def __init__(self, *, seed: int | None = None) -> None:
        """Seed 作为后续自动选腿的随机源；不传则每次运行随机。"""
        self._rng = random.Random(seed)
        self._meta = _parse_metadata(files("stockchart.assets").joinpath("legs.json").read_bytes())
        self._by_id = {meta.leg_id: meta for meta in self._meta}
        self._cache: dict[str, Leg] = {}

        pair_sides: dict[str, dict[str, str]] = {}
        for meta in self._meta:
            pair_sides.setdefault(meta.pair_id, {})[meta.side] = meta.leg_id
        self._pair_map: dict[str, tuple[str, str]] = {
            pair_id: (sides["left"], sides["right"]) for pair_id, sides in pair_sides.items()
        }
        self._pair_ids = tuple(sorted(self._pair_map))

    @property
    def leg_ids(self) -> tuple[str, ...]:
        """全部腿编号，按编号排序。"""
        return tuple(meta.leg_id for meta in self._meta)

    @property
    def pair_ids(self) -> tuple[str, ...]:
        """全部配对编号，按编号排序。"""
        return self._pair_ids

    def __repr__(self) -> str:
        return f"LegLibrary({len(self._meta)} legs / {len(self._pair_ids)} pairs)"

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------

    def get(self, leg_id: str) -> Leg:
        """按编号取一条腿（如 leg_03）。

        Args:
            leg_id: 内置腿编号，格式为 "leg_NN"。

        Returns:
            对应的 Leg 实例（懒加载）。

        Raises:
            KeyError: 编号不存在。
        """
        meta = self._by_id.get(leg_id)
        if meta is None:
            first, last = self._meta[0].leg_id, self._meta[-1].leg_id
            raise KeyError(f"未知腿编号 {leg_id!r}，合法范围 {first} … {last}")
        return self._load_leg(meta)

    def pair(self, pair_id: str) -> tuple[Leg, Leg]:
        """取一对腿，返回 (左腿, 右腿)。

        Args:
            pair_id: 配对编号，格式为 "pair_NN"。

        Returns:
            (左腿, 右腿)。

        Raises:
            KeyError: 配对编号不存在。
        """
        ids = self._pair_map.get(pair_id)
        if ids is None:
            raise KeyError(
                f"未知配对编号 {pair_id!r}，合法范围 {self._pair_ids[0]} … {self._pair_ids[-1]}"
            )
        return self._load_leg(self._by_id[ids[0]]), self._load_leg(self._by_id[ids[1]])

    def alternate(self, n: int, *, paired: bool = False) -> list[Leg]:
        """按左、右、左、右……的顺序选出 n 条腿。

        Args:
            n: 需要的腿数。
            paired: False（默认）时每条腿来自不同素材对；True 时相邻两条腿
                组成一对（左、右），素材对之间按 seed 伪随机且优先不重复。
                n 为奇数时最后一对只取左腿。

        Returns:
            长度为 n 的 Leg 列表，偶数下标为左腿，奇数下标为右腿（0-based）。

        超过 13 对后从已用素材继续复用。
        """
        if n < 0:
            raise ValueError(f"n 不能为负数，得到 {n}")
        pair_ids = self._shuffled_pair_ids()
        result: list[Leg] = []
        for i in range(n):
            pair_index = i // 2 if paired else i
            pair_id = pair_ids[pair_index % len(pair_ids)]
            left, right = self.pair(pair_id)
            result.append(left if i % 2 == 0 else right)
        return result

    def sample_pairs(self, n: int) -> list[tuple[Leg, Leg]]:
        """选出 n 对完整素材（成对布局用），选取规则同 alternate。

        Args:
            n: 需要的对数。

        Returns:
            长度为 n 的 (左腿, 右腿) 列表。

        Raises:
            ValueError: n 为负数。
        """
        if n < 0:
            raise ValueError(f"n 不能为负数，得到 {n}")
        pair_ids = self._shuffled_pair_ids()
        return [self.pair(pair_ids[i % len(pair_ids)]) for i in range(n)]

    def preview(self, *, scale: float = 0.5) -> Image.Image:
        """生成全部内置素材的目录图，供浏览和选型。

        按配对分组排列（每行 4 对），标注 pair_id、leg_id 与左右脚。
        这是浏览工具，不在渲染热路径；首次调用会加载全部腿素材。

        Args:
            scale: 预览图相对设计尺寸的倍率，须为正数。

        Returns:
            RGB 模式的 PIL Image。
        """
        if scale <= 0:
            raise ValueError(f"scale 须为正数，得到 {scale}")

        imgs: dict[str, Image.Image] = {
            meta.leg_id: Image.fromarray(self._load_leg(meta).at_density(scale).image)
            for meta in self._meta
        }
        font = ImageFont.load_default(size=16)
        title_font = ImageFont.load_default(size=22)
        margin, pair_gap, leg_gap, row_gap = 24, 30, 8, 34
        pair_label_h, leg_label_h, pairs_per_row = 22, 22, 4

        pairs = [(pair_id, self._pair_map[pair_id]) for pair_id in self._pair_ids]
        rows = [pairs[i : i + pairs_per_row] for i in range(0, len(pairs), pairs_per_row)]

        leg_h = max(img.height for img in imgs.values())
        row_widths: list[int] = []
        for row in rows:
            width = sum(
                imgs[left_id].width + leg_gap + imgs[right_id].width
                for _, (left_id, right_id) in row
            )
            width += pair_gap * (len(row) - 1)
            row_widths.append(width)

        title = f"stockchart leg library - {len(self._meta)} legs / {len(self._pair_ids)} pairs"
        title_box = title_font.getbbox(title)
        title_w = round(title_box[2] - title_box[0])
        title_h = round(title_box[3] - title_box[1])

        width = max(max(row_widths, default=0), title_w) + 2 * margin
        height = margin + title_h + row_gap
        height += len(rows) * (pair_label_h + leg_h + leg_label_h + row_gap)
        height += margin - row_gap

        canvas = Image.new("RGB", (width, height), DEFAULT_BACKGROUND)
        draw = ImageDraw.Draw(canvas)
        draw.text((margin, margin), title, fill=(58, 58, 58), font=title_font)

        y = margin + title_h + row_gap
        for row in rows:
            x = margin
            for pair_id, (left_id, right_id) in row:
                left, right = imgs[left_id], imgs[right_id]
                pair_w = left.width + leg_gap + right.width
                draw.text((x, y), pair_id, fill=(150, 110, 110), font=font)
                leg_y = y + pair_label_h
                canvas.paste(left, (x, leg_y), left)
                canvas.paste(right, (x + left.width + leg_gap, leg_y), right)
                for leg_id, side, offset in (
                    (left_id, "L", 0),
                    (right_id, "R", left.width + leg_gap),
                ):
                    label = f"{leg_id} {side}"
                    label_box = font.getbbox(label)
                    label_w = round(label_box[2] - label_box[0])
                    leg_w = imgs[leg_id].width
                    draw.text(
                        (x + offset + (leg_w - label_w) // 2, leg_y + leg_h + 4),
                        label,
                        fill=(70, 70, 70),
                        font=font,
                    )
                x += pair_w + pair_gap
            y += pair_label_h + leg_h + leg_label_h + row_gap

        return canvas

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------

    def _load_leg(self, meta: _LegMeta) -> Leg:
        """懒加载单条腿的 SVG，栅格化设计尺寸预览并缓存。"""
        cached = self._cache.get(meta.leg_id)
        if cached is not None:
            return cached

        pkg = files("stockchart.assets")
        svg = pkg.joinpath(f"{meta.leg_id}.svg").read_bytes()
        image = rasterize_svg(svg, meta.width, meta.height)
        leg = Leg(
            image=image,
            width=meta.width,
            height=meta.height,
            foot_center_x=meta.foot_center_x,
            leg_id=meta.leg_id,
            pair_id=meta.pair_id,
            side=meta.side,
            svg=svg,
        )
        self._cache[meta.leg_id] = leg
        return leg

    def _shuffled_pair_ids(self) -> list[str]:
        """返回随机打乱顺序的配对 ID 列表（按 seed 确定性打乱）。"""
        ids = list(self._pair_ids)
        self._rng.shuffle(ids)
        return ids
