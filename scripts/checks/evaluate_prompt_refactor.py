"""Compare intent decisions on synthetic cases; never execute business tools.

Default mode only describes the cases. --live makes bounded LLM requests using
the project's configured provider. Reports contain fixture inputs and metrics,
not credentials, real conversations, or raw provider responses.
"""

import argparse
import asyncio
import ast
import copy
import json
from pathlib import Path
import sys
import time
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.agents import planner as agent
from app.integrations import providers


CASES = [
    ("preferences", "我想去青岛玩", {}, {"search_spots"}, {"consult", "query"}, {}),
    (
        "default",
        "没有偏好，按代表景点推荐吧",
        {"city": "青岛"},
        {"search_spots"},
        {"consult", "query"},
        {"preference_mode": "default"},
    ),
    (
        "more",
        "再来一些轻松的，之前选的留着",
        {"city": "青岛", "days": 3, "preferences": ["人文"]},
        {"search_spots"},
        {"consult", "query"},
        {"expand_spots": True},
    ),
    (
        "hotel",
        "就玩一天，但住一晚第二天走，帮我看看酒店",
        {"city": "青岛", "days": 1, "adults": 2, "start_date": "2026-10-12"},
        {"search_hotels"},
        {"consult", "query"},
        {"patch.return_date": "2026-10-13"},
    ),
    (
        "self_drive",
        "我们自己开车过去，不用查车票了",
        {"city": "青岛"},
        {"transport_arrangement", "chat"},
        {"act"},
        {"patch.intercity_mode": "self_drive"},
    ),
    (
        "explain",
        "为什么这个地方安排了两个多小时？我只是问问",
        {"city": "青岛", "days": 3},
        {"chat"},
        {"explain"},
        {},
    ),
    (
        "timeline",
        "把时间轴重新排一下，尽量别来回跑",
        {"city": "青岛", "days": 3},
        {"adjust_timeline"},
        {"act", "edit_plan"},
        {},
    ),
    (
        "plan",
        "已有计划整体优化一下，住宿和车票保留",
        {"city": "青岛", "days": 3},
        {"optimize_plan"},
        {"edit_plan"},
        {},
    ),
    (
        "review",
        "先看看现在的安排是否太赶，不用修改",
        {"city": "青岛", "days": 3},
        {"review_timeline"},
        {"query"},
        {},
    ),
    (
        "routes",
        "只核对一下交通时间",
        {"city": "青岛", "days": 3},
        {"refresh_routes"},
        {"query"},
        {},
    ),
    (
        "delegate",
        "我不想逐项挑了，剩下的你帮我安排成一份方案",
        {"city": "青岛", "days": 3},
        {"request_auto_selection"},
        {"delegate"},
        {},
    ),
    (
        "companions",
        "带老人，少走路，每天午休一小时，重新安排时间轴",
        {"city": "青岛", "days": 3},
        {"adjust_timeline"},
        {"act", "edit_plan"},
        {"patch.midday_rest_minutes": 60},
    ),
]

VARIANTS = {
    "preferences": ["打算去青岛看看，帮我推荐吧", "目的地青岛，先看看有什么可选的"],
    "default": ["没什么特别想玩的，给我默认推荐就行", "我不挑主题，看看代表景点吧"],
    "more": ["在已选的之外再补充几个休闲去处", "还想多看一些备选，已选的保持"],
    "hotel": [
        "只游玩一天，晚上住酒店，隔天才走，查查住宿",
        "一天游也要住一晚，帮我找酒店",
    ],
    "self_drive": ["来回都自己开车，别给我找票了", "这次自驾，不需要火车或飞机"],
    "explain": [
        "这个景点为什么要这么久？先解释，不用改",
        "两个小时是怎么算出来的？只是了解一下",
    ],
    "timeline": [
        "调整时间轴，顺路一点，别折返",
        "帮我把时间轴里的游玩顺序安排得顺一些",
    ],
    "plan": [
        "修订一下已有计划书，酒店和班次不动",
        "把整份计划书重新整理合理，保留原住宿和车票",
    ],
    "review": ["检查日程合不合理，先不动它", "评估一下安排会不会太累，只给建议"],
    "routes": [
        "更新地点之间预计要走多久，别动游玩安排",
        "查查交通耗时，更新路程预览就行",
    ],
    "delegate": [
        "不用让我挨个选，余下细节由你定成方案",
        "剩余地点和住宿你替我选好，形成旅行方案",
    ],
    "companions": [
        "有老人，不想步行太多，午休保留60分钟，帮我调整时间轴",
        "重排时间轴，照顾老人少走路，每天必须休息一个小时",
    ],
}


def workspace(requirements, existing_plan=False):
    spot = {
        "id": "fixture-spot",
        "kind": "spot",
        "name": "栈桥",
        "location": "120.31,36.06",
    }
    w = {
        "id": "prompt-evaluation-fixture",
        "requirements": copy.deepcopy(requirements),
        "catalog": {"fixture-spot": spot},
        "selected_spots": [],
        "messages": [],
        "ui": {"view": "spot"},
    }
    if requirements.get("days"):
        w["requirements"].setdefault("start_date", "2026-10-12")
        w["selected_spots"] = ["fixture-spot"]
    if existing_plan:
        w["plan"] = {"title": "已有计划", "days": []}
    return w


def baseline_prompt(backup):
    with zipfile.ZipFile(backup / "source-and-config-before.zip") as z:
        source = z.read("app/agent.py").decode("utf-8-sig")
    f = next(
        n
        for n in ast.parse(source).body
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "understand"
    )
    parts = []
    for n in sorted(ast.walk(f), key=lambda n: getattr(n, "lineno", 0)):
        if isinstance(n, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "prompt" for t in n.targets
        ):
            parts = [ast.literal_eval(n.value)]
        elif (
            isinstance(n, ast.AugAssign)
            and isinstance(n.target, ast.Name)
            and n.target.id == "prompt"
        ):
            parts.append(ast.literal_eval(n.value))
    return "".join(parts)


async def request_messages(w, text):
    captured = {}

    async def capture(messages, **kwargs):
        captured.update(messages=messages, tools=kwargs["tools"])
        return {
            "tool_calls": [
                {
                    "function": {
                        "name": "submit_intent",
                        "arguments": '{"action":"chat","patch":{},"answer":"fixture"}',
                    }
                }
            ]
        }, {}

    original = agent.llm
    agent.llm = capture
    try:
        await agent.understand(
            {"workspace": w, "text": text, "progress": lambda _: None}
        )
    finally:
        agent.llm = original
    return captured


def grade(response, actions, modes, fields):
    try:
        calls = response["tool_calls"]
        if len(calls) != 1 or calls[0]["function"]["name"] != "submit_intent":
            return False, {}, ["invalid tool call"]
        intent = json.loads(calls[0]["function"]["arguments"])
        failures = []
        if intent.get("action") not in actions:
            failures.append("action")
        if (intent.get("mission") or {}).get("mode") not in modes:
            failures.append("mode")
        for path, wanted in fields.items():
            actual = intent
            for part in path.split("."):
                actual = actual.get(part) if isinstance(actual, dict) else None
            if actual != wanted:
                failures.append(path)
        if intent.get("select_ids") or intent.get("remove_ids"):
            failures.append("unrequested selection change")
        if (intent.get("patch") or {}).get(
            "transport_mode"
        ) == "walking" and "少走路" in intent.get("answer", ""):
            failures.append("walking preference")
        return (
            not failures,
            {
                "action": intent.get("action"),
                "mode": (intent.get("mission") or {}).get("mode"),
                "patch": intent.get("patch", {}),
            },
            failures,
        )
    except (KeyError, TypeError, ValueError):
        return False, {}, ["invalid response"]


async def run(args):
    backup = Path(
        json.loads(
            (ROOT / "data/runtime/prompt-refactor-backup.json").read_text(
                encoding="utf-8"
            )
        )["backup"]
    )
    old_prompt = baseline_prompt(backup) if not args.after_only else ""
    requests = []
    selected = [c for c in CASES if not args.case or c[0] == args.case]
    cases = []
    for case in selected:
        cases.append(case)
        if args.variants:
            for index, text in enumerate(VARIANTS[case[0]], 1):
                cases.append((case[0] + "-" + str(index), text, *case[2:]))
    for name, text, requirements, actions, modes, fields in cases:
        captured = await request_messages(
            workspace(requirements, name.split("-")[0] == "plan"), text
        )
        for version in ("after",) if args.after_only else ("before", "after"):
            messages = copy.deepcopy(captured["messages"])
            tools = copy.deepcopy(captured["tools"])
            if version == "before":
                messages[0]["content"] = old_prompt
                data = json.loads(messages[-1]["content"])
                data.pop("interaction_state", None)
                messages[-1]["content"] = json.dumps(data, ensure_ascii=False)
                properties = tools[0]["function"]["parameters"]["properties"]
                properties["action"].pop("description", None)
                tools[0]["function"]["parameters"].pop("additionalProperties", None)
                properties["patch"].pop("additionalProperties", None)
                properties["mission"]["properties"]["mode"].pop("description", None)
                for field in ("transport_mode", "days", "return_date", "outbound_date"):
                    properties["patch"]["properties"][field].pop("description", None)
            requests.append(
                (name, text, version, messages, tools, actions, modes, fields)
            )
    if not args.live:
        print(
            json.dumps(
                {
                    "cases": len(cases),
                    "model_requests": len(requests),
                    "live": False,
                    "before_system_chars": len(old_prompt),
                }
            )
        )
        return
    semaphore = asyncio.Semaphore(2)

    async def evaluate(row):
        name, text, version, messages, tools, actions, modes, fields = row
        async with semaphore:
            started = time.monotonic()
            try:
                # Match production token capacity and its one bounded parse repair.
                tokens = 0
                parse_errors = []
                for attempt in range(2):
                    response, usage = await providers.llm(
                        messages, tools=tools, label="prompt_eval_" + version
                    )
                    tokens += usage.get("total_tokens", 0)
                    try:
                        agent.parse_intent(response)
                        break
                    except (KeyError, TypeError, ValueError) as error:
                        parse_errors.append(type(error).__name__ + ": " + str(error))
                        if attempt == 0:
                            messages.insert(
                                -1,
                                {
                                    "role": "user",
                                    "content": "上一次输出不可用。请严格调用唯一的 submit_intent，patch 只填写用户明确条件。",
                                },
                            )
                passed, intent, failures = grade(response, actions, modes, fields)
                if name.split("-")[0] == "hotel":
                    patch = intent.get("patch", {})
                    if (
                        patch.get("days", 1) != 1
                        or patch.get("end_date", "2026-10-12") != "2026-10-12"
                    ):
                        passed = False
                        failures.append("tour dates confused with overnight stay")
                if (
                    name.split("-")[0] == "companions"
                    and intent.get("patch", {}).get("transport_mode") == "walking"
                ):
                    passed = False
                    failures.append("walking preference")
                record = {
                    "case": name,
                    "version": version,
                    "passed": passed,
                    "intent": intent,
                    "failures": failures,
                    "tokens": tokens,
                    "attempts": attempt + 1,
                    "parse_errors": parse_errors,
                    "seconds": round(time.monotonic() - started, 2),
                }
            except Exception as error:
                record = {
                    "case": name,
                    "version": version,
                    "passed": False,
                    "error_type": type(error).__name__,
                    "seconds": round(time.monotonic() - started, 2),
                }
            print(json.dumps(record, ensure_ascii=False), flush=True)
            return record

    results = await asyncio.gather(*(evaluate(r) for r in requests))
    report = {
        "synthetic": True,
        "business_tools_executed": False,
        "cases": len(cases),
        "results": results,
        "summary": {
            v: {
                "passed": sum(r["passed"] for r in results if r["version"] == v),
                "total": len(cases),
                "tokens": sum(r.get("tokens", 0) for r in results if r["version"] == v),
                "seconds": round(
                    sum(r["seconds"] for r in results if r["version"] == v), 2
                ),
            }
            for v in (("after",) if args.after_only else ("before", "after"))
        },
    }
    path = ROOT / "data/runtime/prompt-refactor-evaluation-20261010.json"
    if path.exists():
        path.with_name("prompt-eval-" + str(time.time_ns()) + ".json").write_bytes(
            path.read_bytes()
        )
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("SUMMARY " + json.dumps(report["summary"], ensure_ascii=False), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live",
        action="store_true",
        help="Run synthetic intent requests, with no business actions.",
    )
    parser.add_argument(
        "--variants",
        action="store_true",
        help="Include two held-out phrasings per scenario.",
    )
    parser.add_argument(
        "--after-only",
        action="store_true",
        help="Evaluate only the refactored request.",
    )
    parser.add_argument(
        "--case", choices=[c[0] for c in CASES], help="Evaluate a single scenario."
    )
    asyncio.run(run(parser.parse_args()))
