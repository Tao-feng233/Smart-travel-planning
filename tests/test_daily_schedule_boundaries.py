"""Actual daily events must remain playable after all timing adjustments."""

import asyncio
import copy
from types import SimpleNamespace

import pytest

from app.planning.daily_schedule import DailySchedule
from app.planning.plan_context import PlanContext
from app.planning.time_values import minute
from app.core.errors import DataError


def schedule(opening, *, start="09:00", period="any", not_before=None, duration=60, pin=None):
    point = {"id": "museum", "kind": "spot", "name": "博物馆", "opening": opening}
    workspace = {
        "requirements": {
            "city": "青岛", "start_date": "2026-10-12", "days": 1,
            "day_start": start,
        },
        "catalog": {point["id"]: point},
        "selected_spots": [point["id"]],
    }
    before = copy.deepcopy(workspace)
    if pin:
        workspace["visit_requests"] = {point["id"]: {"period": pin}}
        before = copy.deepcopy(workspace)
    context = PlanContext(workspace, lambda _: None, True, SimpleNamespace())
    context.requirements = workspace["requirements"]
    context.catalog = workspace["catalog"]
    context.routes = {}
    item = {"candidate_id": point["id"], "duration": duration, "period": period}
    if not_before:
        item["not_before"] = not_before
    asyncio.run(DailySchedule(context, {"date": "2026-10-12", "items": [item]}).build())
    assert workspace == before, "Scheduling must preserve the user's selections"
    return context, [event for event in context.computed[0]["events"] if event["kind"] == "spot"]


@pytest.mark.parametrize("options", [
    {"start": "18:00"},
    {"period": "evening"},
    {"not_before": "16:50"},
])
def test_closed_or_unplayable_visit_is_not_written_to_daily_events(options):
    context, visits = schedule("09:00-17:00", **options)
    assert not visits
    assert context.boundary_issues[0]["code"] == "opening_hours"
    assert context.boundary_issues[0]["available_minutes"] < 15


def test_last_entry_is_respected_even_if_the_building_closes_later():
    context, visits = schedule("09:00-20:00,16:00停止入场", not_before="16:30")
    assert not visits
    assert context.boundary_issues[0]["available_minutes"] == 0


def test_early_arrival_waits_for_opening_not_for_last_entry():
    context, visits = schedule("10:00-17:00,16:00停止入场")
    assert visits[0]["start"] == "10:00"
    assert not context.boundary_issues


def test_meal_inside_the_venue_cannot_extend_stay_past_closing():
    context, visits = schedule("09:00-14:00", start="11:30", duration=120)
    assert len(visits) == 1
    assert minute(visits[0]["end"]) <= 14 * 60
    assert visits[0]["duration"] >= 15
    assert context.boundary_issues[0]["code"] == "opening_hours"


@pytest.mark.parametrize("opening,duration", [
    ("13:00-18:00", 60),
    ("11:45-17:00", 30),
    ("09:00-17:00", 180),
])
def test_fixed_morning_window_survives_opening_waits_and_inside_meals(opening, duration):
    with pytest.raises(DataError) as failure:
        schedule(opening, duration=duration, pin="morning", start="09:30")
    assert failure.value.context["code"] == "visit_window"


@pytest.mark.parametrize("preview", [False, True])
def test_skipped_closed_venue_does_not_leave_a_detour_or_wrong_route_origin(preview):
    hotel = {"id": "hotel", "kind": "hotel", "name": "酒店", "location": "120.30,36.05"}
    museum = {"id": "museum", "kind": "spot", "name": "博物馆", "opening": "09:00-17:00", "location": "120.31,36.05"}
    night = {"id": "night", "kind": "spot", "name": "夜市", "opening": "00:00-24:00", "location": "120.32,36.05"}
    workspace = {
        "requirements": {"city": "青岛", "start_date": "2026-10-12", "days": 1, "day_start": "18:00"},
        "catalog": {point["id"]: point for point in [hotel, museum, night]},
        "selected_spots": ["museum", "night"], "hotel": hotel,
    }
    calls = []
    async def routes(start, end):
        calls.append((start["id"], end["id"]))
        return [{"mode": "driving", "minutes": 5, "source": "fixture"}]
    services = SimpleNamespace(route_options=routes, choose_route=lambda options, _: options[0])
    context = PlanContext(workspace, lambda _: None, preview, services)
    context.requirements = workspace["requirements"]
    context.catalog = workspace["catalog"]
    context.routes = {
        ("hotel", "museum"): [{"mode": "driving", "minutes": 5, "source": "fixture"}],
        ("museum", "night"): [{"mode": "driving", "minutes": 5, "source": "fixture"}],
    }
    asyncio.run(DailySchedule(context, {"date": "2026-10-12", "items": [
        {"candidate_id": "museum", "duration": 60},
        {"candidate_id": "night", "duration": 60},
    ]}).build())
    events = context.computed[0]["events"]
    assert not any("博物馆" in event["name"] for event in events)
    assert [event["candidate_id"] for event in events if event["kind"] == "spot"] == ["night"]
    road = next(event for event in events if event["kind"] == "route")
    assert road["name"] == "从酒店前往夜市"
    assert road["route"]["minutes"] == 5
    assert ("hotel", "night") in calls
    assert not any(event["kind"] == "unknown_route" for event in events)
