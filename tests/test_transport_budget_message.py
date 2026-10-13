"""预算文案：往返交通票价是选填项，未填时必须说清"暂不计入预算"，而不是写成 0。

见《往返交通改为用户填写-设计文档》5.5。
"""

from datetime import date, timedelta

from app.persistence import storage
from app.planning import engine
from app.travel import requirements as requirements_mod

START = date.today() + timedelta(days=5)
OUTBOUND = date.today() + timedelta(days=4)


def workspace(**over):
    w = storage.new_workspace("test-owner")
    w["requirements"] = {
        "city": "洛阳",
        "start_date": START.isoformat(),
        "days": 3,
        "adults": 2,
    }
    w["requirements"].update(over)
    w["catalog"] = {}
    w["selected_spots"] = []
    w["plan"] = {}
    return w


def budget_of(w):
    plan = {}
    engine.fill_budget(plan, w)
    return plan["budget"]


def test_missing_ticket_price_is_not_counted_as_zero():
    w = workspace()
    requirements_mod.update_requirements(w, {
        "outbound_date": OUTBOUND.isoformat(), "arrival_period": "afternoon"})
    budget = budget_of(w)
    # 没有票价 -> 不出现"往返交通"费用项
    assert "往返交通" not in (budget.get("items") or {})
    # 且必须明确说明"暂不计入预算"
    pending = budget.get("unknown") or []
    assert any("往返交通" in x and "暂不计入预算" in x for x in pending), pending


def test_filled_ticket_price_is_counted_by_adults():
    w = workspace()
    requirements_mod.update_requirements(w, {
        "outbound_date": OUTBOUND.isoformat(),
        "arrival_period": "afternoon",
        "intercity_ticket_cost": 545,
    })
    budget = budget_of(w)
    item = (budget.get("items") or {}).get("往返交通")
    assert item is not None
    # 单人票价 × 成人数
    assert item["amount"] == 545 * 2
    assert not any("暂不计入预算" in x for x in (budget.get("unknown") or []))
