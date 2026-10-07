"""Keep provider facts and unknowns separate from travel recommendations."""
import re
from datetime import date
from .providers import DataError
from .storage import now

HOTEL_FIELDS=('hotelName','hotelNameEn','starName','brandName','firstPic','address','cityName','cityCode','business',
              'commentScore','checkInTime','checkOutTime','hotelPolicies','policies','commentDigest','reviews','roomTypes')
ROOM_FIELDS=('roomTypeId','roomTypeName','bedType','maxOccupancy','roomSize','floor','images','ratePlans')
RATE_FIELDS=('ratePlanName','vendorRatePlanId','rmbPrices','mealText','cancelText','cancelDesc','count')

def model_facts(value):
    """Media and road vertices are UI data, not useful context for language reasoning."""
    if isinstance(value,dict):return {k:model_facts(v) for k,v in value.items() if k not in ('photos','images','polylines','children')}
    if isinstance(value,list):return [model_facts(v) for v in value]
    return value

def hotel_detail(d):
    # Explicit field allowlists keep payment / booking credentials out of workspace snapshots.
    out={k:d[k] for k in HOTEL_FIELDS if k in d and k!='roomTypes'}
    def scrub(x):
        if isinstance(x,dict):return {k:scrub(v) for k,v in x.items() if not any(t in k.lower() for t in ('token','prebook','payment','password','secret'))}
        if isinstance(x,list):return [scrub(v) for v in x[:100]]
        return x
    out=scrub(out);out['roomTypes']=[]
    for room in (d.get('roomTypes') or [])[:100]:
        row={k:scrub(room[k]) for k in ROOM_FIELDS if k in room and k!='ratePlans'}
        row['ratePlans']=[{k:scrub(rate[k]) for k in RATE_FIELDS if k in rate} for rate in (room.get('ratePlans') or [])[:100]]
        out['roomTypes'].append(row)
    return out

def ticket_date(w,p,args):
    chosen=args.get('visit_date')
    if not chosen:
        chosen=(w.get('visit_requests',{}).get(p['id']) or {}).get('date')
    if not chosen and w.get('plan') and not w['plan'].get('stale'):
        chosen=next((d['date'] for d in w['plan'].get('days',[]) if any(e.get('candidate_id')==p['id'] for e in d.get('events',[]))),None)
    if not chosen:chosen=(p.get('visit_suggestion') or {}).get('date') or w['requirements'].get('start_date')
    try:dt=date.fromisoformat(chosen)
    except (TypeError,ValueError):raise DataError('请提供有效的门票游玩日期（YYYY-MM-DD）。') from None
    if dt<date.today():raise DataError('门票游玩日期不能早于今天。')
    return dt.isoformat()

def ticket_names(p):
    names=[p['name']]
    # Only remove a terminal generic designation; never collapse a child attraction into its parent.
    shorter=re.sub(r'(?:风景名胜区|风景区|旅游景区|博物馆|景区)$','',p['name']).strip()
    if shorter and shorter!=p['name'] and len(shorter)>=3:names.append(shorter)
    return names[:2]

TICKET_FIELDS=('productId','scenicId','scenicName','resId','resName','startPrice','departsDate','resourceIds','startDate','endDate',
               'personType','personTypeName','ticketType','ticketTypeName','startNum','enterTypeName','admissionVoucherDesc',
               'advanceBookDay','advanceBookHour','commonAgeLimit','scenicSpotStar','detailAddr','lossName','scenicOpenInfo','adviseTourDuration')

def ticket_snapshot(rows,requested,provenance,query_name,p):
    items=[];seen=set()
    for x in rows[:200]:
        if not isinstance(x,dict):continue
        row={k:x[k] for k in TICKET_FIELDS if k in x};key=(str(x.get('productId')),str(x.get('resId')),x.get('resName'),x.get('personTypeName'))
        if key in seen:continue
        seen.add(key);name=x.get('resName') or ''
        addon=any(v in name for v in ('不含门票','不含景区','文创','纪念品','餐食','AR剧本','AR眼镜'))
        group='addon' if addon else 'admission' if '门票' in name else 'other'
        row.update(product_group=group,product_group_label={'addon':'附加体验 / 餐食 / 商品','admission':'含门票产品','other':'产品类型需核对'}[group],
                   price_basis='interval_minimum',requested_date_price=None,inventory_status='unknown',
                   date_status='unknown',match_status='景点名称与入园范围需核对')
        start=str(x.get('startDate') or '')[:10];end=str(x.get('endDate') or '')[:10]
        try:
            date.fromisoformat(start);date.fromisoformat(end)
            row['date_status']='in_sales_window' if start<=requested<=end else 'outside_sales_window'
        except ValueError:pass
        items.append(row)
    items.sort(key=lambda x:({'admission':0,'other':1,'addon':2}[x['product_group']],0 if '成人' in (x.get('personTypeName') or '') else 1))
    return {'items':items,'source':provenance,'requested_date':requested,'query_name':query_name,'candidate_name':p['name'],
            'status':'available' if items else 'not_found','checked_at':now(),
            'note':'起价为供应商返回的区间最低价；即使最低价日期与游玩日期相同，也需确认该日价格、适用人群和预约名额。'}
