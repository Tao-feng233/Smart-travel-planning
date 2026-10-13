"""Source admission, native search calls and nationwide discovery regressions."""

import asyncio
import json
from types import SimpleNamespace

import pytest

from app.core.errors import DataError
from app.integrations import tavily, web_sources
from app.integrations.request_cache import close
from app.travel import discovery, web_research, web_spots
from app.travel.requirements import update_requirements
from app.planning import plan_inputs

pytestmark = pytest.mark.web_search_integration


def article(url="https://wlt.example.gov.cn/article", **changes):
    return {
        "url": url,
        "title": "长沙游览",
        "raw_content": "岳麓山、橘子洲适合组合游览。",
        **changes,
    }


def guide():
    item, reason = web_sources.evidence(
        article(), "长沙", "2026-10-12T12:00:00", "official"
    )
    assert not reason
    return item


def native(args, name="search_travel_web", cid="call-1"):
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": cid,
                "type": "function",
                "function": {"name": name, "arguments": json.dumps(args)},
            }
        ],
    }, {}


def test_official_evidence_has_provenance_without_popularity_requirement():
    value = guide()
    assert value["source_kind"] == "official_web" and value["likes"] is None
    assert value["fetched_at"] and value["validity"] == "visit_date_unverified"


@pytest.mark.parametrize(
    "url",
    [
        "https://wlt.example.gov.cn.evil.invalid/a",
        "https://gov.cn@evil.invalid/a",
        "file:///gov.cn/a",
        "https://evil.invalid/?official=gov.cn",
    ],
)
def test_domain_lookalikes_do_not_become_official_sources(url):
    item, _ = web_sources.evidence(article(url), "长沙", "now", "official")
    assert item is None


@pytest.mark.parametrize("count", ["1万", "1.2万", "10,000", "12k"])
def test_popular_articles_need_a_page_like_counter(count):
    item, reason = web_sources.evidence(
        article(
            "https://www.xiaohongshu.com/explore/a",
            raw_content="岳麓山游览体验。\n点赞：" + count + "\n评论：23",
        ),
        "长沙",
        "now",
        "popular",
    )
    assert reason is None and item["likes"] >= 10000 and item["comments"] == 23


@pytest.mark.parametrize(
    "changes",
    [
        {"score": 1.0, "raw_content": "岳麓山游览体验"},
        {"raw_content": "岳麓山游览体验", "content": "点赞：10万"},
        {"raw_content": "岳麓山游览体验\n点赞：9999\n评论：100000"},
        {"raw_content": "作者说别人的文章有点赞：10万，这不代表本文。"},
        {"raw_content": "", "content": "岳麓山游览体验\n点赞：10万"},
        {"raw_content": "作者资料\n获赞：10万\n岳麓山游览体验"},
        {"raw_content": "岳麓山游览体验\n点赞：10000\n推荐另一篇文章\n点赞：20"},
    ],
)
def test_search_scores_comments_and_snippets_cannot_replace_verified_likes(changes):
    item, reason = web_sources.evidence(
        article(
            "https://www.xiaohongshu.com/explore/a",
            **changes,
        ),
        "长沙",
        "now",
        "popular",
    )
    assert item is None and reason == "likes_unverified_or_below_10000"


def test_profile_and_shop_counters_cannot_qualify_as_article_popularity():
    for url in [
        "https://www.xiaohongshu.com/user/profile/a",
        "https://www.ctrip.com/hotels/123",
    ]:
        item, reason = web_sources.evidence(
            article(url, raw_content="点赞：100000"), "长沙", "now", "popular"
        )
        assert item is None and reason == "not_article_url"


def test_model_calls_search_and_only_evidence_bound_names_survive():
    source = guide()
    decisions = [
        native({"query": "长沙轻松游览", "source_type": "official"}),
        (
            {
                "content": json.dumps(
                    {
                        "places": [
                            {"name": "岳麓山", "evidence_ids": [source["id"]]},
                            {"name": "不存在的天宫", "evidence_ids": [source["id"]]},
                            {"name": "橘子洲", "evidence_ids": ["invented"]},
                        ],
                        "summary": "已搜索",
                    }
                )
            },
            {},
        ),
    ]
    calls = []

    async def model(messages, **kwargs):
        if len(decisions) == 1:
            assert messages[-1]["role"] == "tool"
        return decisions.pop(0)

    async def tool(name, args):
        calls.append((name, args))
        return {"items": [source], "status": "available"}

    result = asyncio.run(
        web_research.research({}, "推荐", model, tool, lambda _: None, city="长沙")
    )
    assert [x["name"] for x in result["places"]] == ["岳麓山"]
    assert [x[0] for x in calls] == ["search_travel_web"]


def test_failed_search_is_distinct_from_empty_results():
    decisions = [
        native({"query": "长沙景点", "source_type": "official"}),
        ({"content": '{"places":[],"summary":"暂无"}'}, {}),
    ]

    async def model(*args, **kwargs):
        return decisions.pop(0)

    async def tool(*args):
        raise DataError("额度不足")

    with pytest.raises(DataError, match="额度不足"):
        asyncio.run(web_research.research({}, "推荐", model, tool, lambda _: None))


def test_unadvertised_rag_tool_is_not_executed():
    source = guide()
    decisions = [
        native({"query": "长沙"}, name="retrieve_guides"),
        native({"query": "长沙景点", "source_type": "official"}),
        ({"content": '{"places":[],"summary":"已搜索"}'}, {}),
    ]
    called = []

    async def model(*args, **kwargs):
        return decisions.pop(0)

    async def tool(name, args):
        called.append(name)
        return {"items": [source], "status": "available"}

    asyncio.run(web_research.research({}, "推荐", model, tool, lambda _: None))
    assert called == ["search_travel_web"]


def test_tavily_requests_are_cached_coalesced_and_keep_key_out_of_results(monkeypatch):
    cache, requests = {}, []
    monkeypatch.setattr(
        tavily,
        "setting",
        lambda name, default="": "fixture-secret"
        if name == "TAVILY_API_KEY"
        else default,
    )
    monkeypatch.setattr(tavily.storage, "cached", lambda key: cache.get(key))
    monkeypatch.setattr(
        tavily.storage, "put_cache", lambda key, value, ttl: cache.update({key: value})
    )

    class Response:
        status_code = 200

        def json(self):
            return {"results": [article()]}

    class Client:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, url, **kwargs):
            requests.append(kwargs)
            await asyncio.sleep(0.01)
            return Response()

    monkeypatch.setattr(tavily.httpx, "AsyncClient", Client)

    async def run():
        try:
            values = await asyncio.gather(
                tavily.search("长沙景点"), tavily.search("长沙景点")
            )
            await tavily.search("长沙景点")
            return values
        finally:
            await close()

    result = asyncio.run(run())
    assert len(requests) == 1
    assert (
        requests[0]["json"]["include_domains"]
        and not requests[0]["json"]["include_answer"]
    )
    assert requests[0]["headers"]["Authorization"] == "Bearer fixture-secret"
    assert "fixture-secret" not in json.dumps(result)


def test_nationwide_city_is_not_rejected_by_local_corpus():
    w = {"requirements": {}, "catalog": {}, "selected_spots": [], "plan": None}
    update_requirements(w, {"city": "长沙"})
    assert w["requirements"]["city"] == "长沙"


def test_changing_city_discards_previous_city_web_evidence():
    w = {
        "requirements": {"city": "青岛"},
        "catalog": {},
        "selected_spots": [],
        "plan": None,
        "web_guides": [guide()],
    }
    update_requirements(w, {"city": "长沙"})
    assert not w.get("web_guides")


def test_application_status_does_not_load_local_rag_corpus(monkeypatch):
    from app.api import system
    from app.knowledge import retrieval

    def forbidden():
        pytest.fail("The active app status endpoint should not load RAG")

    monkeypatch.setattr(retrieval, "corpus", forbidden)
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(tool_names=["search_travel_web"]))
    )
    result = system.status(request, user={})
    assert result["data_source"] == "tavily" and not result["rag_enabled_in_app"]
    assert result["knowledge_records"] is None


def test_nationwide_search_resolves_web_candidates_to_map_ids(monkeypatch):
    source = guide()
    w = {
        "requirements": {"city": "长沙", "days": 1},
        "catalog": {},
        "selected_spots": [],
    }
    decisions = [
        native({"query": "长沙代表景点", "source_type": "official"}),
        (
            {
                "content": json.dumps(
                    {
                        "places": [
                            {
                                "name": name,
                                "description": "资料介绍",
                                "evidence_ids": [source["id"]],
                            }
                            for name in ["岳麓山", "橘子洲"]
                        ],
                        "summary": "已发现",
                    }
                )
            },
            {},
        ),
    ]
    called = []

    async def model(*args, **kwargs):
        return decisions.pop(0)

    async def tool(name, args):
        called.append(name)
        assert name != "retrieve_guides"
        if name == "search_travel_web":
            return {"items": [source], "status": "available"}
        assert name == "search_places"
        return {
            "items": [
                {
                    "id": "amap:" + args["keywords"],
                    "kind": "spot",
                    "name": args["keywords"],
                    "location": "112.9,28.1",
                    "city": "长沙",
                }
            ]
        }

    async def recommend(w, items, task, guides):
        assert guides == [source]
        return "比较完成"

    monkeypatch.setattr(discovery, "local_tool", tool)
    result = asyncio.run(
        discovery.search(w, {}, lambda _: None, recommend, model=model)
    )
    assert "2个景点" in result and len(w["spot_search"]["ids"]) == 2
    assert w["web_guides"] == [source] and "rag_results" not in w
    assert "get_spot_candidates" not in called


def test_map_identity_does_not_accept_a_similarly_named_shop():
    assert not web_spots.same_place("长沙", "岳麓山", {"name": "岳麓山纪念品店"})
    assert web_spots.same_place("北京", "故宫", {"name": "故宫博物院"})


def test_alternate_names_must_be_present_in_cited_evidence():
    source = guide()
    value = {
        "places": [
            {
                "name": "岳麓山",
                "aliases": ["岳麓山", "毫无依据的另一座山"],
                "evidence_ids": [source["id"]],
            }
        ]
    }
    assert web_research.grounded_places(value, [source], "长沙")[0]["aliases"] == [
        "岳麓山"
    ]


def test_web_verified_alternate_name_can_resolve_a_map_registered_name():
    called = []

    async def tool(name, args):
        called.append(args["keywords"])
        return {
            "items": [
                {
                    "id": "amap:museum",
                    "kind": "spot",
                    "name": "湖南省博物馆",
                    "location": "112.9,28.1",
                }
            ]
        }

    place = {
        "name": "湖南博物院",
        "aliases": ["湖南省博物馆"],
        "description": "介绍",
        "evidence": [],
    }
    rows = asyncio.run(
        web_spots.resolve("长沙", [place], tool, discovery.main_pois, [], [])
    )
    assert rows[0]["id"] == "amap:museum" and called == ["湖南博物院"]


def test_plan_acquires_web_evidence_without_rag():
    source = guide()
    decisions = [
        native({"query": "长沙岳麓山开放预约", "source_type": "official"}),
        ({"content": '{"places":[],"summary":"已核对资料"}'}, {}),
    ]
    called = []

    async def model(*args, **kwargs):
        return decisions.pop(0)

    async def tool(name, args):
        called.append(name)
        return {"items": [source], "status": "available"}

    ctx = SimpleNamespace(
        requirements={"city": "长沙"},
        spots=[{"name": "岳麓山"}],
        services=SimpleNamespace(model=model, tool=tool),
        progress=lambda _: None,
    )
    assert asyncio.run(plan_inputs.acquire_guides(ctx)) == [source]
    assert called == ["search_travel_web"]


def test_complete_plan_generation_uses_web_guides_and_keeps_known_place_ids(
    monkeypatch, tmp_path
):
    from app.planning import engine
    from datetime import date, timedelta

    source = guide()
    day = (date.today() + timedelta(days=2)).isoformat()
    calls = []
    search_steps = [
        native({"query": "长沙岳麓山开放预约", "source_type": "official"}),
        ({"content": '{"places":[],"summary":"已查询"}'}, {}),
    ]

    async def model(messages, **kwargs):
        if kwargs.get("label") == "web_research":
            return search_steps.pop(0)
        if kwargs.get("label") == "review":
            return {"content": '{"issues":[],"summary":"审核完成"}'}, {}
        return {
            "content": json.dumps(
                {
                    "days": [
                        {
                            "date": day,
                            "items": [
                                {
                                    "candidate_id": "amap:mountain",
                                    "duration": 60,
                                    "evidence_ids": [source["id"]],
                                },
                            ],
                        }
                    ]
                }
            )
        }, {}

    async def tool(name, args):
        calls.append(name)
        assert name not in (
            "retrieve_guides",
            "knowledge_status",
            "get_spot_candidates",
        )
        return {"items": [source]} if name == "search_travel_web" else {"items": []}

    monkeypatch.setattr(engine, "llm", model)
    monkeypatch.setattr(engine, "local_tool", tool)
    monkeypatch.setattr(engine, "RUNTIME", tmp_path)
    w = {
        "requirements": {"city": "长沙", "start_date": day, "days": 1, "adults": 1},
        "catalog": {
            "amap:mountain": {"id": "amap:mountain", "kind": "spot", "name": "岳麓山"}
        },
        "selected_spots": ["amap:mountain"],
        "hotel": None,
        "tickets": {},
    }
    plan = asyncio.run(engine.generate(w, lambda _: None))
    assert plan["guides"] == [source]
    assert any(
        e.get("candidate_id") == "amap:mountain"
        for d in plan["days"]
        for e in d["events"]
    )
    assert calls == ["search_travel_web"] and not search_steps
