import asyncio,json
from datetime import date,timedelta
from app import agent,planning,providers
from app.providers import DataError
import pytest,httpx

def test_completion_only_asks_missing_origin():
 w={'requirements':{'city':'青岛','start_date':'2026-10-12','days':3,'adults':1},'catalog':{},'selected_spots':[],'hotel':{'id':'h1'},'selected_room':{'id':'r1'},
 'stay_hotels':{'2026-10-12':'h1','2026-10-13':'h1','2026-10-14':'h1'}}
 answer=asyncio.run(agent.handle(w,'complete_hotel',{},lambda _:None))
 assert '出发城市' in answer and '日期' not in answer and '天数' not in answer

def test_weather_automatically_covers_supplied_dates_and_flags_far_forecast(monkeypatch):
 calls=[];dt=(date.today()+timedelta(days=7)).isoformat()
 async def tool(name,args):calls.append(name);return {'days':[{'date':dt,'text':'晴','low':16,'high':24}],'source':{'name':'测试'}}
 monkeypatch.setattr(agent,'local_tool',tool)
 w={'requirements':{'city':'青岛','start_date':dt,'days':2},'catalog':{'s1':{'id':'s1','kind':'spot','location':'120,36'}},'selected_spots':['s1']}
 asyncio.run(agent.ensure_weather(w,lambda _:None));asyncio.run(agent.ensure_weather(w,lambda _:None))
 assert calls==['daily_weather'] and '不确定' in w['weather_note']
 assert w['weather']['days'][0]['date']==dt

def test_native_stream_parses_deltas_without_exposing_reasoning(monkeypatch):
 chunks=[];client=httpx.AsyncClient
 monkeypatch.setattr(providers,'setting',lambda name,default='':{'LLM_BASE_URL':'https://model.test','LLM_API_KEY':'fake-only','LLM_MODEL':'test-model'}.get(name,default))
 def handler(request):
  body=json.loads(request.content);assert body['stream'] is True
  frames=[{'choices':[{'delta':{'reasoning_content':'PRIVATE_REASONING'}}]}, {'choices':[{'delta':{'content':'欢迎'}}]}, {'choices':[{'delta':{'content':'使用'}}]}, {'choices':[],'usage':{'completion_tokens':2}}]
  return httpx.Response(200,text=''.join('data: '+json.dumps(f)+'\n\n' for f in frames)+'data: [DONE]\n\n')
 monkeypatch.setattr(providers.httpx,'AsyncClient',lambda **kw:client(transport=httpx.MockTransport(handler)))
 text,usage=asyncio.run(providers.llm_stream([{'role':'user','content':'测试'}],chunks.append))
 assert chunks==['欢迎','使用'] and text=='欢迎使用' and 'PRIVATE' not in text and usage['completion_tokens']==2

def test_rounded_route_and_late_arrival_are_separate_explicit_events(monkeypatch,tmp_path):
 monkeypatch.setattr(planning,'RUNTIME',tmp_path);day='2026-10-12'
 async def llm(messages,**kw):
  if '审核助手' in messages[0]['content']:return {'content':'{"issues":[],"summary":"请核对班次"}'},{}
  return {'content':json.dumps({'days':[{'date':day,'items':[]},{'date':'2026-10-13','items':[{'candidate_id':'s1','duration':90,'note':'建议沿栈桥步行，先看回澜阁，再欣赏海岸景色。'}]},{'date':'2026-10-14','items':[]}],'packing':[],'todos':[]})},{}
 async def tool(name,args):return {'items':[]}
 async def route(a,b):return [{'mode':'driving','available':True,'minutes':13,'distance':4800,'source':{'name':'测试','queried_at':day}}]
 monkeypatch.setattr(planning,'llm',llm);monkeypatch.setattr(planning,'local_tool',tool);monkeypatch.setattr(planning,'route_options',route)
 w={'requirements':{'city':'青岛','start_date':day,'days':3,'adults':1,'pace':'relaxed'},'catalog':{'s1':{'id':'s1','kind':'spot','name':'栈桥','location':'120,36'}},'selected_spots':['s1'],'hotel':{'id':'h1','name':'酒店','location':'120.1,36.1'},'selected_room':{'name':'大床房','price':289},'selected_transport':{'name':'G1834','departure':day+' 18:40','arrival':day+' 22:26'},'selected_return':{'name':'G2097','departure':'2026-10-14 11:22','arrival':'2026-10-14 15:09'}}
 p=asyncio.run(planning.generate(w,lambda _:None))
 assert p['summary']=='' and [e['kind'] for e in p['days'][0]['events']]==['transport','arrival']
 route_event=next(e for e in p['days'][1]['events'] if e['kind']=='route');assert route_event['start']=='09:00' and route_event['end']=='09:30' and route_event['route']['minutes']==13
 spot=next(e for e in p['days'][1]['events'] if e['kind']=='spot');assert spot['start']=='09:30' and spot['end']=='11:00' and '回澜阁' in spot['note']
 assert not any('超出每日结束' in issue or '重叠' in issue for issue in p['warnings'])
 assert any('身份证件' in s for s in p['packing'])
 assert p['budget']['selected_room_quote']==289 and p['budget']['hotel_reference'] is None
