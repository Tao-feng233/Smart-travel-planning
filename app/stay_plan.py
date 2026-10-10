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
    return _return_departure(w)[0]


def return_date_bounds(w):
    """住宿晚数要用哪个返程日期，以及班次日期与用户明确日期是否冲突。

    用户的明确日期优先：推荐班次自己的出发日期不能把住宿晚数截短
    （用户说 10-14 返程、推荐班次 10-13 出发时，13 日那晚仍要住）。
    班次的确定出发时刻只在用户没有明确日期时才决定"当天走、不算住宿"。
    """
    r = (w.get('requirements') or {})
    explicit = _d(r.get('return_date'))
    stamp, departure = _return_departure(w)
    if explicit and stamp and stamp != explicit:
        return explicit, '用户明确的返程日期（' + explicit.isoformat() + '）；班次日期 '
    if explicit:
        return explicit, '用户明确的返程日期'
    return (stamp, '已选返程班次的出发日期') if stamp else (None, '尚未选定返程班次')


def _return_departure(w):
    """(日期, 分钟) 或 (None, None)：仅当班次日期可作为返程日依据时返回。"""
    r = (w.get('requirements') or {})
    selected = w.get('selected_return') or {}
    stamp = selected.get('departure')
    if not stamp:
        return (None, None)
    # 用户明确给了返程日期时，推荐态班次自己填的日期不能当依据（它只是建议）。
    if selected.get('selection_status') != 'confirmed' and not r.get('return_date'):
        return (None, None)
    text = str(stamp)
    day = _d(text)
    if day is None:
        return (None, None)
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
    # 去程日期是"从出发地动身"的那天，通常早于开始游玩日（如 10 号出发、11 号开玩）。
    # 那晚要在目的地过夜，因此住宿起点必须跟着提前。
    outbound = _d(r.get('outbound_date'))
    arrival = w.get('selected_transport') or {}
    # 已选班次即可（recommended 只表示尚未最终确认，不代表当晚不住）；
    # 此前只认 confirmed，导致"选了班次却选不了抵达当晚住宿"。
    arrived = _d(arrival.get('arrival')) if arrival.get('arrival') else None
    earlier = [x for x in (arrived, outbound) if x]
    if earlier:
        base = min(earlier)
        start = base if start is None else min(start, base)
    tour = [_d(x) for x in (visits.dates(w) or [])]
    tour = [x for x in tour if x]
    if not start:
        return []
    last_date, _ = return_date_bounds(w)
    last = None
    if last_date:
        # 返程当天不订酒店，故最后一晚是返程前一天。
        last = last_date - timedelta(days=1)
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


def center_of_spots(w):
    """全部已选景点的几何中心：主住宿（一键住全程）的推荐参照点。

    逐晚推荐以"当天收尾地点"为锚点，但"设为主住宿、其余夜晚沿用"是一次决定
    住哪一带，必须照顾整趟行程的所有景点，只看某一天会把住宿拉偏到一端。
    返回 (中心点, 参与计算的景点数) 或 (None, 0)。
    """
    points = []
    from .spot_hierarchy import state
    for cid in state(w)['active_ids']:
        p = _usable(w, cid)
        if p:
            try:
                lng, lat = (float(x) for x in str(p['location']).split(',')[:2])
            except (TypeError, ValueError):
                continue
            points.append((lng, lat))
    if not points:
        return None, 0
    lng = sum(p[0] for p in points) / len(points)
    lat = sum(p[1] for p in points) / len(points)
    return {'id': 'center:all-spots', 'kind': 'anchor', 'name': '全部已选景点的中心',
            'location': f'{lng:.6f},{lat:.6f}', 'center_of_spots': True}, len(points)


def trip_closure(w, before_day=None):
    """行程最后一个活动的地点：某晚没有当天活动时用它作兜底参照。

    没有活动的夜晚（例如景点全排在第一天）不能显示"待定周边"，
    否则用户不知道这一晚该住在哪一带。返回 (地点, 依据) 或 (None, 原因)。
    """
    order = touring_days(w)
    days = [d for d in order if not before_day or d <= before_day]
    for day in reversed(sorted(days)):
        for cid in reversed(order.get(day) or []):
            p = (w.get('catalog') or {}).get(cid)
            if p:
                p = dict(p)
                p['_closure'] = 'spot'
                return p, '行程最后一个活动（' + day + '）'
    return None, '行程还没有可参照的活动地点'


def between_anchor(spot, station, bias=0.5):
    """取两点之间、偏向车站一侧的参考点。

    bias=0 为景点端、1 为车站端；默认取中间略偏车站，便于次日赶车。
    缺少坐标时返回 None，由调用方回落到原锚点（不猜）。
    """
    def xy(point):
        loc = str((point or {}).get('location') or '')
        if ',' not in loc:
            return None
        try:
            x, y = [float(t) for t in loc.split(',')[:2]]
        except ValueError:
            return None
        return x, y
    a, b = xy(spot), xy(station)
    if not a or not b:
        return None
    x = a[0] + (b[0] - a[0]) * bias
    y = a[1] + (b[1] - a[1]) * bias
    name = str((spot or {}).get('name') or '最后一个活动')
    st = str((station or {}).get('name') or '返程车站')
    return {'id': None, 'kind': 'stay_between', 'name': name + '与' + st + '之间',
            'location': '%.6f,%.6f' % (x, y), '_closure': 'between'}


def return_station_for(w, day):
    """该晚次日若为返程日，返回返程车站地点（含坐标）；否则 None。

    车站优先取班次自带的候选地点，其次按名称在目录里找同名站点。
    """
    back_day, _ = _return_departure(w)
    if not back_day:
        return None
    if back_day.isoformat() != (date.fromisoformat(day) + timedelta(days=1)).isoformat():
        return None
    ret = w.get('selected_return') or {}
    cand = ret.get('departure_station_candidate')
    if cand and cand.get('location'):
        return cand
    name = str(ret.get('departure_station') or '').strip()
    if not name:
        return None
    for p in (w.get('catalog') or {}).values():
        if p.get('location') and str(p.get('name') or '').strip() == name:
            return p
    return None


def day_closure(w, day):
    """某天用于定位住宿的收尾地点：先最后一个活动景点，再顺路晚餐餐厅。

    返回 (地点, 依据)。锚点不要求已有坐标：poiName 查询只用到名称，坐标仅用于
    额外核算通行距离，因此没有坐标的收尾景点仍是有效的锚点。
    当天没有活动时退回行程最后一个活动，而不是留空。
    提前抵达日（去程早于开始游玩日）以抵达车站/机场为中心：那天人刚落地，
    住宿与餐饮都该围着到达地点安排。
    """
    from . import travel_review
    if any(d.isoformat() == day for d in travel_review.pre_tour_days(w)):
        anchor = travel_review.arrival_anchor(w)
        if anchor:
            point = dict(anchor)
            point['_closure'] = 'station' if anchor.get('kind') == 'station' else 'hotel'
            return point, anchor.get('basis') or '抵达地点'
    order = touring_days(w).get(day) or []
    last_spot = None
    for cid in reversed(order):
        p = (w.get('catalog') or {}).get(cid)
        if p:
            last_spot = dict(p)
            last_spot['_closure'] = 'spot'
            break
    if last_spot:
        # 次日就是返程日：最后一晚放在"当天最后活动 ↔ 返程车站"之间，
        # 既照顾当晚就近，也避免次日先折返住宿再去车站。
        st = return_station_for(w, day)
        if st:
            point = between_anchor(last_spot, st, bias=0.5)
            if point:
                return point, ('次日 ' + str((w.get('selected_return') or {}).get('departure') or '')[:10]
                               + ' 返程，最后一晚安排在当天最后的活动与出发站之间')
        return last_spot, '当天最后一个活动'
    dinner = dinner_for(w, day)
    if dinner:
        return dinner, '当天已选晚餐餐厅（当天以用餐收尾）'
    last,basis=trip_closure(w,day)
    if last:return last,basis
    future=[d for d in touring_days(w) if d>day]
    if future:
        cid=touring_days(w)[min(future)][0]
        return (w.get('catalog') or {}).get(cid),'后续首个游玩地点附近的住宿参照'
    return None,'行程还没有可参照的活动地点'


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


def same_hotel(a,b):
    if not a or not b:return False
    if a.get('provider_id') is not None and b.get('provider_id') is not None:
        return str(a['provider_id'])==str(b['provider_id'])
    return a.get('id')==b.get('id')


def stay_hotel_ids(w):
    """本次住宿实际用到的酒店 ID（按夜晚顺序去重）。"""
    return [h for h in dict.fromkeys(assignment_map(w).values()) if h]


def multi_stay_note(w):
    """跨酒店住宿的如实提示：换酒店当天要退房并带行李转场。"""
    ids=stay_hotel_ids(w);used=[]
    for cid in ids:
        h=w.get('catalog',{}).get(cid) or {}
        if not any(same_hotel(h,x) for x in used):used.append(h)
    if len(used) <= 1:
        return None
    return ('本次住宿跨 '+str(len(used))+' 家酒店，换酒店当天需要办理退房并携带行李转场；'
            '道路时间参与安排，入住、寄存及行李条件需核实，可将相邻夜晚改成同一家以减少搬动。')


def anchor_signature(w, anchor_id, basis, day):
    """锚点依赖签名：景点改期、换主住宿、换逐晚分配都会改变它。"""
    import json as _json
    return _json.dumps({'anchor_id': anchor_id, 'anchor_basis': basis or '',
                        'stay_hotels': (w.get('stay_hotels') or {}).get(day),
                        'primary': (w.get('hotel') or {}).get('id')}, ensure_ascii=False, sort_keys=True)


def plan(w):
    """住宿编排总览：每晚一行，含锚点、依据、逐晚分配到哪家酒店、晚餐顺路建议。

    分配在这里一次算清，避免 plan 与 assignment_map 互相调用形成循环：
    每晚只有"用户明确指定"才算有酒店，没选就是没选，不由任何主住宿兜底。
    """
    stays = w.get('stay_hotels') or {}
    rows = []
    for day in nights(w):
        anchor, basis = day_closure(w, day)
        next_day_early = False
        back_day, back_minutes = _return_departure(w)
        if back_day and back_day.isoformat() == (date.fromisoformat(day) + timedelta(days=1)).isoformat():
            next_day_early = back_minutes is None or back_minutes <= RETURN_STATION_LEAD_MINUTES
        station = None
        if next_day_early:
            station = (w.get('selected_return') or {}).get('departure_station_candidate') or None
            if station and station.get('name'):
                anchor = dict(station)
                anchor['_closure'] = 'station'
                basis = '次日 ' + back_day.isoformat() + ' 需赶返程班次，最后一晚靠近出发站'
        # 住宿只按晚指定：没有显式指定就是"还没选"，不再由任何主住宿兜底。
        # 赶车前一晚同样如此，界面上如实显示未选，由用户决定住哪。
        unsuitable = bool(station and station.get('name') and not stays.get(day))
        explicit = stays.get(day)
        if explicit:
            hotel_id, source = explicit, 'explicit'
        else:
            hotel_id, source = None, 'unset'
        rows.append({'date': day, 'checkin': day,
                     'anchor_id': anchor.get('id') if anchor else None,
                     'anchor_name': anchor.get('name') if anchor else None,
                     'anchor_kind': (anchor or {}).get('_closure'),
                     'anchor_basis': basis,
                     'anchor_is_station': bool(station),
                     'hotel_fallback_unsuitable': unsuitable,
                     'query_index': None, 'queried_at': None, 'candidate_ids': [],
                     'hotel_id': hotel_id, 'hotel_source': source,
                     'is_primary': False,
                     'dinner_hint': dinner_options(w, day, None) if anchor else []})
    last_date, last_basis = return_date_bounds(w)
    for row in rows:
        row['signature'] = anchor_signature(w, row.get('anchor_id'), row.get('anchor_basis'), row['date'])
    return {'nights': [x['date'] for x in rows], 'rows': rows,
            'return_departure': last_date.isoformat() if last_date else None,
            'return_basis': last_basis,
            'primary_hotel_id': None,
            'unassigned': [x['date'] for x in rows if x['hotel_source'] != 'explicit'],
            'needs_own_hotel': [x['date'] for x in rows if x['hotel_source'] != 'explicit'],
            'note': ('返程当天不安排住宿；最后一晚只到返程前一天（依据：'+last_basis+'）。'
                     if last_date else '尚未选定返程班次，暂按游玩日最后一天作为最后一晚。')}


def merge_plan(w, plan_rows, previous=None):
    """保留未变化的夜晚已查到的候选，只替换本次实际重查、或锚点依赖已变的夜晚。

    复核 P2：补查一晚不应把其它晚的 candidate_ids 清空，否则界面上已比较过的
    酒店会整批消失。签名变化（景点改期、换主住宿等）时该晚必须重算，不复用旧结果。
    """
    previous = previous or {}
    old_by_date = {row.get('date'): row for row in (previous.get('rows') or [])}
    for row in plan_rows.get('rows') or []:
        old = old_by_date.get(row['date'])
        if not old:
            continue
        if row.get('signature') != old.get('signature'):
            continue                                   # 锚点依赖变了：不沿用旧结果
        for key in ('candidate_ids', 'queried_at', 'empty', 'excluded'):
            if key in old:
                row[key] = old[key]
    return plan_rows


def _plan_rows(w):
    # Refresh factual assignments, retaining only still-applicable query snapshots.
    return merge_plan(w,plan(w),w.get('stay_plan'))['rows']


def assignment_view(w):
    stays=w.get('stay_hotels')
    legacy=(w.get('hotel') or {}).get('id') if stays is None else None
    return {day:{'hotel_id':(stays or {}).get(day) or legacy,
                 'source':'explicit' if (stays or {}).get(day) else 'legacy' if legacy else 'unset'}
            for day in nights(w)}


def hotel_assignments(w):return assignment_view(w)


def assignment_map(w):
    return {day:item['hotel_id'] for day,item in assignment_view(w).items()}


def hotel_for(w,day,*,morning=False):
    # Morning belongs to the preceding night's stay, except on actual arrival day.
    arrival=str((w.get('selected_transport') or {}).get('arrival') or '')[:10]
    night=(date.fromisoformat(day)-timedelta(days=1)).isoformat() if morning and day!=arrival else day
    if 'stay_hotels' not in w:
        return w.get('hotel')
    cid=(w.get('stay_hotels') or {}).get(night)
    if cid:
        return (w.get('catalog') or {}).get(cid)
    # 提前抵达日还没选定酒店，但那一晚确实要住：用抵达地点作参照，
    # 否则时间轴上这一晚会没有任何住宿条目，看起来像系统漏排了。
    from . import travel_review
    if any(d.isoformat()==night for d in travel_review.pre_tour_days(w)):
        anchor=travel_review.arrival_anchor(w)
        if anchor:
            return {**anchor,'kind':'hotel','name':'抵达'+str(anchor.get('name'))+'周边住宿',
                    'arrival_area':True,'basis':anchor.get('basis')}
    return None


def anchor(w,day,*,morning=False):
    from .locations import hotel_anchor
    h=hotel_for(w,day,morning=morning)
    return hotel_anchor({**w,'hotel':h}) if h else None


def facts(w):
    return {day:{'hotel_id':cid,'hotel':{k:(w.get('catalog',{}).get(cid) or (w.get('hotel') if cid and cid==(w.get('hotel') or {}).get('id') else {}) or {}).get(k)
                    for k in ('id','name','location','entrance','citycode','location_status','selection_stale','location_stale')}}
            for day,cid in assignment_map(w).items()}


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
    """还没有指定酒店的夜晚：没选就是还没选，不再由"主住宿"兜底。"""
    return [d for d,item in assignment_view(w).items() if not item['hotel_id']]


def row_for(w, day):
    """取某晚的编排行；工作区尚未落库时按当前选择即时计算，避免调用方顺序耦合。"""
    rows = _plan_rows(w)
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


def center_search_plan(w):
    """主住宿（住全程）的查询参数：以全部已选景点的中心为参照。

    途牛按 poiName 检索，取"离中心最近的那个已选景点"作为检索名，
    这样检索半径覆盖的正是所有景点的中心地带，而不是某一天的一端。
    """
    r = w.get('requirements') or {}
    center, count = center_of_spots(w)
    if not center:
        return None, None, 0
    try:
        clng, clat = (float(x) for x in center['location'].split(',')[:2])
    except (TypeError, ValueError):
        return None, None, 0
    nearest, best = None, None
    for cid in w.get('selected_spots') or []:
        p = _usable(w, cid)
        if not p:
            continue
        try:
            lng, lat = (float(x) for x in str(p['location']).split(',')[:2])
        except (TypeError, ValueError):
            continue
        gap = (lng - clng) ** 2 + (lat - clat) ** 2
        if best is None or gap < best:
            nearest, best = p, gap
    days = nights(w)
    params = {'cityName': r.get('city'), 'checkIn': days[0] if days else r.get('start_date'),
              'checkOut': days[-1] if days else None, 'adultNum': int(r.get('adults') or 2)}
    if params['checkOut']:
        params['checkOut'] = (date.fromisoformat(params['checkOut']) + timedelta(days=1)).isoformat()
    if nearest:
        params['poiName'] = nearest['name']
    if r.get('children'):
        if len(r.get('child_ages') or []) != int(r['children']):
            from .providers import DataError
            raise DataError('酒店查询需要每位儿童的年龄。')
        params.update(childNum=int(r['children']), childAges=r['child_ages'])
    return params, nearest, count
