"""Bounded candidate-leg checks; unknown provider results never mean impassable."""
import asyncio
from .providers import DataError
from .locations import coordinate
from .storage import now


async def check(w,p,anchor,route_options,choose_route,meal=None):
    r=w['requirements']
    stamp={'checked_at':now(),'anchor_id':anchor.get('id') if anchor else None,
           'anchor_name':anchor.get('name') if anchor else None,
           'origin':anchor.get('location') if anchor else None,'destination':p.get('location'),
           'meal_date':meal[0] if meal else None,'meal_period':meal[1] if meal else None}
    if not anchor or not coordinate(anchor.get('location')) or not coordinate(p.get('location')):
        return {**stamp,'status':'unknown','message':'缺少参照点或地点坐标，实际通行待核实'}
    start,end=(p,anchor) if p.get('kind')=='hotel' else (anchor,p)
    options=await route_options(start,end)
    chosen=choose_route(options,r)
    result={**stamp,'status':'available' if chosen else 'unknown','options':options}
    if chosen:
        result.update(route=chosen,message='从'+start['name']+'到'+end['name']+'，'+{'walking':'步行','driving':'驾车','transit':'公交'}.get(chosen['mode'],'通行')+'预计'+str(chosen['minutes'])+'分钟')
        if meal:
            from .schedule import meal_window,PERIODS
            from .planning import meal_allocation
            low,high=meal_window(w,*meal)
            # 通行缓冲与规划阶段共用同一口径，避免预检查放行、生成时报超时。
            allocation=meal_allocation(chosen['minutes'],r)
            needed=allocation['minutes']+PERIODS[meal[1]][2]
            result.update(minutes_needed=needed,allocation_basis=allocation['basis'])
            if low+needed>high:
                result.update(status='time_conflict',message='该餐次可用时段不足以容纳已查询通行（含'+str(allocation['buffer'])+'分钟机动）与完整用餐')
        if p.get('kind')=='food' and meal and meal[1]=='dinner' and coordinate((w.get('hotel') or {}).get('location')):
            back=await route_options(p,w['hotel']);result['return_options']=back
            back_route=choose_route(back,r)
            if back_route:
                result['return_route']=back_route
                from .schedule import day_limit
                from .planning import route_allocation
                limit=day_limit(w,meal[0])
                back_allocation=route_allocation(back_route['minutes'],r)
                if low+needed+back_allocation['minutes']>limit:
                    result.update(status='time_conflict',message='该餐次含前往餐厅、完整用餐及返回住宿的通行，超过当前结束或返程准备时刻')
            elif back and all(x.get('status')=='no_route' for x in back):result.update(status='no_route',message='当前已核对的方式均未返回餐厅至住宿的方案')
            else:result.update(status='unknown',message='已核对去餐厅通行，返回住宿方案尚未核实')
    elif options and all(x.get('status')=='no_route' for x in options):
        result.update(status='no_route',message='当前已核对的方式均未返回该路段方案，请更换地点或调整安排')
    else:result['message']='通行尚未核实：'+('；'.join(dict.fromkeys(x.get('reason','未知') for x in options if not x.get('available'))) or '缺少查询结果')
    return result


async def screen(w,items,anchor_for,route_options,choose_route,meal=None):
    """No more than three candidate checks at once, with a 20s batch budget."""
    sem=asyncio.Semaphore(3)
    async def one(p):
        async with sem:
            try:p['access']=await check(w,p,anchor_for(p),route_options,choose_route,meal)
            except DataError:p['access']={'status':'unknown','checked_at':now(),'message':'通行预检查暂未完成，可重试'}
    tasks=[asyncio.create_task(one(p)) for p in items]
    done,pending=await asyncio.wait(tasks,timeout=20) if tasks else (set(),set())
    if done:await asyncio.gather(*done)
    for t in pending:t.cancel()
    if pending:await asyncio.gather(*pending,return_exceptions=True)
    for p in items:
        if not p.get('access'):p['access']={'status':'unknown','checked_at':now(),'message':'通行预检查超时，可重试；未认定为不可通行'}
    excluded=[p for p in items if p['access']['status'] in ('no_route','time_conflict')]
    return [p for p in items if p not in excluded], [{ 'id':p['id'],'name':p['name'],**p['access']} for p in excluded]
