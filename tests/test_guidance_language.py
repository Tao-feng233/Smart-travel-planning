import asyncio
import json

import pytest

from app import journey,replies


def trip(confirmed=False):
    return {'requirements':{'city':'青岛'},'catalog':{'s':{'id':'s','name':'栈桥','kind':'spot'}},
            'selected_spots':['s'],'spots_confirmed':confirmed,'messages':[],'tickets':{}}


def test_missing_information_is_deferred_while_selecting_spots():
    w=trip();step=journey.next_step(w)
    assert '选择完成后' in step['message']
    assert step['view']=='spot' and step['action']=='complete_spots'
    assert '出游日期' in step['message'] and '成人数' in step['message']
    assert '下一步：' not in step['message']


def test_confirmed_spots_invite_information_for_hotel_query():
    step=journey.next_step(trip(True))
    assert step['view']=='hotel' and '便于' in step['message']
    assert '选择完成后' not in step['message']


@pytest.mark.parametrize('semantic',[True,False])
def test_reply_prompt_uses_current_stage_without_command_heading(monkeypatch,semantic):
    w=trip();w.update(turn_action='search_spots',turn_is_chat=True,spot_search={'city':'青岛','ids':['s'],'page':1})
    if semantic:w['assistant_goal']={'mode':'consult','objective':'比较景点','status':'completed'}
    seen=[]
    async def stream(messages,sink,**kwargs):
        seen.extend(messages);return '可以继续比较景点。',{}
    monkeypatch.setattr(replies,'llm_stream',stream)
    token=replies.PREFIX.set('')
    try:asyncio.run(replies.compose(w,'已查询到景点'))
    finally:replies.PREFIX.reset(token)
    assert '结尾以**下一步：具体操作**' not in seen[0]['content']
    assert '不强制输出' in seen[0]['content']
    assert '选择完成后' in json.loads(seen[-1]['content'])['next_step']['message']
