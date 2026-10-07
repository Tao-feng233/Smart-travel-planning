"""Project-owned MCP tools. Vendor schemas are handled separately."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mcp.server.fastmcp import FastMCP
from app import providers
from app.rag import retrieve

mcp=FastMCP('识途本地数据工具')

@mcp.tool()
async def search_places(city: str, keywords: str, category: str='spot',page:int=1,page_size:int=6,location:str|None=None,radius:int=5000) -> dict:
    """高德真实地点查询。category 为 spot/hotel/food/market，不包含真实门票价格。location用于周边查询。"""
    return {'items':await providers.search_poi(city,keywords,category,page,page_size,location,radius)}

@mcp.tool()
async def get_place_details(ids:list[str]) -> dict:
    """使用真实POI ID查询景点、餐厅等的营业资料、联系方式、图片和位置；单次最多10个。"""
    return await providers.place_details(ids)

@mcp.tool()
async def calculate_route(origin: str, destination: str, mode: str='walking', citycode: str='0532') -> dict:
    """高德路线：walking/driving/transit，坐标经度在前，耗时为查询时预计。"""
    return await providers.route(origin,destination,mode,citycode)

@mcp.tool()
async def daily_weather(location: str) -> dict:
    """和风每日天气与当前预警，仅覆盖返回的日期范围。"""
    return await providers.weather(location)

@mcp.tool()
def retrieve_guides(city: str, query: str) -> dict:
    """检索官方资料，保留来源与日期。青岛景区资料及青岛/成都/杭州/西安目的地概览。"""
    return {'items':retrieve(city,query)}

if __name__=='__main__': mcp.run(transport='stdio')
