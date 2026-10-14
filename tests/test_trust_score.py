"""Unit tests for trust_score: pure post-processing, no network."""

from datetime import date, timedelta

from app.integrations import trust_score


def test_score_official_web_is_full_trust():
    assert trust_score.score({"source_kind": "official_web"}) == 1.0


def test_score_popular_article_scales_with_likes():
    assert trust_score.score({"source_kind": "popular_article", "likes": 150000}) == 0.85
    assert trust_score.score({"source_kind": "popular_article", "likes": 50000}) == 0.6
    assert trust_score.score({"source_kind": "popular_article", "likes": 10000}) == 0.6
    # Below the upstream 10000 floor (defensive only, upstream filters this).
    assert trust_score.score({"source_kind": "popular_article", "likes": 100}) == 0.4


def test_score_unknown_kind_is_low():
    assert trust_score.score({"source_kind": "blog"}) == 0.3
    assert trust_score.score({}) == 0.3


def test_fresh_until_official_is_90_days():
    ev = {"source_kind": "official_web", "fetched_at": "2026-10-13"}
    assert trust_score.fresh_until(ev) == "2027-01-11"


def test_fresh_until_popular_is_30_days():
    ev = {"source_kind": "popular_article", "fetched_at": "2026-10-13"}
    assert trust_score.fresh_until(ev) == "2026-11-12"


def test_fresh_until_accepts_datetime_string():
    ev = {"source_kind": "official_web", "fetched_at": "2026-10-13T10:00:00"}
    assert trust_score.fresh_until(ev) == "2027-01-11"


def test_fresh_until_falls_back_to_published_at():
    ev = {
        "source_kind": "popular_article",
        "fetched_at": None,
        "published_at": "2026-10-01",
    }
    assert trust_score.fresh_until(ev) == "2026-10-31"


def test_fresh_until_none_when_no_dates():
    ev = {"source_kind": "popular_article"}
    assert trust_score.fresh_until(ev) is None


def test_is_stale_true_after_window():
    ev = {
        "source_kind": "popular_article",
        "fetched_at": "2026-09-01",  # 30d window -> 2026-10-01
    }
    assert trust_score.is_stale(ev, today=date(2026, 10, 13)) is True


def test_is_stale_false_within_window():
    ev = {
        "source_kind": "official_web",
        "fetched_at": "2026-10-01",  # 90d window -> 2027-01-01
    }
    assert trust_score.is_stale(ev, today=date(2026, 10, 13)) is False


def test_is_stale_false_when_no_fresh_until():
    assert trust_score.is_stale({"source_kind": "popular_article"}) is False


def test_enrich_adds_three_fields_in_place():
    items = [
        {"source_kind": "official_web", "fetched_at": "2026-10-13"},
        {"source_kind": "popular_article", "likes": 50000, "fetched_at": "2026-10-13"},
    ]
    result = trust_score.enrich(items, today=date(2026, 10, 13))
    assert result is items  # in place
    assert items[0]["trust_score"] == 1.0
    assert items[0]["fresh_until"] == "2027-01-11"
    assert items[0]["is_stale"] is False
    assert items[1]["trust_score"] == 0.6
    assert items[1]["fresh_until"] == "2026-11-12"
    assert items[1]["is_stale"] is False


def test_enrich_skips_items_without_source_kind():
    items = [{"url": "no kind here"}]
    trust_score.enrich(items)
    assert "trust_score" not in items[0]


def test_rank_puts_high_trust_first_and_stale_last():
    items = [
        {"source_kind": "popular_article", "likes": 50000, "fetched_at": "2026-09-01"},  # stale, 0.6
        {"source_kind": "official_web", "fetched_at": "2026-10-13"},                    # fresh, 1.0
        {"source_kind": "popular_article", "likes": 150000, "fetched_at": "2026-10-13"}, # fresh, 0.85
    ]
    ranked = trust_score.rank(items, today=date(2026, 10, 13))
    # Official first, then high-likes popular, then stale last
    assert ranked[0]["source_kind"] == "official_web"
    assert ranked[1]["likes"] == 150000
    assert ranked[2]["is_stale"] is True


def test_top_trusted_returns_best_non_stale():
    items = [
        {"source_kind": "popular_article", "likes": 50000, "fetched_at": "2026-10-13"},  # 0.6
        {"source_kind": "official_web", "fetched_at": "2026-10-13"},                    # 1.0
    ]
    best = trust_score.top_trusted(items, today=date(2026, 10, 13))
    assert best is not None
    assert best["source_kind"] == "official_web"


def test_top_trusted_none_when_all_stale():
    items = [
        {"source_kind": "popular_article", "likes": 50000, "fetched_at": "2026-08-01"},  # stale
    ]
    assert trust_score.top_trusted(items, today=date(2026, 10, 13)) is None
