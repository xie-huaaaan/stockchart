"""L0 素材库与 PNG/SVG 外部素材加载。"""

from __future__ import annotations

import json
import math
import random
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from importlib.resources import files
from io import BytesIO
from pathlib import Path
from types import MappingProxyType
from typing import Literal, cast

import numpy as np
from numpy.typing import NDArray
from PIL import Image, ImageDraw, ImageFont

from stockchart.defaults import DEFAULT_BACKGROUND
from stockchart.legs import Leg
from stockchart.vector import svg_dimensions

_LEG_ID = re.compile(r"^leg_\d{2,}$")
_PAIR_ID = re.compile(r"^pair_\d{2,}$")


def _estimate_foot_center(image: NDArray[np.uint8], width: float, height: float) -> float:
    """按底部最多 20 个设计像素的 alpha 质心估算足底中心。"""
    rows = min(image.shape[0], max(1, round(20 * image.shape[0] / height)))
    alpha = image[-rows:, :, 3].astype(np.float64)
    columns = alpha.sum(axis=0)
    if columns.sum() <= 0:
        return width / 2
    xs = np.arange(image.shape[1], dtype=np.float64) * width / image.shape[1]
    return float((columns * xs).sum() / columns.sum())


def load_leg(
    path: str | Path,
    *,
    foot_center_x: float | None = None,
    leg_id: str | None = None,
    pair_id: str | None = None,
    side: Literal["left", "right"] | None = None,
) -> Leg:
    """从 PNG 或 SVG 加载一条外部素材。

    Args:
        path: PNG 或 SVG 文件路径。
        foot_center_x: 足底中心设计坐标；省略时按底部 alpha 质心估算。
        leg_id: 可选的库内标识。
        pair_id: 可选的配对标识。
        side: 可选的左右侧；需与 pair_id 同时提供才参与配对。

    Returns:
        统一的不可变 `Leg` 素材源。

    Raises:
        OSError: 文件无法读取。
        ValueError: 格式、尺寸或锚点无效。
    """
    file_path = Path(path)
    suffix = file_path.suffix.lower()
    source = file_path.read_bytes()
    if suffix == ".svg":
        width, height = svg_dimensions(source)
        source_type: Literal["png", "svg"] = "svg"
    elif suffix == ".png":
        with Image.open(BytesIO(source)) as opened:
            if opened.format != "PNG":
                raise ValueError("PNG 路径须包含 PNG 素材")
            width, height = map(float, opened.size)
        source_type = "png"
    else:
        raise ValueError(f"仅支持 PNG 或 SVG，得到 {file_path.suffix!r}")
    leg = Leg(
        source=source,
        source_type=source_type,
        width=width,
        height=height,
        foot_center_x=width / 2 if foot_center_x is None else foot_center_x,
        leg_id=leg_id,
        pair_id=pair_id,
        side=side,
    )
    if foot_center_x is None:
        anchor = _estimate_foot_center(leg.raster_at(), width, height)
        leg = replace(leg, foot_center_x=anchor)
    return leg


_META_KEYS = frozenset({"leg_id", "pair_id", "side", "width", "height", "foot_center_x"})


@dataclass(slots=True, frozen=True)
class _LegMeta:
    """legs.json 中的一条素材元数据（设计像素）。

    Attributes:
        leg_id: 腿编号，形如 leg_NN。
        pair_id: 配对编号，形如 pair_NN。
        side: 左腿或右腿。
        width: 设计像素宽。
        height: 设计像素高。
        foot_center_x: 足底中心的设计像素 x。
    """

    leg_id: str
    pair_id: str
    side: Literal["left", "right"]
    width: int
    height: int
    foot_center_x: int


def _parse_meta(raw: object) -> _LegMeta:
    """校验并转换单条 legs.json 元数据。

    Args:
        raw: JSON 解析后的单个对象。

    Returns:
        校验通过的 _LegMeta。

    Raises:
        ValueError: 不是对象、字段缺失/多余、字段类型或取值不合法。
    """
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
        """读取必填的非空字符串字段。

        Raises:
            ValueError: 字段缺失或不是非空字符串。
        """
        value = entry[key]
        if not isinstance(value, str) or not value:
            raise ValueError(f"{key} 应为非空字符串")
        return value

    def integer(key: str) -> int:
        """读取必填的整数字段（bool 不算整数）。

        Raises:
            ValueError: 字段缺失或不是整数。
        """
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
    """解析并校验 legs.json，返回按 leg_id 排序的元数据。

    一次性收集全部错误，便于修复素材文件。

    Args:
        raw: legs.json 的原始字节。

    Returns:
        按 leg_id 排序的元数据元组。

    Raises:
        ValueError: JSON 非法、顶层不是非空数组，或任一条目/配对关系不合法。
    """
    try:
        data = cast("object", json.loads(raw))
    except json.JSONDecodeError as exc:
        raise ValueError(f"legs.json 不是合法 JSON：{exc}") from exc
    if not isinstance(data, list):
        raise ValueError("legs.json 顶层应为数组")
    if not data:
        raise ValueError("legs.json 不能为空")

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


class _LibraryState:
    """库拥有的懒加载对象，不持有目标倍率的大型像素缓存。"""

    __slots__ = ("loaded",)

    def __init__(self) -> None:
        self.loaded: dict[str, Leg] = {}


@dataclass(slots=True, frozen=True, init=False, repr=False)
class LegLibrary:
    """由内置或外部素材组成的不可变腿库，像素按需生成。

    Args:
        legs: 素材序列；None 使用内置库，可混入默认库中的 Leg。
        seed: 选腿方法的默认种子；方法级 seed 优先，不记录随机状态。

    Raises:
        ValueError: 自定义库为空、腿标识重复、同一配对的左右侧重复，
            或内置元数据无效。
    """

    _entries: tuple[Leg | _LegMeta, ...]
    _by_id: Mapping[str, Leg | _LegMeta]
    _pairs: Mapping[str, tuple[Leg | _LegMeta, Leg | _LegMeta]]
    _state: _LibraryState
    _seed: int | None

    def __init__(self, legs: Sequence[Leg] | None = None, *, seed: int | None = None) -> None:
        entries: tuple[Leg | _LegMeta, ...] = (
            _parse_metadata(files("stockchart.assets").joinpath("legs.json").read_bytes())
            if legs is None
            else tuple(legs)
        )
        if not entries:
            raise ValueError("LegLibrary 至少需要一条腿")
        by_id: dict[str, Leg | _LegMeta] = {}
        grouped: dict[str, dict[str, Leg | _LegMeta]] = {}
        for leg in entries:
            if leg.leg_id is not None:
                if leg.leg_id in by_id:
                    raise ValueError(f"leg_id 重复：{leg.leg_id}")
                by_id[leg.leg_id] = leg
            if leg.pair_id is not None and leg.side is not None:
                sides = grouped.setdefault(leg.pair_id, {})
                if leg.side in sides:
                    raise ValueError(f"{leg.pair_id} 重复 {leg.side} 腿")
                sides[leg.side] = leg
        pairs = {
            pair_id: (sides["left"], sides["right"])
            for pair_id, sides in sorted(grouped.items())
            if "left" in sides and "right" in sides
        }
        object.__setattr__(self, "_entries", entries)
        object.__setattr__(self, "_by_id", MappingProxyType(by_id))
        object.__setattr__(self, "_pairs", MappingProxyType(pairs))
        object.__setattr__(self, "_state", _LibraryState())
        object.__setattr__(self, "_seed", seed)

    @property
    def legs(self) -> tuple[Leg, ...]:
        """按库内顺序返回全部腿，包括无标识或未配对素材。

        Returns:
            只读 Leg 元组；内置腿的源文件在首次访问时读取，不生成预览。
        """
        return tuple(self._load(entry) for entry in self._entries)

    @property
    def leg_ids(self) -> tuple[str, ...]:
        """返回按编号排序的非空腿标识，不加载素材源。"""
        return tuple(sorted(self._by_id))

    @property
    def pair_ids(self) -> tuple[str, ...]:
        """返回按编号排序的完整配对标识，不加载素材源。"""
        return tuple(self._pairs)

    def __repr__(self) -> str:
        """返回腿数和完整配对数。"""
        return f"LegLibrary({len(self._entries)} legs / {len(self._pairs)} pairs)"

    def _load(self, entry: Leg | _LegMeta) -> Leg:
        """懒加载内置源；外部 Leg 直接复用，混合库保持对象身份。"""
        if isinstance(entry, Leg):
            return entry
        cached = self._state.loaded.get(entry.leg_id)
        if cached is not None:
            return cached
        source = files("stockchart.assets").joinpath(f"{entry.leg_id}.svg").read_bytes()
        leg = Leg(
            source,
            "svg",
            entry.width,
            entry.height,
            entry.foot_center_x,
            entry.leg_id,
            entry.pair_id,
            entry.side,
        )
        self._state.loaded[entry.leg_id] = leg
        return leg

    def get(self, leg_id: str) -> Leg:
        """按标识取一条腿。

        Args:
            leg_id: 库中已有的腿标识。

        Returns:
            同一库内反复访问返回同一个 Leg。

        Raises:
            KeyError: 标识不存在。
        """
        try:
            return self._load(self._by_id[leg_id])
        except KeyError:
            raise KeyError(f"未知腿编号 {leg_id!r}") from None

    def pair(self, pair_id: str) -> tuple[Leg, Leg]:
        """按配对标识取 (左腿, 右腿)。

        Args:
            pair_id: 完整配对标识。

        Returns:
            对应的左腿、右腿。

        Raises:
            KeyError: 配对不存在或不完整。
        """
        try:
            left, right = self._pairs[pair_id]
        except KeyError:
            raise KeyError(f"未知或不完整配对 {pair_id!r}") from None
        return self._load(left), self._load(right)

    def alternate(self, n: int, *, paired: bool = False, seed: int | None = None) -> list[Leg]:
        """选取 n 条腿；成对时按左、右顺序展开完整配对。

        Args:
            n: 所需腿数。
            paired: False 从全部腿中打乱选取；True 仅使用完整配对，奇数末项取左腿。
            seed: 本次选择的随机种子，不受此前调用影响；None 使用库默认种子或每次随机。

        Returns:
            优先不重复、数量不足时循环复用的 Leg 列表。

        Raises:
            ValueError: n 为负数，或成对选取时没有完整配对。
        """
        if n < 0:
            raise ValueError(f"n 不能为负数，得到 {n}")
        if n == 0:
            return []
        if paired:
            pairs = self.sample_pairs((n + 1) // 2, seed=seed)
            return [leg for pair in pairs for leg in pair][:n]
        entries = list(self._entries)
        random.Random(self._seed if seed is None else seed).shuffle(entries)
        return [self._load(entries[i % len(entries)]) for i in range(n)]

    def sample_pairs(self, n: int, *, seed: int | None = None) -> list[tuple[Leg, Leg]]:
        """按本次 seed 选取 n 个完整左右配对。

        Args:
            n: 所需配对数。
            seed: 本次选择的随机种子；None 使用库默认种子或每次随机。

        Returns:
            优先不重复、数量不足时循环复用的 (左腿, 右腿) 列表。

        Raises:
            ValueError: n 为负数，或 n 大于零而库中没有完整配对。
        """
        if n < 0:
            raise ValueError(f"n 不能为负数，得到 {n}")
        if not self._pairs and n:
            raise ValueError("库中没有完整的左右配对")
        ids = list(self._pairs)
        random.Random(self._seed if seed is None else seed).shuffle(ids)
        return [self.pair(ids[i % len(ids)]) for i in range(n)]

    def preview(self, *, scale: float = 0.5) -> Image.Image:
        """生成全部素材的目录图，完整配对相邻，未配对腿单独展示。

        Args:
            scale: 相对设计尺寸的预览倍率，须为正的有限数。

        Returns:
            标注库内标识、配对与左右侧的 RGB 模式 PIL Image。

        Raises:
            ValueError: scale 不是正的有限数。
        """
        if not math.isfinite(scale) or scale <= 0:
            raise ValueError(f"scale 须为正数，得到 {scale}")
        groups = [(pair_id, list(self.pair(pair_id))) for pair_id in self.pair_ids]
        paired = {id(leg) for _, group in groups for leg in group}
        groups += [("unpaired", [leg]) for leg in self.legs if id(leg) not in paired]
        images = {id(leg): Image.fromarray(leg.raster_at(scale)) for leg in self.legs}
        font, title_font = ImageFont.load_default(size=16), ImageFont.load_default(size=22)
        margin, gap, leg_gap, row_gap = 24, 30, 8, 34
        label_h = 22
        rows = [groups[i : i + 4] for i in range(0, len(groups), 4)]
        leg_h = max(image.height for image in images.values())

        def group_width(group: list[Leg]) -> int:
            """计算一组腿的实际预览宽度。"""
            return sum(images[id(leg)].width for leg in group) + leg_gap * (len(group) - 1)

        row_widths = [
            sum(group_width(group) for _, group in row) + gap * (len(row) - 1) for row in rows
        ]
        title = f"stockchart leg library - {len(self._entries)} legs / {len(self._pairs)} pairs"
        title_box = title_font.getbbox(title)
        title_w, title_h = round(title_box[2] - title_box[0]), round(title_box[3] - title_box[1])
        canvas = Image.new(
            "RGB",
            (
                max(max(row_widths), title_w) + 2 * margin,
                2 * margin + title_h + len(rows) * (2 * label_h + leg_h + row_gap),
            ),
            DEFAULT_BACKGROUND,
        )
        draw = ImageDraw.Draw(canvas)
        draw.text((margin, margin), title, fill=(58, 58, 58), font=title_font)
        y = margin + title_h + row_gap
        for row in rows:
            x = margin
            for pair_id, group in row:
                draw.text((x, y), pair_id, fill=(150, 110, 110), font=font)
                for leg in group:
                    image = images[id(leg)]
                    canvas.paste(image, (x, y + label_h + leg_h - image.height), image)
                    label = f"{leg.leg_id or 'unnamed'} {leg.side or ''}"
                    draw.text((x, y + label_h + leg_h + 4), label, fill=(70, 70, 70), font=font)
                    x += image.width + leg_gap
                x += gap - leg_gap
            y += 2 * label_h + leg_h + row_gap
        return canvas


DEFAULT_LEG_LIBRARY = LegLibrary()
"""随包内置素材的默认库；创建时仅读取元数据。"""
