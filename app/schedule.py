"""Provisional timeline, meal windows and conservative transport conflicts.

Estimates are labelled; only the generated plan contains queried road timings.
"""
from datetime import date,datetime,timedelta
from . import visits
from .journey import coordinate_distance

PERIODS={'breakfast':('早餐',480,45),'lunch':('午餐',720,75),'dinner':('晚餐',1020,60)}
MEAL_WINDOWS={'breakfast':(450,600),'lunch':(720,900),'dinner':(1020,1260)}

def minutes(s,default=0):
 try:
  h,m=map(int,s[-5:].split(':'));return h*60+m
 except (ValueError,TypeError,AttributeError):return default

def clock(n):return f'{max(0,min(1439,int(n)))//60:02d}:{max(0,min(1439,int(n)))%60:02d}'

def transport_time(p,key):
 try:return datetime.fromisoformat((p or {}).get(key,'').replace(' ','T'))
 except (ValueError,TypeError):return None

def windows(w,dt):
 arrival=transport_time(w.get('selected_transport'),'arrival');back=transport_time(w.get('selected_return'),'departure')
 start=0;end=1440
 if arrival:
  if dt<arrival.date().isoformat():return 1440,0
  if dt==arrival.date().isoformat():start=arrival.hour*60+arrival.minute+90
 if back:
  if dt>back.date().isoformat():return 1440,0
  if dt==back.date().isoformat():end=max(0,back.hour*60+back.minute-120)
 return start,end

def day_end(w,dt):
 pins=w.get('visit_requests',{});cat=w.get('catalog',{})
 evening=any((pins.get(cid) or cat.get(cid,{}).get('visit_suggestion') or {}).get('date')==dt and (pins.get(cid) or cat.get(cid,{}).get('visit_suggestion') or {}).get('period')=='evening' for cid in w.get('selected_spots',[]))
 return max(minutes(w['requirements'].get('day_end','18:30')),22*60 if evening else 0)

def meal_window(w,dt,period):
 low,high=windows(w,dt);begin,end=MEAL_WINDOWS[period]
 return max(begin,low),min(end,high,day_end(w,dt))

def meal_start(w,dt,period,preferred=None):
 begin,end=meal_window(w,dt,period);_,at,duration=PERIODS[period]
 if begin+duration>end:return None
 return max(begin,min(at if preferred is None else preferred,end-duration))

def point(w,cid):return w.get('catalog',{}).get(cid)

def provisional(w):
 from . import visit_analysis
 ds=visits.dates(w);cat=w.get('catalog',{});pins=w.get('visit_requests',{});hotel=w.get('hotel');selected=[cat[i] for i in w.get('selected_spots',[]) if i in cat]
 if not ds:return []
 estimates={x['candidate_id']:x for x in visit_analysis.preview(w)}
 buckets={dt:[] for dt in ds}
 for p in selected:
  if estimates.get(p['id'],{}).get('date') in buckets:buckets[estimates[p['id']]['date']].append(p)
 rows=[];order={cid:i for i,cid in enumerate(w.get('visit_order',[]))}
 for dt,places in buckets.items():
  floor,end=windows(w,dt);t=max(minutes(w['requirements'].get('day_start','09:00')),floor);last=hotel;arranged=[]
  # Respect explicit periods and orders; within flexible groups use nearest
  # coordinates. Straight distance is never displayed as road travel time.
  while places:
   def rank(p):
    period=estimates[p['id']].get('period','any')
    return ({'morning':0,'any':1,'afternoon':2,'evening':3}.get(period,1),order.get(p['id'],9999),coordinate_distance(last,p) if last and last.get('location') and p.get('location') else 0)
   p=min(places,key=rank);places.remove(p);estimate=estimates[p['id']];period=estimate.get('period','any');duration=estimate['duration']
   t=max(t,{'afternoon':13*60,'evening':18*60}.get(period,0))
   # A long visit can span lunch with a labelled meal pause. Do not move a
   # whole half-day visit into the afternoon just because it crosses noon.
   for _,at,length in PERIODS.values():
    if at<=t<at+length:t=at+length
   finish=t+duration
   for _,at,length in PERIODS.values():
    if t<at<finish:finish+=length
   pin_period=pins.get(p['id'],{}).get('period')
   over=finish>min(end,day_end(w,dt)) or pin_period in ('morning','afternoon') and finish>{'morning':720,'afternoon':1080}[pin_period]
   arranged.append({'key':dt+'|'+p['id'],'date':dt,'time':clock(t),'end':clock(finish),'duration':duration,'kind':'spot','candidate_id':p['id'],'name':p['name'],'period':period,'confirmed':bool(pins.get(p['id'])),'estimated':True,'estimate_basis':estimate['basis'],'reason':estimate['reason'],'includes_meal_break':finish-t>duration,'over_capacity':over})
   t=finish+20;last=p
  rows+=arranged
  for period,(label,at,duration) in PERIODS.items():
   at=meal_start(w,dt,period)
   if at is None:continue
   choice=(w.get('meal_choices') or {}).get(dt+'|'+period,{})
   if not choice and (w.get('meal_mode')=='self' or w.get('dining_reviewed')):choice={'mode':'self'}
   p=point(w,choice.get('food_id'))
   before=[x for x in arranged if minutes(x['time'])<=at]
   anchor=(point(w,before[-1]['candidate_id']) if before else hotel) or (point(w,arranged[0]['candidate_id']) if arranged else None)
   if period=='breakfast' and hotel:anchor=hotel
   rows.append({'key':dt+'|'+period,'date':dt,'time':clock(at),'end':clock(at+duration),'kind':'meal','period':period,'name':label+' · '+(p['name'] if p else '自行安排' if choice.get('mode')=='self' else '待选择'),'candidate_id':p['id'] if p else None,'anchor_id':anchor['id'] if anchor else None,'confirmed':bool(choice),'estimated':True})
  if hotel and end>=22*60 and floor<22*60:rows.append({'key':dt+'|stay','date':dt,'time':'22:00','kind':'hotel','candidate_id':hotel['id'],'name':hotel['name'],'confirmed':True,'estimated':True})
 return rows

def build(w):
 plan=w.get('plan');rows=[]
 if plan and not plan.get('stale'):
  for d in plan.get('days',[]):
   for i,e in enumerate(d.get('events',[])):
    if e.get('kind') not in ('spot','meal','transport','arrival'):continue
    cid=e.get('candidate_id') or (e.get('food') or {}).get('id')
    period=next((k for k,(label,_,_) in PERIODS.items() if e.get('name','').startswith(label)),None) if e.get('kind')=='meal' else None
    rows.append({'key':d['date']+'|'+(period or cid or str(i)),'date':d['date'],'time':e['start'],'end':e['end'],'kind':e['kind'],'candidate_id':cid,'period':period,'name':e.get('name',''),'confirmed':e.get('kind')!='meal' or bool(w.get('meal_choices',{}).get(d['date']+'|'+str(period))),'estimated':False})
 else:rows=provisional(w)
 # Include transport-only dates, outside the sightseeing period.
 for key,kind in [('selected_transport','去程'),('selected_return','返程')]:
  p=w.get(key);dt=transport_time(p,'departure')
  if p and dt and not any(x['kind']=='transport' and x['date']==dt.date().isoformat() and x['time']==dt.strftime('%H:%M') for x in rows):rows.append({'key':key,'date':dt.date().isoformat(),'time':dt.strftime('%H:%M'),'kind':'transport','candidate_id':p.get('id'),'direction':'return' if key=='selected_return' else 'outbound','name':kind+' · '+p.get('name','班次'),'confirmed':p.get('selection_status')=='confirmed','estimated':False})
 rows.sort(key=lambda x:(x['date'],x['time'],x['key']))
 slots=[x for x in rows if x['kind']=='meal']
 from . import visit_analysis
 analysis=visit_analysis.current(w)
 return {'entries':rows,'meal_slots':slots,'provisional':not bool(plan and not plan.get('stale')),'conflicts':conflicts(w),'analysis_status':analysis['status'] if analysis else 'initial','notices':visit_analysis.notices(w,visit_analysis.preview(w))}

def conflicts(w):
 result=[];arrival=transport_time(w.get('selected_transport'),'arrival');back=transport_time(w.get('selected_return'),'departure');pins=w.get('visit_requests',{});ds=visits.dates(w)
 for cid in w.get('selected_spots',[]):
  p=point(w,cid);pin=pins.get(cid,{})
  if not p or not pin.get('date'):continue
  if pin['date'] not in ds:
   result.append({'code':'date_range','level':'error','date':pin['date'],'candidate_ids':[cid],'view':'spot','message':p['name']+'的指定日期已不在当前游玩范围内，请重新选择日期或恢复由助手安排。'})
   continue
  dt=pin['date'];start,end=windows(w,dt);period=pin.get('period','any');low={'morning':9*60,'afternoon':13*60,'evening':18*60}.get(period,9*60);high={'morning':12*60,'afternoon':18*60,'evening':23*60}.get(period,23*60)
  # Minimum supported visit is 30min; catch impossibility, not a merely
  # crowded provisional ordering that could be shortened or rearranged.
  if max(start,low)+30>min(end,high):
   direction='return' if back and dt>=back.date().isoformat() else 'outbound'
   result.append({'code':'fixed_window','level':'error','date':dt,'candidate_ids':[cid],'direction':direction,'view':'spot','message':p['name']+'的指定游玩时段与'+('返程接驳准备' if direction=='return' else '去程到达时间')+'冲突，调整顺序也无法满足当前时段；请修改游玩日期/时段或班次。'})
 if ds and w.get('selected_spots'):
  capacity=sum(max(0,min(windows(w,d)[1],day_end(w,d))-max(windows(w,d)[0],minutes(w['requirements'].get('day_start','09:00')))) for d in ds)
  if capacity<30*len(w['selected_spots']) and not result:
   direction='return' if back and back.date().isoformat()<=ds[-1] else 'outbound'
   result.append({'code':'minimum_capacity','level':'error','date':back.date().isoformat() if direction=='return' else arrival.date().isoformat() if arrival else ds[0],'candidate_ids':list(w['selected_spots']),'direction':direction,'view':'spot','message':'当前交通与每日游玩时段留下的总时间不足，即使每个景点只安排30分钟也无法容纳全部选择；请延长游玩日期、减少景点或调整班次。'})
 if w.get('meal_mode')!='self':
  for key,choice in (w.get('meal_choices') or {}).items():
   parts=key.split('|')
   if len(parts)!=2 or parts[1] not in PERIODS or choice.get('mode')!='chosen':continue
   dt,period=parts;p=point(w,choice.get('food_id'))
   if p and (dt not in ds or meal_start(w,dt,period) is None):
    result.append({'code':'meal_window','level':'error','date':dt,'meal_period':period,'candidate_ids':[p['id']],'direction':'return' if windows(w,dt)[1]<1440 else 'outbound','view':'food','message':dt+' '+PERIODS[period][0]+'（'+p['name']+'）已不适合当前日期或交通时段，请修改餐次、日期或班次。'})
 return result
