"""把用户填写的往返交通信息合成为工作区使用的交通记录。

设计依据：《往返交通改为用户填写-设计文档.md》。

本项目无法完成真正的订票（不能支付、出票、锁座），因此不再从班次卡片里选车次；
用户只提供**规划真正需要的两件事**：到达站 + 到达时间、返程站 + 开车时间。
本模块把它们合成为与既有结构同形的对象，这样下游读取
`w["selected_transport"]["arrival"]` / `w["selected_return"]["departure"]`
的十余处代码**无需改动**。

关键约束：
* 合成值**必须带日期**。`daily_schedule.py` 用 `[:10]` 取日期判断
  "今天是不是抵达日/返程日"，缺日期会让首尾日退化成完整游玩日。
* 用户没填站名时**不编造站名**，只留空并标 `station_pending`。
* 票价是选填；未填时 `price` 为 None，由 `fill_budget` 天然跳过（不写成零）。
"""

from datetime import date, datetime

from app.travel import travel_time

OUTBOUND_ID = "user-transport:outbound"
RETURN_ID = "user-transport:return"


def _date_text(value):
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    try:
        return date.fromisoformat(str(value or "")[:10]).isoformat()
    except (TypeError, ValueError):
        return None


def _stamp(moment):
    """既有的班次时刻格式是 'YYYY-MM-DD HH:MM'（`transport_time` 按此解析）。"""
    return moment.strftime("%Y-%m-%d %H:%M") if moment else None


def _clean(value, limit=40):
    text = str(value or "").strip()
    return text[:limit]


def _price(requirements, direction):
    """票价选填（requirements.intercity_ticket_cost）。

    未填时返回 None —— `fill_budget` 会自然跳过，**不会写成零**
    （见 engine.py:209-223 的既有处理）。
    """
    single = requirements.get("intercity_ticket_cost")
    if single in (None, ""):
        return None
    try:
        return float(single)
    except (TypeError, ValueError):
        return None


def _vehicle_label(requirements):
    """出行方式展示名；自驾时站点与时刻不适用。"""
    from app.travel.transport_required import VEHICLE_LABELS, vehicle_of

    return VEHICLE_LABELS.get(vehicle_of(requirements), "交通")


def outbound(requirements):
    """合成去程记录；无法确定到达时刻（缺日期）时返回 None。

    名称带上出行方式，让计划书与时间轴能看出是高铁/飞机还是自驾，而不是只有站名。
    去程出发站已按用户要求移除，因此不再写入 origin_station。
    """
    requirements = requirements or {}
    moment, basis = travel_time.resolve(requirements, "outbound")
    if moment is None:
        return None
    arrival = _clean(requirements.get("arrival_station"))
    label = _vehicle_label(requirements)
    city = _clean(requirements.get("city"))
    if arrival:
        name = arrival if label == "自驾" else label + "・" + arrival
    elif label == "自驾":
        name = "自驾前往" + (city or "目的地")
    else:
        name = label + "前往" + (city or "目的地")
    return {
        "id": OUTBOUND_ID,
        "kind": "transport",
        "direction": "outbound",
        "name": name,
        "vehicle": label,
        "departure": None,          # 用户只填到达时刻；出发时刻不猜
        "arrival": _stamp(moment),
        "arrival_station": arrival or None,
        "station_pending": not arrival,
        "time_basis": basis,
        "price": _price(requirements, "outbound"),
        "seat_type": None,
        "source": "user_entered",
        "selection_status": "confirmed",
    }


def inbound(requirements):
    """合成返程记录；无法确定开车时刻（缺日期）时返回 None。

    返程日期未填时使用推导值（默认返程日 = 最后一个游玩日的次日）。
    """
    requirements = requirements or {}
    base = requirements.get("return_date") or travel_time.default_return_date(requirements)
    moment, basis = travel_time.resolve(requirements, "return", base_date=base)
    if moment is None:
        return None
    station = _clean(requirements.get("return_station"))
    label = _vehicle_label(requirements)
    city = _clean(requirements.get("origin")) or "出发地"
    if station:
        name = station if label == "自驾" else label + "・" + station
    elif label == "自驾":
        name = "自驾返回" + city
    else:
        name = label + "返回" + city
    return {
        "id": RETURN_ID,
        "kind": "transport",
        "direction": "return",
        "name": name,
        "vehicle": label,
        "departure": _stamp(moment),
        "arrival": None,            # 用户只填开车时刻；到达时刻不猜
        "departure_station": station or None,
        "station_pending": not station,
        "time_basis": basis,
        "price": _price(requirements, "return"),
        "seat_type": None,
        "source": "user_entered",
        "selection_status": "confirmed",
    }


def _filled(requirements, direction):
    """用户是否确实就这个方向填写了信息。

    **只有填了才合成写入**：否则会覆盖既有记录
    （例如历史数据里已有的班次对象，或测试固件预置的记录）。
    这也保证"改别的字段不会把交通信息动掉"。
    """
    requirements = requirements or {}
    time_key, period_key, _ = travel_time.DIRECTIONS[direction]
    station_key = "arrival_station" if direction == "outbound" else "return_station"
    return any(
        str(requirements.get(key) or "").strip()
        for key in (time_key, period_key, station_key)
    )


def apply(w):
    """按用户填写重建两个方向的交通记录，并返回给用户看的提示列表。

    * 用户填了该方向的信息 → 写入（或覆盖）对应记录
    * 用户没填该方向        → **不写入、不清除**已有记录
    """
    requirements = w.get("requirements") or {}
    notes = []

    for value, key, direction in (
        (outbound(requirements), "selected_transport", "outbound"),
        (inbound(requirements), "selected_return", "return"),
    ):
        if _filled(requirements, direction) and value is not None:
            w[key] = value
        note = travel_time.note_for(requirements, direction)
        if note:
            notes.append(note)
    return notes


def summary(requirements):
    """给表单回显用的一句话摘要（含推导出的返程日）。"""
    requirements = requirements or {}
    lines = []
    go, basis_go = travel_time.resolve(requirements, "outbound")
    if go:
        lines.append(
            "去程："
            + (go.strftime("%m-%d %H:%M"))
            + " 到达 "
            + (_clean(requirements.get("arrival_station")) or "（未填到达站）")
            + ("（估算）" if basis_go != travel_time.BASIS_PRECISE else "")
        )
    if not requirements.get("return_date"):
        derived = travel_time.default_return_date(requirements)
        if derived:
            lines.append(
                "返程：未填日期，已按 "
                + derived.isoformat()
                + " 出发（最后一个游玩日的次日）；如实际更晚请修改"
            )
    back, basis_back = travel_time.resolve(
        requirements, "return",
        base_date=requirements.get("return_date")
        or travel_time.default_return_date(requirements))
    if back:
        lines.append(
            "返程："
            + back.strftime("%m-%d %H:%M")
            + " 从 "
            + (_clean(requirements.get("return_station")) or "（未填返程站）")
            + " 出发"
            + ("（估算）" if basis_back != travel_time.BASIS_PRECISE else "")
        )
    return "；".join(lines)
