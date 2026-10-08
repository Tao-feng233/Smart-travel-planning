"""Bounded proposal batches for long trips; every selected ID is validated once."""
import json,math

def _fit_days(movable,allowed_tour,cap,used,step_budget=20000,rest=None):
    """把可调整景点装进各日剩余容量；能装下返回分配，装不下返回 None。

    贪心（最紧优先）会把 150+150 塞满两天、剩下两个装不下；这里用有限的
    深度优先搜索，先放大件、优先放剩余最多的日期，属于"有限顺序比较"，
    不是全局最优求解。节点数有上限，超限即放弃并让调用方给出可读原因。
    ``used`` 是每天已排的景点数：同一天第二处起要额外占休息与机动。
    """
    from .schedule import REST_BETWEEN_MINUTES
    rest=REST_BETWEEN_MINUTES if rest is None else rest
    order=sorted(movable,key=lambda x:-x['duration'])
    assignment={}
    nodes=[0]

    def need_on(dt,duration):
        # 当天已经排过景点时，这一处前面还要一段参观间休息。
        return duration+(rest if used.get(dt) else 0)

    def place(index):
        if index==len(order):return True
        nodes[0]+=1
        if nodes[0]>step_budget:return False
        item=order[index]
        options=[dt for dt in allowed_tour if cap[dt][0]>=need_on(dt,item['duration']) and item['duration']<=cap[dt][1]]
        # 先试剩余最多的日期，让大件有位置；失败再回退换一天。
        # 排序先取快照，避免 key 在容量变化后再被重新求值。
        ranked=sorted(options,key=lambda d:cap[d][0],reverse=True)
        for dt in ranked:
            cost=need_on(dt,item['duration'])
            cap[dt][0]-=cost;used[dt]=used.get(dt,0)+1
            if place(index+1):
                assignment[id(item)]=dt
                return True
            cap[dt][0]+=cost;used[dt]-=1
        return False

    if not place(0):return None
    return [(item,assignment[id(item)]) for item in order]


def day_load(w,day):
    """当天占用的可排分钟：景点时长 + 相邻参观之间的休息与机动。

    规划阶段会在两处参观之间插入 REST_BETWEEN_MINUTES，校验与容量比较时
    必须把它算进去，否则"排得下"只是纸面上成立。
    """
    from .schedule import REST_BETWEEN_MINUTES
    items=day.get('items',[])
    return sum(item.get('duration',0) for item in items)+max(0,len(items)-1)*REST_BETWEEN_MINUTES


def day_overload(w,day,allowed_tour=None):
    """返回当天超出容量的分钟数；为 0 表示没有超出。"""
    if allowed_tour is not None and day['date'] not in allowed_tour:return 0
    from .schedule import capacity
    return max(0,day_load(w,day)-capacity(w,day['date'])['available_minutes'])


def groups_overload(w,groups,allowed_tour=None):
    return [day['date'] for day in groups if day_overload(w,day,allowed_tour)]


def rebalance(w,groups,requests,allowed_tour,dates):
    """确定性有限重排：把可调整的景点分配到有空档的日期。

    模型两次都没把景点排开时，不该把死结丢给用户——只要存在可行分配，
    就由程序按当日可用时间（含到达/返程边界、餐次与往返住宿）重新分配；
    用户明确指定日期时段的景点保持不动。分配失败返回 None，由调用方给出
    可读原因。只调整日期，不改动模型给出的时长、时段与说明。
    """
    from .schedule import capacity,REST_BETWEEN_MINUTES
    cap={}
    for dt in allowed_tour:
        # 容量必须与规划阶段同口径：已扣餐次与往返住宿，并受每日结束时刻与
        # 返程截止约束，不能再用 windows() 上界（它最长可到当天 24:00）。
        # 每多放一处参观，还要额外扣掉两处之间的休息与机动。
        info=capacity(w,dt)
        cap[dt]=[info['available_minutes'],info['available_minutes']]   # [剩余分钟, 原始可用分钟]
    placed={dt:[] for dt in allowed_tour}
    movable=[]
    for d in groups:
        dt=d['date']
        if dt not in placed:continue
        for item in d.get('items',[]):
            cid=item['candidate_id']
            # 用户指定日期时的景点固定在原日；其余（含模型放错日期的）重新分配，
            # 否则模型把全部景点堆在返程日时，重排会误判为不可行。
            if requests.get(cid,{}).get('date')==dt:placed[dt].append(item)
            else:movable.append(item)
    for dt,items in placed.items():
        cap[dt][0]-=sum(x['duration'] for x in items)
        cap[dt][0]-=max(0,len(items)-1)*REST_BETWEEN_MINUTES
        # 用户指定的日子本身就装不下时，不存在可重排方案，直接说不可行。
        if cap[dt][0]<0:return None
    used={dt:len(placed[dt]) for dt in placed}
    fitted=_fit_days(movable,allowed_tour,cap,used)
    if fitted is None:return None
    for item,dt in fitted:placed[dt].append(item)
    out=[]
    for dt in sorted(placed):
        items=placed[dt]
        if not items:continue
        ranks={cid:i for i,cid in enumerate(w.get('visit_order',[]))}
        items.sort(key=lambda x:({'morning':0,'any':1,'afternoon':2,'evening':3}.get(x.get('period','any'),1),ranks.get(x['candidate_id'],9999)))
        out.append({'date':dt,'theme':'','items':items})
    return out or None

async def create(w,spots,payload,prompt,progress,model,runtime):
    from .providers import DataError
    from .planning import round_up
    requests=w.get('visit_requests',{})
    spots=sorted(spots,key=lambda p:requests.get(p['id'],{}).get('date') or (p.get('visit_suggestion') or {}).get('date') or '9999')
    chunks=[spots[i:i+16] for i in range(0,len(spots),16)]
    dates=payload['dates'];tour_dates=payload['tour_dates'];by_date={};draft={'packing':[],'todos':[]};usage={}
    for index,chunk in enumerate(chunks):
        first=math.floor(index*len(tour_dates)/len(chunks));last=max(first+1,math.floor((index+1)*len(tour_dates)/len(chunks)))
        allowed_tour=tour_dates[min(first,len(tour_dates)-1):min(last,len(tour_dates))]
        if len(chunks)==1:allowed_tour=tour_dates
        fixed=[requests[p['id']]['date'] for p in chunk if p['id'] in requests]
        if any(d not in tour_dates for d in fixed):raise DataError('景点指定日期不在当前游玩范围，请先调整景点日期安排。')
        allowed_tour=sorted(set(allowed_tour+fixed))
        allowed_dates=[d for d in dates if allowed_tour[0]<=d<=allowed_tour[-1]]
        allowed_ids={p['id'] for p in chunk}
        if len(chunks)>1:progress(f'正在安排第{index+1}/{len(chunks)}阶段的地点与日期')
        content={**payload,'spots':chunk,'dates':allowed_dates,'tour_dates':allowed_tour,'visit_requests':{cid:requests[cid] for cid in allowed_ids if cid in requests},'phase':index+1,'phases':len(chunks)}
        messages=[{'role':'system','content':prompt+' candidate_id逐字复制输入ID，不能用名称或酒店ID。只在tour_dates安排景点；仅输出有景点的日期，避免填充大量空白天。visit_order是用户明确先后顺序；在同一天同一时段内遵守，不能覆盖指定日期时段。'}, {'role':'user','content':json.dumps(content,ensure_ascii=False)}]
        for attempt in range(2):
            message,used=await model(messages,json_mode=True,max_tokens=5000)
            raw=message.get('content','');(runtime/'last-plan-proposal.json').write_text(raw or '{}',encoding='utf-8')
            errors=[];seen=set();groups=[];time_context=None
            try:
                value=json.loads(raw)
                for day in value.get('days',[]):
                    dt=day.get('date');items=[]
                    if dt not in dates:errors.append('无效日期：'+str(dt))
                    if day.get('items') and dt not in allowed_tour:errors.append('当前阶段之外的游玩日期：'+str(dt))
                    for item in day.get('items',[]):
                        cid=item.get('candidate_id')
                        if cid not in allowed_ids:errors.append('未选择ID：'+str(cid));continue
                        if cid in seen:errors.append('重复ID：'+cid);continue
                        pin=requests.get(cid,{})
                        if pin.get('date') and dt!=pin['date']:errors.append('必须遵守指定日期：'+cid+' '+pin['date'])
                        period=pin.get('period') or item.get('period') or 'any'
                        if period not in ('any','morning','afternoon','evening'):period='any'
                        seen.add(cid);items.append({**item,'period':period,'duration':round_up(max(30,min(240,int(item.get('duration',90)))),15)})
                    if items and dt in allowed_tour:
                        from .schedule import capacity
                        room_space=capacity(w,dt)
                        if sum(i['duration'] for i in items)>room_space['available_minutes']:
                            fixed_ids=[x['candidate_id'] for x in items if x['candidate_id'] in requests]
                            movable=str(len(items)-len(fixed_ids))
                            room=[other for other in allowed_tour if other!=dt and capacity(w,other)['available_minutes']>=30]
                            errors.append('所选班次与每日结束时刻限制了'+dt+'的可用时间（'+room_space['basis']+'；当日已排'
                                          +str(sum(i['duration'] for i in items))+'分钟）；'
                                          '把可调整的'+movable+'个景点换到有空档的日期：'+(','.join(room) if room else '本次没有可用日期')+'。'
                                          '用户明确指定日期时段的'+str(len(fixed_ids))+'个必须留在原日期，也不得删除任何景点。')
                            back=(w.get('selected_return') or {}).get('departure','')[:10]
                            time_context={'date':dt,'direction':'return' if back and dt>=back else 'outbound','candidate_ids':[x['candidate_id'] for x in items],'view':'spot','phase':'proposal','available_dates':room,
                                          'capacity':room_space}
                    ranks={cid:i for i,cid in enumerate(w.get('visit_order',[]))}
                    if ranks:items.sort(key=lambda x:({'morning':0,'any':1,'afternoon':2,'evening':3}.get(x['period'],1),ranks.get(x['candidate_id'],9999)))
                    groups.append({**day,'items':items})
                if seen!=allowed_ids:errors.append('遗漏ID：'+','.join(sorted(allowed_ids-seen)))
                if len({d['date'] for d in groups})!=len(groups):errors.append('日期重复')
            except (ValueError,TypeError,KeyError,AttributeError):errors.append('JSON日程结构或时长无效')
            if not errors:break
            if attempt:
                # 修订后仍不可行：先尝试确定性重排（存在可行分配时不该失败）
                repaired=rebalance(w,groups,requests,allowed_tour,dates)
                if repaired:
                    moved=[cid for d in repaired for cid in [x['candidate_id'] for x in d['items']]]
                    overloaded=groups_overload(w,repaired,allowed_tour)
                    if set(moved)==allowed_ids and not overloaded:
                        progress('模型两次未排开，已按当日可用时间自动重排景点日期')
                        # 只更新 groups：并入 by_date 统一放在本批末尾做一次，
                        # 否则同一天会被加入两次（items += 自己还会翻倍）。
                        groups=repaired;errors=[]
                        break
                    if overloaded:
                        # 同一把尺子复核不过：宁可给出可读冲突，也不交给规划阶段
                        # 压缩时长或跳过景点。
                        first=next(d for d in repaired if d['date']==overloaded[0])
                        from .schedule import capacity
                        raise DataError(overloaded[0]+'的可调整重排仍放不下当天景点：当日可排'
                                        +str(capacity(w,overloaded[0])['available_minutes'])+'分钟（'+capacity(w,overloaded[0])['basis']
                                        +'），已排'+str(sum(i['duration'] for i in first['items']))+'分钟。'
                                        '请延长游玩日期、减少景点或调整住宿/班次后重排。',
                                        {'date':overloaded[0],'candidate_ids':[i['candidate_id'] for i in first['items']],
                                         'view':'spot','phase':'proposal','capacity':capacity(w,overloaded[0]),
                                         'available_dates':[d['date'] for d in repaired if d['date']!=overloaded[0]]})
                if time_context:raise DataError(time_context['date']+'的活动与'+('返程冲突' if time_context['direction']=='return' else '去程到达时间冲突')+'，修订后仍无法容纳建议游玩时长。请调整相关景点日期、时段或班次。',time_context)
                raise DataError('行程草稿未通过候选/日期校验，已保留用户选择，请重新生成。')
            progress('正在根据候选与日期校验结果修订草稿')
            messages.extend([{'role':'assistant','content':raw or '{}'}, {'role':'user','content':json.dumps({'validation_errors':errors,'allowed_ids':sorted(allowed_ids),'allowed_dates':allowed_tour},ensure_ascii=False)}])
        for key,n in used.items():
            if isinstance(n,(int,float)):usage[key]=usage.get(key,0)+n
        if not draft.get('title'):draft['title']=value.get('title')
        for key in ('packing','todos'):draft[key]=list(dict.fromkeys(draft[key]+[x for x in value.get(key,[]) if isinstance(x,str)]))
        for day in groups:
            dt=day['date']
            if dt not in by_date:by_date[dt]={**day,'items':list(day['items'])}
            else:by_date[dt]['items']=by_date[dt]['items']+list(day['items'])
    return draft,list(by_date.values()),usage
