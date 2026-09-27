"""B 线 P0 链路演示脚本（B7）：把「一句话需求 → 攻略 → 改动」整条链走一遍并逐步打印 stage。

用法（在仓库根目录跑）：

```powershell
python tools/check_b_flow.py                 # 用测试替身（自带住宿/路线/室内备选）→ 能一路跑到新版本
python tools/check_b_flow.py --deps real     # 用真实 Mock Provider → 用来量 A 的数据缺口
python tools/check_b_flow.py --show-json     # 额外打印每一步的关键 JSON 片段
```

为什么要有两个 `--deps`：

* `fake` 用的是 `backend/tests/test_graph_planning._deps()`，它补齐了 A 还没提供的
  住宿、路线、室内备选数据，所以整条链（含 C6 重规划）能真正跑通 —— 这是**演示证据**。
* `real` 用的是 `app.api.deps.build_node_deps()`，也就是 A 的 `V04MockMCPProvider`。
  现在会在「缺住宿候选」处**明确停在 `INSUFFICIENT_DATA`**（刻意设计的诚实出口），
  所以它更像个探针：A 一补数据，这一步就会自己往前走。

退出码：

* `0` 全链路跑到「报突发 → 新版本」
* `1` 中途出现真失败（应报 bug，不是数据问题）
* `2` 因数据缺口没跑完（是 A 的待办，见 `handoff/A_待办总表.md`）

这个脚本**不联网、不引入新依赖**，只用 FastAPI 的 `TestClient`。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from fastapi.testclient import TestClient  # noqa: E402

from app.api.deps import build_node_deps, build_session_service, get_session_service  # noqa: E402
from app.main import create_app  # noqa: E402
from app.services.session_store import InMemorySessionRepository  # noqa: E402

#: 七部分攻略的顶层字段名（`CONTRACTS.md` §9）。少一个就说明组装不完整。
GUIDE_SECTIONS = (
    "trip_summary",
    "arrival_and_departure",
    "preparation",
    "lodging",
    "daily_itinerary",
    "budget_and_alternatives",
    "sources_and_freshness",
)

#: 信息不全的一条（缺返回日期与预算），用来演示 B3 追问卡。
INCOMPLETE_TEXT = "国庆想去成都，从上海出发，两个人"
#: 一条完整需求（含往返日期、人数、预算、兴趣）。
FULL_TEXT = "从上海出发，10月2号到10月6号，2个人，预算5000元，喜欢美食和人文，想去成都"


class Steps:
    """按顺序记下每一步，最后统一打印，方便直接贴进演示材料。"""

    def __init__(self, show_json: bool) -> None:
        self.rows: list[tuple[str, str, str, bool]] = []
        self.show_json = show_json
        self.data_gap = False

    def ok(self, name: str, detail: str) -> None:
        self.rows.append((name, "OK", detail, True))
        print(f"  [OK  ] {name:<26} {detail}")

    def fail(self, name: str, detail: str) -> None:
        self.rows.append((name, "FAIL", detail, False))
        print(f"  [FAIL] {name:<26} {detail}")

    def gap(self, name: str, detail: str) -> None:
        """数据缺口：不是 bug，是 A 还没补的数据。"""
        self.data_gap = True
        self.rows.append((name, "GAP", detail, False))
        print(f"  [GAP ] {name:<26} {detail}")

    def dump(self, label: str, payload: object) -> None:
        if not self.show_json:
            return
        text = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
        print(f"    --- {label} ---")
        for line in text.splitlines():
            print(f"    {line}")


def _build_client(deps_name: str) -> TestClient:
    app = create_app()
    if deps_name == "fake":
        # 测试替身放在 tests/ 下（只在一处维护），显式加进 sys.path，
        # 不用 pytest 的 rootdir 机制，这样脚本能独立跑。
        sys.path.insert(0, str(BACKEND_DIR / "tests"))
        from test_graph_planning import _deps  # noqa: PLC0415

        node_deps = _deps()
    else:
        node_deps = build_node_deps()
    service = build_session_service(repository=InMemorySessionRepository(), node_deps=node_deps)
    app.dependency_overrides[get_session_service] = lambda: service
    return TestClient(app)


def _unwrap(response, steps: Steps, name: str) -> dict | None:
    """统一信封解包。非 2xx 或 `ok=false` 时把后端给的原因原样打出来。

    注意别只认 200：建会话按契约返回 **201**。
    """

    body = response.json()
    if 200 <= response.status_code < 300 and body.get("ok"):
        return body
    error = body.get("error") or (body.get("detail") or {}).get("error") or {}
    steps.fail(name, f"HTTP {response.status_code} code={error.get('code')} :: {error.get('message')}")
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="B 线 P0 链路演示（逐步打印 stage）")
    parser.add_argument(
        "--deps",
        choices=("fake", "real"),
        default="fake",
        help="fake=测试替身（能跑通全链路）；real=A 的 Mock Provider（用来量数据缺口）",
    )
    parser.add_argument("--show-json", action="store_true", help="额外打印每一步的关键 JSON")
    args = parser.parse_args()

    client = _build_client(args.deps)
    steps = Steps(args.show_json)

    print("B 线 P0 链路演示")
    print("=" * 62)
    print(f"依赖来源：{args.deps}（{'测试替身' if args.deps == 'fake' else 'A 的 Mock Provider'}）")
    print("=" * 62)

    # --- 1. 建会话 ------------------------------------------------------------
    body = _unwrap(client.post("/api/sessions", json={"run_mode": "DEMO"}), steps, "建会话")
    if body is None:
        return 1
    session_id = body["data"]["session_id"]
    stage = body["data"]["state"]["stage"]
    steps.ok("1 建会话", f"session={session_id} stage={stage}")

    # --- 2. 追问：信息不全 ------------------------------------------------
    body = _unwrap(
        client.post(f"/api/sessions/{session_id}/messages", json={"text": INCOMPLETE_TEXT}),
        steps,
        "追问",
    )
    if body is None:
        return 1
    data = body["data"]
    if data["stage"] != "ASKING_CLARIFICATION":
        steps.fail("2 追问", f"期望 ASKING_CLARIFICATION，实际 {data['stage']}")
        return 1
    steps.ok("2 追问", f"stage={data['stage']} 提示={data['assistant_message'].splitlines()[0]}")
    steps.dump("追问响应", data)

    # --- 3. 补全需求 → 推荐目的地 -----------------------------------------
    body = _unwrap(
        client.post(f"/api/sessions/{session_id}/messages", json={"text": FULL_TEXT}),
        steps,
        "推荐目的地",
    )
    if body is None:
        return 1
    data = body["data"]
    candidates = [item["destination_id"] for item in (data.get("destination_candidates") or [])]
    if data["stage"] != "AWAITING_DESTINATION_CONFIRMATION":
        steps.fail("3 推荐目的地", f"期望 AWAITING_DESTINATION_CONFIRMATION，实际 {data['stage']}")
        return 1
    steps.ok("3 推荐目的地", f"候={candidates or '无'}")
    steps.dump("推荐响应", data)

    # --- 4. 确认目的地 → 排程/验证/组攻略 ---------------------------------
    body = _unwrap(
        client.post(f"/api/sessions/{session_id}/messages", json={"text": "确认"}),
        steps,
        "确认目的地",
    )
    if body is None:
        return 1
    data = body["data"]
    guide_id = data.get("guide_id")
    if data["stage"] == "READY" and guide_id:
        steps.ok("4 确认目的地", f"stage=READY guide_id={guide_id}")
    elif data["stage"] == "INSUFFICIENT_DATA":
        missing = "；".join(data.get("degraded_items") or []) or "（未给出降级说明）"
        steps.gap("4 确认目的地", f"stage=INSUFFICIENT_DATA :: {missing}")
        print()
        print("结论：链路本身没崩（200，不是 500），但数据不够，走不到攻略。")
        print("      这是 A 的待办，用 `python tools/check_a_data.py` 看缺哪几项；")
        print("      想看完整链路请去掉 `--deps real`（用测试替身）。")
        return 2
    else:
        steps.fail("4 确认目的地", f"意外 stage={data['stage']} guide_id={guide_id}")
        return 1
    steps.dump("确认后响应", data)

    # --- 5. 取攻略：七部分齐不齐 -----------------------------------------
    body = _unwrap(client.get(f"/api/guides/{guide_id}"), steps, "取攻略")
    if body is None:
        return 1
    guide = body["data"]["travel_guide"]
    missing = [name for name in GUIDE_SECTIONS if name not in guide]
    days = len(guide["daily_itinerary"])
    if missing:
        steps.fail("5 取攻略", f"缺部分 {missing}")
        return 1
    steps.ok(
        "5 取攻略",
        f"v{guide['guide_version']} 七部分齐 天数={days} "
        f"readiness={guide['guide_readiness']} lifecycle={guide['lifecycle_status']}",
    )

    # --- 6. 确认攻略：锁住"动不了"的节点 --------------------------------
    #
    # 锁全部节点会让后面那步报突发**正确地**失败（409「没有需要调整的安排」）——
    # 这也是个该演给人看的诚实出口，但它是另一条用例，不是主链路。
    # 这里按真实场景只锁「抵达班次」和「已入住的酒店」：这两样用户改不动。
    lock_types = {"ARRIVAL", "CHECK_IN"}
    lock_ids = [
        node["node_id"]
        for day in guide["daily_itinerary"]
        for node in day["nodes"]
        if node["node_type"] in lock_types
    ]
    locked_names = [
        node["name"]
        for day in guide["daily_itinerary"]
        for node in day["nodes"]
        if node["node_type"] in lock_types
    ]
    body = _unwrap(
        client.post(
            f"/api/guides/{guide_id}/confirm",
            json={
                "expected_guide_version": guide["guide_version"],
                "lock_node_ids": lock_ids,
                "idempotency_key": f"demo-confirm-{guide_id}-{guide['guide_version']}",
            },
        ),
        steps,
        "确认攻略",
    )
    if body is None:
        return 1
    confirmed = body["data"]["travel_guide"]
    locked = sum(1 for day in confirmed["daily_itinerary"] for node in day["nodes"] if node["locked"])
    if confirmed["lifecycle_status"] != "CONFIRMED" or confirmed["guide_version"] != guide["guide_version"] + 1:
        steps.fail(
            "6 确认攻略",
            f"期望 CONFIRMED 且版本 +1，实际 {confirmed['lifecycle_status']} "
            f"v{confirmed['guide_version']}",
        )
        return 1
    steps.ok(
        "6 确认攻略",
        f"v{guide['guide_version']} → v{confirmed['guide_version']} "
        f"lifecycle=CONFIRMED 锁定 {locked}/{len(lock_ids)} 个（{'、'.join(locked_names) or '无'}）",
    )

    # --- 7. 报突发「今天下雨了」→ 重规划 + 版本谱系 ------------------------
    before = confirmed
    body = _unwrap(
        client.post(
            f"/api/guides/{guide_id}/incident",
            json={
                "action": {
                    "action_id": "demo-act-incident",
                    "idempotency_key": f"demo-incident-{guide_id}-{before['guide_version']}",
                    "action_type": "REPORT_INCIDENT",
                    "session_id": before["session_id"],
                    "guide_id": guide_id,
                    "expected_guide_version": before["guide_version"],
                    "raw_text": "今天下雨了",
                }
            },
        ),
        steps,
        "报突发",
    )
    if body is None:
        return 1
    data = body["data"]
    new_guide = data["travel_guide"]
    lineage = data["version_lineage"]
    conflicts = data["conflicts"]
    if new_guide["guide_version"] <= before["guide_version"]:
        steps.fail("7 报突发", f"版本没有前进：v{before['guide_version']} → v{new_guide['guide_version']}")
        return 1
    steps.ok(
        "7 报突发",
        f"v{before['guide_version']} → v{new_guide['guide_version']} "
        f"保留 {len(lineage['preserved_node_ids'])} / 替换 {len(lineage['changed_node_ids'])} "
        f"/ 移除 {len(lineage['removed_node_ids'])} 冲突 {len(conflicts)} 条",
    )

    # --- 8. 谱系里的节点名能不能解析出来（前端「本轮改动」面板要用） -----
    new_names = {
        node["node_id"]: node["name"]
        for day in new_guide["daily_itinerary"]
        for node in day["nodes"]
    }
    old_names = {
        node["node_id"]: node["name"]
        for day in before["daily_itinerary"]
        for node in day["nodes"]
    }
    unresolved: list[str] = []
    for key in ("removed_node_ids",):
        for node_id in lineage[key]:
            if node_id not in new_names and node_id not in old_names:
                unresolved.append(node_id)
    for relation in lineage["replacement_relations"]:
        if relation["old_node_id"] not in new_names and relation["old_node_id"] not in old_names:
            unresolved.append(relation["old_node_id"])
    if unresolved:
        steps.fail("8 谱系节点名解析", f"解析不出来 {unresolved}")
        return 1
    steps.ok(
        "8 谱系节点名解析",
        "「保留/替换」在新版、「移除/被替换」在旧版，两版合起来全覆盖",
    )
    for relation in lineage["replacement_relations"]:
        old_name = new_names.get(relation["old_node_id"]) or old_names.get(relation["old_node_id"])
        new_name = new_names.get(relation["new_node_id"]) or old_names.get(relation["new_node_id"])
        print(f"          {old_name} → {new_name}")
    steps.dump("版本谱系", lineage)

    # --- 9. 取新版本，确认落库一致 ---------------------------------------
    body = _unwrap(client.get(f"/api/guides/{guide_id}"), steps, "取新版本")
    if body is None:
        return 1
    latest = body["data"]["travel_guide"]
    if latest["guide_version"] != new_guide["guide_version"]:
        steps.fail(
            "9 取新版本",
            f"接口里最新版是 v{latest['guide_version']}，与报突发返回的 "
            f"v{new_guide['guide_version']} 不一致",
        )
        return 1
    steps.ok("9 取新版本", f"v{latest['guide_version']} 与报突发返回一致")

    # --- 汇总 -------------------------------------------------------------
    print("=" * 62)
    back = client.get(f"/api/guides/{guide_id}?version={before['guide_version']}")
    print(
        f"备注：历史版本检索 `?version={before['guide_version']}` "
        f"→ HTTP {back.status_code}"
        + ("（同 guide_id 只保留最新版，前端靠改动前那一版做本地索引）" if back.status_code != 200 else "")
    )
    print("=" * 62)
    print("全链路跑通：建会话 → 追问 → 推荐 → 确认 → 七部分攻略 → 确认攻略 → 报突发 → 新版本")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
