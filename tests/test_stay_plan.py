"""逐晚住宿编排在整合分支上的回归：每晚以当天最后一个活动为锚点分别查询。"""
import asyncio
import copy

import pytest

from app import agent, stay_plan, visits

D1, D2, D3 = '2026-10-12', '2026-10-13', '2026-10-14'


def workspace():
    cats = {'s1': {'id': 's1', 'kind': 'spot', 'name': '栈桥', 'location': '120.31,36.06'},
            's2': {'id': 's2', 'kind': 'spot', 'name': '八大关', 'location': '120.34,36.05'},
            'h1': {'id': 'h1', 'kind': 'hotel', 'name': '示例酒店', 'location': '120.30,36.00'}}
    return {'id': 'stay', 'owner_id': 'u', 'revision': 1,
            'requirements': {'city': '青岛', 'origin': '郑州', 'start_date': D1, 'days': 3,
                             'adults': 2, 'day_start': '09:00', 'day_end': '18:30'},
            'selected_spots': ['s1', 's2'], 'catalog': cats, 'hotel': None,
            'meal_choices': {}, 'visit_requests': {}, 'messages': []}


def install(monkeypatch):
    calls = []
    async def vendor(service, tool, params):
        calls.append(params)
        prices = {D1: 100, D2: 300}
        return {'data': {'hotels': [{'hotelId': 900001, 'hotelName': '候选酒店',
                                     'lowestPrice': prices.get(params.get('checkIn'), 200)}]},
                'source': {'name': '途牛'}}
    async def tool(name, args):
        return {'items': []}
    monkeypatch.setattr(agent, 'tuniu', vendor)
    monkeypatch.setattr(agent, 'local_tool', tool)
    monkeypatch.setattr(agent, 'recommend', lambda *a, **k: asyncio.sleep(0, result='已比较'))
    monkeypatch.setattr(agent, 'hotel_query_budget', lambda: asyncio.sleep(0, result=5))
    return calls


def test_each_night_is_queried_with_its_own_anchor_and_keeps_its_own_quote(monkeypatch):
    """每晚各自查询：带该晚的入住日期与当天收尾地点；同店两晚的报价互不覆盖。"""
    w = workspace()
    visits.save(w, [{'candidate_id': 's1', 'date': D1, 'period': 'morning'},
                    {'candidate_id': 's2', 'date': D2, 'period': 'afternoon'}])
    calls = install(monkeypatch)
    asyncio.run(agent.handle(w, 'search_hotels', {'stay_date': D1}, lambda _: None))
    night = [c for c in calls if c['checkIn'] == D1 and c['checkOut'] == D2]
    assert len(night) == 1 and night[0]['poiName'] == '栈桥', night
    calls.clear()
    answer = asyncio.run(agent.handle(w, 'search_hotels', {'stay_date': D2}, lambda _: None))
    night = [c for c in calls if c['checkIn'] == D2 and c['checkOut'] == D3]
    assert len(night) == 1 and night[0]['poiName'] == '八大关', night
    # 两晚各自留下候选，且报价不同（同店不同晚不能互相覆盖）
    rows = {r['date']: r for r in w['stay_plan']['rows']}
    first = w['catalog'][rows[D1]['candidate_ids'][0]]
    second = w['catalog'][rows[D2]['candidate_ids'][0]]
    assert first['id'] != second['id']
    assert first['price'] == 100 and second['price'] == 300
    assert first['query_conditions']['checkIn'] == D1
    assert second['query_conditions']['checkIn'] == D2
    # 补查第二晚不能把第一晚已查到的候选清空
    assert rows[D1]['candidate_ids'], '补查一晚不得清空其它晚'
    assert '逐晚' in answer or '住' in answer


def test_nights_exclude_the_return_day_and_fall_back_to_the_trip_close(monkeypatch):
    """返程当天不计住宿；当天没有活动时锚点退回行程最后一个活动。"""
    w = workspace()
    # 两个景点都排在 D1：D2 当天没有活动，只能退回行程最后一个活动
    visits.save(w, [{'candidate_id': 's1', 'date': D1, 'period': 'morning'},
                    {'candidate_id': 's2', 'date': D1, 'period': 'afternoon'}])
    w['selected_return'] = {'id': 'b', 'kind': 'train', 'name': 'G1',
                            'departure': D3 + ' 15:00', 'arrival': D3 + ' 20:00',
                            'selection_status': 'confirmed', 'source': {'name': '途牛'}}
    assert stay_plan.nights(w) == [D1, D2]
    rows = stay_plan.plan(w)['rows']
    assert [r['date'] for r in rows] == [D1, D2]
    # D1 有活动：锚点是当天最后一个活动（八大关）
    assert rows[0]['anchor_name'] == '八大关' and rows[0]['anchor_basis'] == '当天最后一个活动'
    # D2 没有活动：退回行程最后一个活动，而不是留空显示"待定"
    assert rows[1]['anchor_name'] == '八大关' and '最后' in rows[1]['anchor_basis']


def test_room_details_are_explicit_and_use_the_candidate_quote_dates(monkeypatch):
    """点选住宿即取房型：前端据此直接打开房型详情，不必再点一次"房型详情"。"""
    w = workspace()
    candidate = {'id': 'tuniu:hotel:900001@' + D1, 'provider_id': 900001, 'kind': 'hotel',
                 'name': '示例酒店', 'location': '120.30,36.00',
                 'query_conditions': {'checkIn': D1, 'checkOut': D2, 'adultNum': 2, 'roomNum': 1}}
    w['catalog'][candidate['id']] = candidate
    calls = []
    async def vendor(service, tool, params):
        calls.append((tool, params))
        return {'data': {'starName': '高档型', 'policies': {'checkInTime': '14:00'},
                         'roomTypes': [{'roomTypeId': 'r1', 'roomTypeName': '大床房',
                                        'ratePlans': [{'rmbPrices': '199', 'count': 3}]}]},
                'source': {'name': '途牛'}}
    monkeypatch.setattr(agent, 'tuniu', vendor)
    async def tool(name, args):
        return {'items': []}
    monkeypatch.setattr(agent, 'local_tool', tool)
    reply = asyncio.run(agent.handle(w, 'select', {'id': candidate['id']}, lambda _: None))
    assert calls == [], '仅选择住宿不能自动依赖房型查询'
    asyncio.run(agent.handle(w,'hotel_detail',{'id':candidate['id']},lambda _:None))
    assert len(calls) == 1 and calls[0][0] == 'tuniuHotelDetail'
    # 用该候选自己的入住日期核对，而不是整段旅行日期
    assert calls[0][1]['checkIn'] == D1 and calls[0][1]['checkOut'] == D2
    assert candidate.get('room_choices'), '房型必须已就绪，前端才能直接打开房型详情'
    assert '具体房型可选' in reply
    # 已有房型时不重复请求
    calls.clear()
    asyncio.run(agent.handle(w, 'select', {'id': candidate['id']}, lambda _: None))
    assert calls == []


def test_room_fetch_failure_keeps_the_hotel_selection(monkeypatch):
    """取房型失败不能把住宿选择弄丢，要保留选择并说明可重试。"""
    from app.providers import DataError
    w = workspace()
    candidate = {'id': 'tuniu:hotel:900002@' + D1, 'provider_id': 900002, 'kind': 'hotel',
                 'name': '示例酒店', 'location': '120.30,36.00',
                 'query_conditions': {'checkIn': D1, 'checkOut': D2, 'adultNum': 2, 'roomNum': 1}}
    w['catalog'][candidate['id']] = candidate
    async def failing(service, tool, params):
        raise DataError('本项目的途牛查询预算已用完，请稍后再试')
    monkeypatch.setattr(agent, 'tuniu', failing)
    reply = asyncio.run(agent.handle(w, 'select', {'id': candidate['id']}, lambda _: None))
    assert w['hotel']['id'] == candidate['id'], '取房型失败也必须保留住宿选择'
    assert '已选择住宿' in reply and '房型可选' in reply
    with pytest.raises(DataError):asyncio.run(agent.handle(w,'hotel_detail',{'id':candidate['id']},lambda _:None))
    assert w['hotel']['id']==candidate['id']


def test_full_run_queries_only_within_budget_and_marks_skipped(monkeypatch):
    """一次查全程受剩余额度限制，未查的晚次要明确标出，不能静默少查。"""
    w = workspace()
    visits.save(w, [{'candidate_id': 's1', 'date': D1, 'period': 'morning'}])
    calls = install(monkeypatch)
    monkeypatch.setattr(agent, 'hotel_query_budget', lambda: asyncio.sleep(0, result=1))
    asyncio.run(agent.handle(w, 'search_hotels', {}, lambda _: None))
    # 逐晚只查了 1 晚；另外会发一次"全部景点中心"的主住宿查询
    assert w['hotel_query']['skipped_nights'], '未查的晚次必须标出'


def test_primary_hotel_is_queried_from_the_centre_of_all_spots(monkeypatch):
    """主住宿参照点必须是全部已选景点的中心，而不是某一天的收尾地点。

    只看某一天会把主住宿拉偏到行程一端；"设为主住宿"是一次决定住哪一带。
    """
    w = workspace()
    # 三个景点排成一条东西向的线：中心落在中间那个
    w['catalog'].update({
        'w1': {'id': 'w1', 'kind': 'spot', 'name': '西端景点', 'location': '120.10,36.05'},
        'w2': {'id': 'w2', 'kind': 'spot', 'name': '中间景点', 'location': '120.30,36.05'},
        'w3': {'id': 'w3', 'kind': 'spot', 'name': '东端景点', 'location': '120.50,36.05'}})
    w['selected_spots'] = ['w1', 'w2', 'w3']
    center, count = stay_plan.center_of_spots(w)
    assert count == 3
    lng, lat = (float(x) for x in center['location'].split(','))
    assert abs(lng - 120.30) < 1e-6 and abs(lat - 36.05) < 1e-6, center
    params, nearest, n = stay_plan.center_search_plan(w)
    # 检索名取离中心最近的已选景点，覆盖的正是中心地带
    assert nearest['name'] == '中间景点', nearest
    assert params['poiName'] == '中间景点'
    # 主住宿覆盖整段行程的夜晚
    assert params['checkIn'] == D1 and params['checkOut'] == '2026-10-15', params

    calls = install(monkeypatch)
    visits.save(w, [{'candidate_id': 'w2', 'date': D1, 'period': 'morning'}])
    asyncio.run(agent.handle(w, 'search_hotels', {}, lambda _: None))
    center_calls = [c for c in calls if c.get('poiName') == '中间景点' and c['checkOut'] == '2026-10-15']
    assert center_calls, '必须发出一次以全部景点中心为参照的主住宿查询'
    assert w['hotel_query']['center_matches'], '主住宿候选要单独列出，便于设为主住宿'


def test_timeline_uses_the_same_first_last_day_timing_as_the_plan(monkeypatch):
    """时间轴与计划书必须同一口径：首尾日准备时长用同一份 travel_timing。"""
    from app import schedule, time_policy
    w = workspace()
    w['selected_transport'] = {'id': 'a', 'kind': 'train', 'name': 'G0',
                               'departure': D1 + ' 06:00', 'arrival': D1 + ' 10:00',
                               'selection_status': 'confirmed', 'source': {'name': '途牛'}}
    w['selected_return'] = {'id': 'b', 'kind': 'train', 'name': 'G1',
                            'departure': D3 + ' 15:00', 'arrival': D3 + ' 19:00',
                            'selection_status': 'confirmed', 'source': {'name': '途牛'}}
    # 没有 travel_timing 时退回 time_policy 的保守默认值
    start, end = schedule.windows(w, D1)
    assert start == 10 * 60 + time_policy.FALLBACK_ARRIVAL_BUFFER_MINUTES
    _, back_end = schedule.windows(w, D3)
    assert back_end == 15 * 60 - time_policy.FALLBACK_PREPARATION_MINUTES
    # 有实查结果时用实查结果（这里给一个更短、更贴近实际路线的准备时长）
    import time
    from app import transport_links
    w['transport_links']={'signature':transport_links.signature(w),'expires':time.time()+900,'links':{'outbound':{'status':'available','required_minutes':40},'return':{'status':'available','required_minutes':75}}}
    start, _ = schedule.windows(w, D1)
    assert start == 10 * 60 + 40, '时间轴必须用实查准备时长'
    _, back_end = schedule.windows(w, D3)
    assert back_end == 15 * 60 - 75


def test_center_candidates_survive_a_later_per_night_query(monkeypatch):
    """主住宿候选必须留下来：逐晚查询会替换候选列表，但不能让主住宿组消失。

    用户看到的现象：切到某一晚查完，主住宿（全部景点中心）那组就没了。
    """
    w = workspace()
    visits.save(w, [{'candidate_id': 's1', 'date': D1, 'period': 'morning'},
                    {'candidate_id': 's2', 'date': D2, 'period': 'afternoon'}])
    calls = install(monkeypatch)
    # 第一次：查全程中心 → 产生主住宿候选
    asyncio.run(agent.handle(w, 'search_hotels', {}, lambda _: None))
    first_center = list(w['hotel_query'].get('center_matches') or [])
    assert first_center, '主住宿组必须有候选'
    assert any(p.get('center_of_spots') for p in (w['catalog'][i] for i in first_center))
    # 第二次：只查某一晚 → 主住宿组必须还在
    calls.clear()
    asyncio.run(agent.handle(w, 'search_hotels', {'stay_date': D2}, lambda _: None))
    still = list(w['hotel_query'].get('center_matches') or [])
    assert still == first_center, ('逐晚查询不能让主住宿组消失', first_center, still)
    assert all(cid in w['catalog'] for cid in still)


def test_timeline_shows_each_nights_own_hotel(monkeypatch):
    """时间轴的住宿条目必须逐晚取分配结果；没选的夜晚不显示任何酒店。"""
    from app import schedule
    w = workspace()
    visits.save(w, [{'candidate_id': 's1', 'date': D1, 'period': 'morning'}])
    w['catalog'].update({
        'main': {'id': 'main', 'kind': 'hotel', 'name': '第一晚酒店', 'location': '120.30,36.00'},
        'only2': {'id': 'only2', 'kind': 'hotel', 'name': '第二晚酒店', 'location': '120.40,36.10'}})
    stay_plan.assign(w, 'main', [D1])
    stay_plan.assign(w, 'only2', [D2])
    entries = [e for e in schedule.build(w)['entries'] if e['kind'] == 'hotel']
    names = {e['date']: e['name'] for e in entries}
    assert len(entries) == len(names), ('同一晚不能出现多条住宿', entries)
    assert names[D1] == '第一晚酒店', names
    assert names[D2] == '第二晚酒店', names
    # D3 没选住宿：时间轴不显示酒店条目，而不是显示别人的
    assert D3 not in names, names


def test_unpicked_nights_show_as_unpicked(monkeypatch):
    """没选的夜晚就是还没选：不沿用任何主住宿，界面据此显示"尚未选这一晚"。"""
    w = workspace()
    visits.save(w, [{'candidate_id': 's1', 'date': D1, 'period': 'morning'}])
    w['catalog']['h1'] = {'id': 'h1', 'kind': 'hotel', 'name': '第一晚酒店', 'location': '120.30,36.00'}
    w['hotel'] = dict(w['catalog']['h1'])          # 最近选定的这一家
    stay_plan.assign(w, 'h1', [D1])                # 但只指定了第一晚
    view = stay_plan.assignment_view(w)
    assert view[D1]['hotel_id'] == 'h1' and view[D1]['source'] == 'explicit'
    assert view[D2]['hotel_id'] is None and view[D2]['source'] == 'unset', view
    assert view[D3]['hotel_id'] is None and view[D3]['source'] == 'unset', view
    assert stay_plan.unassigned(w) == [D2, D3]
    # 还有未选夜晚时不能算完成住宿
    with pytest.raises(agent.DataError, match='没有选住宿'):
        asyncio.run(agent.handle(w, 'complete_hotel', {}, lambda _: None))


def test_choosing_a_hotel_for_one_night_does_not_overwrite_the_others(monkeypatch):
    """逐晚选择：选某一晚的酒店不得改动其它晚；没选的晚仍然没选。"""
    w = workspace()
    visits.save(w, [{'candidate_id': 's1', 'date': D1, 'period': 'morning'}])
    for hid, name in (('h1', '第一晚酒店'), ('h2', '第二晚酒店')):
        w['catalog'][hid] = {'id': hid, 'kind': 'hotel', 'name': name, 'provider_id': 900000,
                             'location': '120.30,36.00',
                             'query_conditions': {'checkIn': D1, 'checkOut': D3, 'adultNum': 2, 'roomNum': 1}}
    async def vendor(service, tool, params):
        return {'data': {'roomTypes': []}, 'source': {'name': '途牛'}}
    async def tool(name, args):
        return {'items': []}
    monkeypatch.setattr(agent, 'tuniu', vendor)
    monkeypatch.setattr(agent, 'local_tool', tool)

    # 只给第一晚选 h1：其它晚不得被一起定成 h1
    asyncio.run(agent.handle(w, 'select', {'id': 'h1', 'stay_date': D1}, lambda _: None))
    view = stay_plan.assignment_view(w)
    assert view[D1]['hotel_id'] == 'h1' and view[D1]['source'] == 'explicit', view
    assert view[D2]['hotel_id'] is None and view[D2]['source'] == 'unset', view
    assert list(w['stay_hotels']) == [D1], w['stay_hotels']

    # 再给第二晚选 h2：第一晚必须保持 h1
    asyncio.run(agent.handle(w, 'select', {'id': 'h2', 'stay_date': D2}, lambda _: None))
    view = stay_plan.assignment_view(w)
    assert view[D1]['hotel_id'] == 'h1', view
    assert view[D2]['hotel_id'] == 'h2', view
    assert view[D3]['hotel_id'] is None, view


def test_stay_rows_carry_anchor_and_assignment_for_the_ui(monkeypatch):
    """逐晚面板需要行级数据：锚点、依据、已选来源；未选时两晚都算未分配。"""
    w = workspace()
    visits.save(w, [{'candidate_id': 's1', 'date': D1, 'period': 'morning'}])
    stay = stay_plan.plan(w)
    assert [r['date'] for r in stay['rows']] == [D1, D2, D3]
    for row in stay['rows']:
        assert row['anchor_name'] and row['anchor_basis']
    # 还没选任何酒店：每晚都返回 source=unset，界面据此显示"尚未选这一晚"
    view = stay_plan.assignment_view(w)
    assert set(view) == {D1, D2, D3}
    assert all(v['hotel_id'] is None and v['source'] == 'unset' for v in view.values()), view
    assert set(stay['unassigned']) == {D1, D2, D3}
