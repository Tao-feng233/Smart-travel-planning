"""Route-aware provisional schedule without another model-generation call."""
import asyncio
import hashlib
import json
import time

from . import visit_analysis
from .providers import DataError


def signature(w):
    endpoints=[w.get('hotel')]+[w.get('catalog',{}).get(cid) for cid in w.get('selected_spots',[])]
    value={'version':3,'visit_inputs':visit_analysis.signature(w),'analysis':visit_analysis.current(w),
        'endpoints':[{k:p.get(k) for k in ('id','location','entrance','citycode')} for p in endpoints if p],
        'selected_rooms':w.get('selected_rooms',{}),'selected_room':w.get('selected_room'),'meal_choices':w.get('meal_choices',{}),'meal_mode':w.get('meal_mode'),
        'foods':[{k:w.get('catalog',{}).get(c.get('food_id'),{}).get(k) for k in ('id','name','location','entrance','citycode')}
                 for c in w.get('meal_choices',{}).values() if c.get('mode')=='chosen']}
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def current(w):
    value=w.get('travel_preview')
    return value if value and value.get('status')=='ready' and value.get('signature')==signature(w) and value.get('expires',0)>time.time() else None


async def refresh(w,progress,*,model=None,optimize=False):
    if not w.get('selected_spots') or not w['requirements'].get('start_date'):return
    if current(w):return
    from .planning import _generate
    from .planning import local_tool,route_options,choose_route
    from .transport_links import resolve
    from .schedule import plan_rows
    await resolve(w,progress,local_tool,route_options,choose_route)
    stamp=signature(w)
    progress('正在核对住宿、景点与已选餐厅之间的通行，并更新时间轴')
    try:
        async with asyncio.timeout(25):plan=await _generate(w,progress,preview=True)
    except (DataError,TimeoutError) as error:
        message=str(error) or '通行核对超时，可继续选择或稍后重试。'
        from .diagnostics import from_error
        w['travel_preview']={'signature':stamp,'status':'pending','message':message,
            'issues':from_error(w,getattr(error,'context',None),message),'expires':time.time()+60}
        if optimize and model and getattr(error,'context',{}):
            from .timeline_tools import optimize as repair
            try:
                async with asyncio.timeout(45):await repair(w,model,progress,conflict={'message':message,'context':getattr(error,'context',None)})
            except TimeoutError:pass
        return
    w['travel_preview']={'signature':signature(w),'status':'ready','expires':time.time()+900,
        'entries':plan_rows(w,plan,provisional=True),'warnings':plan.get('warnings',[]),
        'planning_issues':plan.get('planning_issues',[]),'parent_coverage':plan.get('parent_coverage',{})}

    if optimize and model:
        from .timeline_tools import optimize as repair
        try:
            async with asyncio.timeout(45):await repair(w,model,progress)
        except TimeoutError:pass
