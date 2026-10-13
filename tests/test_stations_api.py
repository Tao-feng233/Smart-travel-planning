"""站点清单接口：按城市返回火车站/机场，且强必填在真实 HTTP 路径上生效。

与 test_accounts.py 相同的测试栈（TestClient + 隔离数据库）。
站点查询本身打高德，这里注入假工具，避免测试依赖外网。
"""

import asyncio
import secrets
import uuid

import pytest
from fastapi.testclient import TestClient
from app import main
from app.application import jobs as job_runner
from app.persistence import storage
from app.travel import stations

PASSWORD = "Aa-test-" + secrets.token_urlsafe(24)


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "DB", tmp_path / "test.db")
    storage.init()
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def lifespan(app):
        job_runner.SHUTTING_DOWN = False
        job_runner.TASKS.clear()
        job_runner.LOCKS.clear()
        yield
        for task in list(job_runner.TASKS.values()):
            task.cancel()

    monkeypatch.setattr(main.app.router, "lifespan_context", lifespan)
    with TestClient(
        main.app,
        base_url="http://127.0.0.1:8767",
        headers={
            "Origin": "http://127.0.0.1:8767",
            "Content-Type": "application/json",
        },
    ) as c:
        yield c


def signup(client, name="alice"):
    r = client.post(
        "/api/auth/register",
        json={"username": name, "password": PASSWORD, "nickname": name},
    )
    assert r.status_code == 201
    client.headers["X-CSRF-Token"] = r.json()["csrf_token"]


def create(client, requirements=None):
    r = client.post("/api/workspaces", json={})
    assert r.status_code == 201
    w = r.json()
    if requirements:
        # 必须真的提交到工作区：只改返回值不会落库，
        # 否则后续动作看到的是空条件（例如"还没告诉我想去哪个城市"）。
        resp = submit(client, w, "requirements", {"patch": requirements})
        assert resp.status_code == 202
        w = wait(client, resp.json()["job_id"])["workspace"]
    return w


def submit(client, w, action, args=None):
    return client.post(
        f"/api/workspaces/{w['id']}/actions",
        json={
            "revision": w["revision"],
            "action": action,
            "args": args or {},
            "request_id": str(uuid.uuid4()),
        },
    )


def wait(client, jid):
    import time

    for _ in range(200):
        j = client.get(f"/api/jobs/{jid}").json()
        if j["status"] != "running":
            return j
        time.sleep(0.01)
    raise AssertionError("任务未完成")


@pytest.fixture
def fake_stations(monkeypatch):
    """注入假的高德查询，避免测试打外网。

    先抓住原函数再替换：假实现里若再调用同名函数会无限递归。
    """
    calls = []
    original = stations.list_stations

    async def fake_tool(name, args):
        calls.append(args)
        return {
            "items": [
                {"name": "洛阳龙门站", "address": "洛龙区"},
                {"name": "洛阳站", "address": "西工区"},
                {"name": "洛阳师范学院西门(公交站)", "address": "噪音"},
            ]
        }

    def make(city, kind, *, tool=None):
        return original(city, kind, tool=fake_tool)

    monkeypatch.setattr(stations, "list_stations", make)
    return calls


def test_stations_endpoint_returns_clean_list(client, fake_stations):
    signup(client)
    w = create(client, {"city": "洛阳"})
    r = client.get(f"/api/workspaces/{w['id']}/stations?kind=train")
    assert r.status_code == 200
    body = r.json()
    assert body["kind"] == "train" and body["city"] == "洛阳"
    names = [x["name"] for x in body["items"]]
    assert "洛阳龙门站" in names and "洛阳站" in names
    # 公交站必须被过滤掉
    assert not any("公交" in n for n in names)
    assert fake_stations and fake_stations[0]["category"] == "train_station"


def test_stations_endpoint_accepts_explicit_city(client, fake_stations):
    """返程站通常属于出发城市，所以要允许显式传 city。"""
    signup(client)
    w = create(client, {"city": "洛阳"})
    r = client.get(f"/api/workspaces/{w['id']}/stations?kind=flight&city=郑州")
    assert r.status_code == 200
    assert r.json()["city"] == "郑州"


def test_stations_endpoint_rejects_unknown_kind(client):
    signup(client)
    w = create(client, {"city": "洛阳"})
    assert (
        client.get(f"/api/workspaces/{w['id']}/stations?kind=bogus").status_code == 422
    )


def test_stations_endpoint_requires_ownership(client):
    signup(client, "alice")
    w = create(client, {"city": "洛阳"})
    client.headers.pop("X-CSRF-Token", None)
    client.post("/api/auth/logout")
    signup(client, "bob")
    assert client.get(f"/api/workspaces/{w['id']}/stations").status_code == 404


def test_plan_is_blocked_when_transport_incomplete(client, monkeypatch):
    """非自驾且缺到达/返程时间时，生成计划必须被拒绝。

    直接调用 do_plan：这是真正挂着校验的地方，比绕 HTTP 编排更可靠
    （HTTP 路径上 dispatch 会先因"没填城市"拦掉，掩盖这道校验）。
    """
    from types import SimpleNamespace

    from app.core.errors import DataError
    from app.travel.handlers import planning as planning_handler

    w = storage.new_workspace("probe-owner")
    w["requirements"] = {
        "city": "青岛",
        "start_date": "2026-10-12",
        "days": 1,
        "intercity_vehicle": "highspeed",
        # 四项必填一个都没填
    }
    called = []

    async def fake_generate(workspace, progress):
        called.append(True)          # 不该被调用
        return {}

    services = SimpleNamespace(generate=fake_generate)
    with pytest.raises(DataError) as e:
        asyncio.run(
            planning_handler.do_plan(
                w, "plan", {}, lambda _msg: None, services
            )
        )
    assert "到达站" in str(e.value)
    assert called == []              # 校验在调用生成之前就拦住了
    storage.delete_workspace(w["id"], "probe-owner")


def test_plan_gate_passes_when_transport_complete(monkeypatch):
    """必填齐备后这道校验放行（后续流程成功与否不由本校验决定）。"""
    from types import SimpleNamespace

    from app.travel.handlers import planning as planning_handler

    w = storage.new_workspace("probe-owner2")
    w["requirements"] = {
        "city": "青岛",
        "start_date": "2026-10-12",
        "days": 1,
        "intercity_vehicle": "highspeed",
        "arrival_station": "青岛站",
        "arrival_time": "10:00",
        "return_station": "青岛站",
        "return_time": "18:00",
    }
    reached = []

    async def fake_generate(workspace, progress):
        reached.append(True)
        return {"title": "草稿", "days": [], "warnings": []}

    services = SimpleNamespace(generate=fake_generate)
    asyncio.run(planning_handler.do_plan(w, "plan", {}, lambda _m: None, services))
    assert reached == [True]         # 校验放行，走到了生成
    storage.delete_workspace(w["id"], "probe-owner2")


def test_drive_skips_the_plan_gate(client, monkeypatch):
    """自驾时缺站点与时刻也应放行。"""
    from types import SimpleNamespace

    from app.travel.handlers import planning as planning_handler

    w = storage.new_workspace("probe-owner3")
    w["requirements"] = {
        "city": "洛阳",
        "origin": "郑州",
        "start_date": "2026-10-12",
        "days": 1,
        "intercity_vehicle": "drive",
    }
    reached = []

    async def fake_generate(workspace, progress):
        reached.append(True)
        return {"title": "草稿", "days": [], "warnings": []}

    services = SimpleNamespace(generate=fake_generate)
    asyncio.run(planning_handler.do_plan(w, "plan", {}, lambda _m: None, services))
    assert reached == [True]
    storage.delete_workspace(w["id"], "probe-owner3")
