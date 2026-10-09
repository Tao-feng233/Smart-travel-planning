import asyncio
import json

from app import schedule,visit_analysis,planning


def trip():
    return {'requirements':{'city':'青岛','start_date':'2026-10-12','days':1},
            'catalog':{'s':{'id':'s','kind':'spot','name':'小鱼山','location':'120.3,36.06'}},'selected_spots':['s'],'tickets':{}}


def test_preview_has_separate_midday_rest_before_afternoon():
    w=trip();w['visit_requests']={'s':{'date':'2026-10-12','period':'afternoon'}}
    rows=schedule.provisional(w)
    rest=next(r for r in rows if r.get('rest_type')=='midday')
    spot=next(r for r in rows if r['kind']=='spot')
    assert rest['time']=='13:15' and rest['end']=='14:15'
    assert spot['time']>=rest['end']


def test_model_rest_reaches_preview_and_time_budget():
    w=trip();w['requirements']['companion_notes']=['带老人，希望宽裕些'];seen=[]
    async def model(messages,**kwargs):
        seen.append(json.loads(messages[1]['content']))
        return {'content':json.dumps({'items':[{'candidate_id':'s','date':'2026-10-12','period':'afternoon','duration':120,'reason':'含观景拍照与慢行'}],
            'day_pacing':[{'date':'2026-10-12','rest_minutes':90,'break_minutes':45,'reason':'午后休息更充分'}]})},{}
    value=asyncio.run(visit_analysis.analyze(w,model,lambda _:None))
    assert value['day_pacing'][0]['rest_minutes']==90
    rows=schedule.provisional(w)
    assert next(r for r in rows if r.get('rest_type')=='midday')['end']=='14:45'
    assert seen[0]['recommendation_context']['party']['companion_notes']==['带老人，希望宽裕些']
    assert visit_analysis.budgets(w)[0]['midday_rest_minutes']==90


def test_final_plan_retains_midday_rest_in_timeline(monkeypatch,tmp_path):
    w=trip()
    async def model(*args,**kwargs):
        return {'content':json.dumps({'issues':[],'summary':'建议'} if kwargs.get('label')=='review' else
            {'days':[{'date':'2026-10-12','items':[{'candidate_id':'s','period':'afternoon','duration':120}]}]})},{}
    async def tool(*args):return {'items':[]}
    monkeypatch.setattr(planning,'llm',model);monkeypatch.setattr(planning,'local_tool',tool);monkeypatch.setattr(planning,'RUNTIME',tmp_path)
    plan=asyncio.run(planning.generate(w,lambda _:None));w['plan']=plan
    events=plan['days'][0]['events'];rest=next(e for e in events if e.get('rest_type')=='midday')
    spot=next(e for e in events if e['kind']=='spot')
    assert spot['start']>=rest['end']
    assert any(r.get('rest_type')=='midday' for r in schedule.build(w)['entries'])


def test_user_can_skip_midday_rest_and_early_return_has_no_rest():
    w=trip();w['requirements']['midday_rest_minutes']=0
    assert not any(r.get('rest_type')=='midday' for r in schedule.provisional(w))
    w['requirements'].pop('midday_rest_minutes');w['selected_return']={'departure':'2026-10-12 12:00'}
    assert not any(r.get('rest_type')=='midday' for r in schedule.provisional(w))
