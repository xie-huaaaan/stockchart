"""L0 素材层：LegLibrary 与 load_leg。"""

from __future__ import annotations

import json
import random
from importlib.resources import files
from pathlib import Path

import numpy as np
from numpy.typing import NDArray
from PIL import Image

from stockchart.legs import Leg

# ---------------------------------------------------------------------------
# load_leg：从外部 PNG 加载自定义腿素材
# ---------------------------------------------------------------------------


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
    img = np.asarray(Image.open(png).convert("RGBA"))
    H, W = img.shape[:2]

    est_cx, est_fw = _estimate_foot(img)
    return Leg(
        image=img,
        width=W,
        height=H,
        foot_center_x=foot_center_x if foot_center_x is not None else est_cx,
        foot_width=foot_width if foot_width is not None else est_fw,
    )


def _estimate_foot(img: NDArray[np.uint8]) -> tuple[int, int]:
    """按底部若干行的 alpha 估计足底中心 x 与足底宽度。"""
    H, W = img.shape[:2]
    foot_rows = min(20, H)
    bot = img[H - foot_rows :, :, 3].astype(float)
    col_sum = bot.sum(0)
    if col_sum.sum() < 1:
        return W // 2, W // 3
    xs = np.arange(W, dtype=float)
    center = int((col_sum * xs).sum() / col_sum.sum())
    width = int((bot > 0).sum(1).mean())
    return center, width


# ---------------------------------------------------------------------------
# LegLibrary：内置素材库
# ---------------------------------------------------------------------------


class LegLibrary:
    """内置腿部素材库（26 条腿 / 13 对）。

    所有 Leg 对象在首次访问时懒加载并缓存；反复调用 get/pair 不会重复读磁盘。
    """

    def __init__(self, *, seed: int | None = None) -> None:
        """Seed 同时作为后续自动选腿的默认随机源。"""
        self._rng = random.Random(seed)
        self._meta: list[dict[str, str | int]] = []
        self._cache: dict[str, Leg] = {}
        self._pair_map: dict[str, list[str]] = {}  # pair_id → [left_id, right_id]
        self._load_metadata()

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------

    def get(self, leg_id: str) -> Leg:
        """按编号取一条腿（如 leg_03）。

        Args:
            leg_id: 内置腿编号，格式为 "leg_NN"（01–26）。

        Returns:
            对应的 Leg 实例（懒加载）。

        Raises:
            KeyError: 编号不存在。
        """
        if leg_id not in {m["leg_id"] for m in self._meta}:
            raise KeyError(f"未知腿编号 {leg_id!r}，合法范围 leg_01 … leg_26")
        return self._load_leg(leg_id)

    def pair(self, pair_id: str) -> tuple[Leg, Leg]:
        """取一对腿，返回 (左腿, 右腿)。

        Args:
            pair_id: 配对编号，格式为 "pair_NN"（01–13）。

        Returns:
            (左腿, 右腿)。

        Raises:
            KeyError: 配对编号不存在。
        """
        if pair_id not in self._pair_map:
            raise KeyError(f"未知配对编号 {pair_id!r}，合法范围 pair_01 … pair_13")
        left_id, right_id = self._pair_map[pair_id]
        return self._load_leg(left_id), self._load_leg(right_id)

    def alternate(self, n: int) -> list[Leg]:
        """按左、右、左、右……的顺序选出 n 条腿。

        Args:
            n: 需要的腿数。

        Returns:
            长度为 n 的 Leg 列表，偶数下标为左腿，奇数下标为右腿（0-based）。

        具体使用哪几对素材按 seed 伪随机、优先不重复；超过 13 对后从已用素材继续复用。
        """
        pair_ids = self._shuffled_pair_ids()
        result: list[Leg] = []
        for i in range(n):
            pair_id = pair_ids[i % len(pair_ids)]
            left, right = self.pair(pair_id)
            result.append(left if i % 2 == 0 else right)
        return result

    def sample_pairs(self, n: int) -> list[tuple[Leg, Leg]]:
        """选出 n 对完整素材（成对布局用），选取规则同 alternate。

        Args:
            n: 需要的对数。

        Returns:
            长度为 n 的 (左腿, 右腿) 列表。
        """
        pair_ids = self._shuffled_pair_ids()
        return [self.pair(pair_ids[i % len(pair_ids)]) for i in range(n)]

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------

    def _load_metadata(self) -> None:
        """读取 legs.json，构建 pair_map。"""
        pkg = files("stockchart.assets")
        json_bytes = (pkg / "legs.json").read_bytes()
        loaded: list[dict[str, str | int]] = json.loads(json_bytes)
        self._meta = loaded
        for entry in self._meta:
            pid = str(entry["pair_id"])
            lid = str(entry["leg_id"])
            side = str(entry["side"])
            if pid not in self._pair_map:
                self._pair_map[pid] = ["", ""]
            if side == "left":
                self._pair_map[pid][0] = lid
            else:
                self._pair_map[pid][1] = lid

    def _load_leg(self, leg_id: str) -> Leg:
        """懒加载单条腿，结果缓存。"""
        if leg_id in self._cache:
            return self._cache[leg_id]

        entry = next(m for m in self._meta if m["leg_id"] == leg_id)
        pkg = files("stockchart.assets")
        png_bytes = (pkg / f"{leg_id}.png").read_bytes()

        import io

        img = np.asarray(Image.open(io.BytesIO(png_bytes)).convert("RGBA"))

        leg = Leg(
            image=img,
            width=int(entry["width"]),
            height=int(entry["height"]),
            foot_center_x=int(entry["foot_center_x"]),
            foot_width=int(entry["foot_width"]),
            leg_id=leg_id,
            pair_id=str(entry["pair_id"]),
            side="left" if entry["side"] == "left" else "right",  # type: ignore[arg-type]
        )
        self._cache[leg_id] = leg
        return leg

    def _shuffled_pair_ids(self) -> list[str]:
        """返回随机打乱顺序的配对 ID 列表（按 seed 确定性打乱）。"""
        ids = sorted(self._pair_map.keys())
        self._rng.shuffle(ids)
        return ids
