"""Explicit dependencies supplied by the agent to business action handlers."""

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class ActionServices:
    llm: Callable
    tuniu: Callable
    local_tool: Callable
    recommend: Callable
    handle: Callable
    generate: Callable
    route_options: Callable
    choose_route: Callable
    search_hotels: Callable
    load_hotel_detail: Callable
