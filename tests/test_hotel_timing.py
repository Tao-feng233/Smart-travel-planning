import asyncio
import copy
import time

from app import agent, schedule, travel_preview


def trip():
    hotel = {'id': 'h', 'kind': 'hotel', 'name': '已选酒店', 'location': '120.30,36.05'}
    spot = {'id': 's', 'kind': 'spot', 'name': '栈桥', 'location': '120.31,36.05'}
    return {
        'requirements': {'city': '青岛', 'start_date': '2026-10-12', 'days': 1, 'adults': 1},
        'catalog': {'h': hotel, 's': spot}, 'hotel': copy.deepcopy(hotel),
        'selected_spots': ['s'], 'messages': [], 'ui': {},
    }


def test_initial_timeline_shows_stay_but_never_invents_a_checkin_clock():
    # 住宿要能看见（用户要求），但不能编造"22:00 入住"这类未确认时刻。
    w = trip()
    rows = schedule.provisional(w)
    assert w['hotel']['id'] == 'h'
    assert not any(r.get('kind') == 'hotel' and r.get('time') for r in rows), rows


def test_formal_timeline_shows_stay_without_a_default_checkin_clock():
    w = trip()
    plan = {'days': [{'date': '2026-10-12', 'events': [
        {'kind': 'spot', 'name': '栈桥', 'candidate_id': 's', 'start': '10:00', 'end': '12:00'},
    ]}]}
    rows = schedule.plan_rows(w, plan)
    assert [r['kind'] for r in rows if r['kind'] == 'spot'] == ['spot']
    stay = [r for r in rows if r.get('kind') == 'hotel']
    # 住宿可见，但不得带编造的入住时刻
    assert stay and all(not r.get('time') for r in stay), stay


def test_hotel_selection_asks_about_checkin_without_querying_rooms(monkeypatch):
    w = trip()
    w['hotel'] = None
    async def forbidden(*args, **kwargs):
        raise AssertionError('Selecting a location must not fetch room policies or choose a checkin time')
    monkeypatch.setattr(agent, 'tuniu', forbidden)
    answer = asyncio.run(agent.handle(w, 'select', {'id': 'h'}, lambda _: None))
    assert '入住时间' in answer and '自行安排' in answer
    assert w['stay_hotels'] == {'2026-10-12': 'h'}
    assert not w.get('selected_room')


def test_old_preview_with_default_checkin_is_not_reused():
    import hashlib
    import json
    w = trip()
    original_sha256 = hashlib.sha256
    def old_signature(value):
        inputs = json.loads(value)
        inputs['version'] = 2
        return original_sha256(json.dumps(inputs, sort_keys=True, ensure_ascii=False).encode())
    from unittest.mock import patch
    with patch.object(travel_preview.hashlib, 'sha256', old_signature):
        old = travel_preview.signature(w)
    w['travel_preview'] = {'status': 'ready', 'signature': old, 'expires': time.time() + 900,
                          'entries': [{'kind': 'hotel', 'time': '22:00', 'confirmed': True}]}
    assert travel_preview.current(w) is None
    # 旧的 22:00 伪造入住行不得被复用，也不得被标为已确认；
    # 但住宿行本身应正常出现在时间轴上（新口径：看得见、但不编造时刻）。
    rows=schedule.build(w)['entries']
    assert not any(r['kind'] == 'hotel' and (r.get('time') or r.get('confirmed')) for r in rows)
    assert any(r['kind'] == 'hotel' for r in rows)
