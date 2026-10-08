"""Bounded proposal batches for long trips; every selected ID is validated once."""
import json,math

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
        if any(d not in tour_dates for d in fixed):
            from .diagnostics import invalid_dates
            issues=invalid_dates(w,[p['id'] for p in chunk],tour_dates)
            raise DataError('部分景点的指定日期已超出当前游玩范围，请查看具体安排。',{'issues':issues,'view':'spot','candidate_ids':[i for x in issues for i in x['candidate_ids']]})
        allowed_tour=sorted(set(allowed_tour+fixed))
        allowed_dates=[d for d in dates if allowed_tour[0]<=d<=allowed_tour[-1]]
        allowed_ids={p['id'] for p in chunk}
        if len(chunks)>1:progress(f'正在安排第{index+1}/{len(chunks)}阶段的地点与日期')
        content={**payload,'spots':chunk,'dates':allowed_dates,'tour_dates':allowed_tour,'visit_requests':{cid:requests[cid] for cid in allowed_ids if cid in requests},'phase':index+1,'phases':len(chunks)}
        messages=[{'role':'system','content':prompt+' candidate_id逐字复制输入ID，不能用名称或酒店ID。只在tour_dates安排景点；仅输出有景点的日期，避免填充大量空白天。visit_order是用户明确先后顺序；在同一天同一时段内遵守，不能覆盖指定日期时段。'}, {'role':'user','content':json.dumps(content,ensure_ascii=False)}]
        for attempt in range(2):
            message,used=await model(messages,json_mode=True,max_tokens=5000,label='plan_proposal')
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
                        if limited and low>=high:
                            errors.append('所选班次限制了'+dt+'可用时间；请将可调整的景点换到其他游玩日期，保留明确指定日期时段，不删除景点。')
                            back=(w.get('selected_return') or {}).get('departure','')[:10]
                            time_context={'date':dt,'direction':'return' if back and dt>=back else 'outbound','candidate_ids':[x['candidate_id'] for x in items],'view':'spot','phase':'proposal'}
                    ranks={cid:i for i,cid in enumerate(w.get('visit_order',[]))}
                    if ranks:items.sort(key=lambda x:({'morning':0,'any':1,'afternoon':2,'evening':3}.get(x['period'],1),ranks.get(x['candidate_id'],9999)))
                    groups.append({**day,'items':items})
                if seen!=allowed_ids:errors.append('遗漏ID：'+','.join(allowed_ids-seen))
                if len({d['date'] for d in groups})!=len(groups):errors.append('日期重复')
                allocation=[{**item,'date':d['date']} for d in groups for item in d['items']]
                advisories=visit_analysis.distribution_warnings(w,allocation,allowed_tour)
            except (ValueError,TypeError,KeyError,AttributeError):errors.append('JSON日程结构或时长无效')
            if not errors and (not advisories or attempt):break
            if attempt:
                from .diagnostics import proposal
                message,context=proposal(w,errors,groups,allowed_ids,tour_dates,time_context)
                raise DataError(message,context)
            progress('正在根据候选与日期校验结果修订草稿')
            messages.extend([{'role':'assistant','content':raw or '{}'}, {'role':'user','content':json.dumps({'validation_errors':errors,'workload_advisories':advisories if not errors else [],'allowed_ids':sorted(allowed_ids),'allowed_dates':allowed_tour,'instruction':'保留全部已选地点及明确安排，尝试改善建议负担；休息时间不必填满，估算偏紧可说明而不是编造可行性。'},ensure_ascii=False)}])
        for key,n in used.items():
            if isinstance(n,(int,float)):usage[key]=usage.get(key,0)+n
        if not draft.get('title'):draft['title']=value.get('title')
        for key in ('packing','todos'):draft[key]=list(dict.fromkeys(draft[key]+[x for x in value.get(key,[]) if isinstance(x,str)]))
        for day in groups:
            dt=day['date']
            if dt not in by_date:by_date[dt]=day
            else:by_date[dt]['items']+=day['items']
    draft['planning_issues']=visit_analysis.distribution_warnings(w,[{**i,'date':d['date']} for d in by_date.values() for i in d['items']],tour_dates)
    return draft,list(by_date.values()),usage
