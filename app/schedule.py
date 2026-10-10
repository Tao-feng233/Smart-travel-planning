"""Provisional timeline, meal windows and conservative transport conflicts.

Estimates are labelled; only the generated plan contains queried road timings.
"""
from datetime import date,datetime,timedelta
from . import visits,stay_plan,foods
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
 from .transport_links import offset
 arrival=transport_time(w.get('selected_transport'),'arrival');back=transport_time(w.get('selected_return'),'departure')
 start=0;end=1440
 if arrival:
  if dt<arrival.date().isoformat():return 1440,0
  if dt==arrival.date().isoformat():start=arrival.hour*60+arrival.minute+offset(w,'outbound')
 if back:
  if dt>back.date().isoformat():return 1440,0
  if dt==back.date().isoformat():end=max(0,back.hour*60+back.minute-offset(w,'return'))
 return start,end

def day_end(w,dt):
 pins=w.get('visit_requests',{});cat=w.get('catalog',{})
 evening=any((pins.get(cid) or cat.get(cid,{}).get('visit_suggestion') or {}).get('date')==dt and (pins.get(cid) or cat.get(cid,{}).get('visit_suggestion') or {}).get('period')=='evening' for cid in w.get('selected_spots',[]))
 from .visit_analysis import current
 analysis=current(w)
 evening=evening or any(x.get('date')==dt and x.get('period')=='evening' for x in (analysis or {}).get('items',[]))
 return max(minutes(w['requirements'].get('day_end','18:30')),22*60 if evening else 0)

def meal_latest_end(w,dt,period):
    """某餐次的窗口上界。

    晚餐是当天最后一件事，吃完才算结束，因此**不该被当天活动结束时刻(day_end)卡住**：
    用户设 day_end=18:30 意思是"18:30 结束游览"，不是"18:30 必须吃完饭"。
    晚餐上界取「活动结束时刻 + 90 分钟」与 21:00 的较大者，再受返程准备时刻限制；
    这样 day_end=18:30 时晚餐可排到 20:00，有晚间活动时也不会被人为压到 21:00 之前。
    早餐/午餐仍在活动时段内，继续受 day_end 约束。
    """
    low,high=windows(w,dt)
    begin,end=MEAL_WINDOWS[period]
    if period!='dinner':return min(end,high,day_end(w,dt))
    return min(end,high,max(day_end(w,dt)+90,21*60))


def meal_window(w,dt,period):
 from . import pacing
 low,high=windows(w,dt);begin,end=MEAL_WINDOWS[period]
 begin=min(begin,pacing.meal_time(w,dt,period))
 return max(begin,low),meal_latest_end(w,dt,period)

def meal_start(w,dt,period,preferred=None,as_late=False):
    """某餐次的开饭时刻。

    as_late：尽量晚开饭（不早于默认时刻、不超出窗口、吃完仍赶得上）。
    返程日用它——例如 11:00 发车时准备时刻是 09:00，早餐就从 08:00 推到 09:00，
    吃完直接上车，而不是吃完再干等一小时。
    """
    from . import pacing
    begin,end=meal_window(w,dt,period);at=pacing.meal_time(w,dt,period);duration=pacing.meal_duration(w,dt,period)
    if begin+duration>end:return None
    want=at if preferred is None else preferred
    latest=end-duration
    if as_late:
        # 窗口内尽量靠后，但不能早于默认时刻（不能把早餐排到很早）
        want=max(want,latest)
    return max(begin,min(want,latest))

def stay_rows(w):
    """住宿与退房行：如实呈现，不编造入住时刻。

    * 每住一晚一行，不带具体时刻，注明"入住时间以酒店确认为准"；
    * 退房行落在该晚住宿的**次日**，标"一般 12:00 前"并注明以酒店确认为准；
      续住同一家时不重复提示。
    """
    rows=[]
    # 以实际分配为准：assignment_view 与 stay_hotels 的键合并（
    # nights() 可能不含用户后来选定的那一晚，不能作为唯一依据）。
    _assigned=dict(stay_plan.assignment_view(w) or {})
    for _d,_cid in (w.get('stay_hotels') or {}).items():
        if _cid:_assigned.setdefault(_d,{'hotel_id':_cid,'source':'explicit'})
        elif _d not in _assigned:_assigned[_d]={'hotel_id':None,'source':'unset'}
    ordered=[(d,v.get('hotel_id')) for d,v in sorted(_assigned.items()) if v.get('hotel_id')]
    for _dt,_cid in ordered:
        h=w.get('catalog',{}).get(_cid) or (w.get('hotel') if (w.get('hotel') or {}).get('id')==_cid else None)
        if not h:continue
        rows.append({'key':_dt+'|stay','date':_dt,'time':'','end':'','kind':'hotel',
            'candidate_id':h.get('id'),'name':'当晚住宿：'+str(h.get('name') or '已选住宿'),
            'confirmed':False,'estimated':True,'stay_date':_dt,
            'note':'入住时间以酒店确认为准；如需确认办理入住或加早，请与酒店核实。',
            'reason':'入住时间以酒店确认为准'})
    for _i,(_dt,_cid) in enumerate(ordered):
        _next=ordered[_i+1][1] if _i+1<len(ordered) else None
        if _next==_cid:continue
        _out=(date.fromisoformat(_dt)+timedelta(days=1)).isoformat()
        rows.append({'key':_out+'|checkout','date':_out,'time':'12:00','end':'12:00','kind':'checkout',
            'candidate_id':_cid,'name':'退房并寄存行李（一般 12:00 前）',
            'confirmed':False,'estimated':True,
            'note':'多数酒店退房时间为 12:00 前，具体以酒店确认为准；换住处当天可先寄存行李再开始游览。',
            'reason':'退房时间以酒店确认为准'})
    return rows


def planned_meals(w,dt):
    """当天时间轴里实际排定的餐次 → {period: 开饭时刻(分钟)}。

    作为规划阶段与预览的唯一口径：provisional 里没有的餐次就不该被正式计划书补排。
    """
    out={}
    for e in provisional(w):
        if e.get('date')!=dt or e.get('kind')!='meal':continue
        period=e.get('period')
        if period:out[period]=minutes(e.get('time'))
    return out


def is_return_day(w,dt):
    """当天是不是返程日：是的话餐次尽量往后排（吃完就上车）。"""
    back=transport_time(w.get('selected_return'),'departure')
    return bool(back and back.date().isoformat()==dt)

def return_bounded(w,dt):
    """当天的时间窗是否真的被返程班次压住。

    只有这种情况才把餐次往后推：例如 11:00 发车、准备时刻 09:00 恰好落进早餐窗口，
    就把早餐推到窗口内最晚（吃完直接上车）。
    普通游玩日没有班次压着，晚餐不该被推到 19:00/20:00；返程之后的日期也不该被推。
    """
    if not is_return_day(w,dt):return False
    # 返程之后的日期窗口是空的，不该被当成"被班次压住"。
    back=transport_time(w.get('selected_return'),'departure')
    if back and dt>back.date().isoformat():return False
    return windows(w,dt)[1]<1440

def last_meal_before_return(w,dt):
    """返程日"最靠近返程"的那一餐：只优化这一餐，其余餐次保持默认时刻。

    用户要求：不是把返程日所有餐次都往后推，而是只把紧挨着返程的那一餐排到
    "吃完就上车"。例如 11:00 发车时早餐贴到 09:00；20:00 发车时只有晚餐贴到 18:00，
    早餐与午餐仍按 08:00 / 12:00。若三顿都吃不上则不返回任何餐次。
    """
    if not return_bounded(w,dt):return None
    from . import pacing
    back=transport_time(w.get('selected_return'),'departure')
    if not back:return None
    departure=back.hour*60+back.minute
    # 候选顺序按一天中的先后：早餐 → 午餐 → 晚餐，取最后一个能安排在发车前的。
    candidates=[]
    for period in ('breakfast','lunch','dinner'):
        duration=pacing.meal_duration(w,dt,period)
        begin,end=meal_window(w,dt,period)
        if begin+duration>end:continue
        latest=end-duration
        if latest+duration<=departure:candidates.append((period,latest))
    return candidates[-1][0] if candidates else None

def meal_too_late(w,dt,period,start,tolerance=5):
    """该餐的开饭时刻是否已超出餐次窗口（默认容差 5 分钟）。

    返回 (是否过多, 超出分钟数, 窗口结束时刻)。
    """
    if start is None:return False,0,None
    end_window=meal_window(w,dt,period)[1]
    over=start-end_window
    return over>=tolerance,over,end_window


def chosen_meal_fit(w,dt,start,duration,period):
    """已选餐厅时，给出"把这一餐放回窗口内"所需的最长游玩时长。

    返回 (可用的游玩时长, 是否需要缩减)。窗口已过则返回 (duration, False)，
    交由上层提醒用户自行安排。
    """
    from . import pacing
    end_window=meal_window(w,dt,period)[1]
    need=pacing.meal_duration(w,dt,period)
    latest_start=end_window-need
    if start>=latest_start:return duration,False          # 窗口已过，无法硬塞
    budget=latest_start-start
    if budget>=duration:return duration,False
    return max(0,budget),True


def meal_inside(w,dt,start,duration,period,lunch_used=False):
    """判断某餐是否应"在游玩过程中"解决。

    返回 (是否在游程内, 用餐时刻或 None)。
    口径（用户确定）：游玩不切断也不缩短；吃饭与休息发生在游玩过程中，
    所以游程时段 = 游玩 + 用餐 + 休息。窗口已过则不排餐，交由提醒说明。
    """
    from . import pacing
    if period=='lunch' and lunch_used:return False,None
    at=pacing.meal_time(w,dt,period)
    duration_meal=pacing.meal_duration(w,dt,period)
    end_of_window=meal_window(w,dt,period)[1]
    if start+duration_meal>end_of_window:return False,None       # 窗口放不下这一餐
    if start<=at<start+duration:return True,at                   # 游玩跨过饭点 → 游程内解决
    return False,None


def clip_visit(w,dt,start,duration,period,lunch_used):
    """按当天约束给出该景点可用的最长时长（必要时缩减）。

    约束优先级：返程/日程硬边界 → 午餐窗口前收尾 → 保留原时长。
    """
    from . import pacing
    hard=min(windows(w,dt)[1],day_end(w,dt),24*60)
    budget=hard-start
    if budget>=duration:return duration
    # 只有真的超出当天边界才缩减（返程准备、日程结束或跨日）
    return max(0,budget)


def point(w,cid):return w.get('catalog',{}).get(cid)

def provisional(w):
 from . import visit_analysis
 from . import pacing
 from .spot_hierarchy import state
 hierarchy=state(w)
 ds=visits.dates(w);cat=w.get('catalog',{});pins=hierarchy['visit_requests'];hotel=w.get('hotel');selected=visit_analysis.selected(w)
 if not ds:return []
 estimates={x['candidate_id']:x for x in visit_analysis.preview(w)}
 buckets={dt:[] for dt in ds}
 for p in selected:
  if estimates.get(p['id'],{}).get('date') in buckets:buckets[estimates[p['id']]['date']].append(p)
 rows=[];order={cid:i for i,cid in enumerate(w.get('visit_order',[]))}
 for dt,places in buckets.items():
  hotel=stay_plan.hotel_for(w,dt,morning=True)
  floor,end=windows(w,dt);_floor_base=max(minutes(w['requirements'].get('day_start','09:00')),floor)
  t=_floor_base;last=hotel;arranged=[]
  # 返程日餐次尽量往后（吃完就上车），但留够准备时间且不超出餐次窗口。
  # 只优化最靠近返程的那一餐（其余餐次保持默认时刻）
  last_meal=last_meal_before_return(w,dt)
  def _late(period):return period==last_meal

  lunch_at=meal_start(w,dt,'lunch',as_late=_late('lunch'));rest_start=lunch_at+pacing.meal_duration(w,dt,'lunch') if lunch_at is not None else None
  rest_minutes=pacing.rest_length(w,dt,rest_start) if rest_start is not None else 0
  # 餐次与午休不再作为"障碍物"插进景点之间——那会把长时景区切成碎片。
  # 景点先连续排定，餐次时刻随后跟随（见下方 meal_flow.resolve_meals）。
  # Respect explicit periods and orders; within flexible groups use nearest
  # coordinates. Straight distance is never displayed as road travel time.
  while places:
   def rank(p):
    period=estimates[p['id']].get('period','any')
    return ({'morning':0,'any':1,'afternoon':2,'evening':3}.get(period,1),order.get(p['id'],9999),estimates[p['id']].get('sequence',9999),coordinate_distance(last,p) if last and last.get('location') and p.get('location') else 0)
   p=min(places,key=rank);places.remove(p);estimate=estimates[p['id']];period=estimate.get('period','any');duration=estimate['duration']
   t=max(t,{'afternoon':13*60,'evening':18*60}.get(period,0),minutes(estimate.get('not_before')))
   # 餐次不再参与景点摆位：长时景点跨过饭点就连续玩完，那一餐随后顺延。
   # 但午休仍是边界——被钉在下午/晚上的活动应从午休结束后开始。
   if rest_minutes and rest_start is not None and period in ('afternoon','evening') and t<rest_start+rest_minutes:
    t=rest_start+rest_minutes
   # 游玩时长不缩短（用户口径）：若游玩跨过饭点，则把用餐放进游程内，
   # 游程时段相应延长；窗口已过则不排这一餐，交由提醒说明。
   _inside=[]
   for _period in ('lunch','dinner'):
    _in,_at=meal_inside(w,dt,t,duration,_period,any(x.get('period')=='lunch' for x in arranged))
    if _in:_inside.append((_period,_at))
   _extra=sum(pacing.meal_duration(w,dt,_p) for _p,_a in _inside)
   finish=t+duration+_extra
   pin_period=pins.get(p['id'],{}).get('period')
   over=finish>min(end,day_end(w,dt)) or pin_period in ('morning','afternoon') and finish>{'morning':720,'afternoon':1080}[pin_period]
   arranged.append({'key':dt+'|'+p['id'],'date':dt,'time':clock(t),'end':clock(finish),'duration':duration,'not_before':estimate.get('not_before'),'sequence':estimate.get('sequence'),'kind':'spot','candidate_id':p['id'],'name':p['name'],'period':period,'confirmed':bool(pins.get(p['id'])),'estimated':True,'estimate_basis':estimate['basis'],'reason':estimate['reason'],'includes_meal_break':bool(_inside),'inside_meals':_inside,'over_capacity':over})
   t=finish+pacing.for_day(w,dt)['break_minutes'];last=p
  rows+=arranged
  _visits=[(minutes(x['time']),minutes(x['end'])) for x in arranged if x.get('time') and x.get('end')]
  # 餐次时刻跟随景点与午休（长时景点跨过饭点时，那一餐顺延到结束后）。
  # preferred 与原先 meal_start 的口径一致，只有真正重叠时才顺延。
  # floor 取最后一个景点的结束时刻：餐次不该早于活动结束，
  # 也不该被"结束后的机动时间"往后推（那会造成无意义的空档）。
  _floor=max([minutes(x['end']) for x in arranged if x.get('end')] or [_floor_base])
  preferred={}
  for _p in PERIODS:
   _at=meal_start(w,dt,_p,as_late=_late(_p))
   if _at is None:continue
   if _p!='dinner':
    _at=max(_at,_floor)
   _lo,_hi=meal_window(w,dt,_p)
   preferred[_p]=min(_at,_hi-pacing.meal_duration(w,dt,_p))
  from . import meal_flow as _meal_flow
  # 午休不参与餐次解析：它是可伸缩的余量，先让景点与餐次各就各位。
  _inside_periods={p for x in arranged for p,_a in (x.get('inside_meals') or [])}
  for _p in _inside_periods:preferred.pop(_p,None)
  resolved=_meal_flow.resolve_meals(w,dt,_visits,preferred)

  # 午休是可伸缩的弹性余量，不是固定占用：
  #   用户可明确取消（requirements.cancel_rest）；
  #   在景点与餐次都定好之后，找一段真正空着的时段放它；放不下就取消。
  if rest_minutes and w['requirements'].get('cancel_rest'):
   rest_minutes=0
  if rest_minutes:
   _busy=sorted([(minutes(x['time']),minutes(x['end'])) for x in arranged if x.get('end') and x.get('time')]
                +[(at,at+pacing.meal_duration(w,dt,p)) for p,at in resolved.items() if at is not None])
   _limit=min(windows(w,dt)[1],24*60)
   _probe=max(rest_start or 0,minutes(w['requirements'].get('day_start','09:00')))
   for _a,_b in _busy:
    if _probe<_b and _a<_probe+rest_minutes:_probe=_b
   if any(_probe<_b and _a<_probe+rest_minutes for _a,_b in _busy):
    _probe=max([b for _a,b in _busy if b>_probe] or [_probe])
   if _probe+rest_minutes>_limit:
    rest_minutes=0
   else:
    rest_start=_probe
  if rest_minutes:
   rows.append({'key':dt+'|midday_rest','date':dt,'time':clock(rest_start),'end':clock(rest_start+rest_minutes),
                'kind':'rest','rest_type':'midday','name':'午休与放松','estimated':True,'confirmed':False,
                'reason':pacing.for_day(w,dt)['reason']})
  # 餐次时刻跟随景点与午休（长时景点跨过饭点时，那一餐顺延到结束后）。
  # preferred 与原先 meal_start 的口径一致，只有真正重叠时才顺延。
  # floor 取最后一个景点的结束时刻：餐次不该早于活动结束，
  # 也不该被"结束后的机动时间"往后推（那会造成无意义的空档）。
  _floor=max([minutes(x['end']) for x in arranged if x.get('end')] or [_floor_base])
  preferred={}
  for _p in PERIODS:
   _at=meal_start(w,dt,_p,as_late=_late(_p))
   if _at is None:continue
   if _p!='dinner':
    _at=max(_at,_floor)
   _lo,_hi=meal_window(w,dt,_p)
   preferred[_p]=min(_at,_hi-pacing.meal_duration(w,dt,_p))
  from . import meal_flow as _meal_flow
  # 午休不参与餐次解析：它是可伸缩的余量，先让景点与餐次各就各位。
  for period,(label,at,duration) in PERIODS.items():
   at=resolved.get(period)
   duration=pacing.meal_duration(w,dt,period)
   if at is None:continue
   choice=(w.get('meal_choices') or {}).get(dt+'|'+period,{})
   if not choice and (w.get('meal_mode')=='self' or w.get('dining_reviewed')):choice={'mode':'self'}
   p=point(w,choice.get('food_id'));included=foods.included_meal(w,dt,period)
   if included['included']:choice={'mode':'included'}
   before=[x for x in arranged if minutes(x['time'])<=at]
   anchor=(point(w,before[-1]['candidate_id']) if before else hotel) or (point(w,arranged[0]['candidate_id']) if arranged else None)
   if period=='breakfast' and hotel:anchor=hotel
   rows.append({'key':dt+'|'+period,'date':dt,'time':clock(at),'end':clock(at+duration),'kind':'meal','period':period,'included_in_room':included['included'],'name':label+' · '+('酒店含早（'+included['note']+'）' if included['included'] else p['name'] if p else '自行安排' if choice.get('mode')=='self' else '待选择'),'candidate_id':p['id'] if p else None,'anchor_id':anchor['id'] if anchor else None,'confirmed':bool(choice),'estimated':True})
  hotel=stay_plan.hotel_for(w,dt)
 # 住宿与退房也要出现在预览时间轴上（用户要求看得见）。
 rows+=stay_rows(w)
 return rows

def pending_legs(w,rows):
 # No clock or duration is invented before route lookup.
 legs=[]
 for dt in sorted({r['date'] for r in rows}):
  last=stay_plan.anchor(w,dt,morning=True);ordinal=0
  activity=sorted([r for r in rows if r['date']==dt and r['kind'] in ('spot','meal') and r.get('candidate_id') and not r.get('included_in_room')],key=lambda r:r['time'])
  for row in activity:
   target=point(w,row['candidate_id'])
   if not target:continue
   if not last or last['id']!=target['id']:
    ordinal+=1
    legs.append({'key':dt+'|pending-road|'+str(ordinal),'date':dt,'time':'','sort_time':row['time'],'sort_order':0,'kind':'unknown_route',
     'name':(last['name'] if last else '出发位置待确定')+' → '+target['name'],'candidate_id':target['id'],
     'route_status':'unknown','mode':None,'route_minutes':None,'end':None,'estimated':True,'confirmed':False,
     'reason':'交通方式、出发及抵达时间尚未查询；点击核对交通时间后更新，当前游玩时刻仍为初步建议。'})
   last=target
  hotel=stay_plan.anchor(w,dt)
  if activity and hotel and last and last['id']!=hotel['id']:
   legs.append({'key':dt+'|pending-return','date':dt,'time':'','sort_time':activity[-1].get('end') or activity[-1]['time'],'sort_order':1,'kind':'unknown_route',
    'name':last['name']+' → '+hotel['name'],'candidate_id':hotel['id'],'route_status':'unknown','mode':None,'route_minutes':None,'end':None,'estimated':True,'confirmed':False,
    'reason':'返回住宿的交通方式和耗时待查询。'})
 return legs


def plan_rows(w,plan,provisional=False):
 rows=[]
 from .spot_hierarchy import state
 pins=state(w)['visit_requests']
 for d in plan.get('days',[]):
  for i,e in enumerate(d.get('events',[])):
   kind=e.get('kind')
   if kind not in ('spot','spot_continue','meal','transport','arrival','route','unknown_route','transfer_plan') and e.get('rest_type')!='midday':continue
   cid=e.get('candidate_id') or (e.get('food') or {}).get('id')
   direction=None;ticket={}
   if kind=='transport':
    for slot,label in [('selected_transport','outbound'),('selected_return','return')]:
     candidate=w.get(slot) or {}
     depart=transport_time(candidate,'departure')
     if depart and depart.date().isoformat()==d['date'] and depart.strftime('%H:%M')==e['start']:
      direction=label;ticket=candidate;cid=ticket.get('id');break
   arrival=transport_time(ticket,'arrival') if kind=='transport' else None
   period=next((k for k,(label,_,_) in PERIODS.items() if e.get('name','').startswith(label)),None) if kind=='meal' else None
   route=e.get('route') or {}
   confirmed=bool(w.get('meal_choices',{}).get(d['date']+'|'+str(period))) if kind=='meal' else bool(pins.get(cid)) if provisional and kind in ('spot','spot_continue') else kind in ('spot','spot_continue','transport','arrival')
   rows.append({'key':d['date']+'|'+(period or cid or str(i))+('|continue'+str(i) if kind=='spot_continue' else '|'+kind+'|'+str(i) if kind not in ('spot','meal') else ''),
                'date':d['date'],'time':e['start'],'end':arrival.strftime('%H:%M') if arrival else e['end'],'end_date':arrival.date().isoformat() if arrival else None,'kind':kind,'rest_type':e.get('rest_type'),
                'candidate_id':cid,'period':period,'name':e.get('name',''),'confirmed':confirmed,'estimated':provisional or kind in ('rest','unknown_route','transfer_plan'),
                'duration':e.get('duration'),'included_in_room':e.get('included_in_room',False),'transport_kind':(ticket.get('kind') if kind=='transport' else None),'train_type':(ticket.get('train_type') if kind=='transport' else None),
                 'mode':route.get('mode'),'route_minutes':route.get('minutes'),'route_distance':route.get('distance'),'buffer_minutes':e.get('buffer'),'direction':direction,
                'route_status':route.get('status') or ('waiting_estimate' if e.get('transfer_scope')=='waiting' else 'unknown' if kind in ('unknown_route','transfer_plan') else None),
                'source':route.get('source') or e.get('source'),'reason':e.get('note','')})
 rows+=stay_rows(w)
 return rows


def build(w):
 from .spot_hierarchy import duplicate_plan
 from .travel_preview import current
 plan=w.get('plan');rows=[];checked=current(w)
 formal=bool(plan and not plan.get('stale') and not duplicate_plan(w,plan))
 if formal:rows=plan_rows(w,plan)
 elif checked:rows=checked['entries']
 else:rows=provisional(w);rows+=pending_legs(w,rows)
 # Include transport-only dates outside the sightseeing period.
 for key,kind in [('selected_transport','去程'),('selected_return','返程')]:
  p=w.get(key);dt=transport_time(p,'departure')
  if p and dt and not any(x['kind']=='transport' and x['date']==dt.date().isoformat() and x['time']==dt.strftime('%H:%M') for x in rows):rows.append({'key':key,'date':dt.date().isoformat(),'time':dt.strftime('%H:%M'),'kind':'transport','candidate_id':p.get('id'),'direction':'return' if key=='selected_return' else 'outbound','name':kind+' · '+p.get('name','班次'),'transport_kind':p.get('kind'),'train_type':p.get('train_type'),'end':(transport_time(p,'arrival').strftime('%H:%M') if transport_time(p,'arrival') else None),'end_date':(transport_time(p,'arrival').date().isoformat() if transport_time(p,'arrival') else None),'confirmed':p.get('selection_status')=='confirmed','estimated':False})
 rows=sorted(rows,key=lambda x:(x['date'],x.get('sort_time',x['time']),x.get('sort_order',1),x['key']))
 slots=[x for x in rows if x['kind']=='meal']
 from .locations import hotel_anchor
 partial=not hotel_anchor(w) or any(not stay_plan.anchor(w,dt,morning=True) for dt in {x['date'] for x in rows if x['kind']=='spot'}) or any(x.get('route_status')=='unknown' for x in rows)
 from . import visit_analysis
 from .travel_preview import signature
 pending=w.get('travel_preview') or {}
 pending=pending if pending.get('status')=='pending' and pending.get('signature')==signature(w) else {}
 analysis=visit_analysis.current(w)
 return {'entries':rows,'meal_slots':slots,'provisional':not formal,'conflicts':conflicts(w),'analysis_status':analysis['status'] if analysis else 'initial',
         'route_status':('partial' if partial else 'checked') if formal or checked else 'pending','route_message':pending.get('message'),'route_issues':pending.get('issues'),
         'notices':visit_analysis.notices(w,visit_analysis.preview(w))}

def conflicts(w):
 from .spot_hierarchy import state
 hierarchy=state(w)
 result=list(hierarchy['issues']);arrival=transport_time(w.get('selected_transport'),'arrival');back=transport_time(w.get('selected_return'),'departure');pins=hierarchy['visit_requests'];ds=visits.dates(w)
 for cid in hierarchy['active_ids']:
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
  if capacity<30*len(hierarchy['active_ids']) and not result:
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
