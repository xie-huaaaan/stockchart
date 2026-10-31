# 白盒测试：直接检查 legs.json 的解析与校验
# pyright: reportPrivateUsage=false

"""legs.json 元数据校验测试。"""

from __future__ import annotations

import json
from collections.abc import Mapping

import pytest

from stockchart.library import _parse_metadata

LEFT = {
    "leg_id": "leg_01",
    "pair_id": "pair_01",
    "side": "left",
    "width": 100,
    "height": 200,
    "foot_center_x": 50,
}
RIGHT = {**LEFT, "leg_id": "leg_02", "side": "right"}


def dump(*entries: Mapping[str, object]) -> bytes:
    return json.dumps([dict(entry) for entry in entries]).encode("utf-8")


def test_valid_metadata_round_trip() -> None:
    metas = _parse_metadata(dump(RIGHT, LEFT))
    assert [meta.leg_id for meta in metas] == ["leg_01", "leg_02"]
    assert metas[0].side == "left"


def test_empty_metadata_raises() -> None:
    with pytest.raises(ValueError, match="不能为空"):
        _parse_metadata(dump())


def test_missing_pair_side_raises() -> None:
    with pytest.raises(ValueError, match="缺少右腿"):
        _parse_metadata(dump(LEFT))


def test_unknown_field_raises() -> None:
    with pytest.raises(ValueError, match="未知字段"):
        _parse_metadata(dump({**LEFT, "foot_width": 30}, RIGHT))


def test_duplicate_leg_id_raises() -> None:
    with pytest.raises(ValueError, match="leg_id 重复"):
        _parse_metadata(dump(LEFT, {**RIGHT, "leg_id": "leg_01"}))


def test_foot_center_out_of_range_raises() -> None:
    with pytest.raises(ValueError, match="foot_center_x 超出"):
        _parse_metadata(dump({**LEFT, "foot_center_x": 100}, RIGHT))
