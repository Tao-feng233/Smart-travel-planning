"""餐饮推荐规则回归：早餐双参照+早点优先、午餐景区周边、晚餐回酒店顺路、每餐5~6家且评分优先。"""
import asyncio

import pytest

from app import foods

D1 = '2026-10-12'


def workspace():
    return {'id': 'food', 'owner_id': 'u', 'revision': 1,
            'requirements': {'city': '洛阳', 'start_date': D1, 'days': 2, 'adults': 2,
                             'day_start': '09:00', 'day_end': '18:30'},
            'catalog': {
                's1': {'id': 's1', 'kind': 'spot', 'name': '龙门石窟', 'location': '112.47,34.55'},
                's2': {'id': 's2', 'kind': 'spot', 'name': '洛阳博物馆', 'location': '112.45,34.62'},
                'h1': {'id': 'h1', 'kind': 'hotel', 'name': '示例酒店', 'location': '112.44,34.60'}},
            'selected_spots': ['s1'], 'hotel': {'id': 'h1', 'kind': 'hotel', 'name': '示例酒店',
                                               'location': '112.44,34.60'},
            'meal_choices': {}, 'visit_requests': {}, 'messages': []}


def test_breakfast_keywords_are_breakfast_specific():
    """早餐不能用「美食」这类正餐词，要用早点类关键词。"""
    _, plan = foods.query_keywords({'food_preferences': None}, {'meal_period': 'breakfast'})
    assert plan[0] in foods.BREAKFAST_KEYWORDS, plan
    assert '早餐' in plan
    # 午晚餐仍走正餐兜底词
    _, lunch = foods.query_keywords({'food_preferences': None}, {'meal_period': 'lunch'})
    assert lunch[0] in foods.FALLBACK_KEYWORDS, lunch


def test_breakfast_anchors_cover_both_hotel_and_spot_with_labels():
    """早餐参照点要同时有酒店周边和景区周边，并各自带标注。"""
    w = workspace()
    refs = foods.anchors(w, {'meal_date': D1, 'meal_period': 'breakfast'})
    kinds = {p.get('_anchor_kind') for p in refs}
    assert 'hotel' in kinds, refs
    labels = {p.get('_anchor_label') for p in refs}
    assert '酒店周边' in labels, refs
    hotel = next(p for p in refs if p.get('_anchor_kind') == 'hotel')
    assert hotel['id'] == 'h1' and hotel['location']


def test_lunch_anchor_is_the_scenic_area():
    """午餐按景区周边推荐：参照点必须是景点，不是酒店。"""
    w = workspace()
    refs = foods.anchors(w, {'meal_date': D1, 'meal_period': 'lunch'})
    assert refs and all(p['kind'] == 'spot' for p in refs), refs
    assert any(p['id'] == 's1' for p in refs), refs


def test_dinner_anchor_includes_the_hotel_for_the_way_back():
    """晚餐要能按"回酒店顺路"推荐：酒店必须在参照点里。"""
    w = workspace()
    from app import visits
    visits.save(w, [{'candidate_id': 's1', 'date': D1, 'period': 'afternoon'}])
    refs = foods.anchors(w, {'meal_date': D1, 'meal_period': 'dinner'})
    assert any(p['id'] == 'h1' for p in refs), refs


def test_breakfast_places_rank_before_other_restaurants():
    """早餐场景：早点铺排在正餐馆前面，即使正餐馆评分更高。"""
    congee = {'id': 'a', 'kind': 'food', 'name': '老洛阳粥铺', 'rating': '4.3'}
    tavern = {'id': 'b', 'kind': 'food', 'name': '某某酒楼', 'rating': '4.9', 'poi_type': '中餐厅'}
    ranked = sorted([tavern, congee], key=lambda p: foods.rank_food(p, 'breakfast'))
    assert ranked[0]['id'] == 'a', ranked
    # 午餐不按早餐类优先，按评分
    ranked = sorted([congee, tavern], key=lambda p: foods.rank_food(p, 'lunch'))
    assert ranked[0]['id'] == 'b', ranked


def test_ratings_without_a_score_rank_after_scored_places():
    """没有评分的不能当成高分排在有评分的前面。"""
    scored = {'id': 'a', 'kind': 'food', 'name': '甲', 'rating': '4.1'}
    unknown = {'id': 'b', 'kind': 'food', 'name': '乙'}
    ranked = sorted([unknown, scored], key=lambda p: foods.rank_food(p, 'lunch'))
    assert [p['id'] for p in ranked] == ['a', 'b']


def test_search_returns_five_to_six_highly_rated_candidates(monkeypatch):
    """每餐给 5~6 个候选，且按评分高的优先。"""
    w = workspace()
    items = [{'id': f'f{i}', 'kind': 'food', 'name': f'餐厅{i}', 'location': '112.47,34.55',
              'rating': str(3.0 + i / 10)} for i in range(9)]
    async def tool(name, args):
        return {'items': [] if args['category'] == 'market' else items}
    async def rank(w, rows, *args):
        for i, p in enumerate(rows):
            p['recommendation_rank'] = i
    monkeypatch.setattr(foods, 'local_tool', tool)
    asyncio.run(foods.search(w, {'meal_date': D1, 'meal_period': 'lunch'}, lambda _: None, rank))
    chosen = w['food_query']['ids']
    assert 5 <= len(chosen) <= 6, chosen
    # 入选的应是评分最高的那批（f8 评分最高）
    assert 'f8' in chosen, chosen
    assert 'f0' not in chosen, chosen


def test_each_result_says_which_area_it_was_queried_around(monkeypatch):
    """候选要标明是酒店周边还是景区周边查询的结果。"""
    w = workspace()
    items = [{'id': 'f1', 'kind': 'food', 'name': '甲公司', 'location': '112.44,34.60', 'rating': '4.5'}]
    async def tool(name, args):
        if args['category'] == 'market':
            return {'items': []}
        return {'items': items}
    async def rank(w, rows, *args):
        pass
    monkeypatch.setattr(foods, 'local_tool', tool)
    asyncio.run(foods.search(w, {'meal_date': D1, 'meal_period': 'breakfast'}, lambda _: None, rank))
    rows = [w['catalog'][i] for i in w['food_query']['ids']]
    assert rows, '早餐应有候选'
    basis = rows[0]['recommendation_basis']
    assert '酒店周边' in basis or '景区周边' in basis, basis
