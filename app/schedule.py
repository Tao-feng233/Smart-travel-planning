"""Provisional timeline, meal windows and conservative transport conflicts.

Estimates are labelled; only the generated plan contains queried road timings.
"""
from datetime import date,datetime,timedelta
from . import visits
from .journey import coordinate_distance
from . import time_policy

PERIODS={'breakfast':('早餐',480,45),'lunch':('午餐',720,75),'dinner':('晚餐',1020,60)}
MEAL_WINDOWS={'breakfast':(450,600),'lunch':(720,900),'dinner':(1020,1260)}
MIN_VISIT_MINUTES=30   # 与规划阶段"不足30分钟就跳过并说明"一致
REST_BETWEEN_MINUTES=20  # 与规划阶段两处参观之间的"休息与机动时间"一致
TRANSFER_DAY_MINUTES=60  # 一天内往返住宿与景点间通行的保守估计（含规划缓冲）

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
 if arrival and dt<arrival.date().isoformat():return 1440,0
 if back and dt>back.date().isoformat():return 1440,0
 start=arrival_start_minutes(w,dt)
 cutoff=return_cutoff_minutes(w,dt)
 end=max(0,cutoff) if cutoff is not None else 1440
 return start,end

def policy_identity(w,dt,direction):
    """时间口径的缓存身份：只比班次 ID 会在换酒店/换末站/改顺序后继续用旧值。

    复核报告 S3：把方向、日期、班次时刻、起终点与交通偏好都算进来；
    任何一项变化都视为缓存失效，重新按兜底口径计算。
    """
    selected=(w.get('selected_transport') if direction=='arrival' else w.get('selected_return')) or {}
    hotel=w.get('hotel') or {}
    stops=[(w.get('catalog') or {}).get(cid) or {} for cid in (w.get('selected_spots') or [])]
    last_stop=str((stops[-1] if stops else {}).get('id') or '')
    requirements=w.get('requirements') or {}
    return {'direction':direction,'date':dt,'transport_id':selected.get('id'),
            'departure':selected.get('departure'),'arrival':selected.get('arrival'),
            'station':selected.get('arrival_station') if direction=='arrival' else selected.get('departure_station'),
            'hotel_id':hotel.get('id'),'hotel_location':hotel.get('location'),
            'last_stop':last_stop,'transport_mode':requirements.get('transport_mode'),
            'pace':requirements.get('pace'),'day_start':requirements.get('day_start'),
            'day_end':requirements.get('day_end')}

def policy_matches(w,dt,direction,entry):
    """缓存条目是否仍适用于当前工作区状态。"""
    if not isinstance(entry,dict) or not isinstance(entry.get('minutes'),int):return False
    identity=policy_identity(w,dt,direction)
    if entry.get('identity') is not None:return entry.get('identity')==identity
    # 兼容没有身份字段的旧条目：至少班次 ID 要一致。
    return entry.get('transport_id')==identity.get('transport_id')

def arrival_ready_minutes(w,dt):
 """抵达日需要的准备分钟数：统一由 time_policy 计算，缺路线依据时标明待核实。"""
 solution=w.get('time_policy') or {}
 entry=(solution.get('arrival') or {}).get(dt)
 if policy_matches(w,dt,'arrival',entry):
  return entry['minutes']
 return time_policy.arrival_ready(w.get('selected_transport'),None)['minutes']

def return_preparation_minutes(w,dt):
 """返程日需要提前的分钟数：统一由 time_policy 计算；相关选择一变就不能复用旧值。"""
 solution=w.get('time_policy') or {}
 entry=(solution.get('return') or {}).get(dt)
 if policy_matches(w,dt,'return',entry):
  return entry['minutes']
 return time_policy.return_preparation(w.get('selected_return'),None)['minutes']

def arrival_start_minutes(w,dt):
 """抵达日最早可开始活动的分钟数：与 windows/容量共用同一份 time_policy 结果。"""
 arrival=transport_time(w.get('selected_transport'),'arrival')
 if not arrival or dt!=arrival.date().isoformat():return 0
 return arrival.hour*60+arrival.minute+arrival_ready_minutes(w,dt)

def return_cutoff_minutes(w,dt):
 """返程日最后一项活动必须结束的分钟数；不是返程日返回 None。"""
 back_source=w.get('selected_return')
 back=transport_time(back_source,'departure')
 if not back or dt!=back.date().isoformat():return None
 depart=back.hour*60+back.minute
 preparation=(w.get('time_policy') or {}).get('return',{}).get(dt)
 # 只复用与当前班次一致的口径；班次被换掉后必须重新计算，不能用旧值。
 if isinstance(preparation,dict) and isinstance(preparation.get('minutes'),int) and preparation.get('transport_id')==(back_source or {}).get('id'):
  return time_policy.return_cutoff(depart,preparation)
 return depart-return_preparation_minutes(w,dt)

def day_end(w,dt):
 pins=w.get('visit_requests',{});cat=w.get('catalog',{})
 evening=any((pins.get(cid) or cat.get(cid,{}).get('visit_suggestion') or {}).get('date')==dt and (pins.get(cid) or cat.get(cid,{}).get('visit_suggestion') or {}).get('period')=='evening' for cid in w.get('selected_spots',[]))
 return max(minutes(w['requirements'].get('day_end','18:30')),22*60 if evening else 0)

def day_limit(w,dt):
 """当天最后一次活动允许结束的分钟数：每日结束时刻与返程截止时刻取更早者。

 餐次窗口与容量判断都必须用它，否则会出现"餐次窗口说可以、容量说不行"，
 或反过来把返程日的晚餐排到接驳准备之后。
 """
 limit=day_end(w,dt)
 cutoff=return_cutoff_minutes(w,dt)
 return limit if cutoff is None else min(limit,cutoff)

def meal_window(w,dt,period):
 low,high=windows(w,dt);begin,end=MEAL_WINDOWS[period]
 return max(begin,low),min(end,high,day_limit(w,dt))

def meal_start(w,dt,period,preferred=None):
 begin,end=meal_window(w,dt,period);_,at,duration=PERIODS[period]
 if begin+duration>end:return None
 return max(begin,min(at if preferred is None else preferred,end-duration))

def _binding_summary(w,dt,period,choice):
 """时间轴用的绑定摘要：让用户看到这餐是固定日期还是跟随某景点。"""
 from . import foods
 status=foods.binding_status(w,dt,period)
 return {'binding':status['binding'],'label':status['label'],'method':status.get('method'),
         'spot_id':status.get('spot_id'),'spot_name':status.get('spot_name'),
         'affected':bool(status.get('affected')),'reason':status.get('reason')}


def limit_reason(w,dt):
    """当天可用时间的约束来自哪里：返程接驳准备，还是每日结束时刻。

    用于把"来不及安排"说准：非返程日不应提示"返程准备时刻"。
    """
    limit=day_limit(w,dt);cutoff=return_cutoff_minutes(w,dt)
    if cutoff is not None and cutoff<=limit:
        return '该日是返程日，最后一项活动须在'+clock(cutoff)+'前结束（返程接驳准备）'
    if cutoff is not None:
        return '该日为返程日，须在'+clock(limit)+'前结束（返程接驳准备早于每日结束时刻，按更早者）'
    return '当日须在'+clock(limit)+'前结束（当前没有选定的返程班次，未按返程准备收紧）'

def point(w,cid):return w.get('catalog',{}).get(cid)

def capacity(w,dt):
 """当天真正能装多少分钟游览：与规划阶段同口径的唯一容量来源。

 口径 = 左闭右开窗口 ∩ 每日结束时刻（含晚间 22:00 预留，返程日取
 time_policy 截止时刻）− 当天可用的餐次时长 − 往返住宿的通行与缓冲。

 餐次与通行是"固定开销"而不是"无限可扣"：短日子（例如中午返程）扣完会
 变成负数，但规划阶段确实还能放下一处短时参观。所以固定开销最多扣到
 留一处 MIN_VISIT_MINUTES 的位置，避免把可排的一天判成零。
 这是估计不是承诺，结果带依据与 status。
 """
 req=w.get('requirements') or {}
 low,high=windows(w,dt);day_start=max(low,minutes(req.get('day_start','09:00')));limit=min(high,day_limit(w,dt))
 base=max(0,limit-day_start)
 # 餐次只在窗口内可用；早餐 45、午餐 75、晚餐 60，与规划阶段一致。
 # 但餐次是可调整建议、景点是用户已选：容量不够时先让餐次让位，
 # 不能让"必须吃午饭"把一天判成零可排，再让景点被静默跳过。
 usable_meals={}
 remaining=base
 for period in ('breakfast','lunch','dinner'):
  low_m,high_m=meal_window(w,dt,period)
  duration=PERIODS[period][2]
  if low_m+duration>high_m:continue
  if remaining-duration<MIN_VISIT_MINUTES:continue
  usable_meals[period]=duration;remaining-=duration
 meals_minutes=sum(usable_meals.values())
 # 往返住宿与景点之间的通行按每天 TRANSFER_DAY_MINUTES 估计（含规划缓冲），
 # 而不是把窗口上界当成可排时间。这是估计不是承诺：实际用时由生成阶段查询。
 with_stay=bool((w.get('hotel') or {}).get('location'))
 transfer_minutes=min(TRANSFER_DAY_MINUTES if with_stay else 0,max(0,base-meals_minutes-MIN_VISIT_MINUTES))
 overhead=meals_minutes+transfer_minutes
 available=max(MIN_VISIT_MINUTES,base-overhead) if base>=MIN_VISIT_MINUTES else max(0,base-overhead)
 return {'date':dt,'window':[low,high],'start':day_start,'limit':limit,'base_minutes':base,
         'meals_minutes':meals_minutes,'transfer_minutes':transfer_minutes,'rest_minutes':0,
         'available_minutes':available,
         'basis':'窗口∩每日结束时刻'+str(base)+'分钟 − 餐次'+str(meals_minutes)+'分钟 − 往返住宿估计'+str(transfer_minutes)+'分钟'
                 +('（不足一处最短参观，按最短参观时长计）' if base-overhead<MIN_VISIT_MINUTES else ''),
         'meals':usable_meals,'status':'estimated'}

def provisional(w):
 ds=visits.dates(w);cat=w.get('catalog',{});pins=w.get('visit_requests',{});hotel=w.get('hotel');selected=[cat[i] for i in w.get('selected_spots',[]) if i in cat]
 if not ds:return []
 buckets={dt:[] for dt in ds};free=[]
 for p in selected:
  pin=pins.get(p['id'],{})
  if pin.get('date') in buckets:buckets[pin['date']].append(p)
  else:free.append(p)
 usable=[dt for dt in ds if windows(w,dt)[1]-max(windows(w,dt)[0],minutes(w['requirements'].get('day_start','09:00')))>=30]
 for index,p in enumerate(free):
  suggested=(p.get('visit_suggestion') or {}).get('date')
  dt=suggested if suggested in usable else min(usable or ds,key=lambda d:(len(buckets[d]),d))
  buckets[dt].append(p)
 rows=[];order={cid:i for i,cid in enumerate(w.get('visit_order',[]))}
 for dt,places in buckets.items():
  floor,end=windows(w,dt);t=max(minutes(w['requirements'].get('day_start','09:00')),floor);last=hotel;arranged=[]
  # Respect explicit periods and orders; within flexible groups use nearest
  # coordinates. Straight distance is never displayed as road travel time.
  while places:
   def rank(p):
    period=pins.get(p['id'],{}).get('period') or (p.get('visit_suggestion') or {}).get('period','any')
    return ({'morning':0,'any':1,'afternoon':2,'evening':3}.get(period,1),order.get(p['id'],9999),coordinate_distance(last,p) if last and last.get('location') and p.get('location') else 0)
   p=min(places,key=rank);places.remove(p);period=pins.get(p['id'],{}).get('period') or (p.get('visit_suggestion') or {}).get('period','any')
   t=max(t,{'afternoon':13*60,'evening':18*60}.get(period,0))
   if t<12*60 and t+90>12*60:t=13*60+15
   if 12*60<=t<13*60+15:t=13*60+15
   if t>=17*60+30 and t<19*60 and period!='evening':t=19*60
   arranged.append({'key':dt+'|'+p['id'],'date':dt,'time':clock(t),'end':clock(t+90),'kind':'spot','candidate_id':p['id'],'name':p['name'],'period':period,'confirmed':bool(pins.get(p['id'])),'estimated':True})
   t+=110;last=p
  rows+=arranged
  for period,(label,at,duration) in PERIODS.items():
   # 餐次时刻只由 meal_start（同一份窗口与每日截止口径）决定，
   # 不能再用"当前时间与固定基准取大"的另一套摆放规则。
   at=meal_start(w,dt,period)
   if at is None:continue
   choice=(w.get('meal_choices') or {}).get(dt+'|'+period,{})
   if not choice and (w.get('meal_mode')=='self' or w.get('dining_reviewed')):choice={'mode':'self'}
   p=point(w,choice.get('food_id'))
   before=[x for x in arranged if minutes(x['time'])<=at]
   anchor=(point(w,before[-1]['candidate_id']) if before else hotel) or (point(w,arranged[0]['candidate_id']) if arranged else None)
   if period=='breakfast' and hotel:anchor=hotel
   rows.append({'key':dt+'|'+period,'date':dt,'time':clock(at),'end':clock(at+duration),'kind':'meal','period':period,'name':label+' · '+(p['name'] if p else '自行安排' if choice.get('mode')=='self' else '待选择'),'candidate_id':p['id'] if p else None,'anchor_id':anchor['id'] if anchor else None,'confirmed':bool(choice),'estimated':True,
                'binding':_binding_summary(w,dt,period,choice),
                'basis':'按餐次窗口与当日结束时刻取整后的预计开餐时间'})
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
 return {'entries':rows,'meal_slots':slots,'provisional':not bool(plan and not plan.get('stale')),'conflicts':conflicts(w)}

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
