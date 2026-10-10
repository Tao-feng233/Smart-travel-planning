"""门票按成人/儿童分别计价；餐饮只计成人。"""
from app import planning


def workspace(**req):
    r = {'city': '成都', 'start_date': '2026-10-11', 'days': 2, 'adults': 2, 'children': 1}
    r.update(req)
    return {
        'requirements': r,
        'catalog': {
            's1': {'id': 's1', 'kind': 'spot', 'name': '熊猫基地'},
            's2': {'id': 's2', 'kind': 'spot', 'name': '宽窄巷子'},
            'f1': {'id': 'f1', 'kind': 'food', 'name': '面馆', 'cost': '30.00'},
        },
        'selected_spots': ['s1', 's2'],
        'meal_choices': {'2026-10-11|lunch': {'mode': 'chosen', 'food_id': 'f1'}},
        # 已查询门票：成人 55、儿童 27
        'tickets': {'s1': {'requested_date': '2026-10-11', 'items': [
            {'resName': '成都门票成人票_下午票', 'personTypeName': '成人票', 'startPrice': '55',
             'product_group': 'admission', 'date_status': 'in_sales_window'},
            {'resName': '儿童票', 'personTypeName': '儿童票', 'startPrice': '27',
             'product_group': 'admission', 'date_status': 'in_sales_window'},
            {'resName': '学生票', 'personTypeName': '学生票', 'startPrice': '20',
             'product_group': 'admission', 'date_status': 'in_sales_window'},
            {'resName': '门票+观光车票成人票', 'personTypeName': '成人票', 'startPrice': '85',
             'product_group': 'admission', 'date_status': 'in_sales_window'},
            {'resName': '非遗川剧变脸演出票', 'personTypeName': '成人票', 'startPrice': '10',
             'product_group': 'other', 'date_status': 'in_sales_window'},
        ]}},
    }


def plan():
    # 餐饮按计划书里的餐次计价，因此夹具带上当天的午餐事件
    return {'days': [{'date': '2026-10-11', 'events': [
        {'kind': 'meal', 'name': '午餐 · 面馆', 'food': {'id': 'f1', 'name': '面馆', 'cost': '30.00'}},
    ]}], 'budget': {'hotel_reference': 100.0, 'nights': 1, 'nights_priced': 1}}


def test_ticket_amount_splits_adults_and_children():
    b = planning.fill_budget(plan(), workspace())
    # 成人 55×2 + 儿童 27×1 = 137（学生票 20 不得当作成人票）
    assert b['items']['门票']['amount'] == 137.0
    line = b['items']['门票']['detail'][0]
    assert line['adult_unit'] == 55.0 and line['adults'] == 2
    assert line['child_unit'] == 27.0 and line['children'] == 1


def test_meals_count_only_adults():
    b = planning.fill_budget(plan(), workspace())
    # 餐饮只按成人：30 × 2 = 60（儿童不计）
    assert b['items']['餐饮']['amount'] == 60.0
    line = b['items']['餐饮']['detail'][0]
    assert line['adults'] == 2 and line['basis'] == 'chosen'
    assert '儿童不计入' in b['items']['餐饮']['basis']


def test_unqueried_ticket_stays_pending_and_is_not_counted():
    w = workspace()
    w['tickets'] = {}
    b = planning.fill_budget(plan(), w)
    assert '门票' not in b['items']
    joined = ' '.join(b['unknown'])
    assert '门票' in joined and '尚未查询' in joined
    # 未查门票不按零计入小计
    assert b['known_subtotal'] == 60.0 + 100.0


def test_child_note_mentions_height_or_age_rule():
    b = planning.fill_budget(plan(), workspace(children_ages='5.8'))
    assert '儿童' in b.get('child_note', '')
    assert '免票' in b['child_note'] and '5.8' in b['child_note']


def test_no_children_means_no_child_line():
    b = planning.fill_budget(plan(), workspace(children=0))
    line = b['items']['门票']['detail'][0]
    assert line['children'] == 0
    assert line['amount'] == 110.0  # 55×2


def test_hotel_reference_is_also_counted_in_subtotal():
    b = planning.fill_budget(plan(), workspace())
    assert b['known_subtotal'] == 137.0 + 60.0 + 100.0


def test_student_and_senior_tickets_are_not_used_as_adult_or_child():
    w = workspace()
    # 只有学生票和老人票、没有成人票与儿童票时，不能拿低价票凑数
    w['tickets'] = {'s1': {'requested_date': '2026-10-11', 'items': [
        {'resName': '学生票', 'startPrice': '20', 'product_group': 'admission', 'date_status': 'in_sales_window'},
        {'resName': '老人票', 'startPrice': '0', 'product_group': 'admission', 'date_status': 'in_sales_window'},
    ]}}
    b = planning.fill_budget(plan(), w)
    assert '门票' not in b['items']


def test_only_admission_products_count_not_bundles_or_other():
    w = workspace()
    # 基础门票 55；捆绑「门票+观光车」85 与 other 类演出票 10 都不得作为门票价
    b = planning.fill_budget(plan(), w)
    line = b['items']['门票']['detail'][0]
    assert line['adult_unit'] == 55.0
    assert b['items']['门票']['amount'] == 137.0


def test_spot_without_admission_products_is_not_guessed_free():
    w = workspace()
    w['tickets'] = {'s1': {'requested_date': '2026-10-11', 'items': [
        {'resName': '"趣探宽窄"讲解包团', 'startPrice': '198', 'product_group': 'other',
         'date_status': 'in_sales_window'},
    ]}}
    b = planning.fill_budget(plan(), w)
    # 不把讲解票当门票，也不猜免费：如实说明平台没有门票类商品
    assert '门票' not in b['items']
    joined = ' '.join(b['unknown'])
    assert '平台没有该景点的门票类商品' in joined
    assert '这些不是门票' in joined
