"""Read-only public POI/route probe, without account contents or API credentials."""
import asyncio,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import providers,planning
from app.locations import locate_hotel

async def tool(name,args):
    if name=='search_places':return {'items':await providers.search_poi(**{('keywords' if k=='keywords' else k):v for k,v in args.items()})}
    if name=='calculate_route':return await providers.route(**args)

async def main():
    rows=[]
    for city,name,address in [('西安','西安钟楼诺富特酒店','案板街16号（近易俗社街区东门）'),
                              ('青岛','维也纳国际酒店·山东青岛火车站东广场栈桥店','湖南路59号'),
                              ('青岛','青岛五四广场海景美仑国际公寓酒店','香港中路26号')]:
        p={'id':'probe:'+name,'kind':'hotel','name':name,'address':address}
        await locate_hotel({'requirements':{'city':city}},p,tool)
        rows.append({k:p.get(k) for k in ('name','address','location','location_status','match_status')})
    planning.local_tool=tool
    # Public POI points taken from the original Qingdao restaurant example.
    a={'id':'a','name':'全季酒店（青岛五四广场海景店）','location':'120.388233,36.065221','entrance':'120.387995,36.065871','citycode':'0532'}
    b={'id':'b','name':'众品老方子锅贴甜沫(栈桥店)','location':'120.316063,36.063951','entrance':'120.316061,36.063770','citycode':'0532'}
    options=await planning.route_options(a,b)
    result={'hotels':rows,'restaurant_leg':[{k:x.get(k) for k in ('mode','available','status','minutes','reason','endpoint_fallback')} for x in options]}
    out=Path('data/runtime/location-live-check.json');out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))
    assert all(p['location_status']=='verified' for p in rows)
    assert any(x.get('available') for x in options)

if __name__=='__main__':asyncio.run(main())
