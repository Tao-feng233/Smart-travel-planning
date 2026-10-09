import asyncio
import copy
import json

import pytest

from app import discovery,planning,schedule,visit_analysis


def trip():
    source={'name':'合成地图来源','queried_at':'2026-10-09'}
    rows=[{'id':'sea','name':'海滨风景区'},
          {'id':'eight','name':'八大关风景区','parent_id':'sea'},
          {'id':'house','name':'花石楼','parent_id':'eight'}]
    return {'requirements':{'city':'青岛','start_date':'2026-10-12','days':2},
            'catalog':{p['id']:{**p,'kind':'spot','location':'120.3,36.06','source':source} for p in rows},
            'selected_spots':['sea','eight'],'messages':[],'tickets':{},
            'spot_search':{'city':'青岛','ids':['sea','eight','house'],'page':1}}


def test_nested_groups_do_not_repeat_parent_as_another_card():
    w=trip();groups=discovery.groups(w)
    cards=[cid for g in groups for cid in ([g['parent_id']] if g['parent_id'] else [])+[i for i in g['ids'] if i!=g['parent_id']]]
    assert len(groups)==1 and cards.count('eight')==1
    assert set(cards)=={'sea','eight','house'}


def test_parent_and_child_selection_have_one_actual_visit():
    w=trip();before=copy.deepcopy(w['selected_spots'])
    spots=[r for r in schedule.provisional(w) if r['kind']=='spot']
    assert [r['candidate_id'] for r in spots]==['eight']
    assert w['selected_spots']==before
    w['selected_spots']=['sea']
    assert [r['candidate_id'] for r in schedule.provisional(w) if r['kind']=='spot']==['sea']


def test_final_plan_covers_parent_without_double_counting(monkeypatch,tmp_path):
    w=trip();seen=[]
    async def model(messages,**kwargs):
        content=json.loads(messages[1]['content']);seen.append(content)
        return {'content':json.dumps({'issues':[],'summary':'建议'} if kwargs.get('label')=='review' else
            {'days':[{'date':'2026-10-12','items':[{'candidate_id':'eight','duration':120}]}]})},{}
    async def tool(*args):return {'items':[]}
    monkeypatch.setattr(planning,'llm',model);monkeypatch.setattr(planning,'local_tool',tool);monkeypatch.setattr(planning,'RUNTIME',tmp_path)
    plan=asyncio.run(planning.generate(w,lambda _:None))
    assert [e['candidate_id'] for d in plan['days'] for e in d['events'] if e['kind']=='spot']==['eight']
    assert plan['parent_coverage']=={'sea':['eight']}
    assert w['selected_spots']==['sea','eight']
    assert seen[0]['parent_coverage']=={'sea':['eight']}


def test_explicit_parent_date_applies_to_child_but_conflicting_dates_are_actionable():
    w=trip();w['visit_requests']={'sea':{'date':'2026-10-13','period':'afternoon'}}
    rows=[r for r in schedule.provisional(w) if r['kind']=='spot']
    assert rows[0]['date']=='2026-10-13' and rows[0]['period']=='afternoon'
    w['visit_requests']['eight']={'date':'2026-10-12','period':'morning'}
    conflicts=schedule.conflicts(w)
    assert any(c['code']=='parent_child_schedule' and set(c['candidate_ids'])=={'sea','eight'} for c in conflicts)


def test_name_association_is_not_used_to_remove_selected_visits():
    w=trip();w['catalog']['eight'].pop('parent_id');w['catalog']['eight']['name']='海滨风景区·八大关'
    assert {p['id'] for p in visit_analysis.selected(w)}=={'sea','eight'}


def test_old_double_counted_plan_is_not_reused_and_cycles_do_not_merge():
    w=trip();w['plan']={'days':[{'date':'2026-10-12','events':[{'kind':'spot','candidate_id':cid,'name':w['catalog'][cid]['name'],'start':'09:00','end':'10:00'} for cid in ('sea','eight')]}]}
    before=copy.deepcopy(w['plan'])
    assert schedule.build(w)['provisional']
    assert [e['candidate_id'] for e in schedule.build(w)['entries'] if e['kind']=='spot']==['eight']
    assert w['plan']==before
    w['catalog']['sea']['parent_id']='eight'
    assert {p['id'] for p in visit_analysis.selected(w)}=={'sea','eight'}
