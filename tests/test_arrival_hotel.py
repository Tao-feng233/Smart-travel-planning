import asyncio
import copy
import json

import pytest

from app import agent, planning


def trip():
    source={'name':'合成来源','queried_at':'2026-10-09'}
    hotel={'id':'h','kind':'hotel','name':'已选酒店','location':'120.31,36.06','city':'青岛市','price':278,
           'stale':True,'location_status':'verified','source':source,
           'query_conditions':{'cityName':'青岛','checkIn':'2026-10-12','checkOut':'2026-10-13','adultNum':1}}
    spot={'id':'s','kind':'spot','name':'游览地点','location':'120.32,36.06','source':source}
    food={'id':'f','kind':'food','name':'已选早餐店','location':'120.311,36.061','source':source}
    return {'requirements':{'city':'青岛','origin':'郑州','start_date':'2026-10-12','days':1,'adults':1},
            'catalog':{'h':hotel,'s':spot,'f':food},'hotel':copy.deepcopy(hotel),'selected_spots':['s'],
            'selected_transport':{'id':'t','name':'G1834','departure':'2026-10-11 18:40','arrival':'2026-10-11 22:26','arrival_station':'青岛北','source':source},
            'meal_choices':{'2026-10-12|breakfast':{'mode':'chosen','food_id':'f'}},'messages':[]}


def mocks(monkeypatch,tmp_path):
    seen=[]
    async def model(*args,**kwargs):
        value={'issues':[],'summary':'待核实费用'} if kwargs.get('label')=='review' else {
            'days':[{'date':'2026-10-12','items':[{'candidate_id':'s','duration':60}]}]}
        return {'content':json.dumps(value)},{}
    async def tool(name,args):return {'items':[]}
    async def routes(a,b):
        seen.append((a['id'],b['id']))
        return [{'mode':'walking','available':True,'status':'available','minutes':5,'source':{'queried_at':'2026-10-09'}}]
    monkeypatch.setattr(planning,'llm',model);monkeypatch.setattr(planning,'local_tool',tool)
    monkeypatch.setattr(planning,'route_options',routes);monkeypatch.setattr(planning,'RUNTIME',tmp_path)
    return seen


def test_quote_stale_hotel_keeps_breakfast_origin_and_arrival_hotel(monkeypatch,tmp_path):
    w=trip();seen=mocks(monkeypatch,tmp_path)
    plan=asyncio.run(planning.generate(w,lambda _:None))
    assert ('h','f') in seen
    arrival=next(e for d in plan['days'] if d['date']=='2026-10-11' for e in d['events'] if e['kind']=='arrival')
    assert '已选酒店' in arrival['name']
    assert any('2026-10-11' in text and '入住' in text for text in plan['warnings'])
    assert plan['budget']['hotel_reference'] is None
    assert w['hotel']['id']=='h' and w['meal_choices']['2026-10-12|breakfast']['food_id']=='f'


def test_missing_hotel_coordinates_identify_hotel_and_meal(monkeypatch,tmp_path):
    w=trip();w['hotel'].pop('location');mocks(monkeypatch,tmp_path)
    with pytest.raises(planning.DataError) as error:asyncio.run(planning.generate(w,lambda _:None))
    assert error.value.context['view']=='hotel'
    assert {'h','f'}<=set(error.value.context['candidate_ids'])
    assert '已选酒店' in str(error.value) and '2026-10-12' in str(error.value)
    from app.diagnostics import from_error
    issue=from_error(w,error.value.context,str(error.value))['issues'][0]
    assert issue['view']=='hotel' and issue['meal_period']=='breakfast'
    assert issue['candidate_ids']==['h','f']


def test_adding_default_zero_children_does_not_expire_existing_quotes():
    w=trip();w['hotel'].pop('stale');w['catalog']['h'].pop('stale')
    agent.update_requirements(w,{'children':0})
    assert not w['hotel'].get('stale') and not w['catalog']['h'].get('stale')


def test_changed_dates_expire_quotes_but_not_hotel_position():
    from app.locations import hotel_anchor,quote_stale
    w=trip();agent.update_requirements(w,{'start_date':'2026-10-20'})
    assert quote_stale(w['hotel']) and w['selected_room'] is None
    assert hotel_anchor(w)['id']=='h'
    assert w['catalog']['h']['stale']


def test_hotel_from_other_city_is_not_reused_as_route_origin():
    from app.locations import hotel_anchor
    w=trip();w['hotel']['query_conditions']['cityName']='杭州'
    assert hotel_anchor(w) is None


def test_daytime_arrival_visits_hotel_before_selected_lunch(monkeypatch,tmp_path):
    w=trip();w['selected_transport'].update(departure='2026-10-12 06:00',arrival='2026-10-12 10:00')
    w['meal_choices']={'2026-10-12|lunch':{'mode':'chosen','food_id':'f'}}
    seen=mocks(monkeypatch,tmp_path)
    plan=asyncio.run(planning.generate(w,lambda _:None))
    events=next(d['events'] for d in plan['days'] if d['date']=='2026-10-12')
    assert next(e for e in events if e['kind']=='arrival')['candidate_id']=='h'
    assert next(i for i,e in enumerate(events) if e['kind']=='arrival')<next(i for i,e in enumerate(events) if e.get('poi') or e.get('food'))
    assert ('h','s') in seen or ('h','f') in seen
    assert any(e.get('food',{}).get('id')=='f' for e in events)
