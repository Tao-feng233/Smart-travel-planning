"""UI guidance derives from the actual task and saved user choices."""
VIEWS={'discover_destinations':'spot','choose_destination':'spot','search_spots':'spot','spots_page':'spot','dismiss_spot':'spot',
       'search_foods':'food','meal_choice':'food','complete_food':'plan','visit_schedule':'spot','analyze_visits':'spot','search_hotels':'hotel','hotel_detail':'hotel','select_room':'hotel','complete_hotel':'transport','skip_hotel':'transport',
       'weather':'weather','train':'transport','flight':'transport','ticket':'spot','plan':'plan','optimize_plan':'plan'}
VALID_VIEWS={'spot','hotel','weather','transport','plan','knowledge','food','map'}
LOADING={'refresh_routes':'正在核对交通时间','discover_destinations':'正在比较目的地','choose_destination':'正在确认目的地并查询景点','search_spots':'正在查询景点',
         'spots_page':'正在更新景点列表','dismiss_spot':'正在更新推荐偏好','complete_spots':'正在确认景点选择',
         'search_foods':'正在查询餐饮','meal_choice':'正在保存用餐安排','search_hotels':'正在比较住宿','hotel_detail':'正在查询房型','complete_hotel':'正在确认住宿','skip_hotel':'正在更新住宿安排',
         'place_detail':'正在补充地点详情','weather':'正在查询天气','train':'正在查询列车','flight':'正在查询航班','ticket':'正在查询门票',
         'analyze_visits':'正在分析游玩时长与每日分配','plan':'正在生成计划书','optimize_plan':'正在核对冲突并修订完整计划书','select':'正在保存选择','requirements':'正在保存旅行信息','chat':'正在识别需求','undo':'正在恢复版本'}

def describe(w,action='chat',args=None,view=None,status='ready',error=None):
    args=args or {};r=w.get('requirements',{});catalog=w.get('catalog',{});selected=w.get('selected_spots',[])
    view=VIEWS.get(action) or (view if view in VALID_VIEWS else None)
    if action=='place_detail':view=args.get('view') if args.get('view') in VALID_VIEWS else view or {'food':'food','spot':'spot','market':'spot'}.get(catalog.get(args.get('id'),{}).get('kind'))
    if action=='complete_spots':view='transport' if int(r.get('days') or 0)==1 else 'hotel'
    if action in ('complete_hotel','skip_hotel'):
        from .journey import is_local
        if is_local(r):view='food'
    if action=='select':view={'spot':'spot','hotel':'hotel','train':'transport','flight':'transport','food':'food'}.get(catalog.get(args.get('id'),{}).get('kind'),view)
    ui={'action':action,'view':view,'status':status,'focus_id':args.get('id'),'cta':None}
    def output(title,message,label=None,**target):
        ui.update(title=title,message=message)
        if label:ui['cta']={'label':label,**target}
        return ui
    if status=='loading':return output(LOADING.get(action,'正在处理需求'),'正在处理当前请求，已有选择已保存。')
    if status!='ready':
        if status=='failed':return output('本轮未完成',error or '请调整查询条件后重试。','补充旅行信息',settings=True)
        return output('任务已停止',error or '已有对话与选择已保留，可继续规划。','返回当前列表',view=view) if view else output('任务已停止','已有对话与选择已保留。')
    if w.get('pending_plan_warning') and action in ('plan','optimize_plan'):
        return output('请核对规划提醒','估算偏紧或分配不均可以选择继续生成带警告的草稿，也可返回调整。')
    if action=='place_detail':return output('地点资料已更新','在详情窗口核对营业资料、联系方式和来源。')
    if action=='analyze_visits':return output('游玩安排已分析','在时间轴查看每日建议时长与分配原因；正式规划再核对道路和开放条件。','查看时间轴',view='spot')
    if view=='spot':
        if action=='discover_destinations' or w.get('discovery_mode'):
            return output('目的地推荐','比较城市特色与代表景点，点击“选择目的地”后查询具体景点。','查看目的地',view='spot')
        if action=='ticket':return output('门票结果已更新','在景点卡片中核对票种、适用日期与预约要求。','查看门票',view='spot')
        if action in ('select','dismiss_spot'):
            return output(f'已选择 {len(selected)} 个景点','可以继续比较其他景点；确认后点击列表上方“完成景点选择”。','完成景点选择',action='complete_spots') if selected else output('景点选择','请选择景点，或翻页查看更多候选。','查看景点',view='spot')
        from .journey import next_step
        return output('景点推荐',next_step(w)['message'],'查看景点',view='spot')
    if view=='hotel':
        if action=='complete_spots' and not all(r.get(k) for k in ('start_date','days','adults')):
            return output('景点选择已确认','请补充一下出游日期、天数和人数，便于按实际条件比较住宿；可在对话中提供或编辑旅行信息。','补充旅行信息',settings=True)
        if action in ('select','select_room'):return output('住宿选择已保存','已选住宿位置，可直接点击“完成住宿选择”继续；具体房型可选。','完成住宿选择',action='complete_hotel')
        if action=='hotel_detail':return output('房型详情已更新','具体房型可选；如需选择，请核对人数、餐食与退改。','查看房型',view='hotel')
        if any(p.get('kind')=='hotel' and not p.get('stale') for p in catalog.values()):return output('住宿推荐','比较位置、价格与房型。选定住宿仅用于规划，尚未预订。','查看住宿',view='hotel')
        if not selected:return output('住宿推荐','先确认景点，再根据位置与通行条件比较住宿。','选择景点',view='spot')
        return output('住宿推荐','已进入住宿步骤。日期、天数和人数完整后可查询酒店。','查询住宿',action='search_hotels')
    if view=='transport':
        if action in ('complete_spots','complete_hotel','skip_hotel'):return output('往返交通','请核对推荐班次，或切换类型、方向与时段调整。','查看往返交通',view='transport')
        both=w.get('selected_transport') and w.get('selected_return')
        if action=='select' and both:return output('往返班次已选定','可查看天气，或生成旅行计划书。','生成计划书',action='plan')
        return output('往返交通','比较出发、到达时间及查询时可售状态；选定班次不代表已购票。','查看班次',view='transport')
    if view=='food':return output('餐饮选择','可按日期和餐次选餐厅，也可以自行安排。','查看餐饮',view='food')
    if view=='weather':return output('旅行天气','请核对预报覆盖日期；超出窗口的日期需临近出发时再次查询。','查看天气',view='weather')
    if view=='plan':return output('旅行计划书','核对每日安排与待确认事项，可在对话中提出修改。','查看计划书',view='plan')
    if view=='knowledge':return output('资料与依据','查看来源与采集日期，确认信息是否适用于本次旅行。','查看资料',view='knowledge')
    if not r.get('city'):return output('选择目的地','可提供出发城市或旅行偏好，也可以先比较目的地推荐。','推荐目的地',action='discover_destinations')
    if not selected:return output('选择景点','按旅行偏好比较候选，选择完成后再安排住宿。','查询景点',action='search_spots')
    return output('继续规划','已选内容会保留，请完成当前步骤后进入下一步。','完成景点选择',action='complete_spots')

def finish(w,status='ready',error=None):
    prior=w.get('ui',{})
    controls=prior.get('controls')
    w['ui']=describe(w,prior.get('action','chat'),{'id':prior.get('focus_id')},prior.get('view'),status,error)
    if controls:w['ui']['controls']=controls
    return w['ui']
