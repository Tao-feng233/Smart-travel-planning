"""去程/返程选定后的安排审查：把"这天到底还需不需要吃住"一次算清并提示用户。

三条规则（都由用户提出）：
1. 去程日早于开始游玩日（例如 9 号到、10 号才开玩）：这几天同样需要住宿与餐饮，
   住宿与餐饮都以"抵达这座城市的地点"（车站/机场）为中心推荐。
2. 返程早于中午 12:00：返程当天不再需要酒店，直接把那一晚剔除并提示。
3. 去程当天（早于游玩日的那种）只安排"就餐地点与住宿地点"，不给具体时刻：
   抵达时间不确定性太大，写死时刻等于编造。午餐仅在 15:00 前抵达时才安排，
   更晚抵达直接跳过（此时午餐时间已过）。
"""
from datetime import date, datetime, timedelta

LUNCH_CUTOFF_HOUR = 15      # 15:00 之后抵达不再安排午餐
NOON_HOUR = 12              # 返程早于 12:00 则当天不需要住宿
ARRIVAL_SPAN_MINUTES = 120  # 抵达后到能坐下来吃饭的保守估计（出站+接驳）


def _dt(value):
    try:
        return datetime.fromisoformat(str(value or '').replace(' ', 'T'))
    except (TypeError, ValueError):
        return None


def transport_minutes(p, key):
    """班次时刻换算成当天分钟数；没有则返回 None。"""
    value = _dt((p or {}).get(key))
    return value.hour * 60 + value.minute if value else None


def transport_day(p, key):
    value = _dt((p or {}).get(key))
    return value.date() if value else None


def requirement_start(w):
    try:
        return date.fromisoformat((w.get('requirements') or {}).get('start_date'))
    except (TypeError, ValueError):
        return None


def stay_start(w):
    """住宿从哪天开始：去程更早时以去程当天算起，否则按开始游玩日。"""
    start = requirement_start(w)
    out_day = transport_day(w.get('selected_transport'), 'departure')
    days = [d for d in (start, out_day) if d]
    return min(days) if days else None


def pre_tour_days(w):
    """早于开始游玩日、但已经在路上的那些天（需要吃住的"提前抵达日"）。"""
    start = requirement_start(w)
    out_day = transport_day(w.get('selected_transport'), 'departure')
    arrive = transport_day(w.get('selected_transport'), 'arrival') or out_day
    if not start or not arrive:
        return []
    result, cursor = [], arrive
    while cursor < start:
        result.append(cursor)
        cursor += timedelta(days=1)
    return result


def arrival_can_lunch(w):
    """抵达当天还赶得上午饭吗（15:00 前到）。返回 (bool, 到达分钟数或 None)。"""
    arrive = transport_minutes(w.get('selected_transport'), 'arrival')
    if arrive is None:
        return False, None
    return arrive + ARRIVAL_SPAN_MINUTES <= LUNCH_CUTOFF_HOUR * 60, arrive


def return_before_noon(w):
    """返程是否早于中午 12:00（当天不需要住宿）。"""
    departure = transport_minutes(w.get('selected_return'), 'departure')
    if departure is None:
        return False
    return departure < NOON_HOUR * 60


def arrival_anchor(w):
    """抵达日用于推荐吃住的中心：抵达车站/机场；其次当晚住宿；最后按名称兜底。

    车站坐标常需另外核对，但这里的用途是"按名称查周边"，poiName 不要求坐标，
    所以拿不到坐标时仍以站名作锚点（并标明未定位），好过退回市区中心。
    """
    from . import time_policy
    transport = w.get('selected_transport') or {}
    station = time_policy.station_place(w, transport, 'arrival_station') if transport else None
    if station and station.get('location'):
        return {'id': station.get('id'), 'name': station.get('name') or '抵达车站/机场',
                'location': station['location'], 'kind': 'station',
                'basis': '抵达车站/机场', 'status': station.get('location_status')}
    hotel = w.get('hotel') or {}
    if hotel.get('location'):
        return {'id': hotel.get('id'), 'name': hotel.get('name'), 'location': hotel['location'],
                'kind': 'hotel', 'basis': '当晚住宿', 'status': hotel.get('location_status')}
    # 按名称兜底：班次自带的到达站/机场，或目的地城市。
    name = (station or {}).get('name') or transport.get('arrival_station') or transport.get('arrival_city')
    if not name:
        requirement = w.get('requirements') or {}
        name = requirement.get('city')
        basis = '目的地城市（抵达站点尚未核对）'
    else:
        basis = '抵达站点（坐标尚未核对）'
    if not name:
        return None
    return {'id': 'arrival:' + str(name), 'name': name, 'location': None, 'kind': 'station',
            'basis': basis, 'status': 'needs_check'}


def review(w):
    """返回审查结论：提示文本列表与需要调整的夜晚。

    不在这里直接改工作区，便于调用方决定何时应用（避免在只读展示路径里写数据）。
    """
    notices, drop_nights = [], []
    if not w.get('selected_transport') and not w.get('selected_return'):
        return {'notices': notices, 'drop_nights': drop_nights}

    if return_before_noon(w):
        day = transport_day(w.get('selected_return'), 'departure')
        departure = transport_minutes(w.get('selected_return'), 'departure')
        if day:
            drop_nights.append(day.isoformat())
            notices.append('返程 ' + day.isoformat() + ' ' + _clock(departure)
                           + ' 出发（早于中午 12:00），当天不再需要住宿，已把这一晚的酒店剔除。'
                           '如需提前到车站附近住一晚，可在住宿页单独指定。')

    pre = pre_tour_days(w)
    if pre:
        anchor = arrival_anchor(w)
        where = (anchor or {}).get('name') or (w.get('requirements') or {}).get('city') or '抵达地'
        days = '、'.join(d.isoformat() for d in pre)
        notices.append('去程 ' + (transport_day(w.get('selected_transport'), 'departure') or pre[0]).isoformat()
                       + ' 出发、' + (requirement_start(w) or pre[0]).isoformat()
                       + ' 才开始游玩：' + days + ' 这几天已经在路上/已抵达，同样需要住宿与用餐。'
                       '住宿与餐厅按抵达地点「' + where + '」周边推荐。')
        can_lunch, arrive = arrival_can_lunch(w)
        if can_lunch:
            notices.append('抵达当天按到达时间可安排午餐（到达约 ' + _clock(arrive)
                           + '，留出出站与接驳后仍在午后），只给出就餐地点，不写具体时刻。')
        else:
            reason = '到达时间偏晚（约 ' + _clock(arrive) + '）' if arrive is not None else '到达时刻尚未确定'
            notices.append('抵达当天不安排午餐：' + reason + '，午餐时段已过或不明确，直接跳过。'
                           '当天只安排住宿地点与晚餐。')
        notices.append('这些天不显示具体时刻：抵达时间与接驳耗时不确定性较大，给出时刻等于编造；'
                       '先按地点安排，出发前再按实际到站时间细化。')
    return {'notices': notices, 'drop_nights': drop_nights}


def apply(w):
    """把审查结论写回工作区：剔除返程当天住宿、补上提前抵达日的住宿夜晚。

    返回 (提示文本列表, 被剔除的夜晚)。
    """
    result = review(w)
    # 提前抵达日要有住宿：把它们并入逐晚编排的起点（nights() 会据此生成夜晚）。
    anchor_day = (transport_day(w.get('selected_transport'), 'arrival')
                  or transport_day(w.get('selected_transport'), 'departure'))
    if pre_tour_days(w) and anchor_day:
        w['arrival_stay_from'] = anchor_day.isoformat()
    dropped = []
    for day in result['drop_nights']:
        stays = dict(w.get('stay_hotels') or {})
        if day in stays:
            stays.pop(day)
            w['stay_hotels'] = stays
            dropped.append(day)
    return result['notices'], dropped


def _clock(minutes):
    if minutes is None:
        return '时刻待核实'
    return '%02d:%02d' % (int(minutes) // 60, int(minutes) % 60)
