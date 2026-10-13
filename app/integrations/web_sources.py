"""Source admission for web evidence, independent of model judgements."""

import hashlib
import json
import re
from urllib.parse import urlsplit

from app.core.config import ROOT, setting

POPULAR_DOMAINS = (
    "xiaohongshu.com",
    "mafengwo.cn",
    "ctrip.com",
    "bilibili.com",
    "zhihu.com",
    "douyin.com",
    "toutiao.com",
)


def official_domains():
    """Government sites plus explicitly reviewed source-registry/config hosts."""
    domains = {"gov.cn"}
    for path in (ROOT / "data").glob("knowledge-sources*.json"):
        for source in json.loads(path.read_text(encoding="utf-8-sig")):
            if source.get("id", "").startswith("official-"):
                domains.update(source.get("allowed_hosts") or [])
    domains.update(setting("TAVILY_OFFICIAL_DOMAINS").split(","))
    return sorted({x.strip().lower() for x in domains if x.strip()})


def host_of(url):
    try:
        parts = urlsplit(url)
        if parts.scheme not in ("http", "https") or parts.username or parts.password:
            return ""
        return (parts.hostname or "").lower().rstrip(".")
    except (TypeError, ValueError):
        return ""


def admitted_host(host, domains):
    return bool(host) and any(host == d or host.endswith("." + d) for d in domains)


def article_url(url):
    """Only supported content URLs; profile/search/shop counters are not article likes."""
    host = host_of(url)
    paths = {
        "xiaohongshu.com": r"/(?:explore|discovery/item)/",
        "mafengwo.cn": r"/(?:i/|gonglve/)",
        "ctrip.com": r"/travels/",
        "bilibili.com": r"/(?:read/|video/)",
        "zhihu.com": r"/(?:p/|question/[^/]+/answer/)",
        "douyin.com": r"/(?:video|note)/",
        "toutiao.com": r"/(?:article/|i\d+)",
    }
    return any(
        admitted_host(host, [domain]) and re.match(pattern, urlsplit(url).path)
        for domain, pattern in paths.items()
    )


def counter(text, labels):
    """Accept an explicit, standalone page counter; never infer from search score."""
    expression = "|".join(labels)
    number = r"([\d,]+(?:\.\d+)?)\s*(万|亿|[kKmM])?\s*\+?"
    counts = set()
    for line in text.splitlines():
        line = line.strip().strip("*# ")
        match = re.fullmatch(rf"(?:{expression})\s*[:：]?\s*{number}", line)
        if not match:
            match = re.fullmatch(rf"{number}\s*(?:{expression})", line)
        if match:
            scale = {"万": 10000, "亿": 100000000, "k": 1000, "m": 1000000}
            counts.add(
                int(
                    float(match[1].replace(",", ""))
                    * scale.get((match[2] or "").lower(), 1)
                )
            )
    return next(iter(counts)) if len(counts) == 1 else None


def evidence(row, city, queried_at, source_type):
    url = row.get("url") or ""
    host = host_of(url)
    raw = row.get("raw_content")
    raw = raw if isinstance(raw, str) else ""
    snippet = row.get("content")
    snippet = snippet if isinstance(snippet, str) else ""
    text = (raw or snippet).strip()
    if not text or not host:
        return None, "missing_content"
    official = admitted_host(host, official_domains())
    likes = comments = None
    if not official:
        if source_type == "official" or not admitted_host(host, POPULAR_DOMAINS):
            return None, "unreviewed_source"
        if not article_url(url):
            return None, "not_article_url"
        # Popularity must occur in the retrieved page, not the search snippet/title.
        likes = counter(raw, ("点赞", "点赞数", "赞", "赞同", "likes", "Likes"))
        comments = counter(raw, ("评论", "评论数", "comments", "Comments"))
        if likes is None or likes < 10000:
            return None, "likes_unverified_or_below_10000"
    return {
        "id": "web:" + hashlib.sha256(url.encode()).hexdigest()[:20],
        "city": city,
        "title": str(row.get("title") or host)[:250],
        "url": url,
        "text": text[:5000],
        "fetched_at": queried_at,
        "published_at": row.get("published_date"),
        "source_kind": "official_web" if official else "popular_article",
        "source_host": host,
        "likes": likes,
        "comments": comments,
        "popularity_basis": "页面明确标注的点赞数" if likes is not None else None,
        "date_scope": "联网查询资料；发布日期和出游日适用性需分别核实",
        "validity": "visit_date_unverified",
        "retrieval": "Tavily web search",
    }, None
