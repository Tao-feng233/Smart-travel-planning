"""回归：景点周边餐饮查不到时，不能只丢一个「0 候选」给用户。

背景（真实复现）：洛阳·龙门石窟 2026-10-08 的工作区，默认关键词「当地餐厅」+
周边 5 公里查询返回 0 条，页面只剩「完成餐饮安排」和「本餐自行安排」，
体验者反馈"旅游完啥都选不了"。而同一坐标换关键词能查到 12 家。
"""
import asyncio
from app import foods


def trip(city='洛阳', start='2026-10-08', days=7):
    return {'requirements': {'city': city, 'start_date': start, 'days': days, 'origin': '郑州', 'adults': 1},
            'catalog': {'s1': {'id': 's1', 'kind': 'spot', 'name': '龙门石窟', 'location': '112.477482,34.558727'}},
            'selected_spots': ['s1'], 'messages': [], 'tickets': {}}


def restaurant(i, name):
    return {'id': f'f{i}', 'kind': 'food', 'name': name, 'location': '112.47,34.55', 'cost': '80'}


async def no_rank(w, items, *args, **kwargs):
    """替身推荐：只记录，不给推荐理由（真实链路里由模型补）。"""
    return '候选已查到'


def test_nearby_default_keyword_empty_falls_back_to_usable_keyword(monkeypatch):
    """默认关键词「当地餐厅」在景点周边 0 条时，应自动换关键词重试，而不是直接报 0 候选。"""
    w = trip()
    calls = []

    async def tool(name, args):
        calls.append((args['keywords'], args.get('radius')))
        if args['keywords'] == '当地餐厅':
            return {'items': []}
        return {'items': [restaurant(1, '老洛阳平价饭店(龙门石窟店)'), restaurant(2, '有面儿(龙门石窟店)')]}

    monkeypatch.setattr(foods, 'local_tool', tool)
    answer = asyncio.run(foods.search(w, {'meal_date': '2026-10-08', 'meal_period': 'lunch'}, lambda _: None, no_rank))
    assert len(w['food_query']['ids']) == 2, '必须真的拿到候选'
    # 泛指词「当地餐厅」命中率低，已不再作为首选词：直接用「美食」，少一次无效查询。
    assert w['food_query']['keyword'] != '当地餐厅', '记录的关键词应是真正查到结果的那个'
    assert calls and calls[0][0] == '美食', calls
    assert '龙门石窟' in w['food_query']['anchor']
    assert w['food_query']['scope'] == '周边5公里'
    assert '候选' in answer


def test_nearby_radius_is_expanded_before_giving_up(monkeypatch):
    """周边 5 公里查不到时，应先把半径放大再考虑城市范围。"""
    w = trip()
    seen = []

    async def tool(name, args):
        seen.append((args['keywords'], args.get('radius')))
        if args.get('radius') == 10000:
            return {'items': [restaurant(1, '洛阳水席楼·八大碗(非遗)')]}
        return {'items': []}

    monkeypatch.setattr(foods, 'local_tool', tool)
    asyncio.run(foods.search(w, {'meal_date': '2026-10-08', 'meal_period': 'lunch'}, lambda _: None, no_rank))
    assert 10000 in [r for _, r in seen], '必须先试过一次更大的半径'
    assert w['food_query']['ids'], '放大半径后应拿到候选'
    assert w['food_query']['scope'] != '城市范围'


def test_when_all_nearby_queries_fail_fall_back_to_city_and_label_it(monkeypatch):
    """参照点周边怎么都查不到时，退回城市范围，并在界面上如实标注。"""
    w = trip()
    calls = []

    async def tool(name, args):
        calls.append(args)
        if args.get('location'):
            return {'items': []}
        return {'items': [restaurant(1, '真不同饭店'), restaurant(2, '宴天下水席园(长兴街店)')]}

    monkeypatch.setattr(foods, 'local_tool', tool)
    asyncio.run(foods.search(w, {'meal_date': '2026-10-08', 'meal_period': 'lunch'}, lambda _: None, no_rank))
    assert w['food_query']['ids'], '城市范围应拿到候选'
    assert w['food_query']['scope'] == '城市范围', '必须如实告知这是城市范围候选而不是周边'
    assert any(not c.get('location') for c in calls), '必须真的发起过不带坐标的城市范围查询'


def test_explicit_preference_still_wins_and_is_not_replaced_by_fallback(monkeypatch):
    """用户明确说了海鲜，首选关键词仍是海鲜，且命中后不再兜底、也不被兜底词顶掉。"""
    w = trip(city='青岛')
    w['requirements']['food_preferences'] = ['海鲜']
    w['catalog']['s1'] = {'id': 's1', 'kind': 'spot', 'name': '栈桥', 'location': '120.31,36.06'}
    seen = []

    async def tool(name, args):
        if args.get('category') == 'market':
            return {'items': []}          # 海鲜偏好会附带查一次采购场所，这里不参与断言
        seen.append((args['keywords'], args.get('radius')))
        if args['keywords'] == '海鲜':
            return {'items': [restaurant(1, '双合园·海鲜水饺')]}
        raise AssertionError('用户明确说了海鲜，首选词已命中，不该再退到兜底关键词')

    monkeypatch.setattr(foods, 'local_tool', tool)
    asyncio.run(foods.search(w, {'meal_date': '2026-10-08', 'meal_period': 'lunch'}, lambda _: None, no_rank))
    assert {k for k, _ in seen} == {'海鲜'}, '首选关键词命中后不得继续兜底查询'
    assert w['food_query']['keyword'] == '海鲜'
    assert w['food_query']['ids'], '应拿到海鲜候选'


def test_single_meal_choice_can_be_cleared_without_clearing_everything():
    """截图里的死结：本餐已选餐厅 + 0 候选时，必须能只取消这一餐。"""
    w = trip()
    w['catalog']['f1'] = {'id': 'f1', 'kind': 'food', 'name': '真不同饭店'}
    w['catalog']['f2'] = {'id': 'f2', 'kind': 'food', 'name': '宴天下水席园'}
    foods.select_meal(w, {'meal_date': '2026-10-08', 'meal_period': 'lunch', 'food_id': 'f1'})
    foods.select_meal(w, {'meal_date': '2026-10-09', 'meal_period': 'dinner', 'food_id': 'f2'})
    answer = foods.select_meal(w, {'meal_date': '2026-10-08', 'meal_period': 'lunch', 'mode': 'remove'})
    assert '2026-10-08|lunch' not in w['meal_choices'], '被取消的那一餐必须从选择里移除'
    assert w['meal_choices'].get('2026-10-09|dinner', {}).get('food_id') == 'f2', '其他餐次不得被连带清掉'
    assert '取消' in answer or '清除' in answer
