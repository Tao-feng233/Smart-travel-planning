"""Actual return-day events retain roads, meals and confirmed constraints."""

import asyncio
import copy
from datetime import datetime
from types import SimpleNamespace

import pytest

from app.core.errors import DataError
from app.planning.daily_schedule import DailySchedule
from app.planning.plan_context import PlanContext
from app.planning.time_values import minute


def trip(
    *,
    durations=(480,),
    start="09:00",
    opening=None,
    pin=None,
    hotel=False,
    lunch=False,
    return_at="17:00",
    return_day=True,
    road_minutes=5,
    pin_index=0,
):
    dt = "2026-10-12"
    spots = [
        {
            "id": "s" + str(i),
            "kind": "spot",
            "name": "景点" + str(i),
            "location": "120.32,36.05",
            "opening": opening[i] if isinstance(opening, list) else opening,
        }
        for i in range(len(durations))
    ]
    w = {
        "requirements": {
            "city": "青岛",
            "start_date": dt,
            "days": 1,
            "day_start": start,
        },
        "catalog": {p["id"]: p for p in spots},
        "selected_spots": [p["id"] for p in spots],
        "meal_choices": {},
        "visit_requests": {},
    }
    if pin:
        w["visit_requests"]["s" + str(pin_index)] = pin
    if hotel:
        h = {"id": "h", "name": "酒店", "kind": "hotel", "location": "120.30,36.05"}
        w["hotel"] = h
        w["catalog"]["h"] = h
    if lunch:
        f = {"id": "f", "name": "午餐店", "kind": "food", "location": "120.31,36.05"}
        w["catalog"]["f"] = f
        w["meal_choices"][dt + "|lunch"] = {"mode": "chosen", "food_id": "f"}
    stamp = dt + " " + return_at
    w["selected_return"] = {
        "id": "return",
        "name": "返程班次",
        "departure": stamp,
        "arrival": dt + " 21:00",
        "selection_status": "confirmed",
    }
    original = copy.deepcopy(w)
    road_calls = []

    async def roads(a, b):
        road_calls.append((a["id"], b["id"]))
        return [
            {
                "mode": "driving",
                "minutes": road_minutes,
                "distance": 1000,
                "source": {"name": "fixture"},
            }
        ]

    services = SimpleNamespace(
        route_options=roads, choose_route=lambda options, _: options[0]
    )
    ctx = PlanContext(w, lambda _: None, False, services)
    ctx.requirements = w["requirements"]
    ctx.catalog = w["catalog"]
    ctx.routes = {}
    ctx.return_time = datetime.fromisoformat(stamp) if return_day else None
    group = {
        "date": dt,
        "items": [
            {"candidate_id": p["id"], "duration": length, "period": "any"}
            for p, length in zip(spots, durations)
        ],
    }
    engine = DailySchedule(ctx, group)
    asyncio.run(engine.build())
    assert w == original, "Automatic fitting must not change choices or travel facts"
    assert len(road_calls) == len(set(road_calls)), (
        "Trial schedules must reuse road queries"
    )
    return ctx, ctx.computed[0]["events"], engine


def test_long_return_road_is_reserved_before_shortening_visit():
    ctx, events, engine = trip(hotel=True, road_minutes=60)
    road = next(e for e in reversed(events) if e["kind"] == "route")
    assert road["route"]["minutes"] == 60 and road["buffer"] >= 15
    assert minute(road["end"]) <= engine.latest_end()
    assert any(i["code"] == "return_day_trim" for i in ctx.boundary_issues)


def test_selected_lunch_and_midday_rest_are_kept_before_return():
    ctx, events, engine = trip(hotel=True, lunch=True)
    assert not ctx.meal_unplaced
    assert not any(issue["code"] == "meal_not_placed" for issue in ctx.offered)
    lunch = next(e for e in events if e.get("food", {}).get("id") == "f")
    assert minute(lunch["end"]) - minute(lunch["start"]) >= 60
    rest = next(e for e in events if e.get("rest_type") == "midday")
    assert minute(rest["end"]) > minute(rest["start"])
    assert (
        max(
            minute(e["end"])
            for e in events
            if e["kind"] in ("spot", "route", "meal", "rest")
        )
        <= engine.latest_end()
    )


def test_later_visit_and_road_are_not_squeezed_out_by_first_visit():
    _, events, engine = trip(durations=(480, 180), hotel=True)
    visits = [e for e in events if e["kind"] == "spot"]
    assert [e["candidate_id"] for e in visits] == ["s0", "s1"]
    assert all(e["duration"] >= 30 for e in visits)
    assert (
        max(minute(e["end"]) for e in events if e["kind"] == "route")
        <= engine.latest_end()
    )


@pytest.mark.parametrize("lunch", [False, True])
def test_three_visits_reserve_lunch_at_the_actual_position(lunch):
    _, events, engine = trip(
        durations=(480, 180, 60),
        hotel=True,
        lunch=lunch,
        return_at="17:30" if lunch else "17:00",
    )
    visits = [e for e in events if e["kind"] == "spot"]
    assert [e["candidate_id"] for e in visits] == ["s0", "s1", "s2"]
    assert all(e["duration"] >= 30 for e in visits)
    assert (
        max(
            minute(e["end"])
            for e in events
            if e["kind"] in ("spot", "meal", "rest", "route")
        )
        <= engine.latest_end()
    )
    if lunch:
        assert any(e.get("food", {}).get("id") == "f" for e in events)


def test_waiting_for_opening_is_included_in_the_remaining_time():
    _, events, engine = trip(opening="13:00-18:00", durations=(180,))
    visit = next(e for e in events if e["kind"] == "spot")
    assert visit["start"] == "13:00" and minute(visit["end"]) <= engine.latest_end()


def test_no_trim_when_time_is_sufficient():
    ctx, events, _ = trip(durations=(60,))
    assert next(e for e in events if e["kind"] == "spot")["duration"] == 60
    assert not any(i["code"] == "return_day_trim" for i in ctx.boundary_issues)


def test_non_return_day_keeps_original_suggestion():
    ctx, events, _ = trip(return_day=False)
    assert next(e for e in events if e["kind"] == "spot")["duration"] == 480
    assert not any(i["code"] == "return_day_trim" for i in ctx.boundary_issues)


def test_less_than_a_playable_window_reports_real_capacity():
    with pytest.raises(DataError) as error:
        trip(start="14:50", durations=(90,))
    assert error.value.context["code"] == "return_day_capacity"
    assert error.value.context["available_minutes"] < 30


def test_structured_fixed_duration_is_not_silently_trimmed():
    with pytest.raises(DataError) as error:
        trip(pin={"duration": 480})
    assert error.value.context["code"] == "fixed_duration"


def test_requested_morning_window_is_still_checked_after_waiting():
    with pytest.raises(DataError) as error:
        trip(opening="13:00-18:00", durations=(60,), pin={"period": "morning"})
    assert error.value.context["code"] == "visit_window"


def test_shorten_first_visit_to_keep_later_requested_morning_window():
    _, events, _ = trip(durations=(480, 60), pin={"period": "morning"}, pin_index=1)
    second = next(
        e for e in events if e.get("candidate_id") == "s1" and e["kind"] == "spot"
    )
    assert minute(second["end"]) <= 12 * 60


def test_fixed_duration_is_not_clipped_by_opening_hours():
    with pytest.raises(DataError) as error:
        trip(pin={"duration": 480}, opening="09:00-10:00")
    assert error.value.context["code"] == "fixed_duration"


def test_unreachable_opening_window_keeps_explicit_skip_reason():
    ctx, events, _ = trip(durations=(180, 60), opening=[None, "06:00-07:00"])
    assert [e["candidate_id"] for e in events if e["kind"] == "spot"] == ["s0"]
    assert any(
        i["code"] == "opening_hours" and i["candidate_ids"] == ["s1"]
        for i in ctx.boundary_issues
    )


def test_shorten_first_visit_to_keep_later_opening_window_when_possible():
    _, events, _ = trip(durations=(180, 60), opening=[None, "09:00-10:30"])
    assert [e["candidate_id"] for e in events if e["kind"] == "spot"] == ["s0", "s1"]


def test_closed_later_place_does_not_invalidate_a_fitting_fixed_visit():
    ctx, events, _ = trip(
        durations=(180, 60), pin={"duration": 180}, opening=[None, "06:00-07:00"]
    )
    visits = [e for e in events if e["kind"] == "spot"]
    assert len(visits) == 1 and visits[0]["duration"] == 180
    assert any(
        i["code"] == "opening_hours" and i["candidate_ids"] == ["s1"]
        for i in ctx.boundary_issues
    )


def test_contextless_dinner_error_stays_a_business_capacity_error(monkeypatch):
    from app.planning import pacing

    original = pacing.meal_duration
    monkeypatch.setattr(
        pacing,
        "meal_duration",
        lambda w, dt, period: 90 if period == "dinner" else original(w, dt, period),
    )
    with pytest.raises(DataError) as error:
        trip(durations=(60,), return_at="20:00")
    assert error.value.context["code"] == "return_day_capacity"
