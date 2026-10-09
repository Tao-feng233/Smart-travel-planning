"""Project-owned MCP tools. Vendor schemas are handled separately."""
import sys
from contextlib import asynccontextmanager
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mcp.server.fastmcp import FastMCP
from app import providers
from app.rag import retrieve_result, status as knowledge_status_result
from app.data_contracts import items_snapshot
from app.vector_index import close as close_index

@asynccontextmanager
async def data_lifespan(server):
    try:yield {}
    finally:
        close_index()
        from app.request_cache import close
        await close()

mcp=FastMCP('识途本地数据工具',lifespan=data_lifespan)

@mcp.tool()
async def search_places(city: str, keywords: str, category: str='spot',page:int=1,page_size:int=6,location:str|None=None,radius:int=5000) -> dict:
    """高德真实地点查询。category 为 spot/hotel/food/market，不包含真实门票价格。location用于周边查询。"""
    return items_snapshot(await providers.search_poi(city,keywords,category,page,page_size,location,radius),
                          {'city':city,'keywords':keywords,'category':category,'page':page,'page_size':page_size,'location':location,'radius':radius})

@mcp.tool()
async def get_spot_candidates(city:str,keywords:list[str]|None=None,offset:int=0,exclude_ids:list[str]|None=None,exclude_names:list[str]|None=None) -> dict:
    """按已有资料逐批获取真实景点，每批最多4个，返回next_offset与exhausted；按量推荐时继续取下一批，不虚构或代选。"""
    from app.spot_candidates import get_batch
    return await get_batch(city,keywords,offset,exclude_ids,exclude_names)

@mcp.tool()
async def get_place_details(ids:list[str]) -> dict:
    """使用真实POI ID查询景点、餐厅等的营业资料、联系方式、图片和位置；单次最多10个。"""
    return await providers.place_details(ids)

@mcp.tool()
async def search_transport_places(city:str, keywords:str, kind:str='station', include_access_points:bool=False) -> dict:
    """查找车站/机场及可选出入口的真实坐标候选，保留歧义；不猜测用户航站楼或自动确认。"""
    return items_snapshot(await providers.search_transport_places(city,keywords,kind,include_access_points),
                          {'city':city,'keywords':keywords,'kind':kind,'include_access_points':include_access_points})

@mcp.tool()
async def calculate_route(origin: str, destination: str, mode: str='walking', citycode: str='',destination_citycode: str='') -> dict:
    """高德路线：walking/driving/transit，坐标经度在前，耗时为查询时预计。"""
    try:return await providers.route(origin,destination,mode,citycode,destination_citycode)
    except providers.DataError as e:return {'mode':mode,'available':False,'status':'query_failed','reason':str(e)}

@mcp.tool()
async def daily_weather(location: str) -> dict:
    """和风每日天气与当前预警，仅覆盖返回的日期范围。"""
    return await providers.weather(location)

@mcp.tool()
def retrieve_guides(city: str, query: str, visit_date: str|None=None, entity_ids:list[str]|None=None, limit:int=5, end_date:str|None=None) -> dict:
    """检索官方资料，保留来源与日期。青岛景区资料及青岛/成都/杭州/西安目的地概览。"""
    return retrieve_result(city,query,limit,visit_date,entity_ids,end_date=end_date)

@mcp.tool()
def knowledge_status() -> dict:
    """查看知识库文档/父子块数量与索引版本。没有就绪索引时明确降级。"""
    return knowledge_status_result()

if __name__=='__main__':
    # On Windows, load native numerical DLLs before stdio starts blocking reader
    # threads. Lazy numpy import while the pipe reader is active can hang.
    try:import qdrant_client
    except (ImportError,OSError):pass  # Existing installations can still use BM25.
    mcp.run(transport='stdio')
