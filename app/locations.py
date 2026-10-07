"""Verified POI positions and conservative cross-provider hotel matching."""
import math
import re
import unicodedata
from .storage import now
from .providers import DataError


def coordinate(value):
    if not isinstance(value,str):return None
    try:
        lon,lat=map(float,value.split(','))
        if not (math.isfinite(lon) and math.isfinite(lat) and -180<=lon<=180 and -85<=lat<=85):return None
        if lon==0 and lat==0:return None
        return f'{lon:.6f},{lat:.6f}'
    except (ValueError,TypeError):return None


def endpoint(p,entrance=True):
    return (coordinate(p.get('entrance')) if entrance else None) or coordinate(p.get('location'))


def normal(value,city=''):
    s=unicodedata.normalize('NFKC',str(value or '')).casefold()
    # Remove only geographic prefixes, punctuation and the generic hotel suffix.
    # Branch tokens (station/street/landmark) must survive comparison.
    provinces=('黑龙江','内蒙古','广西','宁夏','新疆','西藏','山东','陕西','浙江','四川','广东','江苏','河南','河北','湖南','湖北','福建','江西','安徽','云南','贵州','山西','辽宁','吉林','甘肃','青海','海南')
    for part in provinces:
        if city:
            s=s.replace(part+'省'+city.removesuffix('市'),city.removesuffix('市')).replace(part+city.removesuffix('市'),city.removesuffix('市'))
    for part in provinces:
        if s.startswith(part):s=s[len(part):].removeprefix('省');break
    for part in (city.removesuffix('市'),city):
        if part:s=s.replace(part,'')
    return re.sub(r'[\W_]|酒店','',s)


def street(value):
    text=unicodedata.normalize('NFKC',str(value or '')).split('(')[0]
    text=re.split(r'[市区县]',text)[-1]
    m=re.search(r'([\u4e00-\u9fff]{2,12}(?:路|街|道|巷))\s*(\d+(?:-\d+)?)号',text)
    return (m.group(1),m.group(2)) if m else None


def match_hotel(p,rows,city):
    rows=[x for x in rows if coordinate(x.get('location')) and
          (not x.get('typecode') or str(x['typecode']).startswith('10'))]
    rows=list({x.get('provider_id') or x.get('id') or x.get('location'):x for x in rows}.values())
    target=normal(p.get('name'),city);address=street(p.get('address'))
    compatible=[]
    for x in rows:
        other=normal(x.get('name'),city);addr=street(x.get('address'))
        if address and addr and address!=addr:continue
        if other==target:
            compatible.append(x)
        elif address and addr==address and min(len(target),len(other))>=4 and (target in other or other in target):
            compatible.append(x)
    return compatible[0] if len(compatible)==1 else None, len(compatible)


async def locate_hotel(w,p,tool):
    city=w['requirements']['city']
    previous_location=p.get('location')
    p['location_checked_at']=now()
    try:
        result=await tool('search_places',{'city':city,'keywords':p['name'],'category':'hotel','page_size':12})
        rows=result.get('items',[])
        found,count=match_hotel(p,rows,city)
        # A shorter query improves recall when supplier names include qualifiers;
        # it is still subject to the same branch + address verification.
        if not found and not count:
            shortened=re.split(r'[（(·]',p['name'],maxsplit=1)[0]
            if shortened!=p['name'] and len(shortened)>=4:
                extra=await tool('search_places',{'city':city,'keywords':shortened,'category':'hotel','page_size':12})
                found,count=match_hotel(p,rows+extra.get('items',[]),city)
        if found:
            for key in ('location','entrance','citycode','district','city'):
                if found.get(key):p[key]=found[key]
            p['location']=coordinate(found['location'])
            if p['location']!=previous_location:p.pop('access',None)
            p.update(amap_id=found.get('provider_id') or found.get('id','').removeprefix('amap:'),
                     map_source=found.get('source'),map_address=found.get('address'),location_status='verified',
                     match_status='已核对地图地点'+('与街道门牌' if street(p.get('address')) and street(p.get('address'))==street(found.get('address')) else '名称'))
            if not p.get('address') and found.get('address'):p['address']=found['address'];p['address_source']=found.get('source')
        else:
            p['location_status']='ambiguous' if count>1 else 'not_found'
            p['match_status']='存在多个同名分店，坐标待人工核对' if count>1 else '未找到名称与地址一致的地图地点，暂不标注坐标'
    except DataError:
        p['location_status']='query_failed';p['match_status']='地图位置查询失败，可重试；不代表酒店没有位置'
    selected=w.get('hotel')
    if selected and selected.get('id')==p['id']:
        if p.get('location')!=previous_location:selected.pop('access',None)
        selected.update({k:p[k] for k in ('location','entrance','citycode','district','city','address','address_source','amap_id',
                       'map_address','map_source','location_status','match_status','location_checked_at') if k in p})
        if w.get('plan'):w['plan']['stale']=True
    return p
