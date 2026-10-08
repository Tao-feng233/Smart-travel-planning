"""住宿编排：先按天把景区连成一条线，再以每天收尾地点为锚点推荐当晚住宿。

设计口径（用户反馈确定）：
- 旅游景区先按地理位置与日期编成一条顺路的线（复用 visit_analysis 的分配结果）；
- 每个住宿晚以"当天最后一个活动"为锚点，晚餐优先推荐回住宿顺路的餐厅；
- 返程当天不订酒店：最后一晚只在"返程在次日或更晚"时才存在；
- 最后一晚若需为次日赶车，锚点改用返程站，避免第二晚还要长途赶车。
"""
from datetime import date, timedelta

RETURN_STATION_LEAD_MINUTES = 10 * 60      # 返程在 10:00 前视为赶早班，最后一晚靠近车站
NEARBY_STRAIGHT_KM = 4.0                   # 与 poiName 查询半径一致，用于判断"顺路"


def _d(value):
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def return_departure(w):
    """返程班次的出发时间；未选班次或用未确认日期时返回 None。"""
    from . import journey
    r = (w.get('requirements') or {})
    selected = w.get('selected_return') or {}
    stamp = selected.get('departure')
    if not stamp:
        return None
    if selected.get('selection_status') != 'confirmed' and not r.get('return_date'):
        return None
    text = str(stamp)
    day = _d(text)
    if day is None:
        return None
    minutes = None
    tail = text[11:16] if len(text) >= 16 else ''
    if len(tail) == 5 and tail[2] == ':':
        try:
            minutes = int(tail[:2]) * 60 + int(tail[3:])
        except ValueError:
            minutes = None
    return day, minutes


def nights(w):
    """需要住宿的夜晚列表：从入住日到返程前一天；返程当天不计住宿。"""
    r = w.get('requirements') or {}
    from . import visits
    start = _d(r.get('start_date'))
    tour = [_d(x) for x in (visits.dates(w) or [])]
    tour = [x for x in tour if x]
    if not start:
        return []
    back = return_departure(w)
    last = None
    if back:
        # 返程当天不订酒店，故最后一晚是返程前一天。
        last = back[0] - timedelta(days=1)
    elif tour:
        last = max(tour)
    if last is None or last < start:
        return []
    result, cursor = [], start
    while cursor <= last:
        result.append(cursor.isoformat())
        cursor += timedelta(days=1)
    return result


def touring_days(w):
    """按排期给出的游玩日顺序（每天的活动已按顺序排列）。"""
    from . import visit_analysis
    try:
        items = [x for x in (visit_analysis.preview(w) or []) if x.get('candidate_id')]
    except Exception:
        items = []
    order = {}
    for item in items:
        order.setdefault(item['date'], []).append(item['candidate_id'])
    return order


def _usable(w, cid):
    p = (w.get('catalog') or {}).get(cid)
    return p if p and p.get('location') else None


def day_closure(w, day):
    """某天用于定位住宿的收尾地点：先最后一个活动景点，再顺路晚餐餐厅。

    返回 (地点, 依据)。锚点不要求已有坐标：poiName 查询只用到名称，坐标仅用于
    额外核算通行距离，因此没有坐标的收尾景点仍是有效的锚点。
    """
    order = touring_days(w).get(day) or []
    for cid in reversed(order):
        p = (w.get('catalog') or {}).get(cid)
        if p:
            p = dict(p)
            p['_closure'] = 'spot'
            return p, '当天最后一个活动'
    dinner = dinner_for(w, day)
    if dinner:
        return dinner, '当天已选晚餐餐厅（当天以用餐收尾）'
    return None, '当天没有可用坐标的景点或餐厅'


def dinner_for(w, day, hotel=None):
    """某天已选晚餐餐厅；给定住宿时优先回住宿顺路的那家。"""
    picks = []
    for key, value in (w.get('meal_choices') or {}).items():
        if not isinstance(value, dict) or value.get('mode') != 'chosen':
            continue
        parts = str(key).split('|')
        if len(parts) != 2 or parts[1] != 'dinner' or parts[0] != day:
            continue
        p = _usable(w, value.get('food_id'))
        if p:
            picks.append(dict(p))
    if not picks:
        return None
    if hotel and hotel.get('location') and len(picks) > 1:
        from . import journey
        picks.sort(key=lambda p: journey.coordinate_distance(p, hotel))
        return picks[0]
    return picks[0]


def detour_km(from_point, to_point, place):
    """经某地绕行相对直达多走的直线距离（公里）：越小越顺路。"""
    from . import journey
    if not (from_point and to_point and place):
        return None
    if not all(x.get('location') for x in (from_point, to_point, place)):
        return None
    return round(journey.coordinate_distance(from_point, place)
                 + journey.coordinate_distance(place, to_point)
                 - journey.coordinate_distance(from_point, to_point), 2)


def dinner_options(w, day, hotel):
    """当天晚餐候选的顺路比较：给出绕行直线距离与建议。"""
    from . import journey
    rows = []
    for key, value in (w.get('meal_choices') or {}).items():
        if not isinstance(value, dict) or value.get('mode') != 'chosen':
            continue
        parts = str(key).split('|')
        if len(parts) != 2 or parts[1] != 'dinner' or parts[0] != day:
            continue
        p = _usable(w, value.get('food_id'))
        if p:
            rows.append(p)
    last = None
    order = touring_days(w).get(day) or []
    for cid in reversed(order):
        last = _usable(w, cid)
        if last:
            break
    result = []
    for p in rows:
        straight = round(journey.coordinate_distance(p, hotel), 1) if hotel and hotel.get('location') else None
        detour = detour_km(last, hotel, p)
        result.append({'food_id': p['id'], 'name': p['name'], 'straight_km_to_hotel': straight,
                       'detour_km_via_meal': detour,
                       'on_the_way': (detour is not None and detour <= NEARBY_STRAIGHT_KM)})
    result.sort(key=lambda x: (x['detour_km_via_meal'] if x['detour_km_via_meal'] is not None else 99, x['straight_km_to_hotel'] or 99))
    return result


def assignment_map(w):
    """逐晚最终分配：显式分配优先，未分配的夜晚用主住宿补齐。"""
    stays = w.get('stay_hotels') or {}
    primary = (w.get('hotel') or {}).get('id')
    return {day: (stays.get(day) or primary) for day in nights(w)}


def stay_hotel_ids(w):
    """本次住宿实际用到的酒店 ID（按夜晚顺序去重）。"""
    return [h for h in dict.fromkeys(assignment_map(w).values()) if h]


def multi_stay_note(w):
    """跨酒店住宿的如实提示：换酒店当天要退房并带行李转场。"""
    used = stay_hotel_ids(w)
    if len(used) <= 1:
        return None
    return ('本次住宿跨 '+str(len(used))+' 家酒店，换酒店当天需要先办理退房并把行李带到下一个住宿；'
            '行程已按此预留转场，如需少搬一次可把相邻夜晚改成同一家。')


def plan(w):
    """住宿编排总览：每晚一行，含锚点、依据、查询参数与晚餐顺路建议。"""
    r = w.get('requirements') or {}
    rows = []
    assignments = assignment_map(w)
    primary_id = (w.get('hotel') or {}).get('id')
    for day in nights(w):
        anchor, basis = day_closure(w, day)
        next_day_early = False
        back = return_departure(w)
        if back and back[0].isoformat() == (date.fromisoformat(day) + timedelta(days=1)).isoformat():
            next_day_early = back[1] is None or back[1] <= RETURN_STATION_LEAD_MINUTES
        station = None
        if next_day_early:
            station = (w.get('selected_return') or {}).get('departure_station_candidate') or None
            if station and station.get('name'):
                anchor = dict(station)
                anchor['_closure'] = 'station'
                basis = '次日 ' + back[0].isoformat() + ' 需赶返程班次，最后一晚靠近出发站'
        rows.append({'date': day, 'checkin': day,
                     'anchor_id': anchor.get('id') if anchor else None,
                     'anchor_name': anchor.get('name') if anchor else None,
                     'anchor_kind': (anchor or {}).get('_closure'),
                     'anchor_basis': basis,
                     'anchor_is_station': bool(station),
                     'query_index': None, 'queried_at': None, 'candidate_ids': [],
                     'hotel_id': assignments.get(day), 'is_primary': (assignments.get(day) == primary_id),
                     'dinner_hint': dinner_options(w, day, None) if anchor else []})
    return {'nights': [x['date'] for x in rows], 'rows': rows,
            'return_departure': (return_departure(w) or (None, None))[0].isoformat() if return_departure(w) else None,
            'primary_hotel_id': primary_id, 'unassigned': unassigned(w),
            'note': ('返程当天不安排住宿；最后一晚只到返程前一天。'
                     if return_departure(w) else '尚未选定返程班次，暂按游玩日最后一天作为最后一晚。')}


def assign(w, hotel_id, days=None):
    """把某家酒店分配给指定夜晚；不指定夜晚时清理该酒店的逐晚分配。

    逐晚分配是权威来源，w['hotel'] 只保留为"主住宿"，供默认分配与旧调用方使用。
    返回实际分配的夜晚列表；传入不在住宿夜晚内的日期直接报错，
    不能静默丢弃（否则用户以为改成了、实际没改）。
    """
    from .providers import DataError
    stays = dict(w.get('stay_hotels') or {})
    order = nights(w)
    if days is None:
        for day in [d for d, hid in stays.items() if hid == hotel_id]:
            stays.pop(day, None)
    else:
        unknown = [d for d in days if d not in order]
        if unknown:
            raise DataError('这些日期不在本次住宿夜晚内：'+ '、'.join(unknown)
                            + ('；本次住宿夜晚为'+ '、'.join(order) if order else '；当前没有需要住宿的夜晚')
                            + '。请选择住宿安排里的日期。')
        for day in days:
            stays[day] = hotel_id
    w['stay_hotels'] = stays
    return [d for d in order if stays.get(d) == hotel_id]


def unassigned(w):
    """还没有专属酒店（只能靠主住宿兜底）的夜晚。"""
    stays = w.get('stay_hotels') or {}
    return [d for d in nights(w) if not stays.get(d)]


def row_for(w, day):
    """取某晚的编排行；工作区尚未落库时按当前选择即时计算，避免调用方顺序耦合。"""
    rows = ((w.get('stay_plan') or {}).get('rows') or [])
    if not rows:
        rows = plan(w)['rows']
    for row in rows:
        if row.get('date') == day:
            return row
    return None


def day_search_plan(w, day):
    """某晚的查询参数与锚点：供酒店查询使用，参数不落库以免与缓存键冲突。"""
    row = row_for(w, day)
    if not row:
        return None
    r = w.get('requirements') or {}
    params = {'cityName': r.get('city'), 'checkIn': day,
              'checkOut': (date.fromisoformat(day) + timedelta(days=1)).isoformat(),
              'adultNum': int(r.get('adults') or 2)}
    if r.get('children'):
        if len(r.get('child_ages') or []) != int(r['children']):
            from .providers import DataError
            raise DataError('酒店查询需要每位儿童的年龄。')
        params.update(childNum=int(r['children']), childAges=r['child_ages'])
    if row.get('anchor_name'):
        params['poiName'] = row['anchor_name']
    return params
