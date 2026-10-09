"""Optional, provider-backed dining candidates and per-date meal choices."""
import asyncio
from .providers import DataError,poi_radius
from .tools import local_tool
from .journey import meal_dates,coordinate_distance

PERIODS={'breakfast':'早餐','lunch':'午餐','dinner':'晚餐'}

# 「当地餐厅」是给模型看的意图词，不是真实地点名称。高德按名称检索时，
# 这类泛指词在景区周边经常返回 0 条（如 洛阳·龙门石窟），因此按顺序兜底重试。
GENERIC_KEYWORDS={'当地餐厅','餐厅','本地餐厅','特色餐厅','当地美食'}
FALLBACK_KEYWORDS=('美食','中餐厅','小吃','面馆','火锅')

# 早餐要的是早点铺子，不是正餐馆子：高德按名称检索时用"美食"会返回一堆
# 中午才开门的餐厅，所以早餐单独用早点类关键词。
BREAKFAST_KEYWORDS=('早餐','小吃','包子','粥','面馆')
# 判断一家店是不是"早餐类"。命中名称、类型或标签任一即算。
BREAKFAST_SIGNALS=('早餐','早点','包子','馒头','粥','豆浆','油条','烧饼','煎饼','肠粉','米粉','小笼','蒸饺','饼','面馆','面店','馄饨','饺子','豆腐脑','胡辣汤','汤包')
# 每餐最终给几个候选：用户要求 5~6 个。
MEAL_LIMIT=6

# 房型报价里的餐食文本形如"含双早""无早餐""含早餐""含单早"。据此判断这一晚
# 是否已经在房费里带了早餐——带了就不该再推荐早点铺、也不该重复计早餐费用。
MEAL_INCLUDED_PATTERNS=('含早','含早餐','含双早','含单早','双早','单早','含餐','含双餐','早餐2份','早餐两份','含2早','含二早','自助早')
MEAL_EXCLUDED_PATTERNS=('无早','不含早','不含餐','无早餐','不含早餐','自行解决','不含餐食','无餐')


def parse_room_meal(text):
    """解析房型餐食文本，返回 (是否含早, 份数, 说明)。

    只按字面判断，不做推断：认不出来就当"未说明"，交给用户决定，
    不能把"未说明"当成"含早"（那样会漏掉真实需要的早餐推荐）或"不含"。
    """
    raw=str(text or '').strip()
    if not raw:return (None,0,'房型报价未说明是否含早')
    if any(x in raw for x in MEAL_EXCLUDED_PATTERNS):return (False,0,raw)
    if any(x in raw for x in MEAL_INCLUDED_PATTERNS):
        count=2 if any(x in raw for x in ('双早','2份','两份','含2早','含二早','双餐')) else 1
        return (True,count,raw)
    return (None,0,raw)


def stay_hotel_for(w,dt):
    """某晚实际入住的酒店：逐晚指定优先，其次最近选定的那一家。"""
    stays=w.get('stay_hotels') or {}
    hotel_id=stays.get(dt)
    if hotel_id:
        return (w.get('catalog') or {}).get(hotel_id)
    current=w.get('hotel') or {}
    # 只有这一晚没有别的指定、且主记录代表这一晚时才用它
    return current if current.get('id') and not stays else current or None


def included_meal(w,dt,period='breakfast'):
    """这一晚的房型是否已含该餐。返回 {'included':bool,'count':int,'note':str,'hotel':id}。"""
    room=w.get('selected_room') or {}
    if period!='breakfast' or not room:
        return {'included':False,'count':0,'note':'','hotel':None}
    included,count,note=parse_room_meal(room.get('meal'))
    if not included:return {'included':False,'count':0,'note':note,'hotel':None}
    hotel=stay_hotel_for(w,dt)
    return {'included':True,'count':count,'note':note,'hotel':(hotel or {}).get('id')}


def meal_note(w,dt,period):
    """该餐次给用户的一句话说明（含早时说明无需另选，但仍可出去吃）。"""
    info=included_meal(w,dt,period)
    if not info['included']:return ''
    return ('房型已含'+PERIODS[period]+'（'+str(info['note'])+'），无需另选；'
            '如想出去吃，可在本页自行选择餐厅。')


def is_breakfast_place(p):
    """这家店是不是早餐类：名称／类型／标签里出现早点信号词。"""
    text=' '.join(str(p.get(k) or '') for k in ('name','poi_type','address'))
    text+=' '+' '.join(str(x) for x in (p.get('tags') or []))
    return any(w in text for w in BREAKFAST_SIGNALS)


def rating_value(p):
    """评分数值；没有评分返回 None（不能拿"没评分"当高分）。"""
    try:
        return float(p.get('rating'))
    except (TypeError, ValueError):
        return None


def rank_food(p,period,budget=False):
    """候选排序键：早餐类占主要、评分高的优先，其余按评分与来源补充。

    早餐场景（period=='breakfast'）先按"是否早餐类"分组，让早点铺排在正餐馆前面；
    评分缺失排在有评分之后（不猜分数）。budget 为真时把人均价格也纳入参考。
    """
    breakfast_first=0 if (period!='breakfast' or is_breakfast_place(p)) else 1
    rating=rating_value(p)
    rating_slot=0 if rating is not None else 1
    cost=p.get('cost')
    try:
        cost=float(cost)
    except (TypeError, ValueError):
        cost=float('inf')
    return (breakfast_first,rating_slot,-(rating or 0),cost if budget else 0)

def query_keywords(r,args):
    """首选检索词与兜底顺序。早餐走早点类关键词，午晚餐走正餐类。"""
    words=args.get('keywords') or args.get('food_keywords') or r.get('food_preferences') or ['当地餐厅']
    if isinstance(words,str):words=[words]
    text=[str(x)[:40] for x in words if str(x).strip()]
    period=args.get('meal_period') or 'lunch'
    fallback=list(BREAKFAST_KEYWORDS) if period=='breakfast' else list(FALLBACK_KEYWORDS)
    if any('海鲜' in x for x in text):return '海鲜',list(dict.fromkeys(['海鲜',*fallback]))
    # 没给具体口味时：早餐直接用早点类词，不要拿泛指的正餐词打头（否则第一轮必然偏正餐）。
    if not text or text[0] in GENERIC_KEYWORDS:
        return fallback[0],list(dict.fromkeys(fallback))
    preferred=text[0]
    return preferred,list(dict.fromkeys([preferred,*fallback]))

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

def hotel_reference(w):
    """酒店参照点：优先用酒店自己的坐标；定位失败时退回当晚锚点并如实标注。

    酒店可能因为地址无法匹配地图而没有坐标（location_status=not_found）。这时
    不能直接不给"酒店周边"这一路，否则用户会以为系统不支持；但也不能假装是精确
    的酒店位置——所以用当晚收尾地点兜底，并在标注里写明是"住宿所在区域"。
    """
    hotel=w.get('hotel') or {}
    if hotel.get('location'):
        return {**hotel,'_anchor_kind':'hotel','_anchor_label':'酒店周边'}, None
    if not hotel:
        return None, None
    anchor=(w.get('catalog') or {}).get(hotel.get('stay_anchor_id')) or {}
    if not anchor.get('location'):
        return None, None
    return ({**anchor,'_anchor_kind':'hotel','_anchor_label':'住宿所在区域（酒店未定位）',
             '_hotel_unlocated':True},
            '酒店「'+str(hotel.get('name'))+'」暂时无法在地图上定位，这一路按当晚活动区域（'
            +str(anchor.get('name'))+'）查询。')


def _with_hotel(w,refs):
    """早餐参照点：把"酒店周边"和"当天首站周边"都给上，并标注各自来源。

    用户要的是"景区周围或酒店周围都行，最好给个标注"，所以两边都查、
    候选上带 anchor_label 让界面能写明"酒店周边"还是"景区周边"。
    """
    out=[]
    for p in refs:
        if not (p and p.get('location')):
            continue
        # 参照点本身就是酒店（例如早餐锚在酒店）时不能标成"景区周边"。
        is_hotel=p.get('kind')=='hotel' or p.get('id')==(w.get('hotel') or {}).get('id')
        out.append({**p,'_anchor_kind':'hotel' if is_hotel else 'spot',
                    '_anchor_label':'酒店周边' if is_hotel else '景区周边'})
    hotel,note=hotel_reference(w)
    if hotel and hotel.get('id') not in [p.get('id') for p in out] and hotel.get('location'):
        out.append(hotel)
    return out


def anchors(w,args):
    catalog=w['catalog'];explicit=catalog.get(args.get('anchor_id'))
    if explicit and explicit.get('location'):return [explicit]
    dt=args.get('meal_date');period=args.get('meal_period','lunch')

    def labelled(rows,extra_hotel=False):
        """给参照点标注来源，并可按需补上住宿参照（晚餐回酒店顺路）。"""
        out=[]
        for p in rows:
            if not (p and p.get('location')):
                continue
            is_hotel=p.get('kind')=='hotel' or p.get('id')==(w.get('hotel') or {}).get('id')
            out.append({**p,'_anchor_kind':'hotel' if is_hotel else 'spot',
                        '_anchor_label':'酒店周边' if is_hotel else '景区周边'})
        if extra_hotel:
            hotel,note=hotel_reference(w)
            if hotel and hotel.get('location') and hotel.get('id') not in [p['id'] for p in out]:
                out.append(hotel)
        return out

    day=next((d for d in (w.get('plan') or {}).get('days',[]) if d['date']==dt),None)
    if day and not (w.get('plan') or {}).get('stale'):
        entries=[e for e in day.get('events',[]) if e.get('kind')=='spot' and e.get('candidate_id') in catalog]
        if entries:
            if period=='dinner':entries=entries[-1:]
            elif period=='lunch':entries=sorted(entries,key=lambda e:abs(int(e['end'].split(':')[0])*60+int(e['end'].split(':')[1])-12*60))[:2]
            else:entries=entries[:1]
            found=[catalog[e['candidate_id']] for e in entries]
            # 早餐：酒店和当天第一个景区都可以参照，两个都给，用户按方便选。
            if period=='breakfast':return _with_hotel(w,found)
            # 晚餐：回酒店顺路——把住宿参照点一并给出，通行核对时会比较绕行距离。
            return labelled(found,extra_hotel=(period=='dinner'))
    if period=='breakfast':
        # 早餐优先"酒店周边 + 当天首站周边"：住哪儿附近吃、或出门顺路吃都合理。
        from .schedule import provisional
        slot=next((x for x in provisional(w) if x['kind']=='meal' and x['date']==dt and x['period']==period),None)
        found=[]
        if slot and slot.get('anchor_id') and catalog.get(slot['anchor_id'],{}).get('location'):
            found=[catalog[slot['anchor_id']]]
        return _with_hotel(w,found)
    if period=='breakfast' and (w.get('hotel') or {}).get('location'):return labelled([w['hotel']])
    from .schedule import provisional
    slot=next((x for x in provisional(w) if x['kind']=='meal' and x['date']==dt and x['period']==period),None)
    if slot and slot.get('anchor_id') and catalog.get(slot['anchor_id'],{}).get('location'):
        return labelled([catalog[slot['anchor_id']]],extra_hotel=(period=='dinner'))
    from .visits import meal_refs
    intended=[p for p in meal_refs(w,dt,period) if p.get('location')]
    if intended:return labelled(intended[:2],extra_hotel=(period=='dinner'))
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
    return labelled(result,extra_hotel=(period=='dinner'))

async def attempt(refs,city,word,radius,progress,warnings=None):
    """一轮查询：有参照点时逐个按周边查并各自记录来源；无参照点时查城市范围。

    返回本轮命中的候选行；没有任何命中返回空列表。
    """
    progress('正在按“'+word+'”查询餐饮候选')
    if refs and radius:
        results=await asyncio.gather(*(local_tool('search_places',{'city':city,'keywords':word,'category':'food',
            'page_size':12,'location':p['location'],'radius':radius}) for p in refs),return_exceptions=True)
        rows=[];failures=[]
        for ref,result in zip(refs,results):
            if isinstance(result,asyncio.CancelledError):raise result
            if isinstance(result,Exception):failures.append(result);continue
            for p in result.get('items',[]):
                if p.get('kind')!='food':continue
                rows.append({**p,'search_anchor':ref['name'],'search_anchor_id':ref['id'],'anchor_kind':ref.get('_anchor_kind'),'anchor_label':ref.get('_anchor_label'),'_radius':radius,'_keyword':word,
                             **({'anchor_distance_km':round(coordinate_distance(p,ref),1)} if p.get('location') else {})})
        if failures and not rows:
            error=failures[0]
            if isinstance(error,DataError):raise error
            raise DataError('餐饮查询暂未成功，请稍后重试。') from None
        if failures and warnings is not None:warnings.append('部分参照区域查询失败，当前候选来自查询成功的区域。')
        return rows
    result=await local_tool('search_places',{'city':city,'keywords':word,'category':'food','page_size':12})
    return [{**p,'search_anchor':city,'search_anchor_id':None,'_radius':None,'_keyword':word}
            for p in result.get('items',[]) if p.get('kind')=='food']

async def search(w,args,progress,recommend):
    r=w['requirements']
    if not r.get('city'):raise DataError('查询餐饮前，请先确定目的地。')
    preferred,plan=query_keywords(r,args)
    refs=[p for p in anchors(w,args) if p.get('location')]
    anchor=refs[0] if refs else None
    progress('正在按当前餐次和游览区域查询餐饮候选')
    # 顺序兜底，最多三档：参照点周边 → 换关键词/放大半径 → 城市范围。任何一档有候选就停。
    # 先换关键词再放大半径：泛指词（「当地餐厅」）命中率远低于「美食」，而半径过大会把
    # 近处的候选挤掉（实测龙门石窟：5 公里内 12 家，20 公里却只剩 1 家）。
    nearby=[(refs,5000,word) for word in plan[:3]] if refs else []
    if refs:nearby.append((refs,poi_radius(10000),plan[0]))
    steps=nearby+[([],None,word) for word in plan]
    rows=[];hit=None;query_warnings=[]
    for group,radius,word in steps:
        rows=await attempt(group,r['city'],word,radius,progress,query_warnings)
        if rows:hit=(group,radius,word);break
    if hit and not hit[0]:
        progress('参照点周边未查到候选，已按城市范围补充')
    keyword=hit[2] if hit else preferred
    scope='周边%g公里'%(hit[1]/1000) if hit and hit[0] and hit[1] else '城市范围'
    items=[];seen=set()
    for p in rows:
        if p['id'] in seen:continue
        if any(x in p['name'] for x in ('售票','停车','厕所')):continue
        seen.add(p['id']);items.append(p)
    if items:
        w['catalog'].update({p['id']:p for p in items[:12]})
        w['food_query']={'ids':[p['id'] for p in items[:12]],'keyword':keyword,'scope':scope,'meal_date':args.get('meal_date'),'meal_period':args.get('meal_period'),'anchor':anchor['name'] if anchor else r['city']}
        progress('基础餐厅资料已到达，正在比较特色与核对通行')
        await recommend(w,items,'单独筛选5至6家餐厅，评分高的优先，按餐饮偏好与查询位置比较。只根据返回资料描述，不猜招牌菜、人均、景观或本地人比例。')
    # 早餐让早点铺占主要，其余按评分；午晚餐按评分。评分缺失的排在有评分之后。
    items.sort(key=lambda p:rank_food(p,args.get('meal_period'),bool(r.get('budget'))))
    items=items[:max(MEAL_LIMIT,6)]
    from .planning import route_options,choose_route
    from .access import screen
    progress('正在提前核对餐厅通行与当前餐次可用时段')
    meal=(args['meal_date'],args['meal_period']) if args.get('meal_date') and args.get('meal_period') in PERIODS else None
    by_id={p['id']:p for p in refs}
    items,excluded=await screen(w,items,lambda p:by_id.get(p.get('search_anchor_id')) or anchor,route_options,choose_route,meal)
    items=items[:MEAL_LIMIT]
    for p in items:
        period=PERIODS.get(args.get('meal_period'),'用餐')
        if p.get('search_anchor_id') is None:
            basis=period+'可结合'+r['city']+'当日行程安排（本次为城市范围候选，不是景点周边）'
        else:
            where=p.get('anchor_label') or '景区周边'
            basis=period+'可结合'+p['search_anchor']+'（'+where+'）安排'
            if p.get('anchor_distance_km') is not None:basis+=f'，距参照点直线约{p["anchor_distance_km"]}公里'
        if args.get('meal_period')=='breakfast' and is_breakfast_place(p):
            basis='早餐类店铺；'+basis
        p['recommendation_basis']=basis+'；实际通行与营业时段请核对。'
    # Each result retains the actual reference used for its query.
    markets=[]
    if keyword=='海鲜':
        market_refs,market_radius,_=hit or ([],None,None)
        market_ref=market_refs[0] if market_refs else None
        market_params={'city':r['city'],'keywords':'海鲜市场','category':'market','page_size':6}
        if market_ref:market_params.update(location=market_ref['location'],radius=market_radius)
        try:
            found=await local_tool('search_places',market_params)
            markets=[p for p in found.get('items',[]) if p.get('kind')=='market' and any(x in p.get('name','') for x in ('市场','水产批发'))][:2]
        except DataError:pass
    w['catalog'].update({p['id']:p for p in items+markets});w['food_query']={'ids':[p['id'] for p in items],'excluded':excluded,'markets':[p['id'] for p in markets],'keyword':keyword,'anchor':'、'.join(p['name'] for p in refs) if refs else r['city'],'anchors':[{'id':p['id'],'name':p['name']} for p in refs],'explicit_anchor_id':args.get('anchor_id'),'meal_date':args.get('meal_date'),'meal_period':args.get('meal_period'),'scope':scope};w['turn_food_updated']=True
    if items:
        note='（本次为%s候选）' % scope if scope=='城市范围' else ''
        return '已单独查询到'+str(len(items))+'家餐饮候选'+note+'，可在右侧“餐饮”按日期和餐次选择，也可以自行安排。'+(' '+query_warnings[0] if query_warnings else '')
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
