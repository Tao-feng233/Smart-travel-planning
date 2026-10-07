"""Selections use provider-backed snapshots; no booking operations."""
import hashlib,json
from .providers import DataError

def room_choices(h,r):
    result=[]
    for i,room in enumerate((h.get('detail') or {}).get('roomTypes',[])):
        for j,rate in enumerate(room.get('ratePlans',[])):
            cancel=rate.get('cancelText') or rate.get('cancelDesc')
            identity=[h['id'],room.get('roomTypeId',i),rate.get('vendorRatePlanId',j),r.get('start_date'),r.get('days'),r.get('adults'),r.get('children'),r.get('rooms'),rate.get('rmbPrices'),cancel]
            cid='room:'+hashlib.sha256(json.dumps(identity,ensure_ascii=False).encode()).hexdigest()[:24]
            result.append(dict(id=cid,hotel_id=h['id'],name=room.get('roomTypeName','房型'),rate_name=rate.get('ratePlanName'),price=rate.get('rmbPrices'),capacity=room.get('maxOccupancy'),meal=rate.get('mealText'),cancel=cancel,bed=room.get('bedType'),area=room.get('roomSize'),floor=room.get('floor'),photos=room.get('images') or [],stock=rate.get('count'),quantity=int(r.get('rooms') or 1),source=h.get('detail_source'),query_conditions=dict(h.get('query_conditions') or {}),room_index=i,rate_index=j))
    return result

def select_room(w,cid):
    choices=[(h,p) for h in w['catalog'].values() if h.get('kind')=='hotel' and not h.get('stale') for p in room_choices(h,w['requirements']) if p['id']==cid]
    if len(choices)!=1:raise DataError('房型报价已失效，请重新查看房型后选择。')
    h,p=choices[0];r=w['requirements'];issues=[]
    if str(p.get('stock'))=='0':raise DataError('该房型报价当前显示无房，请选择其他报价或更新详情。')
    people=int(r.get('adults') or 0)+int(r.get('children') or 0)
    if p.get('capacity'):
        try:capacity=int(p['capacity'])*p['quantity']
        except (ValueError,TypeError):capacity=None
        if capacity is not None and people>capacity:raise DataError(f'所选房型共可容纳{capacity}人，当前同行{people}人。请调整房间数或选择更大房型。')
    else:issues.append('房型可住人数未提供，需向酒店确认。')
    if r.get('children'):issues.append('儿童入住与加床政策需酒店确认。')
    if not r.get('rooms'):issues.append('当前按1间房记录，请确认房间数量。')
    if p.get('price') in (None,''):issues.append('具体报价未提供。')
    p['review']={'issues':issues,'status':'needs_confirmation' if issues else 'checked'}
    w['hotel']=dict(h);w['selected_room']=p;w['stay_skipped']=False
    return f'已选房型：{p["name"]}，{p["quantity"]}间'+(f'，参考报价¥{p["price"]}' if p.get('price') is not None else '')+'。'+('；'.join(issues) if issues else '人数与房间数量已检查。')+'\n请点击“完成住宿选择”，查看推荐往返交通。'

# Field names verified against actual Tuniu cached search responses.
SEATS=[('edz','二等座'),('yz','硬座'),('yw','硬卧'),('rw','软卧'),('rz','软座'),('ydz','一等座'),('edw','二等卧'),('ydw','一等卧'),('swz','商务座'),('wz','无座'),('tdz','特等座'),('gjrw','高级软卧'),('dw','动卧')]
def train_seat(x):
    prices=x.get('price') or {};available=x.get('seatAvailable') or {};quotes=[]
    for key,label in SEATS:
        price=prices.get(key+'Price');n=available.get(key+'Num')
        if price in (None,''):continue
        quotes.append(dict(seat_type=label,price=price,seats=n,seat_label='余票待核实' if n is None else '无票' if str(n)=='0' else '有票（非精确库存）' if str(n)=='99' else f'{n}（查询时）'))
    usable=[p for p in quotes if str(p.get('seats'))!='0']
    picked=(usable or quotes or [dict(seat_type='席别待核实',price=None,seats=None,seat_label='余票待核实')])[0]
    return {**picked,'seat_options':quotes}

def transport_select(w,p,replace=False,recommended=False):
    slot='selected_return' if p.get('direction')=='return' else 'selected_transport';old=w.get(slot)
    if old and old['id']!=p['id'] and not replace:raise DataError('该方向已有班次。请确认替换已有选择，同一方向只能保留一个班次。')
    if str(p.get('seats'))=='0':raise DataError('该班次当前显示无票，请选择其他班次或重新查询。')
    other=w.get('selected_transport' if slot=='selected_return' else 'selected_return')
    if other:
        outbound=p if slot=='selected_transport' else other;back=p if slot=='selected_return' else other
        if outbound.get('arrival') and back.get('departure') and outbound['arrival']>=back['departure']:raise DataError('返程出发时间早于或等于去程到达时间，请调整班次。')
    w[slot]={**p,'selection_status':'recommended' if recommended else 'confirmed'}
    return slot
