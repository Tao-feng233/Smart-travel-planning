"""Capture the dependencies used by previews, audits and completion messages."""

from dataclasses import dataclass
import json


def transport_ready(workspace):
    return all(
        (workspace.get(key) or {}).get("selection_status") == "confirmed"
        for key in ("selected_transport", "selected_return")
    )


def choice_signature(workspace):
    return json.dumps(
        {
            "hotel": (workspace.get("hotel") or {}).get("id"),
            "outbound": (workspace.get("selected_transport") or {}).get("id"),
            "return": (workspace.get("selected_return") or {}).get("id"),
            "meals": workspace.get("meal_choices", {}),
        },
        sort_keys=True,
    )


def audit_signature(workspace):
    return json.dumps(
        {
            "requirements": workspace["requirements"],
            "selected": workspace.get("selected_spots"),
            "stays": workspace.get("stay_hotels"),
            "rooms": workspace.get("selected_rooms"),
            "pins": workspace.get("visit_requests"),
            "hotel": (workspace.get("hotel") or {}).get("id"),
            "outbound": workspace.get("selected_transport"),
            "return": workspace.get("selected_return"),
            "meals": workspace.get("meal_choices"),
        },
        sort_keys=True,
    )


@dataclass(frozen=True)
class TurnSnapshot:
    ready: bool
    audit: str
    adjustment: str
    spots: tuple
    choices: str

    @classmethod
    def capture(cls, workspace):
        return cls(
            transport_ready(workspace),
            audit_signature(workspace),
            json.dumps(workspace.get("timeline_adjustment"), sort_keys=True),
            tuple(workspace.get("selected_spots", [])),
            choice_signature(workspace),
        )


@dataclass
class TurnResult:
    answer: str = ""
    status: str = "completed"
    error: str | None = None
    error_context: dict | None = None
    audit: dict | None = None
    performed: str | None = None
