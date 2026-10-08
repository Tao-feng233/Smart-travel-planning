import asyncio
import copy
import json

from app import schedule


def workspace():
    ids = ['a', 'b', 'c', 'd']
    return {'requirements': {'city': '青岛', 'start_date': '2026-10-12', 'days': 3},
            'selected_spots': ids, 'catalog': {
                i: {'id': i, 'name': i, 'kind': 'spot', 'location': f'120.{300+n},36.05',
                    'visit_suggestion': {'date': '2026-10-12', 'period': 'any'}}
                for n, i in enumerate(ids)}}


def test_soft_candidate_dates_do_not_pile_four_spots_on_one_day():
    w = workspace()
    rows = [r for r in schedule.provisional(w) if r['kind'] == 'spot']
    counts = [sum(r['date'] == f'2026-10-{d}' for r in rows) for d in (12, 13, 14)]
    assert max(counts) - min(counts) <= 1, counts


def test_explicit_date_is_kept_even_when_it_makes_load_uneven():
    w = workspace()
    w['visit_requests'] = {i: {'date': '2026-10-12', 'period': 'morning'} for i in ('a', 'b', 'c')}
    rows = [r for r in schedule.provisional(w) if r['kind'] == 'spot']
    assert all(r['date'] == '2026-10-12' and r['period'] == 'morning' for r in rows if r['candidate_id'] in ('a', 'b', 'c'))


def test_model_duration_distribution_is_shared_with_timeline_and_meal_anchors():
    from app import visit_analysis, visits
    w = workspace()
    seen = []
    async def model(messages, **kwargs):
        seen.append(json.loads(messages[1]['content']))
        return {'content': json.dumps({'items': [
            {'candidate_id': i, 'date': f'2026-10-{d}', 'period': period, 'duration': duration,
             'reason': '按游览范围和每日负担分配'}
            for i, d, period, duration in [('a', 12, 'morning', 300), ('b', 13, 'morning', 120),
                                         ('c', 13, 'afternoon', 90), ('d', 14, 'morning', 180)]]})}, {}
    result = asyncio.run(visit_analysis.analyze(w, model, lambda _: None))
    assert result['status'] == 'model'
    assert len(seen[0]['spots']) == 4 and len(seen[0]['day_budgets']) == 3
    rows = {r['candidate_id']: r for r in schedule.provisional(w) if r['kind'] == 'spot'}
    assert rows['a']['duration'] == 300 and rows['a']['date'] == '2026-10-12'
    assert rows['c']['date'] == '2026-10-13'
    assert all(r['estimated'] for r in rows.values())
    assert {p['id'] for p in visits.meal_refs(w, '2026-10-13', 'dinner')} <= {'b', 'c'}
    w['selected_return'] = {'departure': '2026-10-14 08:20'}
    assert visit_analysis.current(w) is None
    assert not any(r['date'] == '2026-10-14' for r in schedule.provisional(w) if r['kind'] == 'spot')


def test_invalid_model_ids_and_dates_cannot_replace_user_selections():
    from app import visit_analysis
    w = workspace(); before = copy.deepcopy(w['selected_spots']); calls = []
    async def model(messages, **kwargs):
        calls.append(messages)
        return {'content': json.dumps({'items': [{'candidate_id': 'foreign', 'date': '2026-10-18', 'duration': 30}]})}, {}
    result = asyncio.run(visit_analysis.analyze(w, model, lambda _: None))
    assert result['status'] == 'fallback' and len(calls) == 2
    assert w['selected_spots'] == before
    assert {i['candidate_id'] for i in result['items']} == set(before)
    assert all(i['estimated'] for i in result['items'])


def test_heaped_model_proposal_gets_concrete_repair_feedback():
    from app import visit_analysis
    w = workspace(); calls = []
    async def model(messages, **kwargs):
        calls.append(copy.deepcopy(messages))
        return {'content': json.dumps({'items': [
            {'candidate_id': i, 'date': '2026-10-12', 'period': 'any', 'duration': 120, 'reason': '位置相近'}
            for i in w['selected_spots']]})}, {}
    result = asyncio.run(visit_analysis.analyze(w, model, lambda _: None))
    assert len(calls) == 2 and 'validation_errors' in calls[1][-1]['content']
    assert result['status'] == 'fallback'
    assert len({i['date'] for i in result['items']}) == 3


def test_final_proposal_repairs_distribution_and_keeps_long_visit(monkeypatch, tmp_path):
    from app.proposals import create
    w = workspace(); calls = []
    async def model(messages, **kwargs):
        calls.append(copy.deepcopy(messages))
        if len(calls) == 1:
            groups = [{'date': '2026-10-12', 'items': [
                {'candidate_id': i, 'duration': 120} for i in w['selected_spots']]}]
        else:
            groups = [{'date': f'2026-10-{day}', 'items': items} for day, items in [
                (12, [{'candidate_id': 'a', 'duration': 300}]),
                (13, [{'candidate_id': 'b', 'duration': 120}, {'candidate_id': 'c', 'duration': 90}]),
                (14, [{'candidate_id': 'd', 'duration': 180}])]]
        return {'content': json.dumps({'days': groups})}, {}
    dates = ['2026-10-12', '2026-10-13', '2026-10-14']
    _, groups, _ = asyncio.run(create(w, list(w['catalog'].values()),
        {'dates': dates, 'tour_dates': dates}, '安排日程', lambda _: None, model, tmp_path))
    assert len(calls) == 2 and '每日负担明显失衡' in calls[1][-1]['content']
    assert groups[0]['items'][0]['duration'] == 300
    assert len({i['candidate_id'] for d in groups for i in d['items']}) == 4


def test_sparse_dense_notices_use_estimated_workload_instead_of_only_count():
    from app import visit_analysis
    w = workspace()
    assert any('较少' in x for x in visit_analysis.notices(w, visit_analysis.allocate(w)))
    w['requirements']['days'] = 1
    dense = [{**i, 'duration': 240} for i in visit_analysis.allocate(w)]
    assert any('超过可用时间' in x for x in visit_analysis.notices(w, dense))
