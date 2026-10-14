"""Networked fallback when the local corpus does not cover a destination.

Append-only by construction: when the local corpus covers the city, none of
this runs and the workspace is left untouched. A city is admitted through the
web only when the retrieved evidence is source-admitted (``web_sources``),
trust-scored (``trust_score``) and names the destination as an administrative
place -- the last gate matters because an official-domain match alone is not
evidence: a broad ``gov.cn`` query happily returns consulate pages for a city
that does not exist, and returns branding pages ("阳光海南网") for a word that
is not a city. Without such evidence the original local rejection still stands,
with a note that a networked lookup was attempted. Nothing is ever invented
here.
"""

from app.core.errors import DataError
from app.knowledge import coverage
from app.integrations import tavily, trust_score
from app.persistence import storage

# Two independent, city-relevant evidences before we trust a destination.
MIN_RELEVANT = 2
MAX_RESULTS = 6
# Official sources first; high-like platform articles only as a last pass. The
# second pass asks with the administrative form of the name -- for a sparse
# destination the first query often surfaces a single useful page, and asking
# for "X市人民政府/文化和旅游局" is what retrieves pages that name it as a
# place at all.
QUERIES = (
    ("official", "{city} 旅游景点 开放时间 门票 官方信息"),
    ("official", "{city}市人民政府 文化和旅游局 景区 开放时间 门票"),
    ("popular", "{city} 必玩景点 行程攻略"),
)
# An administrative unit must follow the name for the evidence to count as
# being *about a place*. Order matters: longer units first.
ADMIN_UNITS = ("特别行政区", "自治州", "自治县", "地区", "市", "省", "区", "县", "盟", "旗")


def admitted_city(w):
    """Canonical key of the city admitted through networked evidence, else None."""
    if not isinstance(w, dict) or w.get("city_source") != "web":
        return None
    return w.get("web_city")


def admits(w, city):
    """True when ``city`` is the city currently admitted through the web."""
    return admitted_city(w) == coverage.key(city)


def source(w, city):
    """"local" | "web" | None -- how the city is currently covered."""
    if coverage.canonical_city(city):
        return "local"
    return "web" if admits(w, city) else None


def require_city_or_web(w, value):
    """Local hit keeps the original behaviour; a web-admitted city passes.

    Never performs I/O. The networked lookup happens once, upstream, on an
    async seam (``admit``); everything downstream only re-reads the mark the
    lookup left on the workspace.
    """
    try:
        coverage.require_city(value)
    except DataError:
        if admits(w, value):
            return "web"
        raise
    return "local"


def _named_as_place(item, city):
    """True when the evidence names ``city`` as an administrative place.

    A bare substring hit is not evidence. A broad official-domain query returns
    pages that merely *contain* the word: "阳光海南网" for 阳光, "火星地貌景区"
    for 火星, "这个春天" for 春天 -- all of them admitted gov.cn sources, none
    of them about a destination. What separates a real destination is that the
    retrieved page names it as a place: "苏州市园林局", "三亚市发展和改革委员
    会", "北京市海淀区". Requiring that keeps the fallback from promoting an
    unrelated page into permission to plan.
    """
    name = str(city or "").strip()
    if len(name) < 2:
        return False
    haystack = "\n".join(str(item.get(field) or "") for field in ("title", "text"))
    return any(name + unit in haystack for unit in ADMIN_UNITS)


def _relevant(items, city):
    return [
        i for i in items if _named_as_place(i, city) and i.get("trust_score") is not None
    ]


async def admit(w, city, progress=None):
    """Admit an uncovered city from networked evidence, or keep rejecting it.

    Returns "local" without touching the workspace when the corpus covers the
    city, "web" once evidence is recorded. Raises DataError -- the original
    rejection plus a note -- when no trustworthy evidence is retrieved, so a
    caller cannot mistake "no data" for "we may proceed".
    """
    if coverage.canonical_city(city):
        return "local"
    if admits(w, city):
        return "web"
    try:
        coverage.require_city(city)
    except DataError as missing:
        original = missing
    else:
        return "local"

    if progress:
        progress("本地资料暂未覆盖该目的地，正在联网检索官方资料")

    collected = []
    attempts = []
    for source_type, query in QUERIES:
        try:
            found = await tavily.search(
                query.format(city=city),
                city=city,
                source_type=source_type,
                max_results=MAX_RESULTS,
            )
        except DataError as err:
            attempts.append({"source_type": source_type, "error": str(err)})
            continue
        items = found.get("items") or []
        collected.extend(items)
        attempts.append(
            {
                "source_type": source_type,
                "returned": len(items),
                "named_as_place": len(_relevant(items, city)),
                "rejected_counts": found.get("rejected_counts") or {},
            }
        )
        if len(_relevant(collected, city)) >= MIN_RELEVANT:
            break

    relevant = _relevant(collected, city)
    # Re-annotate so freshness marks are present even for cached payloads.
    trust_score.enrich(relevant)
    if len(relevant) < MIN_RELEVANT:
        # Rejection leaves no trace on the workspace: a failed lookup must not
        # look like a partial admission.
        raise DataError(
            str(original) + "（已尝试网络检索未取得可信资料）",
            getattr(original, "context", None),
        )

    w["city_source"] = "web"
    w["web_city"] = coverage.key(city)
    w["web_evidence"] = relevant
    w["web_evidence_source"] = "tavily"
    w["web_lookup"] = {
        "city": str(city),
        "attempts": attempts,
        "relevant": len(relevant),
        "required": MIN_RELEVANT,
        "gate": "named_as_place>=%d" % MIN_RELEVANT,
        "checked_at": storage.now(),
    }
    return "web"
