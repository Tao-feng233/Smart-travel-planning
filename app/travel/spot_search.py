"""Bounded candidate collection and publication for one scenic search request."""

from dataclasses import dataclass
import math

from app.core.errors import DataError
from app.knowledge import coverage
from app.travel.spot_hierarchy import candidates


@dataclass(frozen=True)
class SpotSearch:
    city: str
    classic: list
    expanding: bool
    previous: dict
    history: list
    pending_rejections: list
    previous_candidates: list
    excluded_ids: list
    excluded_names: list
    keywords: list
    minimum: int

    @classmethod
    def prepare(cls, w, args, classic, displayed_ids, minimum):
        city = w["requirements"]["city"]
        expanding = args.get("expand_spots") is True
        previous = w.get("spot_search") or {}
        history = (
            list(
                dict.fromkeys(previous.get("history_ids", []) + previous.get("ids", []))
            )
            if previous.get("city") == city
            else []
        )
        pending = [cid for cid in displayed_ids if cid not in w["selected_spots"]]
        excluded_ids = list(
            dict.fromkeys(
                w.get("rejected_spots", [])
                + w.get("selected_spots", [])
                + pending
                + (history if expanding else [])
            )
        )
        excluded_names = list(w.get("rejected_spot_names", [])) + [
            w["catalog"][cid]["name"] for cid in excluded_ids if cid in w["catalog"]
        ]
        keywords = [
            str(keyword)[:40]
            for keyword in (
                args.get("keywords")
                or (previous.get("keywords") if expanding else None)
                or classic[:3]
            )[:4]
        ]
        return cls(
            city,
            classic,
            expanding,
            previous,
            history,
            pending,
            list(w.get("candidates", [])),
            excluded_ids,
            excluded_names,
            keywords,
            minimum,
        )

    def unavailable_message(self):
        previous_ids = self.previous.get("ids") or []
        if self.previous.get("city") == self.city and previous_ids:
            return (
                "当前条件下暂未查到可替换的新景点，已保留原有 "
                + str(len(previous_ids))
                + " 个候选与已有选择。可以调整偏好或说明具体景点名称后继续查询。"
            )
        if self.expanding:
            return "本轮暂未找到新的相关景点，已有推荐与选择已保留。已有资料的候选已查到末尾或位置暂未核实，可以更换主题或地区；不会重复推荐已看过的地点。"
        return "本次已有资料中的景点暂未取得可用地图候选，当前选择保留。可以稍后重试；不会以背景介绍代替已核对的地点。"

    def recommendation_task(self, count):
        lead = (
            "补充新相关景点，保留已选景点与偏好，避免重复；"
            if self.expanding
            else "结合已知游玩天数推荐能组成整趟旅行的景点集合，并提供适量备选；"
        )
        return (
            lead
            + "本轮目标至少"
            + str(self.minimum)
            + "个候选，已核对"
            + str(count)
            + "个；候选与备选不等于全部必去。数量按预计停留与休息、位置和需求判断。优先匹配条件，其次参考城市代表景点，不把评分当实时热门榜"
        )

    def summary(self, count, model_summary):
        shortage = (
            "\n目前仅核对到"
            + str(count)
            + "个候选，少于本次至少"
            + str(self.minimum)
            + "个的目标；已有资料、位置或通行条件不足，未虚构补齐。"
            if count < self.minimum
            else ""
        )
        return (
            f"已{'补充' if self.expanding else '推荐'}{count}个景点，已展示在右侧，可分页比较行程建议与备选。这些是候选选择，不表示全部必须游玩。"
            + model_summary
            + shortage
        )


@dataclass
class SpotBatch:
    items: list
    next_offset: int
    source_exhausted: bool


async def collect(w, query, progress, tool, filter_pois, maximum):
    items, offset, seen, source_exhausted = [], 0, set(), False
    for batch in range(math.ceil(maximum / 4)):
        progress(
            "正在获取第"
            + str(batch + 1)
            + "批景点（每批最多4个），目标至少"
            + str(query.minimum)
            + "个候选"
        )
        result = await tool(
            "get_spot_candidates",
            {
                "city": query.city,
                "keywords": query.keywords,
                "offset": offset,
                "exclude_ids": query.excluded_ids,
                "exclude_names": query.excluded_names,
            },
        )
        for item in filter_pois(result.get("items", []))[:4]:
            if not coverage.place_known(query.city, item["name"]):
                continue
            if item["id"] in seen or item["id"] in query.excluded_ids:
                continue
            seen.add(item["id"])
            items.append(item)
        merged = {**w["catalog"], **{item["id"]: item for item in items}}
        items = candidates(merged, items)
        next_offset = result.get("next_offset")
        source_exhausted = result.get("exhausted") is True
        advanced = isinstance(next_offset, int) and next_offset > offset
        if advanced:
            offset = next_offset
        if len(items) >= query.minimum or source_exhausted or not advanced:
            break
    return SpotBatch(items, offset, source_exhausted)


def stage_candidates(w, query, items):
    w["catalog"].update({item["id"]: item for item in items})
    w["candidates"] = items
    items = candidates(w["catalog"], items)
    w["spot_search"] = {
        "city": query.city,
        "keywords": query.keywords,
        "ids": [item["id"] for item in items],
        "page": 1,
        "provider_page": 1,
        "history_ids": query.history,
        "exhausted": True,
    }
    w["discovery_mode"] = False
    return items


def rank(items, prefer_known):
    items.sort(
        key=lambda item: (
            (not item.get("classic")) if prefer_known else False,
            item.get("recommendation_rank", 99),
            not item.get("classic"),
            -(
                float(item.get("rating") or 0)
                if str(item.get("rating") or "").replace(".", "", 1).isdigit()
                else 0
            ),
        )
    )
    # Ranking orders candidates; it cannot remove valid unranked alternatives.
    for item in items:
        if item.get("recommendation_rank") is None:
            item.setdefault("discovery_label", "可比较景点")


async def screen_routes(w, items, progress):
    from app.planning.engine import route_options, choose_route
    from app.travel.access import screen

    anchor = w.get("hotel") or next(
        (
            w["catalog"].get(cid)
            for cid in w.get("selected_spots", [])
            if w["catalog"].get(cid, {}).get("location")
        ),
        None,
    )
    if anchor and not anchor.get("stale"):
        progress("正在提前核对景点与已选区域的通行")
        return await screen(w, items, lambda _: anchor, route_options, choose_route)
    return items, []


def restore_candidates(w, query):
    w["candidates"] = query.previous_candidates
    if query.previous:
        w["spot_search"] = query.previous
    else:
        w.pop("spot_search", None)


async def enrich_parents(w, items, tool):
    missing = list(
        dict.fromkeys(
            item["parent_id"]
            for item in items
            if item.get("parent_id") and item["parent_id"] not in w["catalog"]
        )
    )[:4]
    if missing:
        try:
            parents = await tool("get_place_details", {"ids": missing})
            w["catalog"].update(
                {
                    item["id"]: item
                    for item in parents.get("items", [])
                    if item.get("kind") == "spot"
                }
            )
        except DataError:
            pass


def publish(w, query, batch, items, excluded):
    w["spot_search"] = {
        "city": query.city,
        "keywords": query.keywords,
        "provider_page": 1,
        "page": 1,
        "ids": [item["id"] for item in items],
        "history_ids": query.history,
        "excluded": excluded,
        "exhausted": True,
        "source_exhausted": batch.source_exhausted,
        "minimum": query.minimum,
        "batch_size": 4,
        "next_offset": batch.next_offset,
    }
    w["discovery_mode"] = False
    if not query.expanding:
        w["spots_confirmed"] = False
    w["stage"] = "景点"
