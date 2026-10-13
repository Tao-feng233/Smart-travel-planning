"""Bounded live MCP + model + map verification, isolated from user storage."""

# ruff: noqa: E402 -- these scripts bootstrap the workspace import path.

import argparse
import asyncio
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from app.core.data_settings import mcp_environment
from app.integrations import tools
from app.integrations.providers import llm
from app.integrations.request_cache import close
from app.persistence import storage
from app.travel.discovery import main_pois
from app.travel.web_research import research
from app.travel.web_spots import resolve


async def main(city, days):
    folder = ROOT / "data/runtime/tavily-search-20261012"
    folder.mkdir(parents=True, exist_ok=True)
    storage.DB = folder / "live-model-check.sqlite3"
    storage.init()
    setup = (
        "import sys,runpy;sys.path.insert(0," + repr(str(ROOT)) + ");"
        "from pathlib import Path;from app.persistence import storage;"
        "storage.DB=Path("
        + repr(str(folder / "live-mcp-check.sqlite3"))
        + ");storage.init();"
        "runpy.run_module('app.integrations.mcp_server',run_name='__main__')"
    )
    params = StdioServerParameters(
        command=sys.executable, args=["-c", setup], cwd=str(ROOT), env=mcp_environment()
    )
    started = time.perf_counter()
    calls = []
    try:
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                names = {t.name for t in (await session.list_tools()).tools}
                assert {
                    "search_travel_web",
                    "retrieve_guides",
                    "knowledge_status",
                } <= names
                tools.SESSION = session

                async def invoke(name, args):
                    calls.append(name)
                    assert name not in (
                        "retrieve_guides",
                        "knowledge_status",
                        "get_spot_candidates",
                    )
                    return await tools.local_tool(name, args)

                def progress(message):
                    print(message, flush=True)

                result = await research(
                    {"city": city, "days": days, "preferences": ["人文", "轻松"]},
                    f"为{days}天旅行发现至少{days * 2}个具体景点及适量备选，优先当地文旅官方旅游线路和景区介绍。",
                    llm,
                    invoke,
                    progress,
                    city=city,
                )
                items = await resolve(city, result["places"], invoke, main_pois, [], [])
                report = {
                    "city": city,
                    "days": days,
                    "elapsed_seconds": round(time.perf_counter() - started, 2),
                    "tool_calls": calls,
                    "discovered_places": [p["name"] for p in result["places"]],
                    "mapped_places": [
                        {
                            "id": p["id"],
                            "name": p["name"],
                            "has_coordinates": bool(p.get("location")),
                        }
                        for p in items
                    ],
                    "sources": [
                        {"title": g["title"], "url": g["url"], "kind": g["source_kind"]}
                        for g in result["guides"]
                    ],
                    "rag_tools_registered": True,
                    "rag_tools_called": False,
                }
                (folder / "live-model-mcp-check.json").write_text(
                    json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
                assert items, "No evidence-backed place obtained usable map coordinates"
    finally:
        tools.SESSION = None
        await close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--city", default="长沙")
    parser.add_argument("--days", type=int, default=2)
    args = parser.parse_args()
    asyncio.run(main(args.city, args.days))
