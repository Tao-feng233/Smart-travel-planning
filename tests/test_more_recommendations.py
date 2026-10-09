import asyncio
import json

from app import agent,discovery,replies


def trip():
    old={'id':'old','kind':'spot','name':'已有景点'}
    return {'id':'more-fixture','requirements':{'city':'青岛','days':3,'preferences':['人文']},'catalog':{'old':old},
            'selected_spots':['old'],'spots_confirmed':True,'messages':[],'spot_search':{'city':'青岛','ids':['old'],'page':1,'provider_page':1,'keywords':['人文']}}


def test_more_candidates_excludes_shown_and_preserves_selection(monkeypatch):
    w=trip();calls=[]
    async def tool(name,args):
        if name=='retrieve_guides':return {'items':[]}
        calls.append(args)
        return {'items':[w['catalog']['old'],{'id':'new','kind':'spot','name':'八大关','location':'120.35,36.06'}]}
    async def rank(*args):return '新增备选'
    monkeypatch.setattr(discovery,'local_tool',tool)
    result=asyncio.run(discovery.search(w,{'expand_spots':True},lambda _:None,rank))
    assert w['selected_spots']==['old'] and w['spots_confirmed']
    assert w['spot_search']['ids']==['new'] and 'old' in w['spot_search']['history_ids']
    assert calls[0]['page']==2 and '已补充' in result


def test_no_new_candidates_is_a_normal_result_with_old_batch_kept(monkeypatch):
    w=trip()
    async def tool(*args):return {'items':[w['catalog']['old']]}
    monkeypatch.setattr(discovery,'local_tool',tool)
    result=asyncio.run(discovery.search(w,{'expand_spots':True},lambda _:None,None))
    assert '暂未找到新的' in result and w['spot_search']['ids']==['old']


def test_chat_paging_at_end_requests_more_instead_of_failing(monkeypatch):
    w=trip();seen=[]
    async def handle(w,action,args,progress):seen.append((action,args));return '已补充新景点'
    monkeypatch.setattr(agent,'handle',handle)
    intent={'action':'spots_page','patch':{},'answer':'继续推荐','mission':{'mode':'query','objective':'补充更多相关景点','scopes':['spots'],'multi_step':False}}
    token=replies.SINK.set(None)
    try:result=asyncio.run(agent.execute({'workspace':w,'text':'继续推荐一些','intent':intent,'progress':lambda _:None}))
    finally:replies.SINK.reset(token)
    assert seen[0][0]=='search_spots' and seen[0][1]['expand_spots']
    assert '已补充' in result['answer']


def test_model_can_recommend_more_than_eight_with_alternatives(monkeypatch):
    w=trip();items=[{'id':f's{i}','name':f'候选{i}','kind':'spot'} for i in range(12)]
    async def model(messages,**kwargs):
        assert '完整旅行景点集合' in messages[0]['content']
        return {'content':json.dumps({'recommendations':[{'id':p['id'],'reason':'符合三天行程','role':'primary' if i<8 else 'alternative'} for i,p in enumerate(items)],'summary':'三天建议','coverage_note':'8个行程建议与4个备选，按兴趣取舍。'})},{}
    monkeypatch.setattr(agent,'llm',model);monkeypatch.setattr('app.storage.cached',lambda _:None);monkeypatch.setattr('app.storage.put_cache',lambda *args:None)
    result=asyncio.run(agent.recommend(w,items,'推荐完整行程'))
    assert all(p.get('recommendation_rank') is not None for p in items)
    assert sum(p['recommendation_role']=='alternative' for p in items)==4 and '4个备选' in result
    w['catalog'].update({p['id']:p for p in items});w['spot_search']['ids']=[p['id'] for p in items]
    assert len(discovery.visible(w))==12 and discovery.page_info(w)['pages']==3
