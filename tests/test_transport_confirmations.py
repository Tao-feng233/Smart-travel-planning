"""计划书必须把往返交通的缺项列出来，而不是只说"可以补填"。

背景：用户填了目的地/日期/人数，也选了自驾，但没填到达站与时刻。
计划书的往返交通段只写"自行安排，可在旅行信息里补填站点与时间",
读起来像是用户主动选择不填，于是没有任何提醒；而站点缺失会让抵达日与
返程日的可用时间无法核对，是必须让用户知道的缺项。
"""

import sys

sys.path.insert(0, ".")

from app.application import report
from app.persistence import storage


def trip(**over):
    w = storage.new_workspace("test-owner")
    w["requirements"] = {
        "city": "洛阳",
        "origin": "郑州",
        "start_date": "2026-10-14",
        "end_date": "2026-10-15",
        "days": 2,
        "outbound_date": "2026-10-13",
        "return_date": "2026-10-16",
        "intercity_mode": "self_drive",
    }
    w["requirements"].update(over)
    w["plan"] = {
        "title": "洛阳两日",
        "created": "2026-10-13T15:30:00+08:00",
        "days": [],
        "stale": False,
        "budget": {
            "known_subtotal": 0,
            "items": {},
            "unknown": [],
            "hotel_reference": None,
            "basis": "",
        },
        "spots": [],
        "warnings": [],
    }
    return w


def test_missing_station_and_time_are_listed():
    """站点与时刻全空时，四项缺项都要出现。"""
    items = report.transport_confirmations(trip())
    text = "\n".join(items)
    assert "到达站" in text or "停车地点" in text, items
    assert "未填" in text
    # 去程到达时间与返程时间各算一条
    assert len(items) >= 4, items


def test_report_has_confirmation_section_when_incomplete():
    w = trip()
    md = report.markdown(w)
    assert "## 出发前必须确认" in md
    # 必须具体，且不能只是那句笼统的状态
    assert "无法核对抵达日" in md or "暂按下午到达预留" in md


def test_outbound_date_is_flagged_for_confirmation():
    """已按出发日安排住宿时，要提示用户确认这个日期。"""
    items = report.transport_confirmations(trip())
    assert any("2026-10-13" in x for x in items), items


def test_no_confirmation_section_when_complete():
    w = trip(
        arrival_station="洛阳龙门站",
        arrival_period="afternoon",
        return_station="洛阳龙门站",
        return_period="evening",
    )
    assert report.transport_confirmations(w) == []
    assert "## 出发前必须确认" not in report.markdown(w)


def test_self_drive_wording_does_not_mention_station():
    """"自驾时不应说"到达站"，避免和铁路用词混淆。"""
    items = report.transport_confirmations(trip())
    text = "\n".join(items)
    assert "停车地点" in text or "车库" in text, items
