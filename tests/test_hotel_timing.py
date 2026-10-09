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


def test_initial_timeline_does_not_invent_a_confirmed_2200_checkin():
    w = trip()
    rows = schedule.provisional(w)
    assert not any(row['kind'] == 'hotel' for row in rows)
    assert w['hotel']['id'] == 'h'


def test_formal_timeline_does_not_append_a_default_checkin():
    w = trip()
    plan = {'days': [{'date': '2026-10-12', 'events': [
        {'kind': 'spot', 'name': '栈桥', 'candidate_id': 's', 'start': '10:00', 'end': '12:00'},
    ]}]}
    assert [row['kind'] for row in schedule.plan_rows(w, plan)] == ['spot']


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
    assert not any(row['kind'] == 'hotel' for row in schedule.build(w)['entries'])
