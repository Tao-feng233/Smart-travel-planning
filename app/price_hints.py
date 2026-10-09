"""Source-backed card labels; an unknown or zero POI cost is not free admission."""
import json
from decimal import Decimal,InvalidOperation
from functools import lru_cache
from datetime import date,timedelta
from .config import ROOT
from .enrichment import ticket_date
from .providers import DataError


def amount(value):
    if isinstance(value,bool) or value is None:return None
    try:
        n=Decimal(str(value).strip())
        return format(n.normalize(),'f') if n.is_finite() and n>=0 else None
    except InvalidOperation:return None


@lru_cache(maxsize=1)
def policies():
    return json.loads((ROOT/'data/catalog/admission-policies.json').read_text(encoding='utf-8'))


def hint(w,p):
    kind=p.get('kind');cost=amount(p.get('cost'))
    if kind=='food':
        return {'label':'参考人均 ¥'+cost if cost is not None else '人均待核实',
                'basis':'map_reference' if cost is not None else 'unknown',
                'note':'地图参考人均，不是当前菜单或实际消费报价。' if cost is not None else '来源未提供可靠人均消费。','source':p.get('source')}
    if kind!='spot':return None
    wanted=None
    try:wanted=ticket_date(w,p,{})
    except (DataError,ValueError,TypeError,KeyError):
        # A missing/past visit date must not hide a factual consumption reference.
        pass
    city=str(w.get('requirements',{}).get('city') or p.get('city') or '').removesuffix('市')
    for row in policies():
        if row['city']!=city or p.get('name') not in row['names']:continue
        checked=date.fromisoformat(row['checked_at']);visit=date.fromisoformat(wanted) if wanted else date.today()
        if date.today()>checked+timedelta(days=90) or visit>checked+timedelta(days=90):continue
        return {'label':'免费入园','basis':'official_free_admission','note':row['note'],'source':row['source']}
    snapshot=(w.get('tickets') or {}).get(p.get('id')) or {}
    if wanted and snapshot.get('requested_date')==wanted:
        prices=[amount(x.get('startPrice')) for x in snapshot.get('items',[])
                if x.get('product_group')=='admission' and x.get('date_status')=='in_sales_window'
                and '成人' in str(x.get('personTypeName') or '')]
        prices=[Decimal(x) for x in prices if x is not None and Decimal(x)>0]
        if prices:return {'label':'门票起价 ¥'+format(min(prices).normalize(),'f'),'basis':'interval_minimum',
                          'note':'供应商区间最低价；所选日期价格、入园范围和适用票种需核实。','source':snapshot.get('source')}
    if cost is not None:
        return {'label':'参考消费 ¥'+cost+'/人','basis':'map_reference',
                'note':'地图参考人均消费，不等同于门票；入园及附加项目费用需核实。','source':p.get('source')}
    return {'label':'费用待核实','basis':'unknown','note':'未取得可靠费用资料，不能据此判断免费。'}
