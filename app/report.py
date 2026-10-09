from .locations import quote_stale
from .spot_hierarchy import duplicate_plan


def route_lines(rt,self_drive=False):
    """Provider facts only: unknown prices/lines remain explicit in the exported book."""
    if rt.get('mode')=='driving':
        if self_drive:
            lines=['  自驾道路收费：'+('预估 ¥'+str(rt['tolls']) if rt.get('tolls') is not None else '待核实')+'；油费与停车费待核实。']
        else:
            lines=['  打车费用：'+('高德预估 ¥'+str(rt['taxi_cost']) if rt.get('taxi_cost') is not None else '接口未提供，待查询')+'；非实时叫车报价，不含未核实附加费用。']
    elif rt.get('mode')=='transit':
        lines=['  公交／地铁票价：'+('参考 ¥'+str(rt['fare']) if rt.get('fare') is not None else '待核实')+'。']
    else:lines=['  步行无需车费。']
    for step in rt.get('steps') or []:
        text=step.get('instruction') or step.get('road_name') or '通行路段'
        if step.get('from'):text+='：'+step['from']+' 上车 → '+str(step.get('to') or '下车站待核实')+' 下车'
        lines.append('  - '+text)
    if rt.get('mode')=='transit' and not rt.get('steps'):lines.append('  具体线路、换乘与上下车站未返回，出行前请使用实时导航核对。')
    return lines

def markdown(w):
    p=w['plan'];r=w['requirements']
    lines=['# '+p['title'],'',f"生成时间：{p['created']}；工作区版本：{w['revision']}",'',
           '**状态：需要重新生成**' if p.get('stale') or duplicate_plan(w,p) else '**状态：草稿，关键未知需确认**','',
           '## 旅行条件','',f"目的地：{r.get('city')}；开始日期：{r.get('start_date')}；天数：{r.get('days')}；成人：{r.get('adults','未确定')}；儿童：{r.get('children',0)}",'',
           f"总预算：{r.get('budget','未确定')}；节奏：{r.get('pace','balanced')}",'','## 已选住宿','']
    h=w.get('hotel')
    if h:
        lines += [h['name']+'（选定，尚未预订）',h.get('address',''),f"列表起价：¥{h.get('price','未知')}；房型及住宿总价待核实",f"来源：{h['source']['name']}，查询时间：{h['source']['queried_at']}",'']
        lines += ['入住时刻不随酒店选择自动确定；请自行安排，或先与助手讨论后确认。前往及返回住宿的交通参考不代表已确认办理入住。', '']
        if quote_stale(h):lines+=['该起价及房型信息来自原查询，已标记待更新；酒店位置保留，不能据此确认本次住宿费用。','']
    else:lines+=['未确定住宿。','']
    room=w.get('selected_room')
    if h and not room:
        lines += ['具体房型：未选择（可选）。日程按已选住宿位置规划，住宿实际总价与入住条件请在预订前核实。','']
    if room:
        lines += [f"已选房型：{room['name']}，{room['quantity']}间；参考报价：¥{room.get('price','待核实')}，报价覆盖日期与整段总价需核实。",f"餐食：{room.get('meal') or '待核实'}；退改：{room.get('cancel') or '待核实'}"]
        lines += ['- '+x for x in room.get('review',{}).get('issues',[])]+['']
    lines+=['## 用餐选择（可选）','']
    from . import foods as _foods
    from .journey import meal_dates as _meal_dates
    included_notes=[]
    for dt in _meal_dates(w.get('requirements') or {}):
        note=_foods.meal_note(w,dt,'breakfast')
        if note:included_notes.append(dt+'：'+note)
    for key,value in w.get('meal_choices',{}).items():
        restaurant=w.get('catalog',{}).get(value.get('food_id'),{})
        lines+=['- '+key.replace('|',' · ').replace('breakfast','早餐').replace('lunch','午餐').replace('dinner','晚餐')+ '：'+(restaurant.get('name','餐厅待核实') if value.get('mode')=='chosen' else '自行安排')]
    if included_notes:
        # 房型含早时说清这一餐已在房费内，不再需要另选；想出去吃仍可自行选择。
        lines+=['','房型含早（无需另选，想出去吃可自行到餐饮页选择）：']+['- '+x for x in included_notes]
    if not w.get('meal_choices') and not included_notes:lines+=['用餐自行安排，可临时调整，不影响其他选择。']
    lines+=['','## 往返交通','']
    for label,key in [('去程','selected_transport'),('返程','selected_return')]:
        tr=w.get(key)
        if tr:lines += [f"- {label}：{tr['name']}，{tr.get('departure')} → {tr.get('arrival')}；仅选定，尚未预订。",f"  来源：{tr['source']['name']}，查询：{tr['source']['queried_at']}"]
        else:lines += ['- '+label+'：'+({'self_drive':'自驾','self_arranged':'自行安排'}.get(r.get('intercity_mode'),'班次未选（可选）'))+'，实际抵达与离开时间需核实。']
    lines+=['','## 每日安排','']
    for d in p['days']:
        lines+=['### '+d['date']+' · '+d['theme'],'']
        for e in d['events']:
            lines += [f"- {e['start']}–{e['end']} {e['name']}：{e.get('note','')}"]
            if e.get('route'):
                rt=e['route'];lines += [f"  方式：{rt['mode']}；高德预计 {rt['minutes']} 分钟；另留 {e['buffer']} 分钟缓冲；查询：{(rt.get('source') or {}).get('queried_at','未额外请求导航或来源时间未提供')}"]
                lines += route_lines(rt,r.get('intercity_mode')=='self_drive')
            if e.get('poi'):lines += [f"  地址：{e['poi'].get('address','未知')}；来源：高德地图 {e['poi']['source']['queried_at']}"]
        lines+=['']
    lines+=['## 预算与未核实费用','',str(p['budget'].get('hotel_reference','未知'))+' 元住宿起价参考；口径：'+p['budget'].get('basis','住宿未确认'),'']
    lines+=['- '+x+'：尚未完整核实' for x in p['budget'].get('unknown',[])]+['','## 天气','']
    weather=w.get('weather')
    if weather:
        dates={d['date'] for d in p['days']}
        for d in weather['days']:
            if d['date'] in dates:lines+=[f"- {d['date']}：{d['text']}，{d['low']}–{d['high']}℃；降水概率 {round(d['rain']*100) if d.get('rain') is not None else '未知'}%"]
        lines+=['来源：和风天气，'+weather['source']['queried_at']]+weather.get('attributions',[])
    else:lines+=['尚未查询天气；超出预报范围的日期保持待定。']
    lines+=['','## 出发前待办与风险','']+['- '+x for x in (p.get('todos') or [])+(p.get('warnings') or [])]+['','## 携带建议','']+['- '+x for x in p.get('packing',[])]
    review=p.get('review',{})
    lines+=['','## 模型审核','',review.get('summary','未完成')]+['- '+x for x in review.get('issues',[])]+['','## 官方知识资料','']
    for g in p.get('guides',[]):lines += [f"- [{g['title']}]({g['url']})；采集：{g['fetched_at']}；适用日期需核实"]
    return '\n'.join(lines)+'\n'
