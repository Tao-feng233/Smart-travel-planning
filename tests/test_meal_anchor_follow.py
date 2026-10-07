"""回归：锚定景点的餐次必须跟随该景点的实际排期日。

现场（洛阳）：用户在"龙门石窟周边"选了午餐，但排程把龙门石窟放到第 2 天，
这一餐仍留在第 1 天，计划书里没有任何提示；同一天也没有午餐事件。
本用例走完整 generate() 链路（真实排程，不是直接调 meal_alignment），
确保迁移写回、计划书警告与审核上下文三处都对得上。
"""
import asyncio, json
from app import planning

D1, D2 = '2026-10-12', '2026-10-13'


def workspace():
    return {'id': 'w1', 'owner_id': 'u1', 'title': 't', 'revision': 1,
            'requirements': {'city': '洛阳', 'origin': '郑州', 'start_date': D1, 'days': 2, 'adults': 1},
            'selected_spots': ['s1'], 'catalog': {
                's1': {'id': 's1', 'kind': 'spot', 'name': '龙门石窟', 'location': '112.477,34.558'},
                'f1': {'id': 'f1', 'kind': 'food', 'name': '龙门水席楼', 'location': '112.47,34.55',
                       'search_anchor_id': 's1', 'search_anchor': '龙门石窟'}},
            'hotel': None, 'weather': None, 'transport': None, 'tickets': {}, 'plan': None,
            'messages': [], 'trace': [], 'warnings': {},
            # 用户把这一餐选在第 1 天，但龙门石窟实际排在第 2 天
            'meal_choices': {D1 + '|lunch': {'mode': 'chosen', 'food_id': 'f1'}},
            'visit_requests': {'s1': {'date': D2, 'period': 'morning'}}}


def test_anchored_meal_follows_spot_even_when_the_chosen_day_could_serve_it(monkeypatch, tmp_path):
    w = workspace()
    seen = []

    async def tool(name, args):
        if name == 'retrieve_guides':
            return {'items': []}
        if name == 'calculate_route':
            return {'mode': 'walking', 'available': True, 'minutes': 15, 'distance': 1200,
                    'source': {'name': '高德地图', 'queried_at': '2026-10-07'}}
        return {'items': []}

    async def model(messages, **kw):
        calls = [m for m in messages if '审核助手' in str(m.get('content', ''))[:80]]
        if calls:
            seen.append(' '.join(str(m.get('content', '')) for m in messages))
            return {'content': json.dumps({'issues': [], 'summary': '审核通过'})}, {}
        return {'content': json.dumps({'title': '洛阳两日', 'days': [
            {'date': D2, 'items': [{'candidate_id': 's1', 'duration': 120, 'period': 'morning'}]},
        ], 'packing': [], 'todos': []})}, {}

    monkeypatch.setattr(planning, 'local_tool', tool)
    monkeypatch.setattr(planning, 'llm', model)
    monkeypatch.setattr(planning, 'RUNTIME', tmp_path)

    plan = asyncio.run(planning.generate(w, lambda _: None))

    assert D2 + '|lunch' in w['meal_choices'], '锚点餐次应迁到龙门石窟的实际排期日'
    assert D1 + '|lunch' not in w['meal_choices'], '原日期的旧键必须删除，否则同一餐会出现两次'
    moved = [x for x in plan['warnings'] if '实际排期调整' in x]
    assert moved and '龙门石窟' in moved[0], '计划书必须说明这一餐为何改了日期：%s' % plan['warnings']
    assert plan['meal_choices'].get(D2 + '|lunch', {}).get('food_id') == 'f1'
    day = next(d for d in plan['days'] if d['date'] == D2)
    assert any(e.get('kind') == 'meal' and '午餐' in e.get('name', '') for e in day['events']), \
        '迁移后的那一餐必须真的出现在当天日程里'
    assert seen and D2 in seen[-1], '审核上下文必须看到迁移后的餐次'
