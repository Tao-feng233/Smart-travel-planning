"""Recommend only supplied candidates; own context, cached calls and annotations."""

import json

from app import prompts
from app.agents.recommendation_context import context
from app.core.config import setting
from app.core.errors import DataError
from app.core.text import readable
from app.integrations import enrichment
from app.integrations.request_cache import singleflight
from app.persistence import storage
from app.planning import visit_analysis
from app.travel import visits
from app.travel.price_hints import hint
from app.travel.spot_hierarchy import ancestors

ANNOTATIONS = {
    "classic",
    "recommendation_rank",
    "recommendation_role",
    "discovery_label",
    "recommendation",
    "evidence",
    "visit_suggestion",
}


def messages_for(w, items, task, guides):
    payload = {
        "task": task,
        "requirements": w["requirements"],
        "visit_requests": w.get("visit_requests", {}),
        "tour_dates": visits.dates(w),
        "items": [
            {
                **{key: value for key, value in item.items() if key not in ANNOTATIONS},
                **({"reference": "城市代表景点"} if item.get("classic") else {}),
                "evidence": [
                    {key: source.get(key) for key in ("id", "title", "url", "source_kind", "likes", "comments")}
                    for source in item.get("evidence", [])
                ],
            }
            for item in items
        ],
        "parent_relations": {
            item["id"]: ancestors(w.get("catalog", {}), item["id"]) for item in items
        },
        "recommendation_context": context(w),
        "daily_time_budgets": visit_analysis.budgets(w),
        "recommendation_policy": prompts.interaction_state(w)["recommendation_policy"],
        "rest_assumptions": {
            "midday_rest_minutes": w["requirements"].get("midday_rest_minutes", 60),
            "between_visit_break_minutes": 30,
            "note": "未经过模型细化时的初步预留，人数与天气等条件明确后可调整。",
        },
        "guides": [{**guide, "text": guide["text"][:2400]} if guide.get("retrieval") == "Tavily web search" else guide for guide in guides or []],
    }
    # Keep the JSON boundary and message shape stable so existing cache entries
    # and provider input semantics survive the refactor.
    facts = enrichment.model_facts(json.loads(json.dumps(payload, ensure_ascii=False)))
    return [
        {"role": "system", "content": prompts.system("recommend")},
        {"role": "user", "content": json.dumps(facts, ensure_ascii=False)},
    ]


async def cached_response(w, items, messages, model):
    key = storage.cache_key(
        "recommend:v3",
        {
            "workspace": w.get("id"),
            "model": setting("LLM_MODEL", "deepseek-flash"),
            "messages": messages,
        },
    )

    async def produce():
        old = storage.cached(key)
        if old:
            return old
        message, _ = await model(
            messages,
            json_mode=True,
            max_tokens=min(8000, max(2500, len(items) * 200)),
            label="recommend",
        )
        try:
            value = json.loads(message.get("content") or "")
            if not isinstance(value, dict) or not isinstance(
                value.get("recommendations"), list
            ):
                raise ValueError()
        except (ValueError, TypeError):
            return message
        storage.put_cache(key, message, 600)
        return message

    return await singleflight(("recommend", key), produce)


def annotate(w, item, entry, rank, evidence):
    item["recommendation"] = readable(entry.get("reason", ""))[:450]
    item["recommendation_rank"] = rank
    if item.get("kind") == "spot":
        dt = entry.get("visit_date")
        period = entry.get("visit_period", "any")
        if period in visits.PERIODS:
            item["visit_suggestion"] = {
                "date": dt if dt in visits.dates(w) else None,
                "period": period,
                "reason": str(entry.get("timing_reason") or "")[:180],
            }
    item["recommendation_role"] = (
        "alternative" if entry.get("role") == "alternative" else "primary"
    )
    item["discovery_label"] = (
        "备选景点"
        if item.get("kind") == "spot" and entry.get("role") == "alternative"
        else "行程建议景点"
        if item.get("kind") == "spot"
        else "优先推荐"
    )
    item["evidence"] = [
        evidence[cid] for cid in entry.get("evidence_ids", []) if cid in evidence
    ]


def apply_response(w, items, guides, message):
    try:
        data = json.loads(message["content"])
    except (ValueError, TypeError, KeyError):
        return "候选已查到，可以查看来源并选择。"
    by_id = {item["id"]: item for item in items}
    evidence = {guide["id"]: guide for guide in guides or []}
    seen = set()
    limit = 24 if any(item.get("kind") == "spot" for item in items) else 5
    for rank, entry in enumerate(data.get("recommendations", [])):
        if entry.get("id") in by_id and entry["id"] not in seen and len(seen) < limit:
            seen.add(entry["id"])
            annotate(w, by_id[entry["id"]], entry, rank, evidence)
    summary = readable(data.get("summary", "已返回候选，请比较后选择。"))
    if any(item.get("kind") == "spot" for item in items) and isinstance(
        data.get("coverage_note"), str
    ):
        summary += "\n" + readable(data["coverage_note"])[:400]
    return summary


async def recommend(w, items, task, guides, *, model, ensure_weather):
    await ensure_weather(w, lambda _: None)
    for item in items:
        if item.get("kind") in ("spot", "food"):
            item["price_hint"] = hint(w, item)
    messages = messages_for(w, items, task, guides)
    try:
        response = await cached_response(w, items, messages, model)
    except DataError:
        return "真实候选资料已展示，模型比较暂未完成，可直接查看并继续查询。"
    return apply_response(w, items, guides, response)
