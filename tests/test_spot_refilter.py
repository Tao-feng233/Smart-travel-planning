import asyncio
import copy

import pytest

from app.travel import discovery
from app.core.errors import DataError


def workspace():
    chosen = {'id': 'chosen', 'kind': 'spot', 'name': '栈桥', 'location': '120.31,36.06'}
    old = {'id': 'old', 'kind': 'spot', 'name': '八大关', 'location': '120.35,36.06'}
    return {'requirements': {'city': '青岛', 'days': 1}, 'catalog': {'chosen': chosen, 'old': old},
            'selected_spots': ['chosen'], 'candidates': [chosen, old], 'spots_confirmed': True,
            'spot_search': {'city': '青岛', 'ids': ['chosen', 'old'], 'page': 1},
            'rejected_spots': [], 'rejected_spot_names': []}


@pytest.mark.parametrize('response', ['empty', 'missing_location', 'failure'])
def test_unsuccessful_refilter_keeps_visible_candidates(monkeypatch, response,web_candidates):
    w = workspace()
    before = copy.deepcopy(w)
    web_candidates([{'name':'五四广场'}] if response!='empty' else [])

    async def tool(name, args):
        if response == 'failure':
            raise DataError('查询暂时失败')
        if name == 'get_place_details':
            return {'items': []}
        items = [{'id': 'new', 'kind': 'spot', 'name': '五四广场'}] if response == 'missing_location' else []
        return {'items': items, 'exhausted': True}

    monkeypatch.setattr(discovery, 'local_tool', tool)
    if response == 'failure':
        with pytest.raises(DataError):
            asyncio.run(discovery.search(w, {'reject_current': True}, lambda _: None, None))
    else:
        asyncio.run(discovery.search(w, {'reject_current': True}, lambda _: None, None))
    assert discovery.visible(w) == ['chosen', 'old']
    assert w == before


def test_successful_refilter_dismisses_only_unselected_old_candidates(monkeypatch,web_candidates):
    w = workspace()
    observed=web_candidates([{'name':'五四广场'}])

    async def tool(name, args):
        return {'items': [{'id': 'new', 'kind': 'spot', 'name': '五四广场', 'location': '120.38,36.06'}], 'exhausted': True}

    async def recommend(*args):
        return '新候选'

    monkeypatch.setattr(discovery, 'local_tool', tool)
    asyncio.run(discovery.search(w, {'reject_current': True}, lambda _: None, recommend))
    assert w['selected_spots'] == ['chosen']
    assert w['rejected_spots'] == ['old']
    assert discovery.visible(w) == ['new']
    assert {'栈桥','八大关'} <= set(observed[0]['excluded'])


def test_all_selected_page_can_still_query_more_candidates(monkeypatch,web_candidates):
    w = workspace()
    w['selected_spots'] = ['chosen', 'old']
    calls = []
    web_candidates([{'name':'五四广场'}])

    async def tool(name, args):
        calls.append(args)
        return {'items': [{'id': 'new', 'kind': 'spot', 'name': '五四广场', 'location': '120.38,36.06'}], 'exhausted': True}

    async def recommend(*args):
        return '额外备选'

    monkeypatch.setattr(discovery, 'local_tool', tool)
    asyncio.run(discovery.search(w, {'reject_current': True}, lambda _: None, recommend))
    assert calls
    assert w['selected_spots'] == ['chosen', 'old']
    assert w['rejected_spots'] == []
    assert discovery.visible(w) == ['new']
