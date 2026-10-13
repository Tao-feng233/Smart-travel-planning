"""出行方式与往返交通必填规则、站点清单过滤。

用户要求：
  * 出行方式四选一：火车 / 高铁 / 飞机 / 自驾
  * 到达站、到达时间、返程站、返程时间为必填（强必填：填了才允许生成计划）
  * 选自驾则这些都不需要
  * 去程出发站字段删除
"""

import asyncio

import pytest

from app.core.errors import DataError
from app.travel import stations, transport_required as tr


def req(**over):
    base = {
        "city": "洛阳",
        "origin": "郑州",
        "start_date": "2026-10-14",
        "days": 2,
        "arrival_station": "洛阳龙门站",
        "arrival_time": "13:00",
        "return_station": "洛阳龙门站",
        "return_time": "18:00",
    }
    base.update(over)
    return base


# ---------- 出行方式 ----------

def test_vehicle_maps_to_legacy_mode():
    """出行方式要折算成既有的互斥模式，既有逻辑才不用改。"""
    from app.travel.requirements import update_requirements
    from app.persistence import storage

    w = storage.new_workspace("test-owner")
    update_requirements(w, {"intercity_vehicle": "drive"})
    assert w["requirements"]["intercity_vehicle"] == "drive"
    assert w["requirements"]["intercity_mode"] == "self_drive"

    update_requirements(w, {"intercity_vehicle": "flight"})
    assert w["requirements"]["intercity_mode"] == "self_arranged"


def test_invalid_vehicle_is_rejected():
    from app.travel.requirements import update_requirements
    from app.persistence import storage

    w = storage.new_workspace("test-owner")
    with pytest.raises(DataError):
        update_requirements(w, {"intercity_vehicle": "rocket"})


def test_origin_station_is_no_longer_a_known_field():
    """去程出发站按用户要求删除，写入应被忽略。"""
    from app.travel.requirements import update_requirements
    from app.persistence import storage

    w = storage.new_workspace("test-owner")
    update_requirements(w, {"origin_station": "郑州东站"})
    assert not w["requirements"].get("origin_station")


def test_vehicle_of_falls_back_from_legacy_mode():
    assert tr.vehicle_of({"intercity_mode": "self_drive"}) == "drive"
    assert tr.vehicle_of({"intercity_mode": "self_arranged"}) == "highspeed"
    assert tr.vehicle_of({}) == "highspeed"
    assert tr.vehicle_of({"intercity_vehicle": "flight"}) == "flight"


# ---------- 必填规则 ----------

@pytest.mark.parametrize("missing", ["arrival_station", "arrival_time",
                                    "return_station", "return_time"])
def test_each_field_is_required_for_non_drive(missing):
    r = req(**{missing: ""})
    keys = [k for k, _ in tr.missing_fields(r)]
    assert missing in keys, keys
    with pytest.raises(DataError):
        tr.require_complete(r)


def test_complete_non_drive_passes():
    assert tr.missing_fields(req()) == []
    tr.require_complete(req())          # 不抛异常


def test_drive_needs_none_of_them():
    r = {"city": "洛阳", "intercity_vehicle": "drive"}
    assert tr.missing_fields(r) == []
    tr.require_complete(r)


def test_require_complete_message_names_the_missing_fields():
    with pytest.raises(DataError) as e:
        tr.require_complete(req(arrival_time="", return_time=""))
    text = str(e.value)
    assert "到达时间" in text and "返程时间" in text
    assert "自驾" in text                # 告诉用户还有自驾这条出路
    assert e.value.context.get("missing") == ["arrival_time", "return_time"]


# ---------- 站点清单 ----------

def test_kind_for_vehicle():
    assert stations.kind_for("train") == "train"
    assert stations.kind_for("highspeed") == "train"
    assert stations.kind_for("flight") == "flight"
    assert stations.kind_for("drive") is None
    assert stations.kind_for(None) is None


def test_station_filter_drops_noise_and_closed():
    """实测高德会混入公交站、地铁站、客运站与已关闭机场，必须过滤。"""
    raw = [
        {"name": "洛阳龙门站"},
        {"name": "洛阳站"},
        {"name": "洛阳师范学院西门(公交站)"},
        {"name": "洛阳火车站(地铁站)"},
        {"name": "郑州客运南站"},
        {"name": "洛阳北郊机场"},
        {"name": "青岛流亭国际机场(已关闭)"},
        {"name": "青岛流亭国际机场(暂停营业)"},
        {"name": "青岛胶东国际机场航站楼"},
    ]
    train = [x["name"] for x in stations._clean(raw, "洛阳", "train")]
    flight = [x["name"] for x in stations._clean(raw, "洛阳", "flight")]
    assert "洛阳龙门站" in train and "洛阳站" in train
    assert not any("公交" in n or "地铁" in n or "客运" in n for n in train)
    assert "洛阳北郊机场" in flight
    assert not any("已关闭" in n or "暂停营业" in n or "航站楼" in n for n in flight)


def test_list_stations_empty_inputs():
    assert asyncio.run(stations.list_stations("", "train")) == []
    assert asyncio.run(stations.list_stations("洛阳", "bogus")) == []


def test_list_stations_uses_cache_and_tool_injection():
    """第二次调用应命中缓存，不再打高德。"""
    calls = []

    async def fake_tool(name, args):
        calls.append((name, args))
        return {"items": [{"name": "洛阳龙门站"}, {"name": "洛阳站(公交站)"}]}

    from app.persistence import storage

    key = storage.cache_key("stations", {"city": "测试城A", "kind": "train"})
    with storage.connect() as c:
        c.execute("DELETE FROM cache WHERE key=?", (key,))
    first = asyncio.run(stations.list_stations("测试城A", "train", tool=fake_tool))
    second = asyncio.run(stations.list_stations("测试城A", "train", tool=fake_tool))
    assert [x["name"] for x in first] == ["洛阳龙门站"]
    assert first == second
    assert len(calls) == 1               # 第二次走缓存，没有再次查询
    # 清理测试留下的缓存
    with storage.connect() as c:
        c.execute("DELETE FROM cache WHERE key=?", (key,))


def test_list_stations_survives_tool_failure():
    async def boom(name, args):
        raise RuntimeError("上游挂了")

    assert asyncio.run(stations.list_stations("测试城B", "train", tool=boom)) == []
