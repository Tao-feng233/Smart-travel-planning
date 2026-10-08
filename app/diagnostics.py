"""Actionable scheduling failures without blaming valid user choices."""
from . import schedule, visits


def issue(code, message, view='spot', ids=None, dt='', **extra):
    return {'code':code, 'message':message, 'view':view, 'candidate_ids':ids or [], 'date':dt, **extra}


def invalid_dates(w, ids, allowed_dates):
    result=[]
    for cid in ids:
        request=w.get('visit_requests',{}).get(cid,{})
        if request.get('date') and request['date'] not in allowed_dates:
            name=w['catalog'].get(cid,{}).get('name','该景点')
            result.append(issue('fixed_date_range',name+'指定在'+request['date']+'游玩，但当前游玩范围为'+allowed_dates[0]+'至'+allowed_dates[-1]+'。请改回范围内的日期，或调整旅行日期。',ids=[cid],dt=request['date'],settings=True))
    return result


def from_error(w, context, message):
    if context and context.get('issues'): return context
    if not context and not any(word in message for word in ('景点','餐厅','班次','房型','日期','餐次')): return context
    context=dict(context or {})
    ids=context.get('candidate_ids') or [cid for cid,p in w.get('catalog',{}).items() if len(p.get('name',''))>1 and p['name'] in message]
    view=context.get('view') or w.get('ui',{}).get('view') or 'spot'
    current=issue('selection_condition',message,view=view,ids=ids,dt=context.get('date',''),
        **{k:context[k] for k in ('direction','meal_period','settings') if k in context})
    if not ids and any(word in message for word in ('请先补充','请补充','确定日期','出游日期')):current['settings']=True
    return {**context,'candidate_ids':ids,'view':view,'issues':[current]}


def proposal(w, errors, groups, allowed_ids, allowed_dates, time_context=None):
    result=invalid_dates(w,allowed_ids,allowed_dates)
    cat=w.get('catalog',{});seen={i['candidate_id'] for d in groups for i in d.get('items',[])}
    identity=any(e.startswith(('未选择ID','重复ID','遗漏ID','JSON','无效日期','当前阶段之外','日期重复','时长必须')) for e in errors)
    if identity:
        missing=[cat[i]['name'] for i in sorted(set(allowed_ids)-seen) if i in cat]
        message='模型本次生成的安排没有完整对应你的已选景点或游玩日期。'
        if missing:message+='尚未安排：'+'、'.join(missing[:12])+'。'
        message+='已有选择无需因此修改，可按当前选择重新生成。'
        result.append(issue('model_output',message,view='plan',retry=True))
    for cid in allowed_ids:
        pin=w.get('visit_requests',{}).get(cid,{})
        if pin.get('date') in allowed_dates and any(i['candidate_id']==cid and (d['date']!=pin['date']) for d in groups for i in d.get('items',[])):
            result.append(issue('model_fixed_date',cat.get(cid,{}).get('name','景点')+'指定在'+pin['date']+'游玩，模型没有遵守该日期。可重新生成；如需修改原安排，也可点击查看。',ids=[cid],dt=pin['date'],retry=True))
    from . import visit_analysis
    budgets={b['date']:b for b in visit_analysis.budgets(w)}
    for day in groups:
        dt=day['date'];items=day.get('items',[]);budget=budgets.get(dt)
        if not items or not budget:continue
        load=sum(i['duration']+20 for i in items)
        if load>budget['visit_minutes']:
            ids=[i['candidate_id'] for i in items];names='、'.join(cat.get(i,{}).get('name','景点') for i in ids)
            message=dt+'安排了'+names+'，建议游玩及转场预留约'+str(load)+'分钟，而扣除用餐后的估算可用时间为'+str(budget['visit_minutes'])+'分钟。'
            message+='可把可调整的景点移到其他游玩日、减少当日活动，或延长可用时段。'
            extra={}
            if time_context and time_context.get('date')==dt:
                direction=time_context.get('direction');extra['direction']=direction
                p=w.get('selected_return' if direction=='return' else 'selected_transport') or {}
                moment=p.get('departure' if direction=='return' else 'arrival','')
                message+='当前'+('返程出发' if direction=='return' else '去程抵达')+'为'+p.get('name','所选班次')+' '+moment+'，接驳准备时间仍是估算预留。'
            result.append(issue('day_capacity',message,ids=ids,dt=dt,optimize=True,**extra))
    if not result and any('每日负担明显失衡' in e for e in errors):
        dates=[d['date'] for d in groups if d.get('items')]
        result.append(issue('unbalanced_draft','模型仍将游玩时间集中在'+('、'.join(dates) or '少数日期')+'，其他日期有可用时间。可点击优化分配或重新生成；当前已选地点保留。',ids=list(allowed_ids),retry=True,optimize=True))
    if not result:
        result.append(issue('proposal_incomplete','本次自动安排未能满足已选地点、指定时段或可用时间。请先查看当前安排，或按原选择重新生成；无需重新选择所有内容。',ids=list(allowed_ids),retry=True,optimize=True))
    context={**(time_context or {}),'phase':'proposal','issues':result,'candidate_ids':list(dict.fromkeys(i for x in result for i in x['candidate_ids'])),'view':result[0]['view']}
    model_only=all(x['code'].startswith('model') or x['code']=='unbalanced_draft' for x in result)
    context['model_output_error']=model_only
    title='这次自动安排未能完整生成，已有选择保留。' if model_only else '这次安排有需要核对的日期或时间条件，已有选择保留。'
    return title,context
