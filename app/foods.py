"""Optional, provider-backed dining candidates and per-date meal choices."""
import asyncio
from .providers import DataError
from .tools import local_tool
from .journey import meal_dates

PERIODS={'breakfast':'早餐','lunch':'午餐','dinner':'晚餐'}

def infeasible(w,dt,period):
    """Reject meals outside the same buffered window used by the timeline."""
    from .schedule import meal_start,windows,clock
    if meal_start(w,dt,period) is not None:return None
    low,high=windows(w,dt)
    name=PERIODS[period]
    if high<1440:
        detail='返程接驳准备需在'+clock(high)+'开始'
    elif low>0:
        detail='去程抵达及90分钟准备后，最早可从'+clock(low)+'安排'
    else:detail='当前每日结束时刻不足以容纳完整用餐时长'
    return dt+' '+name+'来不及安排：'+detail+'。请调整餐次、日期或班次；也可自行安排。'

def anchors(w,args):
    catalog=w['catalog'];explicit=catalog.get(args.get('anchor_id'))
    if explicit and explicit.get('location'):return [explicit]
    dt=args.get('meal_date');period=args.get('meal_period','lunch')
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
        w['catalog'].update({p['id']:p for p in items[:8]})
        w['food_query']={'ids':[p['id'] for p in items[:8]],'keyword':keyword,'meal_date':args.get('meal_date'),'meal_period':args.get('meal_period'),'anchor':anchor['name'] if anchor else r['city']}
        progress('基础餐厅资料已到达，正在比较特色与核对通行')
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
    w['meal_mode']='optional';w.setdefault('meal_choices',{})[dt+'|'+period]={'mode':mode,'food_id':cid if item else None}
    if w.get('plan'):w['plan']['stale']=True
    return dt+'的'+PERIODS[period]+'已'+('选定：'+item['name'] if item else '改为自行安排')+'。可随时更换，不代表已预订。'

def choice(w,dt,period):
    value=(w.get('meal_choices') or {}).get(dt+'|'+period,{})
    return w['catalog'].get(value.get('food_id')) if value.get('mode')=='chosen' and w.get('meal_mode')!='self' else None
