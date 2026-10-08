"""复核报告回归用例：P1–P5、S1–S3 的定向覆盖。

每条都来自《成员三v12-复核报告-20261008.md》，走真实生成路径或真实接口，
不用只测辅助函数。
"""
import asyncio, json, pathlib
import pytest
from app import foods, journey, planning, proposals, schedule, time_policy, visits

D1, D2 = '2026-10-12', '2026-10-13'
SRC = {'name': '途牛', 'queried_at': 'x'}


def workspace(days=2, day_end='17:00', back=None, spots=('s1', 's2')):
    cats = {'s1': {'id': 's1', 'kind': 'spot', 'name': '栈桥', 'location': '120.31,36.06'},
            's2': {'id': 's2', 'kind': 'spot', 'name': '八大关', 'location': '120.34,36.05'},
            'f1': {'id': 'f1', 'kind': 'food', 'name': '午餐店', 'location': '120.32,36.05'},
            'h1': {'id': 'h1', 'kind': 'hotel', 'name': '示例酒店', 'location': '120.30,36.00'},
            'hub': {'id': 'hub', 'kind': 'station', 'name': '青岛北站', 'location': '120.38,36.10',
                    'location_status': 'verified'}}
    w = {'id': 'w', 'owner_id': 'u', 'revision': 1,
         'requirements': {'city': '青岛', 'origin': '郑州', 'start_date': D1, 'days': days,
                          'adults': 1, 'day_start': '09:00', 'day_end': day_end},
         'selected_spots': list(spots), 'catalog': cats, 'hotel': dict(cats['h1']),
         'meal_choices': {}, 'visit_requests': {}, 'messages': [], 'trace': [], 'warnings': {},
         'selected_transport': None, 'selected_return': None}
    if back:
        w['selected_return'] = {'id': 'b', 'kind': 'train', 'name': 'G2', 'departure': back,
                                'arrival': back, 'departure_station': '青岛北站',
                                'selection_status': 'confirmed', 'source': SRC}
    return w


def install(monkeypatch, tmp_path, allocation, route_minutes=None, sink=None):
    async def tool(name, args):
        if name == 'retrieve_guides':
            return {'items': []}
        if name == 'search_transport_places':
            return {'items': []}
        o = str(args.get('origin') or ''); d = str(args.get('destination') or '')
        minutes = route_minutes(o, d) if route_minutes else (20 if '120.38' in d else 15)
        if sink is not None: sink.append((o, d, minutes))
        return {'mode': args.get('mode'), 'available': True, 'status': 'ok',
                'minutes': minutes, 'distance': 900, 'polylines': []}
    async def model(messages, **kw):
        if '审核助手' in messages[0]['content']:
            return {'content': json.dumps({'issues': [], 'summary': 'ok'})}, {}
        return {'content': json.dumps(allocation)}, {}
    monkeypatch.setattr(planning, 'local_tool', tool)
    monkeypatch.setattr(planning, 'llm', model)
    monkeypatch.setattr(planning, 'RUNTIME', tmp_path)


def test_p1_rebalanced_groups_have_no_duplicate_or_overload(monkeypatch, tmp_path):
    """P1：真实生成路径进入重排分支后，同一天不能重复出现景点。"""
    w = workspace(day_end='17:00')
    allocation = {'title': 't', 'days': [{'date': D1, 'items': [{'candidate_id': 's1', 'duration': 180},
                                                               {'candidate_id': 's2', 'duration': 180}]}],
                  'packing': [], 'todos': []}
    install(monkeypatch, tmp_path, allocation)
    plan = asyncio.run(planning.generate(w, lambda _: None))
    for day in plan['days']:
        ids = [e['candidate_id'] for e in day['events'] if e['kind'] == 'spot']
        assert len(ids) == len(set(ids)), (day['date'], ids)
    placed = sorted(e['candidate_id'] for d in plan['days'] for e in d['events'] if e['kind'] == 'spot')
    assert placed == ['s1', 's2']


def test_p1_create_groups_are_valid_after_repair(monkeypatch, tmp_path):
    """P1：create() 返回的分组必须逐日不超容量、ID 不重复。"""
    w = workspace(day_end='17:00')
    payload = {'dates': [D1, D2], 'tour_dates': [D1, D2]}
    draft = {'title': 't', 'days': [{'date': D1, 'items': [{'candidate_id': 's1', 'duration': 180},
                                                          {'candidate_id': 's2', 'duration': 180}]}],
             'packing': [], 'todos': []}
    async def model(messages, **kw):
        return {'content': json.dumps(draft)}, {}
    _, groups, _ = asyncio.run(proposals.create(
        w, [w['catalog']['s1'], w['catalog']['s2']], payload, '',
        lambda _: None, model, tmp_path))
    assert sorted(i['candidate_id'] for d in groups for i in d['items']) == ['s1', 's2']
    for day in groups:
        ids = [i['candidate_id'] for i in day['items']]
        assert len(ids) == len(set(ids)), ids
        assert proposals.day_load(w, day) <= schedule.capacity(w, day['date'])['available_minutes']


def test_p2_return_preparation_uses_the_actual_final_position(monkeypatch, tmp_path):
    """P2：返程日会先回酒店时，准备时间必须按酒店→车站算。"""
    w = workspace(days=2, back=D2 + ' 16:00')
    allocation = {'title': 't', 'days': [{'date': D1, 'items': [{'candidate_id': 's1', 'duration': 120}]},
                                         {'date': D2, 'items': [{'candidate_id': 's2', 'duration': 120}]}],
                  'packing': [], 'todos': []}
    queries = []
    def minutes(o, d):
        if '120.38' in d: return 100 if '120.30' in o else 20
        return 15
    install(monkeypatch, tmp_path, allocation, route_minutes=minutes, sink=queries)
    plan = asyncio.run(planning.generate(w, lambda _: None))
    entry = plan['time_policy']['return'][D2]
    assert entry['minutes'] == 100 + 30 + 20, entry['basis']
    assert any('120.30' in q[0] and '120.38' in q[1] for q in queries), '必须查询酒店→车站'
    d2 = next(d for d in plan['days'] if d['date'] == D2)
    transfer = next(e for e in d2['events'] if e['kind'] == 'transfer_plan')
    assert transfer['start'] == '13:30', transfer['start']


def test_p3_meal_window_uses_this_runs_preparation(monkeypatch, tmp_path):
    """P3：本轮算出的准备时间必须在选餐判断之前生效，不能读上一次的缓存。"""
    w = workspace(days=1, day_end='22:00', back=D1 + ' 20:00', spots=('s1',))
    w['meal_choices'] = {D1 + '|dinner': {'mode': 'chosen', 'food_id': 'f1'}}
    allocation = {'title': 't', 'days': [{'date': D1, 'items': [{'candidate_id': 's1', 'duration': 120}]}],
                  'packing': [], 'todos': []}
    def minutes(o, d): return 20
    install(monkeypatch, tmp_path, allocation, route_minutes=minutes)
    plan = asyncio.run(planning.generate(w, lambda _: None))
    entry = plan['time_policy']['return'][D1]
    # 本轮口径：20 + 30 + 20 = 70 → 截止 18:50；旧的 120 兜底会给出 18:00
    assert entry['minutes'] == 70
    from app.schedule import return_cutoff_minutes
    assert return_cutoff_minutes(w, D1) == 20 * 60 - 70
    # 生成过程中写回的口径也必须是本轮的 70
    assert schedule.policy_matches(w, D1, 'return', w['time_policy']['return'][D1])
    # 晚餐必须落在本轮截止前；若还在用旧的 120 兜底，这里会报"来不及安排"
    assert not any('来不及安排' in x for x in plan['warnings'])


def test_p4_recommended_return_is_not_confirmed():
    """P4：推荐态返程只是建议，不能算用户确认。"""
    w = workspace(days=2)
    w['selected_return'] = {'id': 'b', 'kind': 'train', 'name': 'G2', 'departure': D2 + ' 16:00',
                            'arrival': D2 + ' 18:00', 'selection_status': 'recommended'}
    assert journey.return_date_confirmed(w) is False
    status = journey.return_date_status(w)
    assert status['status'] == 'suggested' and '需用户确认' in status['basis']


def test_p5_status_does_not_claim_verified_for_estimates():
    """P5：查到路线但终端未确认、或仍有估计值时，整体不能标 verified。"""
    uncertain = time_policy.return_preparation({'kind': 'train', 'name': 'G1'}, 24)
    assert uncertain['status'] == time_policy.STATUS_NEEDS_CHECK
    assert any('终端' in x for x in uncertain['unverified'])
    confirmed = time_policy.return_preparation({'kind': 'train', 'name': 'G1'}, 24, endpoint_confirmed=True)
    assert confirmed['status'] == time_policy.STATUS_ESTIMATED
    assert any('承运方实际要求' in x for x in confirmed['unverified'])
    arrival = time_policy.arrival_ready({'kind': 'train', 'name': 'G1'}, 30, endpoint_confirmed=True)
    assert arrival['status'] == time_policy.STATUS_ESTIMATED
    assert any('估计' in x for x in arrival['unverified'])


def test_s1_half_day_label_requires_matching_period():
    """S1：上午景点配当天晚餐，不能声称"与景点同半天"。"""
    w = workspace(days=1, day_end='22:00', spots=('s1',))
    visits.save(w, [{'candidate_id': 's1', 'date': D1, 'period': 'morning'}])
    foods.select_meal(w, {'meal_date': D1, 'meal_period': 'dinner', 'food_id': 'f1'})
    assert w['meal_choices'][D1 + '|dinner']['binding_method'] == 'same_day'
    # 晚上景点 + 当天晚餐：确实同半天
    w2 = workspace(days=1, day_end='22:00', spots=('s1',))
    visits.save(w2, [{'candidate_id': 's1', 'date': D1, 'period': 'evening'}])
    foods.select_meal(w2, {'meal_date': D1, 'meal_period': 'dinner', 'food_id': 'f1'})
    assert w2['meal_choices'][D1 + '|dinner']['binding_method'] == 'same_half_day'
    # 显式指定跟随时保留 explicit
    w3 = workspace(days=1, day_end='22:00', spots=('s1',))
    foods.select_meal(w3, {'meal_date': D1, 'meal_period': 'lunch', 'food_id': 'f1', 'bind_spot_id': 's1'})
    assert w3['meal_choices'][D1 + '|lunch']['binding_method'] == 'explicit'


def test_s1_period_change_marks_half_day_binding_affected():
    """S1：景点日期没变但时段变了，原本"同半天"的绑定也要提示。"""
    w = workspace(days=1)
    visits.save(w, [{'candidate_id': 's1', 'date': D1, 'period': 'evening'}])
    foods.select_meal(w, {'meal_date': D1, 'meal_period': 'dinner', 'food_id': 'f1'})
    assert w['meal_choices'][D1 + '|dinner']['binding_method'] == 'same_half_day'
    # 景点时段从晚上改到上午：日期没变，但不再同半天
    visits.save(w, [{'candidate_id': 's1', 'date': D1, 'period': 'morning'}])
    status = foods.binding_status(w, D1, 'dinner')
    assert status['affected'] is True and '不再同半天' in status['reason']
    assert w['meal_choices'][D1 + '|dinner']['food_id'] == 'f1', '餐厅选择必须保留'


def test_s2_station_note_matches_the_entity_actually_used():
    """S2：用了工作区已有坐标时，不能提示"未取得可用坐标"。"""
    transport = {'id': 'g', 'name': 'G1', 'arrival_station': '青岛北站'}
    verified = {'name': '青岛北站', 'location': '120.38,36.10', 'location_status': 'verified'}
    note = time_policy.station_candidate_note(transport, 'arrival', verified)
    assert '未取得可用坐标' not in note
    assert '已核对' in note
    candidate = {'name': '青岛北站', 'location': '120.38,36.10', 'location_status': 'candidate',
                 'endpoint_scope': 'primary'}
    assert '尚未由用户或承运方确认终端' in time_policy.station_candidate_note(transport, 'arrival', candidate)
    resolved_none = {'id': 'g', 'name': 'G1', 'arrival_station': '青岛北站', 'arrival_station_candidate': None}
    assert '未取得可用坐标' in time_policy.station_candidate_note(resolved_none, 'arrival', None)
    never = {'id': 'g', 'name': 'G1', 'arrival_station': '青岛北站'}
    assert '尚未查询坐标' in time_policy.station_candidate_note(never, 'arrival', None)


def test_meal_conflict_attributes_to_the_day_not_the_return_trip(monkeypatch, tmp_path):
    """非返程日的餐次冲突，不能提示"返程准备时刻"（复核外的用户反馈）。

    场景：10-09 去程 15:08 抵达（+90 分钟准备→16:38 起），18:30 结束；
    餐厅往返 64+60 分钟、用餐 60 分钟，合计超过当日窗口 → 冲突原因只能是当日结束时刻。
    """
    from app import access, schedule
    w = workspace(days=2, day_end='18:30', spots=('s1',))
    w['selected_transport'] = {'id': 'g', 'kind': 'train', 'name': 'G2831',
                               'departure': D1 + ' 09:08', 'arrival': D1 + ' 15:08', 'source': SRC}
    w['selected_return'] = {'id': 'b', 'kind': 'train', 'name': 'G322',
                            'departure': '2026-10-18 06:56', 'arrival': '2026-10-18 11:24',
                            'departure_station': '成都东', 'selection_status': 'confirmed', 'source': SRC}
    food = {'id': 'f2', 'kind': 'food', 'name': '跨城火锅', 'location': '104.076761,30.657629'}
    w['catalog']['f2'] = food
    async def options(a, b):
        return [{'mode': 'walking', 'available': True, 'status': 'ok',
                 'minutes': 64 if b.get('kind') == 'food' else 60, 'distance': 3600, 'polylines': []}]
    result = asyncio.run(access.check(w, food, w['hotel'], options, planning.choose_route, (D1, 'dinner')))
    assert result['status'] == 'time_conflict', result
    message = result['message']
    # 说出了是哪一步超的，并给出总量
    assert '到餐厅含机动' in message and '返回住宿含机动' in message and '205分钟' in message
    # 这一天不是返程日：归因必须是当日结束时刻，而不是返程接驳准备
    assert '当日须在18:30前结束' in message, message
    assert '最后一项活动须在' not in message and '该日是返程日' not in message
    assert schedule.return_cutoff_minutes(w, D1) is None
    # 真正卡住的是当日结束时刻
    assert schedule.limit_reason(w, D1).startswith('当日须在18:30')


def test_meal_conflict_on_the_real_return_day_does_say_return(monkeypatch, tmp_path):
    """返程日才允许说"返程准备"，且给出接驳截止时刻。"""
    from app import access, schedule
    w = workspace(days=2, day_end='23:00', back='2026-10-13 06:56', spots=('s1',))
    w['selected_return'].update(departure_station='成都东')
    food = {'id': 'f2', 'kind': 'food', 'name': '跨城火锅', 'location': '104.076761,30.657629'}
    w['catalog']['f2'] = food
    async def options(a, b):
        return [{'mode': 'walking', 'available': True, 'status': 'ok',
                 'minutes': 64 if b.get('kind') == 'food' else 60, 'distance': 3600, 'polylines': []}]
    result = asyncio.run(access.check(w, food, w['hotel'], options, planning.choose_route, (D2, 'dinner')))
    assert result['status'] == 'time_conflict'
    assert '按返程接驳准备预留' in result['message']
    assert '该日是返程日' in result['message']
    assert schedule.return_cutoff_minutes(w, D2) is not None
    assert schedule.limit_reason(w, D2).startswith('该日是返程日')


def test_day_end_is_the_single_deadline_including_return_cutoff():
    """返程日的每日结束时刻必须已含接驳截止：时间轴、容量、游玩强度分析共用一处。

    整合分支的 provisional()/visit_analysis 直接用 day_end() 判超容量；
    若 day_end() 不收紧返程截止，返程日会一边按接驳准备要求提前结束，
    一边允许把活动排到接驳之后（与统一时间契约矛盾）。
    """
    from app import schedule
    w = workspace(days=2, day_end='22:00', back=D2 + ' 16:00', spots=('s1',))
    w['visit_requests'] = {'s1': {'date': D2, 'period': 'evening'}}      # 有晚间景点 → 原本延到 22:00
    plain = workspace(days=2, day_end='22:00', spots=('s1',))
    plain['visit_requests'] = {'s1': {'date': D1, 'period': 'evening'}}
    # 非返程日：晚间景点把上限延到 22:00
    assert schedule.day_end(plain, D1) == 22 * 60
    # 返程日：即使有晚间景点，也不能超过返程截止（16:00 − 准备时长）
    cutoff = schedule.return_cutoff_minutes(w, D2)
    assert cutoff is not None
    assert schedule.day_end(w, D2) == cutoff, (schedule.day_end(w, D2), cutoff)
    # 两个名字必须同口径，不允许再出现两套截止定义
    for dt in (D1, D2):
        assert schedule.day_limit(w, dt) == schedule.day_end(w, dt)
    # 餐次窗口也用同一上限
    assert schedule.meal_window(w, D2, 'dinner')[1] <= schedule.day_end(w, D2)


def test_spot_intent_uses_three_level_date_source_names():
    """日期三级来源与成员二对齐：user_explicit / system_suggestion，不用旧字面值。"""
    from app import foods, visits
    w = workspace(days=2, spots=('s1',))
    # 用户明确指定优先
    visits.save(w, [{'candidate_id': 's1', 'date': D1, 'period': 'morning'}])
    intent = foods.spot_intent(w, 's1')
    assert intent['source'] == 'user_explicit' and intent['date'] == D1
    # 无用户指定时落到系统建议
    w2 = workspace(days=2, spots=('s1',))
    w2['catalog']['s1']['visit_suggestion'] = {'date': D2, 'period': 'afternoon'}
    suggested = foods.spot_intent(w2, 's1')
    assert suggested['source'] == 'system_suggestion' and suggested['date'] == D2
    # 两者都无
    w3 = workspace(days=2, spots=('s1',))
    assert foods.spot_intent(w3, 's1') == {'date': None, 'period': 'any', 'source': None}
    # 旧字面值不得再出现
    import inspect
    source = inspect.getsource(foods.spot_intent)
    assert "'user'" not in source and "'suggestion'" not in source


def test_plan_rejection_message_is_layman_and_keeps_data():
    """成员二请求：排程失败提示不能出现"草稿/校验"这类内部口径，且要说清数据没丢。"""
    import inspect
    from app import proposals
    source = inspect.getsource(proposals)
    assert '行程草稿未通过候选/日期校验' not in source
    assert '景点日期或往返班次之间有冲突' in source
    assert '没有丢' in source
    # 给出可执行动作，而不是只说"请重新生成"
    assert '重新生成' in source and ('减少一个景点' in source or '换个班次' in source)


def test_stage_identity_changes_with_planning_inputs():
    """阶段复用：同一份输入身份一致，任一影响排程的选择一变即失效。"""
    from app import planning
    base = workspace(days=2, back=D2 + ' 16:00', spots=('s1', 's2'))
    first = planning.stage_identity(base)
    assert first == planning.stage_identity(workspace(days=2, back=D2 + ' 16:00', spots=('s1', 's2')))
    assert planning.stage_reusable(base, {'identity': first, 'has_plan': True}) is True

    # 身份未变但阶段没有产出计划：不能复用
    assert planning.stage_reusable(base, {'identity': first, 'has_plan': False}) is False
    assert planning.stage_reusable(base, None) is False

    for label, mutate in (
        ('换酒店', lambda w: w.update(hotel={'id': 'h2', 'kind': 'hotel', 'location': '120.60,36.30'})),
        ('改节奏', lambda w: w['requirements'].update(pace='packed')),
        ('改结束时刻', lambda w: w['requirements'].update(day_end='20:00')),
        ('增减景点', lambda w: w.update(selected_spots=['s1'])),
        ('改景点日期', lambda w: w.update(visit_requests={'s1': {'date': D2, 'period': 'morning'}})),
        ('改餐次', lambda w: w.update(meal_choices={D1 + '|lunch': {'mode': 'chosen', 'food_id': 'f1'}})),
        ('换班次', lambda w: w['selected_return'].update(departure=D2 + ' 18:00')),
        ('班次改推荐态', lambda w: w['selected_return'].update(selection_status='recommended')),
    ):
        changed = workspace(days=2, back=D2 + ' 16:00', spots=('s1', 's2'))
        mutate(changed)
        assert planning.stage_identity(changed) != first, label
        assert planning.stage_reusable(changed, {'identity': first, 'has_plan': True}) is False, label


def test_generated_plan_carries_stage_identity(monkeypatch, tmp_path):
    """生成的计划必须带上阶段身份，任务层才能据此复用。"""
    from app import planning
    w = workspace(days=1, day_end='22:00', spots=('s1',), back=D1 + ' 20:00')
    allocation = {'title': 't', 'days': [{'date': D1, 'items': [{'candidate_id': 's1', 'duration': 120}]}],
                  'packing': [], 'todos': []}
    install(monkeypatch, tmp_path, allocation, route_minutes=lambda o, d: 20)
    plan = asyncio.run(planning.generate(w, lambda _: None))
    stage = plan['stage']
    assert stage['action'] == 'plan' and stage['identity'] == planning.stage_identity(w)
    assert stage['has_plan'] is True and 'hotel' in stage['depends_on']
    assert planning.stage_reusable(w, stage) is True
    # 计划生成后工作区再改选择，旧阶段立即失效
    w['selected_spots'] = []
    assert planning.stage_reusable(w, stage) is False


def test_stay_nights_exclude_the_return_day():
    """返程当天不订酒店：最后一晚只到返程前一天；无返程时按游玩最后一天。"""
    from app import stay_plan, visits
    plain = workspace(days=3, spots=('s1',))
    visits.save(plain, [{'candidate_id': 's1', 'date': D2, 'period': 'morning'}])
    # 未选返程班次时保守按游玩日覆盖的夜晚（3 天 → 3 晚），并在说明里提示需确认返程
    assert stay_plan.nights(plain) == [D1, D2, '2026-10-14']
    assert '返程' in stay_plan.plan(plain)['note']
    # 返程在 D2：当天走，不需要 D2 的住宿
    back_same = workspace(days=3, back=D2 + ' 15:18', spots=('s1',))
    visits.save(back_same, [{'candidate_id': 's1', 'date': D1, 'period': 'morning'}])
    assert stay_plan.nights(back_same) == [D1]
    # 返程在 D2 凌晨：同样不需要 D2 住宿
    early = workspace(days=3, back=D2 + ' 06:56', spots=('s1',))
    visits.save(early, [{'candidate_id': 's1', 'date': D1, 'period': 'morning'}])
    assert stay_plan.nights(early) == [D1]


def test_last_night_anchors_on_station_when_leaving_early_next_day():
    """次日赶早班时最后一晚锚点改为返程站；下午返程则仍以当天收尾景点为准。"""
    from app import stay_plan, visits
    station = {'id': 'amap:station', 'name': '青岛北站', 'location': '120.38,36.10', 'endpoint_scope': 'primary'}
    w = workspace(days=3, back=D2 + ' 06:56', spots=('s1',))
    visits.save(w, [{'candidate_id': 's1', 'date': D1, 'period': 'evening'}])
    w['selected_return']['departure_station_candidate'] = dict(station)
    w['catalog']['amap:station'] = dict(station)
    rows = stay_plan.plan(w)['rows']
    assert [r['date'] for r in rows] == [D1]
    assert rows[0]['anchor_name'] == '青岛北站' and rows[0]['anchor_is_station'] is True
    assert '赶' in rows[0]['anchor_basis']
    late = workspace(days=3, back=D2 + ' 18:00', spots=('s1',))
    visits.save(late, [{'candidate_id': 's1', 'date': D1, 'period': 'evening'}])
    late['selected_return']['departure_station_candidate'] = dict(station)
    late['catalog']['amap:station'] = dict(station)
    late_rows = stay_plan.plan(late)['rows']
    assert late_rows[0]['anchor_name'] == '栈桥' and late_rows[0]['anchor_is_station'] is False


def test_stay_plan_anchors_each_night_on_that_days_closure():
    """每晚锚点是"当天最后一个活动"，逐晚不同；不再用全程单一锚点。"""
    from app import stay_plan, visits
    w = workspace(days=2, spots=('s1', 's2'))
    visits.save(w, [{'candidate_id': 's1', 'date': D1, 'period': 'morning'},
                    {'candidate_id': 's2', 'date': D2, 'period': 'afternoon'}])
    rows = stay_plan.plan(w)['rows']
    assert [r['date'] for r in rows] == [D1, D2]
    by_date = {r['date']: r for r in rows}
    assert by_date[D1]['anchor_name'] == '栈桥'      # D1 的收尾活动
    assert by_date[D2]['anchor_name'] == '八大关'    # D2 的收尾活动
    assert all('当天最后一个活动' in r['anchor_basis'] for r in rows)
    params = stay_plan.day_search_plan(w, D1)
    assert params['checkIn'] == D1 and params['checkOut'] == D2
    assert params['poiName'] == '栈桥'


def test_dinner_hint_prefers_the_restaurant_on_the_way_back_to_the_hotel():
    """晚餐提示按"回住宿顺路"排序，且只统计晚餐时段已选的餐厅。"""
    from app import stay_plan
    w = workspace(days=1, day_end='22:00', spots=('s1',))
    w['catalog']['s1']['location'] = '0,0'
    w['catalog']['f1']['name'] = '顺路店'
    w['catalog']['far'] = {'id': 'far', 'kind': 'food', 'name': '绕远店', 'location': '1.0,1.0'}
    w['visit_requests'] = {'s1': {'date': D1, 'period': 'afternoon'}}
    # 晚餐选绕远店、午餐选顺路店：晚餐候选里不能混进午餐
    w['meal_choices'] = {D1 + '|dinner': {'mode': 'chosen', 'food_id': 'far'},
                         D1 + '|lunch': {'mode': 'chosen', 'food_id': 'f1'}}
    rows = stay_plan.dinner_options(w, D1, {'id': 'h9', 'kind': 'hotel', 'location': '0.05,0'})
    # 只应统计晚餐时段已选的餐厅，午餐不得混入
    assert {x['food_id'] for x in rows} == {'far'}
    assert rows[0]['detour_km_via_meal'] is not None
    # 跑到 (1,1) 的口味店相对"景点→酒店"明显绕远，不能判为顺路
    assert rows[0]['on_the_way'] is False
    # 换成紧邻的餐厅则应判为顺路
    w['meal_choices'] = {D1 + '|dinner': {'mode': 'chosen', 'food_id': 'f1'}}
    w['catalog']['f1']['location'] = '0.02,0'
    near = stay_plan.dinner_options(w, D1, {'id': 'h9', 'kind': 'hotel', 'location': '0.05,0'})
    assert near[0]['food_id'] == 'f1' and near[0]['on_the_way'] is True


def test_keyword_hotel_search_keeps_the_single_query_path(monkeypatch):
    """用户指定品牌时仍按其关键词直接查一次，不按晚锚定。"""
    from app import agent
    w = workspace(days=3, spots=('s1',))
    calls = []
    async def vendor(service, tool, params):
        calls.append(params)
        return {'data': {'hotels': []}, 'source': {'name': '途牛'}}
    monkeypatch.setattr(agent, 'tuniu', vendor)
    answer = asyncio.run(agent.handle(w, 'search_hotels', {'keyword': '汉庭'}, lambda _: None))
    assert len(calls) == 1 and calls[0]['keyword'] == '汉庭'
    assert w['hotel_query']['ids'] == [] and w['candidates'] == []
    assert '汉庭' in answer and '未查到' in answer and '偏好' in answer


def test_dinner_ranking_prefers_the_restaurant_on_the_way_back():
    """晚餐候选在同分时优先回住宿顺路的店，且依据如实标注。"""
    from app import foods
    w = workspace(days=1, day_end='22:00', spots=('s1',))
    w['catalog']['s1']['location'] = '0,0'
    w['hotel'] = {'id': 'h1', 'kind': 'hotel', 'name': '酒店', 'location': '0.06,0'}
    w['visit_requests'] = {'s1': {'date': D1, 'period': 'afternoon'}}
    onway = {'id': 'on', 'kind': 'food', 'name': '顺路店', 'location': '0.03,0', 'recommendation_rank': 2}
    detour = {'id': 'off', 'kind': 'food', 'name': '绕远店', 'location': '1.0,1.0', 'recommendation_rank': 2}
    foods.on_the_way_bias(w, onway, (D1, 'dinner'))
    foods.on_the_way_bias(w, detour, (D1, 'dinner'))
    assert onway['on_the_way_to_stay'] is True and onway['route_bias'] > 0
    assert detour['on_the_way_to_stay'] is False and detour['route_bias'] == 0
    # 同分时顺路者排序在前
    ranked = sorted([detour, onway], key=lambda p: (p['recommendation_rank'] - p['route_bias'], p['recommendation_rank']))
    assert ranked[0]['id'] == 'on'
    # 午餐不做顺路偏置，也不编造依据
    lunch = {'id': 'l', 'kind': 'food', 'name': '午餐店', 'location': '0.03,0', 'recommendation_rank': 1}
    foods.on_the_way_bias(w, lunch, (D1, 'lunch'))
    assert lunch['on_the_way_to_stay'] is None and lunch['route_bias'] == 0
    # 尚未选住宿时，只能按"离当天收尾地点近"判断，且依据可说明
    w['hotel'] = None
    near_last = {'id': 'n', 'kind': 'food', 'name': '近店', 'location': '0.02,0', 'recommendation_rank': 2}
    foods.on_the_way_bias(w, near_last, (D1, 'dinner'))
    assert near_last['on_the_way_to_stay'] is True and near_last['route_bias'] > 0


def test_report_export_survives_missing_source_fields():
    """复核确认的输出兼容问题：历史记录缺 source 时，导出要降级而不是崩。"""
    from app import report
    base = {'requirements': {'city': '青岛', 'start_date': D1, 'days': 2}, 'revision': 1, 'meal_choices': {},
            'plan': {'title': 't', 'created': 'now', 'stale': False, 'days': [], 'todos': [], 'warnings': [],
                     'packing': [], 'guides': [], 'budget': {'unknown': []},
                     'review': {'summary': 'ok', 'issues': []}}}
    hotel = dict(base, hotel={'id': 'h', 'name': '酒店', 'price': 480}, selected_room=None)
    assert '未记录' in report.markdown(hotel)
    transport = dict(base, hotel=None, selected_transport={'id': 'g', 'name': 'G1',
                                                           'departure': D1 + ' 06:00', 'arrival': D1 + ' 10:00'})
    assert '未记录' in report.markdown(transport)
    # 有来源时仍按原样展示
    with_source = dict(base, hotel=None, selected_transport={'id': 'g', 'name': 'G1', 'departure': D1 + ' 06:00',
                                                             'arrival': D1 + ' 10:00',
                                                             'source': SRC})
    text = report.markdown(with_source)
    assert '途牛' in text and D1 in text


def test_s3_policy_cache_invalidates_on_other_choice_changes():
    """S3：换酒店/换末站/改偏好后，不能继续复用旧准备时间。"""
    w = workspace(days=2, back=D2 + ' 16:00')
    w['time_policy'] = {'return': {D2: {'minutes': 70, 'transport_id': 'b',
                                        'identity': schedule.policy_identity(w, D2, 'return')}}}
    assert schedule.return_preparation_minutes(w, D2) == 70
    # 换成更远的酒店：同一班次也必须失效
    w['hotel'] = {'id': 'h2', 'kind': 'hotel', 'name': '更远酒店', 'location': '120.60,36.30'}
    assert schedule.return_preparation_minutes(w, D2) != 70
    assert schedule.return_preparation_minutes(w, D2) == time_policy.FALLBACK_PREPARATION_MINUTES
    # 改交通偏好也要失效
    w2 = workspace(days=2, back=D2 + ' 16:00')
    w2['time_policy'] = {'return': {D2: {'minutes': 70, 'transport_id': 'b',
                                         'identity': schedule.policy_identity(w2, D2, 'return')}}}
    w2['requirements']['transport_mode'] = 'driving'
    assert schedule.return_preparation_minutes(w2, D2) != 70
    # 改末站也要失效
    w3 = workspace(days=2, back=D2 + ' 16:00')
    w3['time_policy'] = {'return': {D2: {'minutes': 70, 'transport_id': 'b',
                                         'identity': schedule.policy_identity(w3, D2, 'return')}}}
    w3['selected_spots'] = ['s2', 's1']
    assert schedule.return_preparation_minutes(w3, D2) != 70
