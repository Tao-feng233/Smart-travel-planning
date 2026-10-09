"""Reviewable planning warnings: publish a cached draft only after consent."""
import copy
import time
import uuid

from .auto_selection import signature as selection_signature
from .providers import DataError

def signature(w):
    import hashlib,json
    value={'choices':selection_signature(w),'visit_analysis':w.get('visit_analysis')}
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True).encode()).hexdigest()

SOFT_CODES={'estimated_capacity','estimated_period_capacity','unbalanced_estimate','revision_day_end'}


def request(w,plan,action='plan',analysis=None,time_policy=None):
    from .schedule_quality import serious
    issues=[]
    for item in plan.get('planning_issues',[]):
        if item.get('code') not in SOFT_CODES or not serious(item):continue
        if item.get('code')=='revision_day_end' and any(i['code']==item['code'] and i.get('date')==item.get('date') for i in issues):continue
        issues.append(item)
    if not issues:
        w.pop('pending_plan_warning',None)
        return False
    w['pending_plan_warning']={'id':uuid.uuid4().hex,'signature':signature(w),'expires':time.time()+900,
        'issues':copy.deepcopy(issues),'plan':copy.deepcopy(plan),'action':action,
        'analysis':copy.deepcopy(analysis),'time_policy':copy.deepcopy(time_policy)}
    w['ui']={'action':action,'view':'plan','status':'loading'}
    return True


def waiting():
    return '当前安排有估算偏紧或分配不均的提醒，并不代表无法出行。请查看警告后选择“继续生成带警告的草稿”，或返回调整。当前选择及原计划保留。'


def approve(w,args):
    pending=w.get('pending_plan_warning')
    if not pending or args.get('approval_id')!=pending['id'] or args.get('confirmed') is not True:
        raise DataError('请先在规划提醒窗口确认是否继续生成。')
    if pending['expires']<time.time() or pending['signature']!=signature(w):
        w.pop('pending_plan_warning',None)
        raise DataError('旅行条件或已选内容已变化，请重新生成并核对最新提醒。')
    plan=copy.deepcopy(pending['plan'])
    plan['warning_acceptance']={'confirmed':True,'codes':[i['code'] for i in pending['issues']]}
    for item in pending['issues']:
        text='规划提醒（已选择继续）：'+item['message']
        if text not in plan.setdefault('warnings',[]):plan['warnings'].append(text)
    w['plan']=plan
    if pending.get('analysis') is not None:w['visit_analysis']=pending['analysis']
    if pending.get('time_policy') is not None:w['time_policy']=pending['time_policy']
    w['stage']='计划书';w.pop('pending_plan_warning',None);w.pop('last_plan_conflict',None)
    w['ui']={'action':'plan','view':'plan','status':'loading'}
    return '已按你的确认生成带警告的旅行草稿，请查看计划书中的规划提醒。估算偏紧及分配不均已保留说明，尚未核实的条件不视为可执行保证。可直接发送消息继续调整。'


def cancel(w):
    w.pop('pending_plan_warning',None)
    w['ui']={'action':'cancel_plan_warning','view':'plan','status':'loading'}
    return '已返回调整，当前选择及原计划保留。可修改景点安排、日期或节奏后重新生成。'
