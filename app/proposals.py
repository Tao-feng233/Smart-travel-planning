"""Bounded proposal batches for long trips; every selected ID is validated once."""
import json,math

def rebalance(w,groups,requests,allowed_tour,dates):
    """确定性有限重排：把可调整的景点分配到有空档的日期。

    模型两次都没把景点排开时，不该把死结丢给用户——只要存在可行分配，
    就由程序按当日可用时间（含到达/返程边界）重新分配；用户明确指定日期
    时段的景点保持不动。分配失败返回 None，由调用方给出可读原因。
    只调整日期，不改动模型给出的时长、时段与说明。
    """
    from .schedule import windows,minutes
    req=w['requirements'];day_start=minutes(req.get('day_start','09:00'))
    cap={}
    for dt in allowed_tour:
        low,high=windows(w,dt);low=max(low,day_start)
        usable=max(0,high-low)
        cap[dt]=[usable,usable]           # [剩余分钟, 原始可用分钟]
    placed={dt:[] for dt in allowed_tour}
    movable=[]
    for d in groups:
        dt=d['date']
        if dt not in placed:continue
        for item in d.get('items',[]):
            cid=item['candidate_id']
            if requests.get(cid,{}).get('date')==dt:placed[dt].append(item)   # 用户指定，保持原日
            else:movable.append(item)
    for dt,items in placed.items():
        cap[dt][0]-=sum(x['duration'] for x in items)
    for item in sorted(movable,key=lambda x:-x['duration']):
        need=item['duration']
        # 双重校验：既要当天还有剩余分钟，也要单次游玩装得进当天的可用窗口，
        # 否则会出现"重排后仍放不下"的假可行。
        options=[dt for dt in allowed_tour if cap[dt][0]>=need and need<=cap[dt][1]]
        if not options:return None
        # 先挑剩余时间最紧的、再挑当日已排最少的，避免把时间堆在一天
        dt=min(options,key=lambda d:(cap[d][0]-need,cap[d][1]-cap[d][0],d))
        placed[dt].append(item);cap[dt][0]-=need
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
    from . import visit_analysis
    estimates={i['candidate_id']:i for i in visit_analysis.preview(w)}
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
                        duration=item.get('duration',estimates.get(cid,{}).get('duration',90))
                        if isinstance(duration,bool) or not isinstance(duration,(int,float)) or not 15<=duration<=720:
                            errors.append('时长必须为15至720分钟的建议值：'+cid);continue
                        seen.add(cid);items.append({**item,'period':period,'duration':round_up(duration,15)})
                    if items and dt in allowed_tour:
                        from .schedule import windows,minutes
                        low,high=windows(w,dt)
                        limited=low>0 or high<1440
                        low=max(low,minutes(w['requirements'].get('day_start','09:00')))
                        if limited and low+sum(i['duration'] for i in items)>high:
                            fixed_ids=[x['candidate_id'] for x in items if x['candidate_id'] in requests]
                            movable=str(len(items)-len(fixed_ids))
                            room=[]
                            for other in allowed_tour:
                                if other==dt:continue
                                low_o,high_o=windows(w,other)
                                low_o=max(low_o,minutes(w['requirements'].get('day_start','09:00')))
                                if high_o-low_o>=30:room.append(other)
                            errors.append('所选班次限制了'+dt+'可用时间（'+str(low)+'-'+str(high)+' 分钟口径，当日已排'+str(sum(i['duration'] for i in items))+'分钟）；'
                                          '把可调整的'+movable+'个景点换到有空档的日期：'+(','.join(room) if room else '本次没有可用日期')+'。'
                                          '用户明确指定日期时段的'+str(len(fixed_ids))+'个必须留在原日期，也不得删除任何景点。')
                            back=(w.get('selected_return') or {}).get('departure','')[:10]
                            time_context={'date':dt,'direction':'return' if back and dt>=back else 'outbound','candidate_ids':[x['candidate_id'] for x in items],'view':'spot','phase':'proposal','available_dates':room}
                    ranks={cid:i for i,cid in enumerate(w.get('visit_order',[]))}
                    if ranks:items.sort(key=lambda x:({'morning':0,'any':1,'afternoon':2,'evening':3}.get(x['period'],1),ranks.get(x['candidate_id'],9999)))
                    groups.append({**day,'items':items})
                if seen!=allowed_ids:errors.append('遗漏ID：'+','.join(sorted(allowed_ids-seen)))
                if len({d['date'] for d in groups})!=len(groups):errors.append('日期重复')
                allocation=[{**item,'date':d['date']} for d in groups for item in d['items']]
                errors.extend(visit_analysis.distribution_errors(w,allocation,allowed_tour))
            except (ValueError,TypeError,KeyError,AttributeError):errors.append('JSON日程结构或时长无效')
            if not errors:break
            if attempt:
                # 修订后仍不可行：先尝试确定性重排（存在可行分配时不该失败）
                repaired=rebalance(w,groups,requests,allowed_tour,dates)
                if repaired:
                    moved=[cid for d in repaired for cid in [x['candidate_id'] for x in d['items']]]
                    if set(moved)==allowed_ids:
                        progress('模型两次未排开，已按当日可用时间自动重排景点日期')
                        groups=repaired;errors=[]
                        for d in groups:
                            dt=d['date']
                            if dt not in by_date:by_date[dt]=d
                            else:by_date[dt]['items']+=d['items']
                        break
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
            if dt not in by_date:by_date[dt]=day
            else:by_date[dt]['items']+=day['items']
    return draft,list(by_date.values()),usage
