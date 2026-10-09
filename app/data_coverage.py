"""Local destination/place coverage; map search may enrich records, never expand coverage."""
import json
import re
from functools import lru_cache
from .config import ROOT
from .providers import DataError


def key(value):
    return re.sub(r'[\W_]|风景名胜区|风景区|旅游区|景区|市$','',str(value or ''))


@lru_cache(maxsize=4)
def _read(version):
    cities={};names={}
    for path in sorted((ROOT/'data/catalog').glob('*destinations.json')):
        for row in json.loads(path.read_text(encoding='utf-8-sig')):
            cities[key(row['name'])]=row
            names.setdefault(key(row['name']),set()).update(row.get('highlights') or [])
    corpus_cities=set()
    for path in sorted((ROOT/'data/knowledge').glob('*.json')):
        for row in json.loads(path.read_text(encoding='utf-8-sig')):
            city=key(row.get('city'));corpus_cities.add(city)
            names.setdefault(city,set()).update(row.get('entity_names') or [])
            title=row.get('title','').split('：')[0]
            if ':' in title:title=title.split(':')[0]
            if any(x in title for x in ('博物馆','风景区')):names[city].add(title)
    return {'cities':{c:r for c,r in cities.items() if c in corpus_cities},'names':names}


def snapshot():
    files=sorted((ROOT/'data/catalog').glob('*destinations.json'))+sorted((ROOT/'data/knowledge').glob('*.json'))
    return _read(tuple((str(p),p.stat().st_mtime_ns,p.stat().st_size) for p in files))


def canonical_city(value):
    city=key(value)
    for prefix in ('山东省','山东'):
        if city.startswith(prefix):city=city[len(prefix):]
    return city if city in snapshot()['cities'] else None


def require_city(value):
    if not canonical_city(value):
        raise DataError('数据库暂时缺失“'+str(value)+'”的数据，请选择其他地区。',{'phase':'coverage','view':'spot','requested_location':value})


def place_known(city,value):
    c=canonical_city(city)
    if not c:return False
    name=place_key(city,value)
    return len(name)>=2 and name in {place_key(city,x) for x in snapshot()['names'].get(c,set())}


def place_key(city,value):
    """A stable city-prefix/suffix key; no fuzzy parent-child equivalence."""
    c=canonical_city(city) or ''
    name=key(value)
    if c and name.startswith(c+'市'):name=name[len(c)+1:]
    elif c and name.startswith(c):name=name[len(c):]
    return name.removesuffix('公园')


def covered_places(city):
    c=canonical_city(city)
    if not c:return []
    records=snapshot();first=records['cities'][c].get('highlights') or []
    result=[];seen=set()
    for name in [*first,*sorted(records['names'].get(c,set()))]:
        identity=place_key(city,name)
        if len(identity)<2 or identity in seen:continue
        seen.add(identity);result.append(name)
    return result


def require_place(city,value):
    require_city(city)
    if not place_known(city,value):
        raise DataError('数据库暂时缺失“'+str(value)+'”的地点数据，请选择其他地区或已有资料的景点。',{'phase':'coverage','view':'spot','requested_location':value})
