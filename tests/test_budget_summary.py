"""预算汇总：有数据的项要算出来，没数据的项才列为待核实。"""
from app import planning


def workspace():
    return {
        'requirements': {'city': '杭州', 'start_date': '2026-10-12', 'days': 2, 'adults': 2, 'rooms': 1},
        'catalog': {
            'f1': {'id': 'f1', 'kind': 'food', 'name': '面馆', 'cost': '37.00'},
            'f2': {'id': 'f2', 'kind': 'food', 'name': '酒家', 'cost': '87.00'},
            's1': {'id': 's1', 'kind': 'spot', 'name': '西湖', 'cost': None, 'ticket_price': None},
        },
        'selected_transport': {'id': 'o', 'name': 'G1959', 'seat_type': '二等座', 'price': '470.5',
                               'selection_status': 'confirmed'},
        'selected_return': {'id': 'r', 'name': 'T38', 'seat_type': '硬座', 'price': '135.5',
                            'selection_status': 'confirmed'},
        'meal_choices': {'2026-10-12|lunch': {'mode': 'chosen', 'food_id': 'f1'},
                         '2026-10-12|dinner': {'mode': 'chosen', 'food_id': 'f2'}},
    }


def plan():
    return {'days': [{'date': '2026-10-12', 'events': [
        {'kind': 'route', 'name': 'A→B', 'route': {'mode': 'transit', 'fare': 4.0}},
        {'kind': 'route', 'name': 'B→C', 'route': {'mode': 'transit', 'fare': 5.0}},
        {'kind': 'route', 'name': 'C→D', 'route': {'mode': 'walking'}},
        {'kind': 'meal', 'name': '午餐 · 面馆', 'food': {'id': 'f1', 'name': '面馆', 'cost': '37.00'}},
        {'kind': 'meal', 'name': '晚餐 · 酒家', 'food': {'id': 'f2', 'name': '酒家', 'cost': '87.00'}},
    ]}], 'budget': {'hotel_reference': 431.0, 'nights': 2, 'nights_priced': 2}}


def test_transport_and_local_transit_and_meals_are_summed():
    b = planning.fill_budget(plan(), workspace())
    items = b['items']
    # 往返交通：单人票价 × 成人数
    assert items['往返交通']['amount'] == (470.5 + 135.5) * 2
    # 市内交通：只计入有票价的公交/地铁
    assert items['市内交通']['amount'] == 9.0
    # 餐饮：已选餐厅参考人均 × 成人数
    assert items['餐饮']['amount'] == (37.0 + 87.0) * 2
    # 小计 = 三项 + 住宿起价
    assert b['known_subtotal'] == (470.5 + 135.5) * 2 + 9.0 + (37.0 + 87.0) * 2 + 431.0


def test_unknown_only_lists_items_without_data():
    b = planning.fill_budget(plan(), workspace())
    joined = ' '.join(b['unknown'])
    # 有数据的项不应出现在待核实里
    assert '往返交通' not in joined
    assert '市内交通' not in joined
    # 有已选景点但未查询门票 → 仍在待核实，且提示可去查\n    w2 = workspace()\n    w2['selected_spots'] = ['s1']\n    b2 = planning.fill_budget(plan(), w2)\n    assert '门票' in ' '.join(b2['unknown'])\n

def test_missing_prices_fall_back_to_unknown_without_guessing():
    w = workspace()
    w.pop('selected_transport')
    w.pop('selected_return')
    w.pop('meal_choices')
    # 计划书里没有任何餐次事件时，餐饮无数据可算 → 待核实
    b = planning.fill_budget({'days': [], 'budget': {}}, w)
    assert '往返交通' not in b['items']
    assert '餐饮' not in b['items']
    joined = ' '.join(b['unknown'])
    assert '往返交通' in joined and '餐饮' in joined
    # 未知项不按零计入
    assert b['known_subtotal'] == 0.0


def test_one_direction_only_still_counts_that_direction():
    # 只选了去程时，往返交通只计去程，另一程留待核实
    w = workspace()
    w.pop('selected_return')
    b = planning.fill_budget(plan(), w)
    assert b['items']['往返交通']['amount'] == 470.5 * 2
    assert len(b['items']['往返交通']['detail']) == 1


def test_zero_priced_route_is_still_counted():
    # 票价为 0 的公交也要计入（不能因为 0 被当成缺失）
    pl = plan()
    pl['days'][0]['events'][0]['route']['fare'] = 0.0
    b = planning.fill_budget(pl, workspace())
    assert b['items']['市内交通']['amount'] == 5.0
    assert len(b['items']['市内交通']['detail']) == 2


def test_taxi_and_transit_are_mutually_exclusive_per_leg():
    # 每条路线只按一种方式计费：打车取 taxi_cost，公交取 fare，不会两者相加
    pl = plan()
    pl['days'][0]['events'] = [
        {'kind': 'route', 'name': '打车段', 'route': {'mode': 'taxi', 'taxi_cost': 38.0, 'fare': 4.0}},
        {'kind': 'route', 'name': '公交段', 'route': {'mode': 'transit', 'fare': 5.0}},
    ]
    b = planning.fill_budget(pl, workspace())
    # 38（打车，忽略同段的 fare 4）+ 5（公交）= 43
    assert b['items']['市内交通']['amount'] == 43.0
    kinds = [d['price_kind'] for d in b['items']['市内交通']['detail']]
    assert kinds == ['打车预估', '公交/地铁票价']

def test_driving_mode_taxi_cost_is_counted():
    # 高德把打车/自驾返回为 driving，其 taxi_cost 是打车预估；只认 'taxi' 会漏掉
    pl = plan()
    pl['days'][0]['events'] = [
        {'kind': 'route', 'name': '前往景区', 'route': {'mode': 'driving', 'taxi_cost': 33.0}},
        {'kind': 'route', 'name': '步行段', 'route': {'mode': 'walking'}},
    ]
    b = planning.fill_budget(pl, workspace())
    assert b['items']['市内交通']['amount'] == 33.0
    assert b['items']['市内交通']['detail'][0]['price_kind'] == '打车预估'
