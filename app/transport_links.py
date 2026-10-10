"""Conservative station/airport-to-hotel links, separate from selected tickets."""
import asyncio
import hashlib
import json
import math
import time
import unicodedata

from .locations import endpoint,hotel_anchor
from . import stay_plan,time_policy
from .providers import DataError


def hotel_for_link(w,direction):
    ticket=w.get('selected_transport' if direction=='outbound' else 'selected_return') or {}
    dt=str(ticket.get('arrival' if direction=='outbound' else 'departure') or '')[:10]
    return stay_plan.anchor(w,dt,morning=direction=='return') if dt else hotel_anchor(w)


def signature(w):
    h=hotel_for_link(w,'outbound') or {}
    data={'version':2,'stays':stay_plan.facts(w),'city':w['requirements'].get('city'),'mode':w['requirements'].get('transport_mode'),
          'hotel':{k:h.get(k) for k in ('id','location','entrance','citycode')},
          'tickets':[{k:(w.get(slot) or {}).get(k) for k in ('id','kind','departure','arrival','arrival_station','departure_station')}
                     for slot in ('selected_transport','selected_return')]}
    return hashlib.sha256(json.dumps(data,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def current(w):
    v=w.get('transport_links')
    return v if v and v.get('signature')==signature(w) and v.get('expires',0)>time.time() else None


def offset(w,direction):
    fallback=90 if direction=='outbound' else 120
    link=(current(w) or {}).get('links',{}).get(direction,{})
    return link.get('required_minutes',fallback) if link.get('status')=='available' else fallback


def name_key(value,kind):
    text=''.join(unicodedata.normalize('NFKC',str(value or '')).split())
    if kind=='airport':return text.replace('国际','').removesuffix('机场')
    for suffix in ('火车站','铁路车站','站'):
        if text.endswith(suffix):return text[:-len(suffix)]
    return text


async def resolve(w,progress,tool,roads,choose):
    existing=current(w)
    if existing:return existing
    hotel=hotel_for_link(w,'outbound');links={}
    async def one(direction,slot,field):
        hotel=hotel_for_link(w,direction)
        ticket=w.get(slot) or {};wanted=ticket.get(field)
        if not hotel or not wanted:return direction,{'status':'unknown','reason':'缺少已核对酒店位置或班次站点名称'}
        kind='airport' if ticket.get('kind')=='flight' else 'station'
        try:
            async with asyncio.timeout(10):
                result=await tool('search_transport_places',{'city':w['requirements']['city'],'keywords':wanted,'kind':kind})
                matches=[p for p in result.get('items',[]) if endpoint(p) and p.get('endpoint_scope')=='primary' and name_key(p.get('name'),kind)==name_key(wanted,kind)]
                matches=list({p['id']:p for p in matches}.values())
                if len(matches)!=1:return direction,{'status':'unknown','reason':'未能唯一核对班次对应的车站或机场主地点'}
                station=matches[0];a,b=(station,hotel) if direction=='outbound' else (hotel,station)
                options=await roads(a,b);chosen=choose(options,w['requirements'])
                if not chosen:return direction,{'status':'unknown','reason':'站点至住宿的道路方案尚未核实'}
                route_minutes=chosen.get('minutes')
                if not isinstance(route_minutes,(int,float)) or not math.isfinite(route_minutes) or route_minutes<0:return direction,{'status':'unknown','reason':'道路耗时未提供有效数值'}
                policy=time_policy.arrival_ready(ticket,route_minutes,buffer_minutes=15) if direction=='outbound' else time_policy.return_preparation(ticket,route_minutes,buffer_minutes=15)
                required=math.ceil((policy['minutes']+(15 if direction=='return' else 0))/5)*5
                return direction,{'status':'available','point':station,'hotel':hotel,'preparation':policy,'route':chosen,'required_minutes':required,'kind':kind,
                    'note':'以地图车站/机场主地点核算；具体出入口、航站楼、出站及候车安检仍需核实。'}
        except (DataError,TimeoutError):return direction,{'status':'unknown','reason':'接驳位置或道路查询暂未完成，不代表不可通行'}
    if hotel and any((w.get(slot) or {}).get(field) for slot,field in [('selected_transport','arrival_station'),('selected_return','departure_station')]):progress('正在核对班次站点与酒店之间的接驳路线')
    pairs=await asyncio.gather(one('outbound','selected_transport','arrival_station'),one('return','selected_return','departure_station'))
    links=dict(pairs)
    value={'signature':signature(w),'links':links,'expires':time.time()+(900 if any(v['status']=='available' for v in links.values()) else 60)}
    w['transport_links']=value
    return value


def events(w,direction,moment):
    """Return timed links within a calendar day; cross-midnight stays explicit."""
    link=(current(w) or {}).get('links',{}).get(direction,{})
    if link.get('status')!='available':return []
    h=hotel_for_link(w,direction);route=link['route'];allocation=math.ceil((route['minutes']+15)/5)*5
    clock=lambda n:f'{int(n)//60:02d}:{int(n)%60:02d}'
    if direction=='outbound':
        begin=moment;start=begin+30;finish=start+allocation
        if finish>=1439:return []
        return [{'kind':'arrival','candidate_id':h['id'],'name':'抵达后出站，准备前往'+h['name'],'start':clock(begin),'end':clock(start),'note':'出站暂预留30分钟，具体出口及行李耗时待核实。'},
                {'kind':'route','route_scope':'arrival_transfer','candidate_id':h['id'],'name':'从'+link['point']['name']+'前往'+h['name'],'start':clock(start),'end':clock(finish),'route':route,'options':[route],'buffer':allocation-route['minutes'],'note':link['note']}]
    if moment<offset(w,'return'):return []
    begin=max(0,moment-offset(w,'return'));start=begin+15;finish=start+allocation
    if finish>=moment:return []
    # 这里只是"回到住宿取寄存行李、然后出发去车站"，不是退房本身——
    # 退房通常在当天 12:00 前完成（时间轴上单独有一行）。原先把它命名为
    # "退房与出发准备"，会让用户以为要到 16:24 才退房。
    return [{'kind':'arrival','candidate_id':h['id'],'name':'返回住宿取行李并出发','start':clock(begin),'end':clock(start),'note':'多数酒店退房时间为 12:00 前；此处为返回住宿取寄存行李并出发，'
           '具体寄存与取件条件待核实。'},
            {'kind':'route','route_scope':'return_transfer','name':'从'+h['name']+'前往'+link['point']['name'],'start':clock(start),'end':clock(finish),'route':route,'options':[route],'buffer':allocation-route['minutes'],'note':link['note']},
            {'kind':'transfer_plan','transfer_scope':'waiting','name':'候车或值机、安检准备','start':clock(finish),'end':clock(moment),'note':'具体出入口、航站楼与安检等待时间仍需确认。'}]
