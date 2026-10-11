"""Purpose-specific prompts. Importing this package performs no I/O or model calls."""

from app.prompts.common import VERSION, FACTS
from app.prompts.context import interaction_state
from app.prompts.dialogue import INTENT, GOAL, REPLY
from app.prompts.recommendations import RECOMMEND, CHOOSE
from app.prompts.scheduling import VISIT, PLAN, ADJUST
from app.prompts.review import TIMELINE_REVIEW, PLAN_REVIEW

TEMPLATES = {
    "intent": INTENT,
    "goal": GOAL,
    "reply": REPLY,
    "recommend": RECOMMEND,
    "choose": CHOOSE,
    "visit": VISIT,
    "plan": PLAN,
    "adjust": ADJUST,
    "timeline_review": TIMELINE_REVIEW,
    "plan_review": PLAN_REVIEW,
}


def system(role):
    return TEMPLATES[role] + FACTS
