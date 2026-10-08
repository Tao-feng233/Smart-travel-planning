"""餐次绑定语义测试：固定日期餐次不挪期，明确跟随只提示不影响旧记录。

对应《成员三任务说明》第三批"餐饮绑定"与验收条件第 6 行：
"固定餐次与跟随餐次——固定不挪期，明确绑定可提示联动；旧记录不误改"。

旧实现的缺陷：meal_choices 只存 {mode, food_id}，没有绑定语义；景点改期后
既不会提示受影响，也无法区分"用户指定"和"助手建议"。
"""
import pytest
from app import foods, visits, schedule
from app.providers import DataError

D1, D2, D3 = '2026-10-12', '2026-10-13', '2026-10-14'


def workspace():
    cats = {'s1': {'id': 's1', 'kind': 'spot', 'name': '栈桥', 'location': '120.31,36.06'},
            's2': {'id': 's2', 'kind': 'spot', 'name': '八大关', 'location': '120.34,36.05'},
            'f1': {'id': 'f1', 'kind': 'food', 'name': '午餐店', 'location': '120.32,36.05'},
            'f2': {'id': 'f2', 'kind': 'food', 'name': '晚餐店', 'location': '120.33,36.06'},
            'h1': {'id': 'h1', 'kind': 'hotel', 'name': '示例酒店', 'location': '120.30,36.00'}}
    return {'id': 'w', 'owner_id': 'u', 'revision': 1,
            'requirements': {'city': '青岛', 'origin': '郑州', 'start_date': D1, 'days': 3,
                             'adults': 1, 'day_start': '09:00', 'day_end': '18:30'},
            'selected_spots': ['s1', 's2'], 'catalog': cats, 'hotel': dict(cats['h1']),
            'meal_choices': {}, 'visit_requests': {}, 'messages': [], 'trace': [], 'warnings': {},
            'selected_transport': None, 'selected_return': None}


def select(w, **args):
    return foods.select_meal(w, {'meal_period': 'lunch', **args})


def test_user_specified_day_makes_a_follow_binding():
    w = workspace()
    visits.save(w, [{'candidate_id': 's1', 'date': D1, 'period': 'morning'}])
    select(w, meal_date=D1, food_id='f1')
    choice = w['meal_choices'][D1 + '|lunch']
    assert choice['binding'] == foods.BINDING_FOLLOW
    assert choice['bind_spot_id'] == 's1' and choice['bind_spot_name'] == '栈桥'
    # 上午景点配午餐：只承诺同日；"同半天"要求两者归属同一半天（复核 S1）
    assert choice['binding_method'] == 'same_day'
    status = foods.binding_status(w, D1, 'lunch')
    assert status['binding'] == 'follow_spot' and status['affected'] is False


def test_explicit_follow_request_binds_to_the_named_spot():
    w = workspace()
    select(w, meal_date=D2, food_id='f1', bind_spot_id='s2')
    choice = w['meal_choices'][D2 + '|lunch']
    assert choice['binding'] == foods.BINDING_FOLLOW and choice['bind_spot_id'] == 's2'
    assert choice['binding_method'] == 'explicit'
    with pytest.raises(DataError):
        select(w, meal_date=D3, food_id='f1', bind_spot_id='不存在')


def test_meal_without_any_pin_is_not_bound():
    w = workspace()
    select(w, meal_date=D2, food_id='f1')
    assert w['meal_choices'][D2 + '|lunch']['binding'] == foods.BINDING_FIXED
    assert '固定日期' in select(w, meal_date=D2, food_id='f1')


def test_moving_the_anchored_spot_marks_the_meal_affected():
    w = workspace()
    visits.save(w, [{'candidate_id': 's1', 'date': D1, 'period': 'morning'}])
    select(w, meal_date=D1, food_id='f1')
    # 用户把景点改到后天：餐次记录保持原日期，只标受影响
    message = visits.save(w, [{'candidate_id': 's1', 'date': D3, 'period': 'morning'}])
    choice = w['meal_choices'][D1 + '|lunch']
    assert choice['food_id'] == 'f1' and choice['mode'] == 'chosen', '不能自动挪期或丢弃餐厅'
    assert choice['affected'] is True and '已改到' in choice['affected_reason']
    assert '跟随' in message and '栈桥' in message
    assert foods.binding_status(w, D1, 'lunch')['affected'] is True


def test_removing_the_anchored_spot_marks_the_meal_affected():
    w = workspace()
    visits.save(w, [{'candidate_id': 's1', 'date': D1, 'period': 'morning'}])
    select(w, meal_date=D1, food_id='f1')
    w['selected_spots'] = ['s2']
    status = foods.binding_status(w, D1, 'lunch')
    assert status['affected'] is True and '移除' in status['reason']
    assert w['meal_choices'][D1 + '|lunch']['food_id'] == 'f1'


def test_moving_the_spot_back_clears_the_affected_flag():
    w = workspace()
    visits.save(w, [{'candidate_id': 's1', 'date': D1, 'period': 'morning'}])
    select(w, meal_date=D1, food_id='f1')
    visits.save(w, [{'candidate_id': 's1', 'date': D3, 'period': 'morning'}])
    assert w['meal_choices'][D1 + '|lunch']['affected'] is True
    visits.save(w, [{'candidate_id': 's1', 'date': D1, 'period': 'morning'}])
    assert foods.binding_status(w, D1, 'lunch')['affected'] is False
    assert 'affected' not in w['meal_choices'][D1 + '|lunch']


def test_fixed_date_meal_never_moves_when_another_day_changes():
    w = workspace()
    visits.save(w, [{'candidate_id': 's1', 'date': D1, 'period': 'morning'},
                    {'candidate_id': 's2', 'date': D3, 'period': 'afternoon'}])
    # 两个景点都在指定日期 => 不自动绑定
    select(w, meal_date=D2, food_id='f1')
    choice = w['meal_choices'][D2 + '|lunch']
    assert choice['binding'] == foods.BINDING_FIXED
    visits.save(w, [{'candidate_id': 's1', 'date': D3, 'period': 'morning'}])
    assert w['meal_choices'][D2 + '|lunch']['food_id'] == 'f1'
    assert foods.binding_status(w, D2, 'lunch')['affected'] is False


def test_legacy_records_are_treated_as_fixed_date():
    """旧记录没有 binding 字段：按固定日期处理，不自动挪期。"""
    w = workspace()
    w['meal_choices'][D1 + '|lunch'] = {'mode': 'chosen', 'food_id': 'f1'}
    status = foods.binding_status(w, D1, 'lunch')
    assert status['binding'] == foods.BINDING_FIXED and status['affected'] is False
    w['visit_requests'] = {'s1': {'date': D3, 'period': 'any'}}
    assert foods.binding_status(w, D1, 'lunch')['affected'] is False


def test_bound_meal_uses_the_spot_as_search_anchor():
    """跟随餐次查餐厅时，参照点应该是绑定的景点，而不是猜测。"""
    w = workspace()
    visits.save(w, [{'candidate_id': 's1', 'date': D1, 'period': 'morning'}])
    select(w, meal_date=D1, food_id='f1')
    assert w['meal_choices'][D1 + '|lunch']['bind_spot_id'] == 's1'
    assert foods.anchors(w, {'meal_date': D1, 'meal_period': 'lunch'})[0]['id'] == 's1'


def test_timeline_exposes_binding_summary():
    w = workspace()
    visits.save(w, [{'candidate_id': 's1', 'date': D1, 'period': 'morning'}])
    select(w, meal_date=D1, food_id='f1')
    slot = next(x for x in schedule.build(w)['meal_slots'] if x['key'] == D1 + '|lunch')
    assert slot['binding']['binding'] == 'follow_spot'
    assert slot['binding']['spot_name'] == '栈桥' and slot['binding']['affected'] is False
    visits.save(w, [{'candidate_id': 's1', 'date': D3, 'period': 'morning'}])
    slot = next(x for x in schedule.build(w)['meal_slots'] if x['key'] == D1 + '|lunch')
    assert slot['binding']['affected'] is True
