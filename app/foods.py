"""Optional, provider-backed dining candidates and per-date meal choices."""
import asyncio
from .providers import DataError
from .tools import local_tool
from .journey import meal_dates,coordinate_distance

PERIODS={'breakfast':'早餐','lunch':'午餐','dinner':'晚餐'}

# 「当地餐厅」是给模型看的意图词，不是真实地点名称。高德按名称检索时，
# 这类泛指词在景区周边经常返回 0 条（如 洛阳·龙门石窟），因此按顺序兜底重试。
GENERIC_KEYWORDS={'当地餐厅','餐厅','本地餐厅','特色餐厅','当地美食'}
FALLBACK_KEYWORDS=('美食','中餐厅','小吃','面馆','火锅')

def query_keywords(r,args):
    words=args.get('keywords') or args.get('food_keywords') or r.get('food_preferences') or ['当地餐厅']
    if isinstance(words,str):words=[words]
    text=[str(x)[:40] for x in words if str(x).strip()]
    preferred='海鲜' if any('海鲜' in x for x in text) else (text[0] if text else '当地餐厅')
    if text and preferred not in GENERIC_KEYWORDS:
        # 用户自己说了吃什么（或偏好来自需求），首选词优先；只有它查不到才兜底。
        return preferred,list(dict.fromkeys([preferred,*FALLBACK_KEYWORDS]))
    # 没给具体口味时用的是默认泛指词，先换更贴近高德名称检索的词，而不是直接报 0 候选。
    extra=['海鲜'] if any('海鲜' in x for x in text) else []
    return preferred,list(dict.fromkeys([preferred,*extra,*FALLBACK_KEYWORDS]))

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

async def attempt(refs,city,word,radius,progress):
    """一轮查询：有参照点时逐个按周边查并各自记录来源；无参照点时查城市范围。

    返回本轮命中的候选行；没有任何命中返回空列表。
    """
    progress('正在按“'+word+'”查询餐饮候选')
    if refs and radius:
        results=await asyncio.gather(*(local_tool('search_places',{'city':city,'keywords':word,'category':'food',
            'page_size':12,'location':p['location'],'radius':radius}) for p in refs),return_exceptions=True)
        rows=[]
        for ref,result in zip(refs,results):
            if isinstance(result,Exception):continue
            for p in result.get('items',[]):
                if p.get('kind')!='food':continue
                rows.append({**p,'search_anchor':ref['name'],'search_anchor_id':ref['id'],'_radius':radius,'_keyword':word,
                             **({'anchor_distance_km':round(coordinate_distance(p,ref),1)} if p.get('location') else {})})
        return rows
    result=await local_tool('search_places',{'city':city,'keywords':word,'category':'food','page_size':12})
    return [{**p,'search_anchor':city,'search_anchor_id':None,'_radius':None,'_keyword':word}
            for p in result.get('items',[]) if p.get('kind')=='food']

async def search(w,args,progress,recommend):
    r=w['requirements']
    if not r.get('city'):raise DataError('查询餐饮前，请先确定目的地。')
    preferred,plan=query_keywords(r,args)
    refs=[p for p in anchors(w,args) if p.get('location')]
    progress('正在按当前餐次和游览区域查询餐饮候选')
    # 顺序兜底，最多三档：参照点周边 → 换关键词/放大半径 → 城市范围。任何一档有候选就停。
    # 先换关键词再放大半径：泛指词（「当地餐厅」）命中率远低于「美食」，而半径过大会把
    # 近处的候选挤掉（实测龙门石窟：5 公里内 12 家，20 公里却只剩 1 家）。
    nearby=[(refs,5000,word) for word in plan[:3]]
    nearby+=[(refs,20000,plan[0])]
    steps=nearby+[([],None,word) for word in plan]
    rows=[];hit=None
    for group,radius,word in steps:
        try:rows=await attempt(group,r['city'],word,radius,progress)
        except DataError:rows=[]
        if rows:hit=(group,radius,word);break
    if hit and not hit[0]:
        progress('参照点周边未查到候选，已按城市范围补充')
    items=[];seen=set()
    for p in rows:
        if p['id'] in seen:continue
        if any(x in p['name'] for x in ('售票','停车','厕所')):continue
        seen.add(p['id']);items.append(p)
    if items:
        await recommend(w,items,'单独筛选4至5家餐厅，按餐饮偏好与查询位置比较。只根据返回资料描述，不猜招牌菜、人均、景观或本地人比例。')
        items.sort(key=lambda p:p.get('recommendation_rank',99))
    items=items[:5]
    hit_word=hit[2] if hit else preferred
    scope='城市范围' if (hit and not hit[0]) or (not refs and rows) else ('周边%g公里' % (hit[1]/1000) if hit and hit[1] else '城市范围')
    for p in items:
        period=PERIODS.get(args.get('meal_period'),'用餐')
        if p.get('search_anchor_id') is None:
            basis=period+'可结合'+r['city']+'当日行程安排（本次为城市范围候选，不是景点周边）'
        else:
            basis=period+'可结合'+p['search_anchor']+'周边活动安排'
            if p.get('anchor_distance_km') is not None:basis+=f'，距参照点直线约{p["anchor_distance_km"]}公里'
        p['recommendation_basis']=basis+'；实际通行与营业时段请核对。'
    keyword=hit_word
    # Each result retains the actual reference used for its query.
    markets=[]
    if keyword=='海鲜':
        market_ref=refs[0] if refs else None
        market_params={'city':r['city'],'keywords':'海鲜市场','category':'market','page_size':6}
        if market_ref:market_params.update(location=market_ref['location'],radius=5000)
        try:
            found=await local_tool('search_places',market_params)
            markets=[p for p in found.get('items',[]) if p.get('kind')=='market' and any(x in p.get('name','') for x in ('市场','水产批发'))][:2]
        except DataError:pass
    w['catalog'].update({p['id']:p for p in items+markets});w['food_query']={'ids':[p['id'] for p in items],'markets':[p['id'] for p in markets],'keyword':keyword,'anchor':'、'.join(p['name'] for p in refs) if refs else r['city'],'anchors':[{'id':p['id'],'name':p['name']} for p in refs],'explicit_anchor_id':args.get('anchor_id'),'meal_date':args.get('meal_date'),'meal_period':args.get('meal_period'),'scope':scope};w['turn_food_updated']=True
    if items:
        note='（本次为%s候选）' % scope if scope=='城市范围' else ''
        return '已单独查询到'+str(len(items))+'家餐饮候选'+note+'，可在右侧“餐饮”按日期和餐次选择，也可以自行安排。'
    return '本次在'+('景点周边和城市范围' if refs else '城市范围')+'都没有查到餐厅候选。可在右侧选择“本餐自行安排”，或换一个日期/餐次、也可以告诉我具体想吃的菜系或店名，我再查一次。'

def select_meal(w,args):
    dates=meal_dates(w['requirements']);dt=args.get('meal_date');period=args.get('meal_period')
    mode=args.get('mode') or args.get('meal_mode') or 'chosen';cid=args.get('food_id') or args.get('id')
    if mode=='self' and not dt and not period:
        w['meal_mode']='self';w['meal_choices']={};w['dining_reviewed']=True;return '用餐已改为自行安排，已移除餐厅选择，计划书仍保留可调整的用餐时段。'
    if not dt or not period:
        if not dates:raise DataError('餐厅候选已找到。请先确定日期，再指定哪天的早餐、午餐或晚餐；也可以自行安排。')
        raise DataError('请说明要安排哪天的早餐、午餐或晚餐，避免将同一餐厅强行安排到每一餐。')
    if dt not in dates or period not in PERIODS:raise DataError('请在游玩日期内选择有效餐次。')
    if mode=='remove':
        # 只清掉这一餐的选择，其他餐次不受影响（景区周边 0 候选时也要能退出）。
        removed=(w.get('meal_choices') or {}).pop(dt+'|'+period,None)
        if not removed:raise DataError('这一餐目前没有已选餐厅。')
        if w.get('plan'):w['plan']['stale']=True
        return dt+'的'+PERIODS[period]+'已取消餐厅选择，可重新查询或改为自行安排。'
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
