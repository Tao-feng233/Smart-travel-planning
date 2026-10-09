"""Suggested midday rest and leisure buffers shared by preview and planning."""
import math


def normalize(row):
    out={}
    for key,default,low,high in [('rest_minutes',60,30,120),('break_minutes',30,15,60)]:
        value=row.get(key,default)
        if isinstance(value,bool) or not isinstance(value,int) or not low<=value<=high:raise ValueError('午休或机动时间建议超出有效范围')
        out[key]=math.ceil(value/15)*15
    import re
    for key,low,high in [('breakfast_time',450,570),('lunch_time',660,840),('dinner_time',990,1200)]:
        value=row.get(key)
        if value is None:continue
        if not isinstance(value,str) or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d',value):raise ValueError('餐次时间格式无效')
        h,m=map(int,value.split(':'));at=h*60+m
        if not low<=at<=high:raise ValueError('建议餐次时间超出可调整窗口')
        out[key]=value
    for key,default,low,high in [('breakfast_minutes',45,30,60),('lunch_minutes',75,45,90),('dinner_minutes',60,45,90)]:
        value=row.get(key,default)
        if isinstance(value,bool) or not isinstance(value,int) or not low<=value<=high:raise ValueError('用餐时长无效')
        out[key]=value
    out['reason']=str(row.get('reason') or '为午餐后休息、拍照和临时停留保留宽裕时间。')[:240]
    return out


def for_day(w,dt):
    from .visit_analysis import current
    rows=w.get('_pacing_override')
    if rows is None:rows=(current(w) or {}).get('day_pacing',[])
    row=next((x for x in rows if x.get('date')==dt),{})
    policy=normalize(row)
    explicit=w['requirements'].get('midday_rest_minutes')
    if explicit is not None:policy['rest_minutes']=explicit
    policy['basis']='model_estimate' if row else 'initial_estimate'
    return policy


def rest_length(w,dt,start):
    from .schedule import windows
    # Do not manufacture a nap on a late arrival or beyond a train deadline.
    if start>=16*60:return 0
    high=windows(w,dt)[1]
    return max(0,min(for_day(w,dt)['rest_minutes'],high-start,1440-start))


def reserved(w,dt,low,high):
    from .schedule import meal_start,PERIODS
    lunch=meal_start(w,dt,'lunch')
    if lunch is None:return 0
    start=lunch+meal_duration(w,dt,'lunch')
    return max(0,min(high,start+rest_length(w,dt,start))-max(low,start))


def meal_time(w,dt,period):
    defaults={'breakfast':480,'lunch':720,'dinner':1020}
    value=for_day(w,dt).get(period+'_time')
    if not value:return defaults[period]
    h,m=map(int,value.split(':'));return h*60+m


def meal_duration(w,dt,period):
    return for_day(w,dt)[period+'_minutes']
