"""Bounded, source-backed destination discovery and distinct POI recommendation pages."""
import asyncio,json,re,math
from .config import ROOT
from .tools import local_tool
from .providers import DataError
from .data_contracts import guide_conditions

PAGE_SIZE=4
MAX_RECOMMENDATIONS=24

def destinations():
    from .data_coverage import snapshot
    return list(snapshot()['cities'].values())

def classic_names(city):
    return next((d['highlights'] for d in destinations() if d['name'] in city),[])

def clean_name(name):
    return re.sub(r'[（(].*?[）)]|风景区|景区|公园|\s','',name)

def main_pois(items):
    result=[];seen=set()
    for p in items:
        name=p.get('name','')
        if p.get('kind')!='spot' or str(p.get('typecode') or '').startswith('05') or any(x in name for x in ('餐厅','海鲜火锅','海鲜自助')):continue
        if any(x in name for x in ('停车场','售票处','售票点','检票','出入口','游客中心','服务中心','公共厕所','卫生间','电动车充电')):continue
        if re.search(r'(?:东|西|南|北|正|入口|出口)门(?:$|[（(])',name):continue
        key=clean_name(name)
        if p['id'] in seen or ('name',key) in seen:continue
        seen.add(p['id']);seen.add(('name',key));result.append(p)
    return result

def visible(w):
    search=w.get('spot_search') or {};rejected=set(w.get('rejected_spots',[]))
    return [cid for cid in search.get('ids',[])[:MAX_RECOMMENDATIONS] if cid not in rejected and cid in w['catalog']]

def page_info(w):
    search=w.get('spot_search') or {};grouped=groups(w);page=max(1,min(int(search.get('page',1)),max(1,math.ceil(len(grouped)/PAGE_SIZE))))
    displayed=grouped[(page-1)*PAGE_SIZE:page*PAGE_SIZE]
    return {'page':page,'pages':max(1,math.ceil(len(grouped)/PAGE_SIZE)),
            'ids':list(dict.fromkeys(i for g in displayed for i in ([g['parent_id']] if g.get('parent_id') else [])+g['ids'] if i in w['catalog'])),
            'has_more':False}

def groups(w):
    from .spot_hierarchy import ancestors
    catalog=w.get('catalog',{});ids=visible(w);result=[];by={}
    prefixes={}
    for cid in ids:
        p=catalog[cid];name=p.get('name','');parts=re.split('[·•]',name,maxsplit=1)
        if len(parts)==2 and len(parts[0])>=3:prefixes.setdefault(parts[0],[]).append(cid)
    for cid in ids:
        p=catalog[cid];chain=ancestors(catalog,cid);parent=chain[-1] if chain else None;name=p.get('name','');prefix=re.split('[·•]',name,maxsplit=1)[0]
        if parent:
            key=parent;title=catalog.get(parent,{}).get('name') or prefix;basis='地图父子关系'
        elif len(prefixes.get(prefix,[]))>=2:key='name:'+prefix;title=prefix;basis='名称关联，所属关系待核实'
        else:key=cid;title=name;basis=None
        if key not in by:
            item={'key':key,'title':title,'parent_id':parent if parent in catalog else cid if not basis else None,'ids':[],'basis':basis};by[key]=item;result.append(item)
        by[key]['ids'].append(cid)
        if parent:by[key]['basis']='地图父子关系'
    for g in result:
        g['ids']=list(dict.fromkeys(g['ids']))
        if g['parent_id'] in w.get('rejected_spots',[]):g['parent_id']=None
    return result

async def fetch(w,keywords,page_num):
    results=await asyncio.gather(*(local_tool('search_places',{'city':w['requirements']['city'],'keywords':q,'category':'spot','page':page_num,'page_size':12}) for q in keywords),return_exceptions=True)
    rows=[];successful=False;has_more=False
    for result in results:
        if isinstance(result,Exception):continue
        successful=True;items=result.get('items',[]);rows.extend(items);has_more|=len(items)>=12
    if not successful:raise DataError('景点查询暂时不可用，请稍后重试。')
    rejected=set(w.get('rejected_spots',[]));names=set(w.get('rejected_spot_names',[]))
    from .data_coverage import place_known
    return [p for p in main_pois(rows) if place_known(w['requirements']['city'],p['name']) and p['id'] not in rejected and clean_name(p['name']) not in names],has_more

async def search(w,args,progress,recommend):
    from .data_coverage import require_city,require_place
    require_city(w['requirements']['city'])
    if args.get('requested_place'):require_place(w['requirements']['city'],args['requested_place'])
    city=w['requirements']['city'];classic=classic_names(city)
    expanding=args.get('expand_spots') is True;previous=w.get('spot_search') or {}
    history=list(dict.fromkeys(previous.get('history_ids',[])+previous.get('ids',[]))) if previous.get('city')==city else []
    seen_names={clean_name(w['catalog'][cid]['name']) for cid in history if cid in w['catalog']}
    if args.get('reject_current'):
        for cid in page_info(w)['ids']:
            if cid not in w['selected_spots']:reject_one(w,cid)
    keywords=[str(x)[:40] for x in (args.get('keywords') or (previous.get('keywords') if expanding else None) or classic[:3]+['风景名胜'])[:4]]
    progress('正在查询景点并筛选重复地点与附属设施')
    page=previous.get('provider_page',1)+1 if expanding else 1
    items,more=await fetch(w,keywords,page)
    if expanding:
        items=[p for p in items if p['id'] not in history and p['id'] not in w['selected_spots'] and clean_name(p['name']) not in seen_names]
        if not items and more and page<3:
            page+=1;items,more=await fetch(w,keywords,page)
            items=[p for p in items if p['id'] not in history and p['id'] not in w['selected_spots'] and clean_name(p['name']) not in seen_names]
        if not items:return '本轮暂未找到新的相关景点，已有推荐与选择已保留。可以补充感兴趣的主题或希望扩展的区域，再继续推荐。'
    if not items:raise DataError('未找到新的景点候选，请调整兴趣或搜索名称。')
    from .locations import ready_candidates
    items,location_excluded=await ready_candidates(w,items,local_tool)
    if not items:return '本次景点候选尚未核对到有效坐标，暂不列入推荐。可以更换搜索条件或稍后重试；已有选择保留。'
    items=items[:MAX_RECOMMENDATIONS]
    w['catalog'].update({p['id']:p for p in items});w['candidates']=items
    from .spot_hierarchy import candidates
    items=candidates(w['catalog'],items)
    w['spot_search']={'city':city,'keywords':keywords,'ids':[p['id'] for p in items],'page':1,'provider_page':page,'history_ids':history,'exhausted':True}
    w['discovery_mode']=False
    progress('基础景点资料已到达，正在补充推荐与通行核对')
    for p in items:
        p['classic']=any(clean_name(n)==clean_name(p['name']) for n in classic)
        if p['classic']:p['discovery_label']='城市代表景点'
    guides=(await local_tool('retrieve_guides',guide_conditions(city,' '.join(p['name'] for p in items)+' 游览 特色',w['requirements'])))['items']
    progress('正在按旅行偏好比较推荐顺序')
    summary=await recommend(w,items,('补充新相关景点，保留已选景点与偏好，避免重复；' if expanding else '结合已知游玩天数推荐能组成整趟旅行的景点集合，并提供适量备选；')+'数量按预计停留与休息、位置和需求判断。优先匹配条件，其次参考城市代表景点，不把评分当实时热门榜',guides)
    items.sort(key=lambda p:((not p.get('classic')) if args.get('prefer_known') else False,p.get('recommendation_rank',99),not p.get('classic'),-(float(p.get('rating') or 0) if str(p.get('rating') or '').replace('.','',1).isdigit() else 0)))
    # Publish a bounded set actually compared by the model, rather than all raw API rows.
    ranked=[p for p in items if p.get('recommendation_rank') is not None]
    items=(ranked or items)[:MAX_RECOMMENDATIONS]
    from .planning import route_options,choose_route
    from .access import screen
    anchor=w.get('hotel') or next((w['catalog'].get(cid) for cid in w.get('selected_spots',[]) if w['catalog'].get(cid,{}).get('location')),None)
    if anchor and not anchor.get('stale'):
        progress('正在提前核对景点与已选区域的通行')
        items,excluded=await screen(w,items,lambda p:anchor,route_options,choose_route)
    else:excluded=[]
    w['catalog'].update({p['id']:p for p in items});w['candidates']=items;w['rag_results']=guides
    missing=list(dict.fromkeys(p['parent_id'] for p in items if p.get('parent_id') and p['parent_id'] not in w['catalog']))[:4]
    if missing:
        try:
            parents=await local_tool('get_place_details',{'ids':missing})
            w['catalog'].update({p['id']:p for p in parents.get('items',[]) if p.get('kind')=='spot'})
        except DataError:pass
    w['spot_search']={'city':city,'keywords':keywords,'provider_page':page,'page':1,'ids':[p['id'] for p in items],'history_ids':history,'excluded':location_excluded+excluded,'exhausted':True}
    w['discovery_mode']=False
    if not expanding:w['spots_confirmed']=False
    w['stage']='景点'
    return f'已{"补充" if expanding else "推荐"}{len(items)}个景点，已展示在右侧，可分页比较行程建议与备选。'+summary

async def turn_page(w,args,progress,recommend):
    search=w.get('spot_search')
    if not search:
        if args.get('reject_current'):
            for p in list(w['catalog'].values()):
                if p.get('kind')=='spot' and p['id'] not in w['selected_spots']:reject_one(w,p['id'])
        raise DataError('尚无本轮推荐，请先通过对话筛选景点。')
    current=page_info(w);reject=bool(args.get('reject_current'))
    if reject:
        for cid in current['ids']:
            if cid not in w['selected_spots']:reject_one(w,cid)
    target=int(args.get('page') or (current['page'] if reject else current['page']+1))
    if target<1 or target>50:raise DataError('无效的景点页码。')
    pages=max(1,math.ceil(len(groups(w))/PAGE_SIZE))
    if target>pages:raise DataError('当前推荐没有更多页面。可以在对话中让我重新筛选或指定其他景点名称；已选内容保留。')
    search['page']=target;w['discovery_mode']=False
    return f'已显示第{target}页景点。'+('已排除本页未选择的候选。' if reject else '已有选择保留。')+'选择完成后点击“完成景点选择”。'

async def search_initial(w,progress,recommend):return await search(w,{},progress,recommend)

def reject_one(w,cid):
    p=w['catalog'].get(cid)
    if not p or p.get('kind')!='spot':raise DataError('景点候选已失效。')
    if cid in w['selected_spots']:raise DataError('请先取消选择，再标记为不感兴趣。')
    w['rejected_spots']=list(dict.fromkeys(w.get('rejected_spots',[])+[cid]))
    w['rejected_spot_names']=list(dict.fromkeys(w.get('rejected_spot_names',[])+[clean_name(p['name'])]))
