def markdown(w):
    p=w['plan'];r=w['requirements']
    lines=['# '+p['title'],'',f"生成时间：{p['created']}；工作区版本：{w['revision']}",'',
           '**状态：需要重新生成**' if p.get('stale') else '**状态：草稿，关键未知需确认**','',
           '## 旅行条件','',f"目的地：{r.get('city')}；开始日期：{r.get('start_date')}；天数：{r.get('days')}；成人：{r.get('adults','未确定')}；儿童：{r.get('children',0)}",'',
           f"总预算：{r.get('budget','未确定')}；节奏：{r.get('pace','balanced')}",'','## 已选住宿','']
    h=w.get('hotel')
    if h:
        lines += [h['name']+'（选定，尚未预订）',h.get('address',''),f"列表起价：¥{h.get('price','未知')}；房型及住宿总价待核实",f"来源：{h['source']['name']}，查询时间：{h['source']['queried_at']}",'']
    else:lines+=['未确定住宿。','']
    room=w.get('selected_room')
    if room:
        lines += [f"已选房型：{room['name']}，{room['quantity']}间；参考报价：¥{room.get('price','待核实')}，报价覆盖日期与整段总价需核实。",f"餐食：{room.get('meal') or '待核实'}；退改：{room.get('cancel') or '待核实'}"]
        lines += ['- '+x for x in room.get('review',{}).get('issues',[])]+['']
    lines+=['## 用餐选择（可选）','']
    for key,value in w.get('meal_choices',{}).items():
        restaurant=w.get('catalog',{}).get(value.get('food_id'),{})
        lines+=['- '+key.replace('|',' · ').replace('breakfast','早餐').replace('lunch','午餐').replace('dinner','晚餐')+ '：'+(restaurant.get('name','餐厅待核实') if value.get('mode')=='chosen' else '自行安排')]
    if not w.get('meal_choices'):lines+=['用餐自行安排，可临时调整，不影响其他选择。']
    lines+=['','## 往返交通','']
    for label,key in [('去程','selected_transport'),('返程','selected_return')]:
        tr=w.get(key)
        if tr:lines += [f"- {label}：{tr['name']}，{tr.get('departure')} → {tr.get('arrival')}；仅选定，尚未预订。",f"  来源：{tr['source']['name']}，查询：{tr['source']['queried_at']}"]
        else:lines += ['- '+label+'：尚未选定，接驳与可用时间需核实。']
    lines+=['','## 每日安排','']
    for d in p['days']:
        lines+=['### '+d['date']+' · '+d['theme'],'']
        for e in d['events']:
            lines += [f"- {e['start']}–{e['end']} {e['name']}：{e.get('note','')}"]
            if e.get('route'):
                rt=e['route'];lines += [f"  方式：{rt['mode']}；高德预计 {rt['minutes']} 分钟；另留 {e['buffer']} 分钟缓冲；查询：{rt['source']['queried_at']}"]
            if e.get('poi'):lines += [f"  地址：{e['poi'].get('address','未知')}；来源：高德地图 {e['poi']['source']['queried_at']}"]
        lines+=['']
    lines+=['## 预算与未核实费用','']
    b=p.get('budget') or {}
    if b.get('verified'):
        for item in b['verified']:
            lines.append(f"- {item['item']}（已核实）：¥{item.get('amount')}；来源：{item.get('basis','')}")
    if b.get('estimated'):
        for item in b['estimated']:
            high=item.get('high',item.get('low'))
            amount=(f"约 ¥{item['low']:.0f}" if high==item.get('low') else f"约 ¥{item['low']:.0f}–¥{high:.0f}")
            lines.append(f"- {item['item']}（估计）：{amount}；口径：{item.get('basis','')}")
    if not b.get('verified') and not b.get('estimated'):
        lines.append('- 目前没有已核实金额，也没有可给区间的估算；缺费用依据的项目不记为零。')
    lines.append('')
    for item in b.get('unknown') or []:
        if isinstance(item,dict):lines.append(f"- {item['item']}：尚未核实（{item.get('reason','缺少费用依据')}）")
        else:lines.append('- '+str(item)+'：尚未完整核实')
    if b.get('per_person_note'):lines+=['','人均口径：'+b['per_person_note']]
    lines+=['','## 天气','']
    weather=w.get('weather')
    if weather:
        dates={d['date'] for d in p['days']}
        for d in weather['days']:
            if d['date'] in dates:lines+=[f"- {d['date']}：{d['text']}，{d['low']}–{d['high']}℃；降水概率 {round(d['rain']*100) if d.get('rain') is not None else '未知'}%"]
        lines+=['来源：和风天气，'+weather['source']['queried_at']]+weather.get('attributions',[])
    else:lines+=['尚未查询天气；超出预报范围的日期保持待定。']
    lines+=['','## 出发前待办与风险','']+['- '+x for x in p['todos']+p['warnings']]+['','## 携带建议','']+['- '+x for x in p.get('packing',[])]
    review=p.get('review',{})
    lines+=['','## 模型审核','',review.get('summary','未完成')]+['- '+x for x in review.get('issues',[])]+['','## 官方知识资料','']
    for g in p.get('guides',[]):lines += [f"- [{g['title']}]({g['url']})；采集：{g['fetched_at']}；适用日期需核实"]
    return '\n'.join(lines)+'\n'
