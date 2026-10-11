import asyncio

from app.planning import time_policy
from app.core.errors import DataError


def test_station_suffix_retry_and_cached_lookup():
    calls = []
    transport = {'departure_station': '青岛'}

    async def tool(name, args):
        calls.append(args['keywords'])
        rows = [{'id': 'station', 'name': '青岛站', 'location': '120.31,36.06'}] if args['keywords'] == '青岛站' else []
        return {'items': rows}

    first = asyncio.run(time_policy.resolve_station({}, transport, 'return', '青岛', tool))
    second = asyncio.run(time_policy.resolve_station({}, transport, 'return', '青岛', tool))
    assert first == second
    assert first['id'] == 'station'
    assert calls == ['青岛', '青岛站']


def test_ambiguous_terminals_are_not_silently_selected():
    transport = {'arrival_station': '青岛'}
    calls = []

    async def tool(name, args):
        calls.append(args['keywords'])
        return {'items': [{'id': 'a', 'location': '120.31,36.06'}, {'id': 'b', 'location': '120.32,36.07'}]}

    assert asyncio.run(time_policy.resolve_station({}, transport, 'arrival', '青岛', tool)) is None
    assert calls == ['青岛']


def test_failed_lookup_does_not_block_or_repeat():
    transport = {'departure_station': '青岛站'}
    calls = []

    async def tool(name, args):
        calls.append(args['keywords'])
        raise DataError('服务暂时不可用')

    assert asyncio.run(time_policy.resolve_station({}, transport, 'return', '青岛', tool)) is None
    assert asyncio.run(time_policy.resolve_station({}, transport, 'return', '青岛', tool)) is None
    assert calls == ['青岛站']
