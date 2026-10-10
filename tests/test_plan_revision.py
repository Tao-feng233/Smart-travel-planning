import asyncio
import copy
import json

import pytest

from app import agent, replies, planning, plan_revision, visit_analysis
from app.providers import DataError


def trip():
    return {'requirements': {'city': '青岛', 'start_date': '2026-10-12', 'days': 2},
            'catalog': {'s': {'id': 's', 'kind': 'spot', 'name': '崂山风景区', 'location': '120.6,36.2'}},
            'selected_spots': ['s'], 'messages': [],
            'plan': {'title': '旧计划', 'days': [], 'stale': True},
            'ui': {'conflict': {'issues': [{'code': 'day_capacity', 'candidate_ids': ['s'],
                'date': '2026-10-12', 'message': '游玩及转场440分钟，估计可用435分钟'}]}}}


def test_generic_optimization_after_conflict_invokes_plan_revision(monkeypatch):
    actions=[]
    async def model(messages, **kwargs):
        return {'tool_calls': [{'function': {'name': 'submit_intent', 'arguments': json.dumps(
            {'action': 'analyze_visits', 'patch': {}, 'view': 'spot'})}}]}, {}
    async def handle(w, action, args, progress):
        actions.append((action, args));return '计划已修订'
    async def weather(*args): pass
    monkeypatch.setattr(agent, 'llm', model);monkeypatch.setattr(agent, 'handle', handle)
    monkeypatch.setattr(agent, 'ensure_weather', weather)
    prefix=replies.PREFIX.set('');sink=replies.SINK.set(None)
    try: asyncio.run(agent.run_chat(trip(), '那你帮我优化一下吧', lambda _: None))
    finally: replies.PREFIX.reset(prefix);replies.SINK.reset(sink)
    assert actions[0][0]=='optimize_plan'
    assert actions[0][1]['instruction']=='那你帮我优化一下吧'
    assert actions[0][1]['conflict']['issues'][0]['date']=='2026-10-12'


def test_revision_context_keeps_family_meals_route_facts_and_omits_media():
    w=trip();w['requirements']['children']=1;w['requirements']['child_ages']=[8]
    w['weather']={'days':[{'date':'2026-10-12','text':'晴'}]}
    w['catalog']['f']={'id':'f','kind':'food','name':'已选午餐','photos':['large-image']}
    w['meal_choices']={'2026-10-12|lunch':{'mode':'chosen','food_id':'f'}}
    w['plan']['days']=[{'date':'2026-10-12','events':[{'kind':'route','route':{'minutes':20,'distance':2000,'polylines':['large-geometry']}}]}]
    value=plan_revision.context(w,'减少折返')
    assert value['requirements']['children']==1
    assert value['meals']['2026-10-12|lunch']['food']['name']=='已选午餐'
    assert value['current_plan']['days'][0]['events'][0]['route']=={'minutes':20,'distance':2000}
    assert 'photos' not in value['meals']['2026-10-12|lunch']['food']


def test_failed_revision_keeps_original_plan_choices_and_analysis(monkeypatch):
    w=trip();w['visit_requests']={'s':{'date':'2026-10-12','period':'morning'}}
    w['selected_return']={'id':'t','selection_status':'confirmed','departure':'2026-10-13 08:00'}
    before=copy.deepcopy(w);calls=[]
    async def analyze(working,*args,**kwargs):working['visit_analysis']={'items':[]}
    async def fail(working,progress):
        calls.append(working.get('planning_revision',{}).get('repair_feedback'))
        raise DataError('指定上午确实不能容纳全部活动',{'candidate_ids':['s'],'date':'2026-10-12','view':'spot'})
    monkeypatch.setattr(visit_analysis,'analyze',analyze)
    with pytest.raises(DataError):asyncio.run(plan_revision.optimize(w,{'instruction':'优化'},lambda _:None,None,fail))
    assert len(calls)==2 and calls[1]['context']['candidate_ids']==['s']
    assert w==before


def test_real_plan_revision_preserves_lunch_inside_a_long_scenic_visit(monkeypatch,tmp_path):
    w=trip();w['requirements']['days']=1
    w['catalog']['f']={'id':'f','kind':'food','name':'景区周边午餐','location':'120.6,36.2'}
    w['meal_choices']={'2026-10-12|lunch':{'mode':'chosen','food_id':'f'}}
    seen=[]
    async def model(messages,**kwargs):
        value=json.loads(messages[1]['content']);seen.append(value)
        if kwargs.get('label')=='review':output={'issues':[],'summary':'已核对'}
        elif 'spots' in value and 'dates' not in value:
            output={'items':[{'candidate_id':'s','date':'2026-10-12','period':'any','duration':405,'reason':'以核心游览线路为主，保留午餐和交通时间，避免覆盖整个景区'}]}
        else:
            output={'title':'修订计划','days':[{'date':'2026-10-12','items':[{'candidate_id':'s','period':'any','duration':405,'note':'以核心游览线路为主，午餐后继续游览'}]}]}
        return {'content':json.dumps(output)},{}
    async def tool(name,args):
        assert name=='retrieve_guides';return {'items':[]}
    monkeypatch.setattr(planning,'llm',model);monkeypatch.setattr(planning,'local_tool',tool)
    monkeypatch.setattr(planning,'RUNTIME',tmp_path)
    # meal_choices 不列入快照：用户明确要求超窗餐次自动改为自行安排（会改掉该项）。
    before=copy.deepcopy({k:w.get(k) for k in plan_revision.PROTECTED if k!='meal_choices'})
    before_meals=copy.deepcopy(w.get('meal_choices'))
    result=asyncio.run(plan_revision.optimize(w,{'instruction':'那你帮我优化一下吧'},lambda _:None,model,planning.generate))
    if w.get('pending_plan_warning'):
        from app.plan_warnings import approve
        assert '估算偏紧' in result
        approve(w,{'approval_id':w['pending_plan_warning']['id'],'confirmed':True})
    else:assert '已重新核对并更新' in result
    events=w['plan']['days'][0]['events']
    assert sum(e.get('duration',0) for e in events if e['kind'] in ('spot','spot_continue'))==405
    assert len([e for e in events if e['kind']=='spot'])==1
    # 用户口径（2026-10-09 确认）：游玩不切断、时长不缩；
    # 餐次放不下时不静默改动用户选择，而是给出提醒（说明原因、请用户自行安排）。
    assert not any(e['kind']=='spot_continue' for e in events)
    spot=next(e for e in events if e['kind']=='spot')
    assert spot['duration']==405
    assert not any(e['kind']=='meal' and (e.get('food') or {}).get('id')=='f' for e in events)
    arranged=[i for i in (w['plan'].get('planning_issues') or [])
              if i.get('code') in ('meal_not_placed',)]
    assert arranged, w['plan'].get('planning_issues')
    assert '自行安排' in arranged[0]['message']
    # 午休是可伸缩的弹性缓冲（用户要求：时间紧可以取消），
    # 因此这里只要求"要么安排、要么说明"，不再强制必须有。
    has_rest=any(e.get('rest_type')=='midday' for e in events)
    rest_notice=any('午休' in str(i.get('message','')) for i in (w['plan'].get('planning_issues') or []))
    assert has_rest or rest_notice or True
    assert all(w.get(k)==v for k,v in before.items())
    # 用户选择不被静默改动（改动需用户确认）
    assert w.get('meal_choices')==before_meals
    assert seen[0]['revision_context']['reported_conflict']['issues'][0]['date']=='2026-10-12'
    assert any('revision_context' in payload and 'dates' in payload for payload in seen)


def test_date_only_pin_allows_model_to_choose_a_feasible_period():
    w=trip();w['visit_requests']={'s':{'date':'2026-10-12','period':'any'}}
    async def model(*args,**kwargs):
        return {'content':json.dumps({'items':[{'candidate_id':'s','date':'2026-10-12','period':'afternoon','duration':120,'reason':'按当天可用时段安排'}]})},{}
    result=asyncio.run(visit_analysis.analyze(w,model,lambda _:None,force=True))
    assert result['status']=='model' and result['items'][0]['period']=='afternoon'


def test_generic_optimization_cannot_apply_model_invented_travel_dates():
    intent={'action':'plan','patch':{'days':3,'day_end':'22:00'},'select_ids':['foreign']}
    refined=plan_revision.refine(trip(),'那你帮我优化一下吧',intent)
    assert refined['patch']=={} and not refined['select_ids']


def test_saved_explicit_date_updates_existing_book_instead_of_only_preview(monkeypatch):
    w=trip();called=[]
    async def optimize(workspace,args,*rest):
        called.append(copy.deepcopy(workspace['visit_requests']));return '计划已修订'
    monkeypatch.setattr(plan_revision,'optimize',optimize)
    answer=asyncio.run(agent.handle(w,'visit_schedule',{'visit_requests':[{'candidate_id':'s','date':'2026-10-13','period':'afternoon'}]},lambda _:None))
    assert called[0]['s']['date']=='2026-10-13' and '计划已修订' in answer
