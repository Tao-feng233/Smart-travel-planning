"""Real embedding/Qdrant checks through the application's MCP transport."""
import argparse
import asyncio
import json
import sys
import time
from datetime import timedelta
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from app.config import ROOT
from app.data_settings import mcp_environment

def result_data(result):
    assert not result.isError
    return result.structuredContent or json.loads('\n'.join(part.text for part in result.content if part.type=='text'))


async def check(live_poi=False):
    evidence=[]
    parameters=StdioServerParameters(command=sys.executable,args=[str(ROOT/'app/mcp_server.py')],cwd=str(ROOT),env=mcp_environment())
    async with stdio_client(parameters) as (read,write):
        async with ClientSession(read,write,read_timeout_seconds=timedelta(seconds=30)) as session:
            await session.initialize()
            tools=(await session.list_tools()).tools
            assert {'retrieve_guides','knowledge_status','search_transport_places'} <= {t.name for t in tools}
            status=result_data(await session.call_tool('knowledge_status',{}))
            assert status['dense_index_ready'], 'Initialize the knowledge index first'
            cases=[
                ('成都','天气热的时候看不到室外大熊猫怎么办','2026-10-12','official-cd-panda-notice'),
                ('成都','冬天早上几点能进熊猫基地','2026-11-12','official-cd-panda-hours'),
                ('成都','杜甫草堂学生购票优惠','2026-10-12','official-cd-dfct-tickets'),
                ('西安','城墙的历史和建筑特色','2026-10-12','official-xa-citywall-background'),
            ]
            for city,query,visit_date,expected in cases:
                begin=time.perf_counter()
                response=await session.call_tool('retrieve_guides',{'city':city,'query':query,'visit_date':visit_date})
                assert not response.isError
                result=result_data(response)
                assert result['status']=='available', result.get('degraded_reason')
                assert any(expected in p['record_ids'] for p in result['items']), 'Expected source not retrieved'
                assert any(p['dense_score'] is not None for p in result['items']), 'Real dense retrieval missing'
                evidence.append({'city':city,'query':query,'elapsed_ms':round((time.perf_counter()-begin)*1000),
                                 'titles':[p['title'] for p in result['items']],
                                 'dense_scores':[p['dense_score'] for p in result['items']]})
            wrong_city=result_data(await session.call_tool('retrieve_guides',{'city':'杭州','query':'栈桥 八大关'}))
            assert wrong_city['items']==[]
            dated=result_data(await session.call_tool('retrieve_guides',{'city':'青岛','query':'崂山限流','visit_date':'2026-10-12'}))
            assert all(p.get('source_kind')!='historical_notice' for p in dated['items'])
            if live_poi:
                for arguments in ({'city':'成都','keywords':'成都东站','kind':'station'},
                                  {'city':'成都','keywords':'成都双流国际机场','kind':'airport'}):
                    result=result_data(await session.call_tool('search_transport_places',arguments))
                    assert result['status']=='available' and all(p['_data']['coordinate_system']=='GCJ-02' for p in result['items'])
                    evidence.append({'transport_query':arguments,'count':len(result['items']),
                                     'names':[p['name'] for p in result['items']]})
    output={'status':'passed','knowledge':status,'checks':evidence,'live_poi':live_poi}
    folder=ROOT/'data/runtime/data-service-validation';folder.mkdir(parents=True,exist_ok=True)
    (folder/'mcp-check.json').write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(output,ensure_ascii=False,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live-poi',action='store_true')
    asyncio.run(check(parser.parse_args().live_poi))
