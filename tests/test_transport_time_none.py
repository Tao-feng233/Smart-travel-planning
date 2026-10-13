"""用户只填到达时刻/开车时刻时，交通记录里另一头是 None，不得让时间轴崩掉。

背景：往返交通改为用户填写后，合成记录是
    去程：departure=None（用户只填到达时刻，出发时刻不猜）
    返程：arrival=None  （用户只填开车时刻，到达时刻不猜）
这个 None 是"不编造"的正确语义，但 schedule.transport_time() 原先写的是
    (p or {}).get(key, "").replace(" ", "T")
而 dict.get(key, "") 只在【键不存在】时给默认值——键存在且值为 None 时仍返回
None，.replace 抛 AttributeError，且它不在 except (ValueError, TypeError)
的覆盖范围内，于是一路冒泡成 HTTP 500：
    schedule.build → transport_time → AttributeError: 'NoneType' object has no attribute 'replace'

修复后：无法解析（含 None 与空串）一律视为"时刻未知"，返回 None，
时间轴按整天可用处理——与项目"未知时间不按零处理"的一致口径。
"""

from app.planning import schedule


def workspace(**over):
    w = {
        "requirements": {"city": "青岛", "start_date": "2026-10-12", "days": 3},
        "catalog": {
            "a": {"id": "a", "name": "栈桥", "kind": "spot", "location": "120.3,36.0"},
            "b": {"id": "b", "name": "崂山", "kind": "spot", "location": "120.6,36.2"},
            "h": {"id": "h", "name": "酒店", "kind": "hotel", "location": "120.3,36.01"},
        },
        "selected_spots": ["a", "b"],
        "hotel": {"id": "h", "name": "酒店", "kind": "hotel", "location": "120.3,36.01"},
    }
    w.update(over)
    return w


# 与 travel_synthesis 产出的记录同形：另一头是 None
OUTBOUND_SYNTHESIZED = {
    "id": "user-transport:outbound",
    "name": "郑州 → 洛阳",
    "departure": None,
    "arrival": "2026-10-12 13:00",
    "source": "user_entered",
    "time_basis": "period",
}
RETURN_SYNTHESIZED = {
    "id": "user-transport:return",
    "name": "洛阳 → 郑州",
    "departure": "2026-10-14 18:00",
    "arrival": None,
    "source": "user_entered",
    "time_basis": "period",
}


def test_transport_time_tolerates_none():
    """None 与空串都表示"时刻未知"，返回 None 而不是抛异常。"""
    assert schedule.transport_time({"departure": None}, "departure") is None
    assert schedule.transport_time({"departure": ""}, "departure") is None
    assert schedule.transport_time({"departure": "2026-10-12 07:08"}, "departure") is not None


def test_build_survives_none_departure_on_outbound():
    """去程 departure=None：原实现在此崩溃。"""
    w = workspace(selected_transport=dict(OUTBOUND_SYNTHESIZED))
    result = schedule.build(w)          # 修复前抛 AttributeError
    assert result["entries"] is not None


def test_build_survives_none_arrival_on_return():
    """返程 arrival=None。"""
    w = workspace(selected_return=dict(RETURN_SYNTHESIZED))
    result = schedule.build(w)
    assert result["entries"] is not None


def test_build_survives_both_synthesized_records():
    """两个方向都只有一头有值——这正是用户在界面里填写后的常见状态。"""
    w = workspace(
        selected_transport=dict(OUTBOUND_SYNTHESIZED),
        selected_return=dict(RETURN_SYNTHESIZED),
    )
    result = schedule.build(w)
    assert result["entries"] is not None
    # 缺的那一头不能变成"整天不可用"或崩溃，只按整天可用处理
    assert result["conflicts"] == []


def test_signature_does_not_crash_on_synthesized_records():
    """timeline_review.signature 是报错栈里最先触发的那一层。"""
    from app.planning import timeline_review

    w = workspace(
        selected_transport=dict(OUTBOUND_SYNTHESIZED),
        selected_return=dict(RETURN_SYNTHESIZED),
    )
    timeline_review.signature(w)        # 修复前经 schedule.build 崩溃
