"""Revise a plan against all saved facts, then publish only a checked result."""
import copy
import re

from . import diagnostics, schedule, visit_analysis
from .enrichment import model_facts
from .providers import DataError

PROTECTED = ('requirements', 'selected_spots', 'visit_requests', 'visit_order',
             'hotel', 'stay_hotels','selected_rooms','selected_room', 'meal_choices', 'meal_mode',
             'selected_transport', 'selected_return', 'tickets')


def refine(w, text, intent):
    """A follow-up to a failed plan means repair the book, not just its preview."""
    if intent.get('action') not in ('chat', 'plan', 'analyze_visits', 'optimize_plan'):
        return intent
    if intent.get('action') == 'optimize_plan' or (
        (w.get('plan') or w.get('ui', {}).get('conflict') or w.get('last_plan_conflict')) and
        re.search(r'优化|修正|修复|调整一下|改一下|重新安排|重新规划|重排|放慢|轻松一点|少走路', text)
    ):
        generic=re.fullmatch(r'\s*(?:那|好的?[，,]?|请)?你?(?:帮我|给我)?再?(?:优化|修正|修复|调整|重排|重新安排|重新规划)(?:一?下|一?遍)?(?:吧|可以吗|好吗)?[。！!？?]*\s*',text)
        return {**intent, 'action': 'optimize_plan', 'view': 'plan',
                'instruction': text, 'conflict': copy.deepcopy(w.get('ui', {}).get('conflict') or w.get('last_plan_conflict')),
                **({'patch':{}} if generic else {}),
                'select_ids': [], 'remove_ids': []}
    return intent


def context(w, instruction, conflict=None):
    """Road geometries/media are omitted; their measured times and sources stay."""
    from .travel_preview import current
    route_preview=current(w)
    return model_facts({
        'user_request': instruction, 'current_plan': w.get('plan'),
        'reported_conflict': conflict or w.get('ui', {}).get('conflict') or w.get('last_plan_conflict'),
        'requirements': w['requirements'],
        'selected_places': [w.get('catalog', {}).get(i) for i in w.get('selected_spots', [])],
        'visit_requests': w.get('visit_requests', {}), 'visit_order': w.get('visit_order', []),
        'hotel': w.get('hotel'),'stay_hotels':w.get('stay_hotels'),'selected_rooms':w.get('selected_rooms'), 'selected_room': w.get('selected_room'),
        'meals': {k: {**v, 'food': w.get('catalog', {}).get(v.get('food_id'))}
                  for k, v in w.get('meal_choices', {}).items()},
        'meal_mode': w.get('meal_mode'), 'selected_transport': w.get('selected_transport'),
        'selected_return': w.get('selected_return'), 'tickets': w.get('tickets', {}),
        'weather': w.get('weather'), 'weather_note': w.get('weather_note'),
        'route_preview':route_preview,
        'official_guides': w.get('rag_results', []),
        'editable': ['灵活景点的游玩日和顺序', '建议时长与游览范围', '建议时段', '游玩说明'],
        'fixed': ['用户明确日期、时段、顺序', '已选景点、住宿、餐厅', '已选车票机票',
                  '旅行起止日期、人数、预算与节奏要求'],
    })


def check(w, plan):
    from .spot_hierarchy import state
    hierarchy=state(w)
    issues=list(hierarchy['issues']); seen=[]
    for day in plan.get('days', []):
        dt=day.get('date', ''); previous=-1
        for event in day.get('events', []):
            begin=schedule.minutes(event.get('start'), -1)
            end=schedule.minutes(event.get('end'), -1)
            if begin < previous or begin < 0 or end <= begin:
                issues.append(diagnostics.issue('revision_overlap', dt+'的'+event.get('name', '活动')+'时间衔接仍不合理。',
                    ids=[event['candidate_id']] if event.get('candidate_id') else [], dt=dt, retry=True))
            previous=end
            if event.get('kind') in ('spot','spot_continue'):
                cid=event.get('candidate_id')
                if event.get('kind')=='spot':seen.append(cid)
                pin=hierarchy['visit_requests'].get(cid, {})
                if pin.get('date') and pin['date']!=dt or (
                    pin.get('period')=='morning' and end>720 or
                    pin.get('period')=='afternoon' and (begin<780 or end>1080) or
                    pin.get('period')=='evening' and begin<1080
                ):
                    issues.append(diagnostics.issue('revision_fixed_time', event.get('name', '景点')+'的安排未能满足你指定的日期或时段。', ids=[cid], dt=dt))
        high=schedule.day_end(w,dt)
        if any(e.get('kind') in ('spot','spot_continue') and schedule.minutes(e.get('end'))>high for e in day.get('events', [])):
            issues.append(diagnostics.issue('revision_day_end', dt+'的建议游玩超过当前每日结束时间。可调整节奏或查看带警告的草稿；当前结束时刻不会自动延后。',dt=dt,level='warning',overrun_minutes=max(schedule.minutes(e.get('end')) for e in day['events'] if e.get('kind') in ('spot','spot_continue'))-high,available_minutes=max(0,high-schedule.minutes(w['requirements'].get('day_start','09:00')))))
    if len(seen)!=len(set(seen)) or set(seen)!=set(hierarchy['active_ids']):
        issues.append(diagnostics.issue('model_output', '修订没有完整保留全部已选景点，旧计划已保留，可重试。',view='plan',retry=True))
    for key, choice in w.get('meal_choices', {}).items():
        if choice.get('mode')!='chosen':continue
        dt, period=key.split('|');name=w.get('catalog',{}).get(choice.get('food_id'),{}).get('name','已选餐厅')
        if not any(e.get('kind')=='meal' and e.get('food',{}).get('id')==choice.get('food_id') and
                   e.get('name','').startswith(schedule.PERIODS[period][0])
                   for d in plan.get('days',[]) if d['date']==dt for e in d.get('events',[])):
            issues.append(diagnostics.issue('revision_missing_meal', dt+' '+schedule.PERIODS[period][0]+'的'+name+'仍未能放入日程。请核对餐次、营业资料及交通衔接。',view='food',ids=[choice['food_id']],dt=dt,meal_period=period))
    return issues


def changes(before, after):
    def places(plan):
        rows={}
        for d in (plan or {}).get('days',[]):
            for e in d.get('events',[]):
                if e.get('kind') not in ('spot','spot_continue') or not e.get('candidate_id'):continue
                cid=e['candidate_id'];existing=rows.get(cid)
                rows[cid]=(d['date'],existing[1] if existing else e.get('start'),e.get('end'),e.get('note'))
        return rows
    old=places(before);new=places(after);result=[]
    names={e['candidate_id']:e['name'] for d in after.get('days',[]) for e in d.get('events',[])
           if e.get('kind')=='spot' and e.get('candidate_id')}
    for cid, row in new.items():
        if row != old.get(cid):
            result.append(names[cid]+'：'+row[0]+' '+str(row[1])+'–'+str(row[2])+
                          ('（原安排 '+old[cid][0]+' '+str(old[cid][1])+'–'+str(old[cid][2])+'）' if cid in old else ''))
    return result


async def optimize(w, args, progress, model, generate):
    if not w.get('selected_spots'):
        raise DataError('请先选定景点并补充旅行日期，再优化计划书。')
    instruction=str(args.get('instruction') or '结合当前选择和冲突，优化完整计划书。')[:3000]
    working=copy.deepcopy(w);old_plan=copy.deepcopy(w.get('plan'))
    working['planning_revision']=context(w,instruction,args.get('conflict'))
    working.pop('planning_feedback',None)
    progress('正在结合原计划、已选地点、用餐、交通和冲突修订完整行程')
    await visit_analysis.analyze(working,model,progress,force=True)
    # Each generation already bounds proposal and real-route repair. One extra
    # revision is allowed only for a concrete error, with its entire context.
    for attempt in range(2):
        try:
            plan=await generate(working,progress)
            issues=check(working,plan)
            hard=[i for i in issues if i.get('level')!='warning']
            if hard:raise DataError('修订后的安排仍有具体条件需要调整，原计划已保留。',{'issues':hard,'view':hard[0]['view'],'candidate_ids':list(dict.fromkeys(i for x in hard for i in x['candidate_ids']))})
            plan.setdefault('planning_issues',[]).extend(i for i in issues if i.get('level')=='warning')
            if any(working.get(k)!=w.get(k) for k in PROTECTED):
                raise DataError('本次修订涉及更换已有选择，尚未取得确认，原计划已保留。')
            break
        except DataError as error:
            if attempt:raise
            working['planning_revision']['repair_feedback']={'message':str(error),'context':error.context}
            working['planning_feedback']=str(error)
            progress('正在根据具体冲突调整可变日期、顺序和游览范围，再核对实际路线')
    updated=changes(old_plan,plan)
    plan['revision']={'request':instruction,'changes':updated,'checked':True}
    from .plan_warnings import request,waiting
    if request(w,plan,'optimize_plan',working['visit_analysis'],working.get('time_policy')):
        return waiting()
    w['plan']=plan;w['visit_analysis']=working['visit_analysis'];w['stage']='计划书'
    w.pop('last_plan_conflict',None)
    if 'time_policy' in working:w['time_policy']=working['time_policy']
    w['ui']={'action':'optimize_plan','view':'plan','status':'loading'}
    text='旅行计划书已重新核对并更新，请查看右侧每日安排。'
    text+='\n'+'\n'.join(updated[:8]) if updated else '\n当前景点日期与时间已保留，本次重新核对了安排及说明。'
    return text+'\n车票、住宿、餐厅及明确指定的安排已保留。游览时间仍为建议；如需进一步调整，可直接发送消息。'
