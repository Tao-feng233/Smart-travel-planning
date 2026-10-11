"""Read-only provider integration, isolated disposable account. Never prints credentials."""

import sys, time, secrets, json, uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import httpx
from app.persistence import storage

base = "http://127.0.0.1:8767"
c = httpx.Client(base_url=base, headers={"Origin": base}, timeout=20, trust_env=False)
password = secrets.token_urlsafe(24)
session = None
log = []


def req(method, url, body=None):
    r = c.request(method, url, json=body)
    r.raise_for_status()
    return r.json()


def action(a, args=None, text=""):
    global w
    w = req("GET", "/api/workspaces/" + w["id"])
    before = sum(m["role"] == "assistant" for m in w["messages"])
    j = req(
        "POST",
        "/api/workspaces/" + w["id"] + "/actions",
        {
            "revision": w["revision"],
            "action": a,
            "args": args or {},
            "text": text,
            "request_id": str(uuid.uuid4()),
        },
    )
    for _ in range(300):
        d = req("GET", "/api/jobs/" + j["job_id"])
        if d["status"] != "running":
            break
        time.sleep(0.5)
    else:
        raise RuntimeError("task timeout")
    w = d["workspace"]
    assert sum(m["role"] == "assistant" for m in w["messages"]) == before + 1
    log.append({"action": a, "status": d["status"], "error": d.get("error")})
    print(a, d["status"], d.get("error") or "", flush=True)
    if d["status"] != "completed":
        raise RuntimeError(d.get("error") or "action failed")
    return w


try:
    session = req(
        "POST",
        "/api/auth/register",
        {
            "username": "qa_v4_" + secrets.token_hex(5),
            "nickname": "真实链路测试",
            "password": password,
        },
    )
    c.headers["X-CSRF-Token"] = session["csrf_token"]
    w = req("POST", "/api/workspaces", {})
    # Seed only a public map POI snapshot to focus this test on hotel/transport, not user messages or preferences.
    spot = None
    with storage.connect() as db:
        for row in db.execute("select payload from workspaces"):
            d = json.loads(row[0])
            spot = next(
                (
                    p
                    for p in d.get("catalog", {}).values()
                    if p.get("kind") == "spot"
                    and "栈桥" in p.get("name", "")
                    and p.get("location")
                ),
                None,
            )
            if spot:
                break
    assert spot
    w["requirements"] = {
        "city": "青岛",
        "origin": "郑州",
        "start_date": "2026-10-12",
        "days": 3,
        "adults": 2,
        "rooms": 1,
        "children": 0,
    }
    w["catalog"] = {spot["id"]: spot}
    w["selected_spots"] = [spot["id"]]
    w["spots_confirmed"] = True
    w["stage"] = "住宿"
    storage.save(w)
    action("chat", text="请查询栈桥周围有没有汉庭酒店，只查汉庭，不要用其他品牌代替。")
    assert w["hotel_query"]["keyword"] == "汉庭"
    print("verified hotel brand forwarded", flush=True)
    if not w["hotel_query"]["ids"]:
        action("search_hotels")
    assert w["hotel_query"]["ids"]
    hid = w["hotel_query"]["ids"][0]
    action("select", {"id": hid})
    action("hotel_detail", {"id": hid})
    choices = w["catalog"][hid]["room_choices"]
    assert choices
    choice = next((p for p in choices if int(p.get("capacity") or 0) >= 2), choices[0])
    action(
        "chat",
        text=f"请实际选择{choice['name']}，参考报价{choice['price']}，1间，不要只记录偏好。",
    )
    assert w.get("selected_room") and w["selected_room"]["id"] == choice["id"]
    print("verified natural-language room selection persisted", flush=True)
    action("complete_hotel")
    assert w.get("selected_transport") or w.get("selected_return")
    print("verified transport recommendation", flush=True)
    action(
        "flight", {"direction": "return", "time_start": "12:00", "time_end": "23:59"}
    )
    flight = next(
        (p for p in w["transport"]["items"] if str(p.get("seats")) != "0"), None
    )
    if flight:
        action("select", {"id": flight["id"], "replace": True})
        assert w["selected_return"]["kind"] == "flight"
    action(
        "train",
        {
            "direction": "outbound",
            "time_start": "06:00",
            "time_end": "18:00",
            "train_type": "highspeed",
        },
    )
    Path("data/runtime/provider-workspace-v4.json").write_text(
        json.dumps(
            {
                "passed": True,
                "checks": log,
                "room_persisted": True,
                "brand_forwarded": True,
                "single_reply_per_action": True,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print("真实链路检查通过", flush=True)
finally:
    if session:
        if w.get("active_job"):
            req("POST", "/api/jobs/" + w["active_job"]["id"] + "/cancel", {})
        deleted = c.request("DELETE", "/api/account", json={"password": password})
        assert deleted.status_code == 200
    c.close()
