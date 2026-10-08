import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from app import providers, agent, replies, storage


@pytest.mark.parametrize('payload', [
    {'choices': [], 'usage': {'total_tokens': 12}},
    {'choices': [{}], 'usage': {'total_tokens': 12}},
    {'choices': [{'message': None}], 'usage': {'total_tokens': 12}},
])
def test_malformed_success_response_is_recorded_once_as_failure(monkeypatch, payload):
    records = []
    class Response:
        status_code = 200
        def json(self): return payload
    class Client:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def post(self, *args, **kwargs): return Response()
    monkeypatch.setattr(providers.httpx, 'AsyncClient', Client)
    monkeypatch.setattr(providers, 'setting', lambda key, default='': 'https://example.invalid' if key=='LLM_BASE_URL' else 'fixture')
    monkeypatch.setattr(providers, 'record_llm_call', lambda *args, **kwargs: records.append((args, kwargs)))
    with pytest.raises(providers.DataError): asyncio.run(providers.llm([], label='fixture'))
    assert len(records) == 1 and records[0][1]['ok'] is False
    assert records[0][0][2]['total_tokens'] == 12


def test_graph_repairs_once_and_accepts_integrated_analysis_action(monkeypatch):
    calls = []; actions = []
    async def model(messages, **kwargs):
        calls.append(messages)
        if len(calls) == 1: return {'content': 'invalid tool response'}, {}
        intent = {'action': 'analyze_visits', 'patch': {}, 'answer': '已分析', 'view': 'spot'}
        return {'tool_calls': [{'function': {'name': 'submit_intent', 'arguments': json.dumps(intent)}}]}, {}
    async def handle(w, action, args, progress): actions.append(action); return '建议安排已分析'
    async def weather(*args): pass
    monkeypatch.setattr(agent, 'llm', model); monkeypatch.setattr(agent, 'handle', handle)
    monkeypatch.setattr(agent, 'ensure_weather', weather)
    w = {'requirements': {'city': '青岛'}, 'catalog': {}, 'selected_spots': [], 'messages': []}
    prefix = replies.PREFIX.set(''); sink = replies.SINK.set(None)
    try:
        answer = asyncio.run(agent.run_chat(w, '优化景点每日分配', lambda _: None))
    finally:
        replies.PREFIX.reset(prefix); replies.SINK.reset(sink)
    assert len(calls) == 2 and actions == ['analyze_visits']
    assert any('上一次输出不可用' in m['content'] for m in calls[1])
    assert '建议安排' in answer


def test_storage_reuses_connections_within_each_thread_only(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, 'DB', tmp_path/'connections.db')
    storage.init(); gate = Barrier(2)
    def check():
        first = storage.connect(); gate.wait(timeout=5)
        second = storage.connect()
        assert first is second
        identity = id(first); first.close(); return identity
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(check) for _ in range(2)]
        identities = [f.result(timeout=10) for f in futures]
    assert identities[0] != identities[1]
