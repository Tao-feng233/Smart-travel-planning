"""Explicit facts and accumulators shared by one plan build."""

from dataclasses import dataclass, field
from typing import Callable
from pathlib import Path
from datetime import date, datetime


@dataclass(frozen=True)
class PlanningServices:
    model: Callable
    tool: Callable
    route_options: Callable
    choose_route: Callable
    fill_budget: Callable
    validate_plan: Callable
    parse_review: Callable
    now: Callable
    runtime: Path


@dataclass
class PlanContext:
    workspace: dict
    progress: Callable
    preview: bool
    services: PlanningServices
    requirements: dict | None = None
    catalog: dict | None = None
    hierarchy: dict | None = None
    spots: list = field(default_factory=list)
    days: int | None = None
    start: date | None = None
    guides: list = field(default_factory=list)
    prompt: str | None = None
    payload: dict | None = None
    dates: list = field(default_factory=list)
    draft: dict | None = None
    groups: list = field(default_factory=list)
    usage: dict | None = None
    hotel: dict | None = None
    base: dict | None = None
    routes: dict | None = None
    warnings: list = field(default_factory=list)
    return_time: datetime | None = None
    transport: dict | None = None
    arrival: datetime | None = None
    computed: list = field(default_factory=list)
    boundary_issues: list = field(default_factory=list)
    offered: list = field(default_factory=list)
    meal_unplaced: list = field(default_factory=list)
    scheduled_meals: set = field(default_factory=set)
