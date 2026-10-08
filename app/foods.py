"""Optional, provider-backed dining candidates and per-date meal choices."""
import asyncio
from .providers import DataError
from .tools import local_tool
from .journey import meal_dates

PERIODS={'breakfast':'早餐','lunch':'午餐','dinner':'晚餐'}

# 餐次语义（《成员三任务说明》第三批）：
#   fixed_date —— 固定日期餐次：日期与时段由用户指定，任何重排都不自动挪期。
#   follow_spot —— 明确跟随某景点的餐次：保存 bind_spot_id 与绑定方式，
#                  景点改期时只提示受影响，是否改期由用户决定。
#   flexible —— 未明确绑定：日期时段是建议，可以随规划调整。
BINDING_FIXED='fixed_date'
BINDING_FOLLOW='follow_spot'
BINDING_FLEXIBLE='flexible'
BINDING_LABELS={BINDING_FIXED:'固定日期',BINDING_FOLLOW:'跟随景点',BINDING_FLEXIBLE:'未绑定'}
BINDING_METHODS={'same_day':'与景点同日','same_half_day':'与景点同半天','explicit':'用户指定跟随'}
# 时段归属：餐次与景点时段按同一套半天口径比较；any 跨全天，不能说"同半天"。
PERIOD_HALVES={'breakfast':('morning',),'morning':('morning',),'lunch':('midday',),
               'afternoon':('afternoon',),'dinner':('evening',),'evening':('evening',),'any':()}

def same_half_day(meal_period,spot_period):
    """餐次与景点是否确实在同一半天；任一侧为 any 时都不成立。"""
    meal=PERIOD_HALVES.get(meal_period,())
    spot=PERIOD_HALVES.get(spot_period,())
    return bool(meal) and bool(spot) and set(meal)==set(spot)


def binding_of(choice):
    """读取餐次绑定语义；旧记录没有该字段时按固定日期处理（不自动挪期）。"""
    if not isinstance(choice,dict):return BINDING_FIXED
    binding=choice.get('binding')
    return binding if binding in BINDING_LABELS else BINDING_FIXED


def binding_method_label(choice):
    return BINDING_METHODS.get((choice or {}).get('binding_method'),'用户指定跟随')


def spot_intent(w,spot_id):
    """景点当前安排的日期与时段：visit_requests 是用户明确要求，优先于模型建议。"""
    request=(w.get('visit_requests') or {}).get(spot_id)
    if request and request.get('date'):return {'date':request['date'],'period':request.get('period','any'),'source':'user'}
    suggestion=((w.get('catalog') or {}).get(spot_id) or {}).get('visit_suggestion') or {}
    if suggestion.get('date'):return {'date':suggestion['date'],'period':suggestion.get('period','any'),'source':'suggestion'}
    return {'date':None,'period':'any','source':None}


def mark_affected(choice,reason,spot_id=None):
    """把餐次标为受影响：保留用户选择，只提示需要调整或重新查餐厅。"""
    choice['affected']=True
    choice['affected_reason']=reason
    if spot_id:choice['affected_spot_id']=spot_id
    return choice


def clear_affected(choice):
    if isinstance(choice,dict):
        choice.pop('affected',None);choice.pop('affected_reason',None);choice.pop('affected_spot_id',None)
    return choice


def binding_status(w,dt,period):
    """某个餐次的绑定与受影响状态；没有绑定或未受影响时 affected 为 False。

    affected 一律按"当前"景点安排现算，不读历史标记：景点改回原日期时
    受影响状态应当自动消失，历史标记只用来决定是否需要再提示一次。
    """
    choice=(w.get('meal_choices') or {}).get(dt+'|'+period)
    if not isinstance(choice,dict):
        return {'binding':BINDING_FLEXIBLE,'label':BINDING_LABELS[BINDING_FLEXIBLE],'affected':False,
                'reason':None,'spot_id':None,'spot_name':None,'spot_intent':None,'notified':False}
    binding=binding_of(choice);spot_id=choice.get('bind_spot_id')
    status={'binding':binding,'label':BINDING_LABELS[binding],'affected':False,
            'reason':choice.get('affected_reason') if choice.get('affected') else None,
            'spot_id':spot_id,
            'spot_name':choice.get('bind_spot_name'),'spot_intent':choice.get('bind_spot_intent'),
            'method':binding_method_label(choice) if binding==BINDING_FOLLOW else None,
            'notified':bool(choice.get('affected_notified'))}
    if binding!=BINDING_FOLLOW or not spot_id:return status
    if spot_id not in (w.get('selected_spots') or []):
        status.update(affected=True,reason='跟随的景点已从选择中移除，需要改为固定日期或重新绑定')
        return status
    intent=spot_intent(w,spot_id)
    if not intent['date']:
        status.update(affected=True,reason='跟随的景点尚未确定日期，餐次需要重新核对')
        return status
    if intent['date']!=dt:
        status.update(affected=True,
                      reason='跟随的'+str(choice.get('bind_spot_name') or spot_id)+'已改到'+intent['date']
                             +'（原为'+dt+'），需要决定这餐是否跟随改期或重新选餐厅',
                      spot_intent=intent)
        return status
    # 日期没变但时段变了：原本说好"同半天"的绑定不再成立，也要提示（复核 S1）。
    if binding_method_label(choice)=='与景点同半天' and not same_half_day(period,intent.get('period','any')):
        status.update(affected=True,
                      reason='跟随的'+str(choice.get('bind_spot_name') or spot_id)+'时段已改为'
                             +str(intent.get('period'))
                             +'，与这餐不再同半天，需要确认这餐是否仍跟随',
                      spot_intent=intent)
    return status


def followable_spots(w,dt):
    """可绑定为跟随餐次的景点：用户指定日期必须是这一天，避免绑定后又立刻受影响。"""
    result=[]
    for cid in w.get('selected_spots') or []:
        spot=(w.get('catalog') or {}).get(cid)
        if not spot or spot.get('kind')!='spot':continue
        intent=spot_intent(w,cid)
        if intent['date']==dt:result.append(spot)
    return result


def resolve_binding(w,args,dt,period):
    """决定这次选择的绑定语义。

    用户明确要求跟随景点（bind_spot_id）→ follow_spot；
    用户为这一天指定了景点（visit_requests[spot_id].date == 当天）→ 明确绑定；
    只有模型建议时 → 未绑定，允许规划阶段调整。
    """
    explicit=args.get('bind_spot_id')
    if explicit:
        spot=w['catalog'].get(explicit)
        if not spot or spot.get('kind')!='spot':raise DataError('要跟随的景点不在当前候选中，请重新选择景点。')
        intent=spot_intent(w,explicit)
        if intent['date'] and intent['date']!=dt:
            raise DataError(spot['name']+'已安排在'+intent['date']+'，餐次不能同时跟随到'+dt+'；请调整景点日期或改选餐次日期。')
        return {'binding':BINDING_FOLLOW,'binding_method':'explicit','bind_spot_id':explicit,
                'bind_spot_name':spot.get('name'),'bind_spot_intent':intent}
    candidates=[cid for cid in (w.get('visit_requests') or {})
                if (w['visit_requests'][cid] or {}).get('date')==dt and cid in (w.get('selected_spots') or [])]
    if len(candidates)==1:
        spot=w['catalog'].get(candidates[0]) or {}
        intent=spot_intent(w,candidates[0])
        # 只有餐次与景点确实在同一半天时才说"同半天"；否则只能承诺同日。
        method='same_half_day' if same_half_day(period,intent.get('period','any')) else 'same_day'
        return {'binding':BINDING_FOLLOW,'binding_method':method,'bind_spot_id':candidates[0],
                'bind_spot_name':spot.get('name'),'bind_spot_intent':intent}
    return {'binding':BINDING_FIXED,'binding_method':'explicit','bind_spot_id':None,'bind_spot_name':None,'bind_spot_intent':None}


def bindings_clear_or_mark(w):
    """景点改期或移除后重算受影响餐次；返回给用户看的变更说明。

    受影响与否按景点"当前"安排现算：固定日期餐次不动；明确跟随的餐次只
    提示受影响并保留餐厅选择，是否跟随改期由用户决定；景点改回原日期时
    受影响状态自动解除。这里的说明只在原因变化时提示一次。
    """
    messages=[]
    for key,choice in (w.get('meal_choices') or {}).items():
        if not isinstance(choice,dict) or binding_of(choice)!=BINDING_FOLLOW:continue
        parts=key.split('|')
        if len(parts)!=2:continue
        dt,period=parts
        status=binding_status(w,dt,period)
        if status['affected']:
            if status['reason']!=choice.get('affected_reason'):choice.pop('affected_notified',None)
            mark_affected(choice,status['reason'],choice.get('bind_spot_id'))
            if not choice.get('affected_notified'):
                messages.append(dt+'的'+PERIODS.get(period,'用餐')+'跟随'+str(choice.get('bind_spot_name') or '景点')
                                +'：'+str(status['reason'])+'；已保留这餐的餐厅选择，请确认是否跟随改期或重新查餐厅')
                choice['affected_notified']=True
        else:
            # 不再受影响：解除标记，用户选择一直保留。
            clear_affected(choice);choice.pop('affected_notified',None)
    return messages


def infeasible(w,dt,period):
    """Reject meals outside the same buffered window used by the timeline."""
    from .schedule import meal_start,windows,clock,limit_reason,meal_window
    from . import time_policy
    if meal_start(w,dt,period) is not None:return None
    low,high=windows(w,dt)
    name=PERIODS[period]
    if high<1440:
        # 要说清是"返程接驳准备"还是"当日结束时刻"在卡，非返程日不能提返程准备。
        detail='可用时间不足以容纳完整用餐（'+clock(high)+'前须结束）：'+limit_reason(w,dt)
    elif low>0:
        detail='去程抵达及'+str(time_policy.FALLBACK_ARRIVAL_BUFFER_MINUTES)+'分钟准备后，最早可从'+clock(low)+'安排'
    else:detail='当前每日结束时刻不足以容纳完整用餐时长'
    return dt+' '+name+'来不及安排：'+detail+'。请调整餐次、日期或班次；也可自行安排。'

def anchors(w,args):
    catalog=w['catalog'];explicit=catalog.get(args.get('anchor_id'))
    if explicit and explicit.get('location'):return [explicit]
    dt=args.get('meal_date');period=args.get('meal_period','lunch')
    # 跟随餐次优先用绑定的景点作为参照点：餐厅要挨着实际会去的那个景点。
    bound=((w.get('meal_choices') or {}).get(str(dt)+'|'+str(period)) or {}).get('bind_spot_id')
    if not bound:bound=args.get('bind_spot_id')
    spot=catalog.get(bound)
    if spot and spot.get('location'):return [spot]
    day=next((d for d in (w.get('plan') or {}).get('days',[]) if d['date']==dt),None)
    if day and not (w.get('plan') or {}).get('stale'):
        entries=[e for e in day.get('events',[]) if e.get('kind')=='spot' and e.get('candidate_id') in catalog]
        if entries:
            if period=='dinner':entries=entries[-1:]
            elif period=='lunch':entries=sorted(entries,key=lambda e:abs(int(e['end'].split(':')[0])*60+int(e['end'].split(':')[1])-12*60))[:2]
            else:entries=entries[:1]
            return [catalog[e['candidate_id']] for e in entries if catalog[e['candidate_id']].get('location')]
    if period=='breakfast' and (w.get('hotel') or {}).get('location'):return [w['hotel']]
    from .schedule import provisional
    slot=next((x for x in provisional(w) if x['kind']=='meal' and x['date']==dt and x['period']==period),None)
    if slot and slot.get('anchor_id') and catalog.get(slot['anchor_id'],{}).get('location'):
        ref=catalog[slot['anchor_id']]
        return [ref]+([w['hotel']] if period=='dinner' and (w.get('hotel') or {}).get('location') and w['hotel']['id']!=ref['id'] else [])
    from .visits import meal_refs
    intended=[p for p in meal_refs(w,dt,period) if p.get('location')]
    if intended:return intended[:2]+([w['hotel']] if period=='dinner' and w.get('hotel',{} ) and w['hotel'].get('location') and w['hotel']['id'] not in [p['id'] for p in intended] else [])
    points=[catalog[i] for i in w.get('selected_spots',[]) if catalog.get(i,{}).get('location')]
    if not points:
        from .discovery import page_info
        points=[catalog[i] for i in page_info(w)['ids'] if catalog.get(i,{}).get('location')]
    if not points:return []
    from .journey import coordinate_distance
    ordered=sorted(points,key=lambda p:sum(coordinate_distance(p,q) for q in points))
    result=[ordered[0]]
    for p in ordered[1:]:
        if all(coordinate_distance(p,q)>=5 for q in result):result.append(p)
        if len(result)>=3:break
    return result

async def search(w,args,progress,recommend):
    r=w['requirements']
    if not r.get('city'):raise DataError('查询餐饮前，请先确定目的地。')
    words=args.get('keywords') or args.get('food_keywords') or r.get('food_preferences') or ['当地餐厅']
    keyword='海鲜' if any('海鲜' in str(x) for x in words) else str(words[0])[:40]
    refs=anchors(w,args);anchor=refs[0] if refs else None
    progress('正在按当前餐次和游览区域查询餐饮候选')
    params={'city':r['city'],'keywords':keyword,'category':'food','page_size':12}
    queries=[{**params,'location':p['location'],'radius':5000} for p in refs] or [params]
    results=await asyncio.gather(*(local_tool('search_places',q) for q in queries),return_exceptions=True)
    rows=[]
    for index,result in enumerate(results):
        if isinstance(result,Exception):continue
        for p in result.get('items',[]):
            ref=refs[index] if refs else None
            p={**p,'search_anchor':ref['name'] if ref else r['city'],'search_anchor_id':ref['id'] if ref else None}
            if ref:
                from .journey import coordinate_distance
                p['anchor_distance_km']=round(coordinate_distance(p,ref),1) if p.get('location') else None
            rows.append(p)
    result={'items':rows}
    items=[];seen=set()
    for p in result.get('items',[]):
        if p.get('kind')!='food' or p['id'] in seen:continue
        if any(x in p['name'] for x in ('售票','停车','厕所')):continue
        seen.add(p['id']);items.append(p)
    if items:
        await recommend(w,items,'单独筛选4至5家餐厅，按餐饮偏好与查询位置比较。只根据返回资料描述，不猜招牌菜、人均、景观或本地人比例。')
        items.sort(key=lambda p:p.get('recommendation_rank',99))
    items=items[:8]
    from .planning import route_options,choose_route
    from .access import screen
    progress('正在提前核对餐厅通行与当前餐次可用时段')
    meal=(args['meal_date'],args['meal_period']) if args.get('meal_date') and args.get('meal_period') in PERIODS else None
    by_id={p['id']:p for p in refs}
    items,excluded=await screen(w,items,lambda p:by_id.get(p.get('search_anchor_id')) or anchor,route_options,choose_route,meal)
    items=items[:5]
    for p in items:
        period=PERIODS.get(args.get('meal_period'),'用餐')
        basis=period+'可结合'+p['search_anchor']+'周边活动安排'
        if p.get('anchor_distance_km') is not None:basis+=f'，距参照点直线约{p["anchor_distance_km"]}公里'
        p['recommendation_basis']=basis+'；实际通行与营业时段请核对。'
    # Each result retains the actual reference used for its query.
    markets=[]
    if keyword=='海鲜':
        market_params={**queries[0],'keywords':'海鲜市场','category':'market','page_size':6}
        try:
            found=await local_tool('search_places',market_params)
            markets=[p for p in found.get('items',[]) if p.get('kind')=='market' and any(x in p.get('name','') for x in ('市场','水产批发'))][:2]
        except DataError:pass
    w['catalog'].update({p['id']:p for p in items+markets});w['food_query']={'ids':[p['id'] for p in items],'excluded':excluded,'markets':[p['id'] for p in markets],'keyword':keyword,'anchor':'、'.join(p['name'] for p in refs) if refs else r['city'],'anchors':[{'id':p['id'],'name':p['name']} for p in refs],'explicit_anchor_id':args.get('anchor_id'),'meal_date':args.get('meal_date'),'meal_period':args.get('meal_period'),'scope':'周边5公里' if anchor else '城市范围'};w['turn_food_updated']=True
    return '已单独查询到'+str(len(items))+'家餐饮候选，可在右侧“餐饮”按日期和餐次选择，也可以自行安排。' if items else '本次未找到符合条件的餐饮候选，已保留您的饮食偏好。可调整区域或自行安排。'

def select_meal(w,args):
    dates=meal_dates(w['requirements']);dt=args.get('meal_date');period=args.get('meal_period');mode=args.get('meal_mode','chosen');cid=args.get('food_id') or args.get('id')
    if mode=='self' and not dt and not period:
        w['meal_mode']='self';w['meal_choices']={};w['dining_reviewed']=True;return '用餐已改为自行安排，已移除餐厅选择，计划书仍保留可调整的用餐时段。'
    if not dt or not period:
        if not dates:raise DataError('餐厅候选已找到。请先确定日期，再指定哪天的早餐、午餐或晚餐；也可以自行安排。')
        raise DataError('请说明要安排哪天的早餐、午餐或晚餐，避免将同一餐厅强行安排到每一餐。')
    if dt not in dates or period not in PERIODS:raise DataError('请在游玩日期内选择有效餐次。')
    item=None
    if mode=='chosen':
        item=w.get('catalog',{}).get(cid)
        if not item or item.get('kind')!='food':raise DataError('餐厅候选不存在，请重新查询或选择自行安排。')
        blocked=infeasible(w,dt,period)
        if blocked:
            from .schedule import windows
            raise DataError(blocked,{'date':dt,'meal_period':period,'candidate_ids':[cid],'view':'food','direction':'return' if windows(w,dt)[1]<1440 else 'outbound'})
    binding=resolve_binding(w,args,dt,period)
    w['meal_mode']='optional'
    choice={'mode':mode,'food_id':cid if item else None,**binding}
    if mode=='chosen' and binding['binding']==BINDING_FOLLOW:
        # 用户刚为这餐做了决定，受影响状态清除，等景点再变时重新提示。
        clear_affected(choice);choice['affected_notified']=False
    w.setdefault('meal_choices',{})[dt+'|'+period]=choice
    if w.get('plan'):w['plan']['stale']=True
    note=''
    if mode=='chosen' and binding['binding']==BINDING_FOLLOW:
        note=('（'+BINDING_LABELS[BINDING_FOLLOW]+str(binding.get('bind_spot_name') or '')
              +'，'+BINDING_METHODS.get(binding.get('binding_method'),'')+'：景点改期时这餐只做提示，不自动挪期）')
    elif mode=='chosen':
        note='（'+BINDING_LABELS[BINDING_FIXED]+'：重排不会自动挪期）'
    return dt+'的'+PERIODS[period]+'已'+('选定：'+item['name'] if item else '改为自行安排')+note+'。可随时更换，不代表已预订。'

def choice(w,dt,period):
    value=(w.get('meal_choices') or {}).get(dt+'|'+period,{})
    return w['catalog'].get(value.get('food_id')) if value.get('mode')=='chosen' and w.get('meal_mode')!='self' else None
