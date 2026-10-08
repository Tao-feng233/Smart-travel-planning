"""Small deterministic checks around the planner's proposed conversation action."""
import re
from datetime import date,timedelta

def travel_date(r,direction='return'):
    if direction=='outbound':return r.get('outbound_date') or r.get('start_date')
    return r.get('return_date') or ((date.fromisoformat(r['start_date'])+timedelta(days=int(r.get('days') or 2))).isoformat() if r.get('start_date') else None)

def return_date_confirmed(w):
    """返程日期是否已确定：用户明确给出返程日，或返程班次已经确认。

    只"选定"但仍是推荐态（selection_status='recommended'）不算确定，
    否则会把助手推荐的时间当成用户条件（复核报告 P4）。
    """
    r=w.get('requirements') or {}
    if r.get('return_date'):return True
    selected=w.get('selected_return') or {}
    return bool(selected.get('departure')) and selected.get('selection_status')=='confirmed'

def return_date_status(w):
    """返程日期口径：不把"游玩结束次日"或推荐态班次当成用户确认的条件。

    返回 {'date','status','basis'}；status 为 confirmed 或 suggested。
    未确定时给出待确认建议，由业务层保存来源与确认状态。
    """
    r=w.get('requirements') or {}
    explicit=r.get('return_date')
    if explicit:
        return {'date':explicit,'status':'confirmed','basis':'用户明确给出的返程日期'}
    selected=w.get('selected_return') or {}
    departure=selected.get('departure','')
    if departure and selected.get('selection_status')=='confirmed':
        return {'date':departure[:10],'status':'confirmed','basis':'已确认返程班次的出发日期'}
    if departure:
        return {'date':departure[:10],'status':'suggested',
                'basis':'返程班次目前是' + ('推荐待核对的日期 ' if selected.get('selection_status')=='recommended' else '尚未确认的日期 ')
                        + departure[:10] + '，需用户确认后才是确定条件'}
    suggested=travel_date(r)
    if not suggested:
        return {'date':None,'status':'suggested','basis':'出游日期尚未确定，无法给出返程建议'}
    return {'date':suggested,'status':'suggested',
            'basis':'按游玩天数推算的待确认建议（'+str(r.get('days'))+'天游玩后一日），尚未由用户确认'}

def meal_dates(r):
    if not r.get('start_date'):return []
    start=date.fromisoformat(r['start_date'])
    return [(start+timedelta(days=i)).isoformat() for i in range(int(r.get('days') or 2))]

def normal(s):return re.sub(r'[\W_]|酒店|景区|风景区','',s or '')

def is_local(r):
    clean=lambda s:re.sub(r'[市县区\s]+$','',str(s or ''))
    return bool(r.get('local_trip') or r.get('city') and r.get('origin') and clean(r['city'])==clean(r['origin']))

def date_interval(text,r):
    """Only explicit date intervals; never reinterpret a departure time window."""
    if re.search('返程|回程|车票|班次',text) and not re.search('游玩|行程|旅游',text):return {}
    iso=re.search(r'(\d{4}-\d{2}-\d{2})\s*(?:到|至|[~～—])\s*(\d{4}-\d{2}-\d{2})',text)
    if iso:begin,end=map(date.fromisoformat,iso.groups())
    else:
        match=re.search(r'(?:(\d{1,2})月)?(\d{1,2})[号日]\s*(?:到|至|[-~～—])\s*(?:(\d{1,2})月)?(\d{1,2})(?:号|日)?',text)
        if not match:return {}
        m1,d1,m2,d2=match.groups();base=date.fromisoformat(r.get('start_date') or date.today().isoformat())
        month=int(m1 or m2 or base.month);year=base.year
        begin=date(year,month,int(d1));end=date(year,int(m2 or month),int(d2))
        if not m2 and end<begin:
            month=month%12+1;end=date(year+(month==1),month,int(d2))
    return {'start_date':begin.isoformat(),'end_date':end.isoformat(),'days':(end-begin).days+1}

def refine_intent(w,text,intent):
    """Protect temporal slots and preserve mixed interests; ambiguity stays a question."""
    intent={**intent,'patch':dict(intent.get('patch') or {})};patch=intent['patch'];r=w['requirements']
    from .visits import from_text
    requests=from_text(w,text)
    if requests:
        intent.update(action='visit_schedule',visit_requests=requests,view='spot');patch.pop('start_date',None);patch.pop('end_date',None);patch.pop('days',None)
    if intent.get('action')=='visit_schedule' and not re.search('行程改|出游日期改|出发日期改|旅行日期改',text):
        patch.pop('start_date',None);patch.pop('end_date',None);patch.pop('days',None)
    patch.update(date_interval(text,{**r,**patch}))
    city=patch.get('city') or r.get('city')
    if city and re.search(r'(?:出发地|出发城市).*(?:目的地|游玩地|旅游地).*都(?:是|在)?'+re.escape(city),text):patch['origin']=city
    origin=re.search(r'从([\u4e00-\u9fff]{2,12})出发',text)
    if origin:patch['origin']=origin.group(1)
    if any(t in text for t in ('同城','本地游','就在当地','就在'+str(patch.get('city') or r.get('city') or '')+'玩')):
        city=patch.get('city') or r.get('city')
        if city and not (patch.get('origin') or r.get('origin')):patch['origin']=city
    if not intent.get('select_ids') and re.search('高铁|动车|火车',text) and not re.search('不要|不坐|不想',text):
        intent.update(action='train',view='transport')
        if '高铁' in text:intent['train_type']='highspeed'
        elif '动车' in text:intent['train_type']='regular'
        if re.search('返程|回程',text):intent['direction']='return'
        if '中午' in text:intent.update(time_start='11:00',time_end='14:00')
        elif '下午' in text:intent.update(time_start='12:00',time_end='18:00')
        elif '上午' in text or '早上' in text:intent.update(time_start='06:00',time_end='12:00')
    return_only='返程' in text and not re.search('去程|出发日期|开始日期|整个行程|整趟',text)
    if return_only:
        target=patch.pop('start_date',None)
        base=(w.get('selected_return') or {}).get('departure','')[:10] or travel_date(r)
        delta=re.search(r'(?:往后|延后|推迟|后移)(?:一|1)天|后一天',text)
        earlier=re.search(r'(?:往前|提前)(?:一|1)天|前一天',text)
        if base and (delta or earlier):target=(date.fromisoformat(base)+timedelta(days=1 if delta else -1)).isoformat()
        if target:patch['return_date']=target
        # Changing the return trip cannot reinterpret tour length / outbound date.
        patch.pop('days',None);patch.pop('outbound_date',None)
        if any(x in text for x in ('后一天','前一天','延后','往后','改','选')):
            intent.update(action=(w.get('selected_return') or {}).get('kind','train'),direction='return',replace=True,auto_select=any(x in text for x in ('随便选','帮我选','你选','选一个')),view='transport')
    if any(x in text for x in ('不出名','不太出名','没听过','知名','著名','热门')) and intent.get('action') in ('spots_page','search_spots','chat'):
        intent.update(action='search_spots',view='spot',prefer_known=True)
        from .discovery import classic_names
        names=classic_names(r.get('city',''))
        if names:intent['keywords']=names[:4]
        patch['preferences']=list(patch.get('preferences') or [])+['优先城市代表景点']
    if any(x in text for x in ('不吃海鲜','不要海鲜','不想吃海鲜')):
        r['food_preferences']=[x for x in r.get('food_preferences',[]) if '海鲜' not in x]
        r['preferences']=[x for x in r.get('preferences',[]) if '海鲜' not in x]
        w['food_query']=None;w['meal_choices']={};intent['include_food']=False
        if intent.get('action')=='search_foods':intent['food_keywords']=['当地餐厅'];intent['keywords']=['当地餐厅']
        patch['food_preferences']=[x for x in patch.get('food_preferences',[]) if '海鲜' not in x]
        patch['preferences']=[x for x in patch.get('preferences',[]) if '海鲜' not in x]
    elif any(x in text for x in ('海鲜','海鲜市场')):
        patch['food_preferences']=list(patch.get('food_preferences') or [])+['海鲜']
        # Food is not a scenic search keyword.
        if intent.get('keywords'):intent['keywords']=[x for x in intent['keywords'] if not any(t in x for t in ('海鲜','餐厅','餐馆','饭店'))]
        intent['include_food']=True
    if not r.get('food_preferences') and any('海鲜' in x for x in r.get('preferences',[])):
        patch.setdefault('food_preferences',['海鲜'])
    if any(x in text for x in ('下一步','接下来干什么','然后干什么')):
        intent.update(action='chat',view=next_step(w)['view'])
        intent['keywords']=[];intent['select_ids']=[]
    if any(x in text for x in ('自己吃','自己找','自行安排','不选餐','不用安排吃','不安排餐')):
        intent.update(action='meal_choice',meal_mode='self',view='food')
    selecting=any(x in text for x in ('选这个','选那个','就这','帮我选','选择','选好','换成','改成','要这个'))
    if selecting and not return_only:
        # Prefer candidates actually shown, not arbitrary rows from older searches.
        ids=list((w.get('hotel_query') or {}).get('ids',[]))
        ids+=list((w.get('food_query') or {}).get('ids',[]))
        if w.get('spot_search'):
            from .discovery import page_info
            ids+=page_info(w)['ids']
        ids+=list(p.get('id') for p in (w.get('transport') or {}).get('items',[]))
        candidates=[w['catalog'][i] for i in dict.fromkeys(ids) if i in w['catalog'] and not w['catalog'][i].get('stale')]
        matches=[p for p in candidates if len(normal(p['name']))>=2 and (normal(p['name']) in normal(text) or p['name'] in text)]
        if len(matches)==1 and not intent.get('room_id'):
            intent['select_ids']=[matches[0]['id']];intent['replace']=any(x in text for x in ('换','改','替换'))
            if matches[0].get('kind')=='food' and intent.get('action')=='meal_choice':
                intent['food_id']=matches[0]['id'];intent['select_ids']=[]
            if intent.get('action') in ('search_hotels','search_spots','chat'):intent['action']='chat'
    return intent

def next_step(w):
    if w.get('plan') and not w['plan'].get('stale'):
        return {'message':'请查看已生成的旅行计划书；如需调整日期、景点、住宿或餐饮，直接在对话中告诉我。','view':'plan','label':'查看计划书'}
    r=w['requirements'];missing=[label for k,label in [('city','目的地'),('start_date','出游日期'),('days','游玩天数'),('adults','成人数')] if not r.get(k)]
    if not r.get('city'):return {'message':'请先在右侧选定旅游地区，或在对话中告诉我目的地。选定后再比较具体景点，并补充出游日期与人数。','view':'spot','missing':missing}
    if missing:return {'message':'请补充'+ '、'.join(missing)+'，可直接在对话中提供或手动填写。','view':'hotel' if w.get('spots_confirmed') else 'spot','missing':missing}
    if not w.get('selected_spots'):return {'message':'请在右侧选择想去的景点。','view':'spot'}
    if not w.get('spots_confirmed'):return {'message':'请先完成当前景点选择，点击“完成景点选择”；完成后比较住宿位置与房型。','view':'spot','action':'complete_spots','label':'完成景点选择'}
    skip_stay=w.get('stay_skipped') or int(r.get('days') or 0)==1
    if not skip_stay and not w.get('hotel'):return {'message':'请比较住宿，也可以选择暂不安排住宿。','view':'hotel'}
    if not skip_stay and not w.get('selected_room'):return {'message':'住宿已保存。请选择具体房型，或暂不安排住宿。','view':'hotel'}
    if is_local(r):return dining_step(w)
    if not r.get('origin'):return {'message':'请补充出发城市，然后查询往返交通。','view':'transport','missing':['出发城市']}
    for slot,label in [('selected_transport','去程'),('selected_return','返程')]:
        tr=w.get(slot)
        if not tr:return {'message':'请选定'+label+'班次。','view':'transport'}
        if tr.get('selection_status')=='recommended':return {'message':'请核对并确认推荐的'+label+'班次。','view':'transport'}
    return dining_step(w)

def dining_step(w):
    if not w.get('dining_reviewed') and w.get('meal_mode')!='self':
        return {'message':'请先查看餐饮安排，可按日期和餐次选餐厅，也可明确选择自行安排；完成后生成旅行计划书。','view':'food','action':'search_foods','label':'查看周边餐厅'}
    return {'message':'景点、住宿、交通与餐饮安排已基本完成，可以生成旅行计划书。','view':'plan','action':'plan','label':'生成旅行计划书'}

def selection_assessment(w):
    import math
    spots=[w['catalog'][i] for i in w.get('selected_spots',[]) if i in w['catalog']];days=int(w['requirements'].get('days') or 0)
    messages=[];coords=[]
    for p in spots[:120]:
        try:coords.append(tuple(map(float,p['location'].split(','))))
        except (KeyError,TypeError,ValueError):pass
    def distance(a,b):
        x1,y1,x2,y2=map(math.radians,(*a,*b))
        return 6371*2*math.asin(min(1,math.sqrt(math.sin((y2-y1)/2)**2+math.cos(y1)*math.cos(y2)*math.sin((x2-x1)/2)**2)))
    spread=max((distance(a,b) for i,a in enumerate(coords) for b in coords[i+1:]),default=0)
    parents={p.get('parent_id') for p in spots if p.get('parent_id')};main_count=len({p.get('parent_id') or p['id'] for p in spots})
    if days and main_count>max(5,days*3):messages.append(f'已选约{main_count}组游览地点，{days}天安排可能偏紧，建议标记必去地点或增加天数。')
    if days and spread>=50 and days<=4:messages.append(f'地点之间最大直线跨度约{math.ceil(spread)}公里，实际通行可能更远，请考虑减少跨区域往返。')
    return {'messages':messages,'level':'warning' if messages else 'normal','spread_km':round(spread,1),'count':len(spots),'days':days}

def coordinate_distance(a,b):
    import math
    try:
        x1,y1,x2,y2=map(math.radians,(*map(float,a['location'].split(',')),*map(float,b['location'].split(','))))
        return 6371*2*math.asin(min(1,math.sqrt(math.sin((y2-y1)/2)**2+math.cos(y1)*math.cos(y2)*math.sin((x2-x1)/2)**2)))
    except (KeyError,ValueError,TypeError):return 0
