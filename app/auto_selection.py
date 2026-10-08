"""User-approved candidate selection; transport is never delegated here."""
import copy
import hashlib
import json
import re
import time
import uuid

from .providers import DataError
from . import schedule, journey

LABELS = {'spots': '景点', 'hotel': '住宿及房型', 'food': '餐饮'}
STATE_KEYS = ('id', 'requirements', 'selected_spots', 'hotel', 'selected_room',
              'meal_choices', 'meal_mode', 'visit_requests', 'visit_order',
              'selected_transport', 'selected_return', 'catalog')


def signature(w):
    return hashlib.sha256(json.dumps({k: w.get(k) for k in STATE_KEYS},
        sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def delegation(w, text, intent):
    """Also catch delegation when the model mistakenly emits a single meal choice."""
    if re.search(r'不用.{0,4}(自动|代选)|取消.{0,4}(代选|自动配置)', text):
        return {**intent, 'action': 'cancel_auto_selection', 'select_ids': [], 'remove_ids': []}
    if intent.get('action') == 'discover_destinations' or intent.get('meal_mode') == 'self':
        return {**intent, 'auto_select': False}
    if re.search(r'(自行|自己).{0,3}安排', text) and not re.search(r'(你|助手).{0,4}(自动|帮我)', text):
        return {**intent, 'action': 'chat' if intent.get('action') == 'request_auto_selection' else intent.get('action', 'chat'), 'auto_select': False}
    ids=list(intent.get('select_ids',[]))
    if intent.get('food_id'):ids.append(intent['food_id'])
    picks = [w.get('catalog',{}).get(i,{}) for i in dict.fromkeys(ids)]
    if len(picks)==1 and picks[0].get('name') and picks[0]['name'] in text and not re.search('自动|重新|剩余|剩下|还是|或者|哪[个班家]',text):
        return {**intent,'auto_select':False}
    asked = re.search(r'自动.{0,8}(选|挑|安排|配置)|帮我.{0,5}(选|挑|配置)|(?:你|交给你).{0,5}(选|配置)|剩[下余].{0,12}(帮我|你来|安排)', text)
    if not asked and intent.get('action') != 'request_auto_selection': return intent
    categories = []
    for pattern, category in [('景点|景区', 'spots'), ('酒店|住宿|房型', 'hotel'), ('餐饮|餐厅|吃饭|早餐|午餐|晚餐', 'food')]:
        if re.search(pattern, text): categories.append(category)
    if not categories and re.search('车票|机票|高铁|动车|航班', text):
        return {**intent, 'action': 'train' if not re.search('机票|航班', text) else 'flight',
                'select_ids': [], 'remove_ids': [], 'auto_select': False}
    if not categories:
        categories = [x for x in intent.get('auto_categories', []) if x in LABELS]
    if not categories: categories = ['spots', 'hotel', 'food']
    mode = 'replace' if re.search('重新|重选|全部换|换一遍', text) else 'remaining'
    return {**intent, 'action': 'request_auto_selection', 'auto_categories': categories,
            'auto_mode': mode, 'select_ids': [], 'remove_ids': [], 'auto_select': False}


def request(w, args):
    categories = args.get('auto_categories') or ['spots', 'hotel', 'food']
    if not isinstance(categories, list) or any(c not in LABELS for c in categories):
        raise DataError('自动配置支持景点、住宿和餐饮；车票及机票请自行选定。')
    mode = args.get('auto_mode', 'remaining')
    if mode not in ('remaining', 'replace'): raise DataError('请选择补齐剩余内容或重新配置。')
    if not all(w['requirements'].get(k) for k in ('city', 'start_date', 'days')):
        raise DataError('自动配置前请先补充目的地、游玩日期和天数。', {'view': 'spot', 'settings': True})
    w.pop('auto_selection_run', None)
    pending = {'id': uuid.uuid4().hex, 'mode': mode, 'categories': list(dict.fromkeys(categories)),
               'signature': signature(w), 'expires': time.time()+900}
    pending['description'] = ('保留已有选择，补齐尚未安排的' if mode=='remaining' else '重新选择并替换已有的') + '、'.join(LABELS[c] for c in pending['categories'])
    pending['notice'] = '车票、机票由你手动确认；此操作只用于规划，不进行预订。' + ('替换景点时会清除被替换景点的日期安排。' if mode=='replace' and 'spots' in categories else '')
    w['pending_auto_selection'] = pending
    return '请在确认窗口核对代选范围：'+pending['description']+'。确认前不会更改这些选择。'+pending['notice']


def cancel(w):
    w.pop('pending_auto_selection', None); w.pop('auto_selection_run', None)
    return '自动配置已取消，当前已保存的选择保留，可继续手动调整。'


async def choose(w, pool, task, model, used=None, many=False):
    if not pool: raise DataError('没有可用候选，已保留原有选择。')
    m, _ = await model([{'role': 'system', 'content':
        '你是旅游候选选择助手。用户已确认指定范围的代选授权。只从给定候选ID选择，考虑位置、日期、偏好、人数、参考预算和已选内容。'
        '不要选择车票或机票，不编造价格、营业、菜品或库存。餐饮考虑当前餐次和参照区域，在可行候选中尽量避免重复。'
        '输出JSON {"ids":["候选ID"],"reason":"简短理由"}；'+('景点数量按行程负担决定，不为填满日期堆积景点。' if many else '只选一项。')},
        {'role': 'user', 'content': json.dumps({'task': task, 'requirements': w['requirements'],
            'selected_spots': [w['catalog'].get(i) for i in w.get('selected_spots', [])],
            'hotel': w.get('hotel'), 'used_food_ids': used or [], 'candidates': pool}, ensure_ascii=False)}],
        json_mode=True, max_tokens=1800)
    try:
        value = json.loads(m['content']); ids = value['ids']; allowed = {p['id'] for p in pool}
        if not isinstance(ids, list) or not ids or len(ids)!=len(set(ids)) or any(i not in allowed for i in ids) or (not many and len(ids)!=1): raise ValueError()
        return ids, str(value.get('reason') or '结合当前旅行条件选择')[:220]
    except (KeyError, ValueError, TypeError):
        raise DataError('本次自动选择没有匹配到有效候选，已有选择保留，可重试或手动选择。') from None


async def run(w, args, progress, model, handle, continuing=False):
    if continuing:
        state = w.get('auto_selection_run')
        if not state or args.get('approval_id') != state['id']: raise DataError('自动配置授权不存在，请重新确认。')
    else:
        pending = w.get('pending_auto_selection')
        if not pending or args.get('approval_id') != pending['id'] or args.get('confirmed') is not True:
            raise DataError('请先在弹窗中确认是否允许自动配置。')
        if pending['signature'] != signature(w) or pending['expires'] < time.time():
            w.pop('pending_auto_selection', None)
            raise DataError('旅行条件或选择已经变化，请重新核对自动配置范围。')
        state = {**pending, 'expires': time.time()+3600, 'started': False, 'messages': [],
                 'generate_plan': args.get('generate_plan') is True, 'meal_cursor': 0}
        w.pop('pending_auto_selection', None)
    if state['signature'] != signature(w) or state['expires'] < time.time():
        w.pop('auto_selection_run', None)
        raise DataError('自动配置期间旅行条件发生变化，请重新确认。')
    # Whole-object rollback prevents a failed query/choice from clearing a user's
    # old selection. Each successful meal is kept if a later meal cannot be filled.
    transport = {k: copy.deepcopy(w.get(k)) for k in ('selected_transport', 'selected_return')}
    notes = state['messages']; cat = w['catalog']; mode = state['mode']
    try:
        if not state['started']:
            for category in state['categories']:
                backup = copy.deepcopy(w)
                try:
                    if category=='spots' and (mode=='replace' or not w.get('selected_spots')):
                        await handle(w, 'search_spots', {}, progress)
                        ids = (w.get('spot_search') or {}).get('ids') or [p['id'] for p in w.get('candidates', []) if p.get('kind')=='spot']
                        pool = [cat[i] for i in ids if i in cat and cat[i].get('kind')=='spot' and not cat[i].get('stale')]
                        chosen, reason = await choose(w, pool, '选择适合本次旅行的一组景点', model, many=True)
                        w['selected_spots'] = chosen; w['spots_confirmed'] = True
                        if mode=='replace':
                            w['visit_requests'] = {i:v for i,v in w.get('visit_requests', {}).items() if i in chosen}
                            w['visit_order'] = [i for i in w.get('visit_order', []) if i in chosen]
                        if w.get('plan'): w['plan']['stale'] = True
                        from .visit_analysis import analyze
                        await analyze(w, model, progress)
                        notes.append('已选择景点：'+'、'.join(cat[i]['name'] for i in chosen)+'。'+reason)
                    elif category=='hotel' and (mode=='replace' or not w.get('selected_room') or (w.get('hotel') or {}).get('stale')):
                        if int(w['requirements']['days'])==1 or mode=='remaining' and w.get('stay_skipped'):
                            notes.append('保留一日游或自行安排住宿的选择。'); continue
                        if mode=='remaining' and w.get('hotel') and not w['hotel'].get('stale'):
                            hotel_id = w['hotel']['id']; reason = '保留已有酒店，补选可用房型'
                        else:
                            await handle(w, 'search_hotels', {}, progress)
                            pool = [cat[i] for i in (w.get('hotel_query') or {}).get('ids', []) if i in cat and not cat[i].get('stale')]
                            chosen, reason = await choose(w, pool, '按游览区域和参考预算选择住宿', model)
                            hotel_id = chosen[0]
                        await handle(w, 'hotel_detail', {'id': hotel_id}, progress)
                        from .choices import room_choices
                        quotes = [p for p in room_choices(cat[hotel_id],w['requirements']) if str(p.get('stock'))!='0']
                        chosen, _ = await choose(w, quotes, '为'+cat[hotel_id]['name']+'选择合适人数及房间数量的房型报价', model)
                        await handle(w, 'select_room', {'room_id': chosen[0]}, progress)
                        notes.append('已选择住宿及房型：'+cat[hotel_id]['name']+'。'+reason)
                except DataError as e:
                    w.clear(); w.update(backup); cat = w['catalog']
                    notes.append(LABELS[category]+'暂未完成：'+str(e))
            state['started'] = True
            state['slots'] = [dict(x) for x in schedule.build(w)['meal_slots']] if 'food' in state['categories'] else []
        slots = state['slots']; end = min(len(slots), state['meal_cursor']+8)
        while state['meal_cursor'] < end:
            slot = slots[state['meal_cursor']]; state['meal_cursor'] += 1
            key = slot['date']+'|'+slot['period']
            if mode=='remaining' and (key in w.get('meal_choices', {}) or w.get('meal_mode')=='self'): continue
            backup = copy.deepcopy(w)
            try:
                progress('正在自动安排'+slot['date']+' '+schedule.PERIODS[slot['period']][0])
                await handle(w, 'search_foods', {'meal_date':slot['date'],'meal_period':slot['period']}, progress)
                cat = w['catalog']; used = [c.get('food_id') for c in w.get('meal_choices', {}).values()]
                pool = [cat[i] for i in (w.get('food_query') or {}).get('ids', []) if i in cat and cat[i].get('kind')=='food']
                unused = [p for p in pool if p['id'] not in used]; pool = unused or pool
                chosen, reason = await choose(w, pool, {'date':slot['date'],'meal':slot['period'],'anchor':w.get('food_query', {}).get('anchor')}, model, used)
                await handle(w, 'meal_choice', {'meal_date':slot['date'],'meal_period':slot['period'],'food_id':chosen[0],'meal_mode':'chosen'}, progress)
                w['meal_choices'][key]['selection_reason'] = reason
                notes.append(slot['date']+' '+schedule.PERIODS[slot['period']][0]+'：'+cat[chosen[0]]['name']+'。'+reason)
            except DataError as e:
                w.clear(); w.update(backup); cat = w['catalog']
                notes.append(slot['date']+' '+schedule.PERIODS[slot['period']][0]+'未完成：'+str(e))
        if any(w.get(k)!=v for k,v in transport.items()):
            raise DataError('自动配置中检测到交通选择发生变化，已停止本轮配置。')
        if state['meal_cursor'] < len(slots):
            state['signature'] = signature(w); w['auto_selection_run'] = state
            return '已完成当前批次，正在继续安排其余餐次。已有选择保留。'
        w.pop('auto_selection_run', None)
        if 'food' in state['categories']:
            complete = all(x['date']+'|'+x['period'] in w.get('meal_choices', {}) or w.get('meal_mode')=='self' for x in slots)
            w['dining_reviewed'] = complete
        if state['generate_plan']:
            local = journey.is_local(w['requirements'])
            confirmed = all((w.get(k) or {}).get('selection_status')=='confirmed' for k in transport)
            if local or confirmed:
                try: notes.append(await handle(w,'plan',{},progress))
                except DataError as e: notes.append('计划书尚未完成：'+str(e))
            else: notes.append('请先在往返交通中手动选定车票或机票，再生成完整计划书。')
        result = '\n'.join(notes[-18:]) or '当前范围已有安排，已保留原有选择。'
        w['auto_selection_result'] = {'mode':mode,'categories':state['categories'],'messages':notes}
        return result+'\n自动选择仅用于规划，未预订；可点击对应卡片或时间轴修改。'
    finally:
        # Even an interrupted or failed batch cannot silently replace ticket choices.
        for k,v in transport.items():
            if v is None: w.pop(k,None)
            else: w[k]=v
