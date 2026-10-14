"""Post-processing layer that turns Tavily evidence into a credibility engine.

This module sits on top of ``app.integrations.web_sources.evidence`` and the
Tavily adapter. It never touches the network nor rewrites existing evidence;
it only adds three derived fields so callers can rank, filter and expire
evidence the way DeepTravel (arxiv 2509.21842) describes "reflect on tool
responses to explore, verify, and refine".

Added fields (per evidence dict):

* ``trust_score``  -- float in [0, 1]. official_web = 1.0; popular_article
  scales with verified page likes (>=100000 -> 0.85, >=10000 -> 0.6).
  The 10000 floor is already enforced by ``web_sources.evidence`` for popular
  articles, so a popular article never scores below 0.6 here.
* ``fresh_until``  -- ISO date string. official_web stays valid 90 days,
  popular articles 30 days. ``None`` when the source date is missing.
* ``is_stale``     -- bool, True once ``today > fresh_until``.

Why numerical: ``web_sources.evidence`` already classifies sources into
``official_web`` / ``popular_article`` and verifies the 10000-likes floor.
That classification is qualitative. A 0-1 score lets the planner aggregate
multiple evidence items, pick the most trustworthy, and answer "how do you
guarantee the information is correct" in an interview with a number.
"""

from datetime import date, timedelta

# ---------------------------------------------------------------------------
# Freshness policy (days). Official content (gov / registered registry) is
# stable; popular articles drift faster because UGC gets edited or deleted.
# ---------------------------------------------------------------------------
FRESH_DAYS = {"official_web": 90, "popular_article": 30}

# ---------------------------------------------------------------------------
# Trust score brackets for popular articles. The 10000-likes floor is enforced
# upstream by web_sources.evidence, so the <10000 branch is defensive only.
# ---------------------------------------------------------------------------
POPULAR_BRACKETS = (
    (100000, 0.85),
    (10000, 0.6),
)


def _parse_day(value):
    """Accept ISO datetime or date strings; return a date or None."""
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except (ValueError, TypeError):
        return None


def score(ev):
    """Return a 0-1 trust score for one evidence dict.

    official_web is government or registry-reviewed, so it is trusted fully.
    popular_article is UGC/OTA; trust scales with the page's verified likes
    (already stripped of search-score inference by web_sources.counter).
    """
    kind = ev.get("source_kind")
    if kind == "official_web":
        return 1.0
    if kind == "popular_article":
        likes = ev.get("likes")
        if isinstance(likes, (int, float)) and likes >= 0:
            for floor, value in POPULAR_BRACKETS:
                if likes >= floor:
                    return value
        return 0.4
    return 0.3


def fresh_until(ev):
    """Return the ISO date after which the evidence is considered stale.

    Uses ``fetched_at`` (when Tavily retrieved the page) as the anchor.
    Falls back to ``published_at`` when the fetch time is missing.
    """
    kind = ev.get("source_kind") or "popular_article"
    days = FRESH_DAYS.get(kind, 30)
    anchor = _parse_day(ev.get("fetched_at")) or _parse_day(ev.get("published_at"))
    if anchor is None:
        return None
    return (anchor + timedelta(days=days)).isoformat()


def is_stale(ev, today=None):
    """True when the evidence has passed its freshness window."""
    end = _parse_day(ev.get("fresh_until")) or _parse_day(fresh_until(ev))
    if end is None:
        return False
    today = today or date.today()
    return today > end


def enrich(items, today=None):
    """Annotate a list of evidence dicts in place with the three fields.

    Returns the same list so callers can chain. Items missing source_kind are
    skipped (left untouched) so unrecognised payloads do not crash callers.
    """
    for ev in items:
        if not isinstance(ev, dict) or not ev.get("source_kind"):
            continue
        ev.setdefault("trust_score", score(ev))
        ev.setdefault("fresh_until", fresh_until(ev))
        ev.setdefault("is_stale", is_stale(ev, today=today))
    return items


def rank(items, today=None):
    """Return evidence sorted by trust desc, stale items pushed to the end."""
    enrich(items, today=today)
    return sorted(
        items,
        key=lambda ev: (
            ev.get("is_stale") is True,
            -(ev.get("trust_score") or 0),
        ),
    )


def top_trusted(items, today=None, min_score=0.6):
    """Convenience: the most trustworthy non-stale item, or None."""
    ranked = rank(items, today=today)
    for ev in ranked:
        if not ev.get("is_stale") and (ev.get("trust_score") or 0) >= min_score:
            return ev
    return None
