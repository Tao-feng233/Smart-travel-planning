import json
from pathlib import Path
import pytest
from app import knowledge, rag, vector_index, tools, providers
from app.knowledge_collection import collect, extract, publish
from app.embeddings import Encoder, EmbeddingError


def record(identifier='guide', **extra):
    return {'id':identifier,'city':'成都','title':'熊猫基地参观须知','url':'https://example.org/guide',
            'text':'提前预约后持身份证入园。每周一部分区域闭馆，法定节假日除外。',
            'fetched_at':'2026-10-08','scope':'官方页面快照',**extra}


def corpus(tmp_path, rows):
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path/'guides.json').write_text(json.dumps(rows,ensure_ascii=False),encoding='utf-8')
    return knowledge.load_corpus(tmp_path)


class TestEncoder:
    __test__ = False
    def documents(self,texts):return [[1.0,0.0] if '熊猫' in t else [0.0,1.0] for t in texts]
    def query(self,text):return [1.0,0.0]


@pytest.fixture
def index_env(monkeypatch,tmp_path):
    vector_index.close()
    monkeypatch.setenv('RAG_INDEX_PATH',str(tmp_path/'index'))
    monkeypatch.setenv('QDRANT_URL','')
    yield tmp_path
    vector_index.close()


def test_parent_context_contains_exception_and_source(tmp_path,monkeypatch):
    loaded=corpus(tmp_path,[record(text='参观须知。'+('请有序入园。'*35)+'每周一闭馆，法定节假日除外。')])
    monkeypatch.setattr(rag,'corpus',lambda:loaded)
    monkeypatch.setattr(vector_index,'search',lambda *a:([], 'index_not_ready'))
    result=rag.retrieve_result('成都市','周一闭馆')
    assert result['status']=='degraded'
    assert result['items'][0]['text'].endswith('法定节假日除外。')
    assert result['items'][0]['url']=='https://example.org/guide'
    assert all(len(c['text'])<=360 for c in loaded['children'])


def test_duplicate_and_invalid_dates_rejected(tmp_path):
    with pytest.raises(knowledge.CorpusError):corpus(tmp_path,[record(),record(text='不同正文')])
    with pytest.raises(knowledge.CorpusError):corpus(tmp_path,[record(valid_from='2026-10-11',valid_to='2026-10-10')])


def test_date_city_and_entity_filters(tmp_path):
    p=next(iter(corpus(tmp_path,[record(valid_from='2026-10-10',valid_to='2026-10-12',entity_ids=['poi:panda'])])['parents'].values()))
    assert not knowledge.applicable(p,'杭州','2026-10-11')
    assert not knowledge.applicable(p,'成都','2026-10-13')
    assert not knowledge.applicable(p,'成都','2026-10-11',['poi:other'])
    assert knowledge.applicable(p,'成都市','2026-10-08',['poi:panda'],'2026-10-11')
    assert not knowledge.applicable({**p,'source_kind':'historical_notice'},'成都')


def test_versions_never_share_a_parent(tmp_path):
    loaded=corpus(tmp_path,[record('old',source_version='v1'),record('new',source_version='v2')])
    assert len(loaded['parents'])==2


def test_rrf_reward_both_searches_and_stable_ties():
    hits=knowledge.fuse([('a',8),('b',3)],[('b',.9),('c',.8)])
    assert hits[0][0]=='b' and len(hits)==3


def test_overlapping_legacy_windows_are_not_repeated():
    text='参观规则：请有序参观并出示预约凭证，周一闭馆，法定节假日除外。'
    assert knowledge.merge_snippets([text[:30],text[5:],text])==text


def test_qdrant_persistence_and_parent_filter(index_env):
    loaded=corpus(index_env/'corpus',[record(),record('other',city='杭州',text='西湖游览')])
    manifest=vector_index.build(loaded,TestEncoder())
    assert manifest['dimensions']==2
    vector_index.close()
    allowed={pid for pid,p in loaded['parents'].items() if p['city']=='成都'}
    rows,reason=vector_index.search(loaded,'可否看动物',allowed,encoder=TestEncoder())
    assert reason is None and rows
    assert all(next(c for c in loaded['children'] if c['id']==cid)['parent_id'] in allowed for cid,_ in rows)
    assert vector_index.build(loaded,TestEncoder())['rebuilt'] is False


def test_failed_rebuild_keeps_previous_index(index_env):
    loaded=corpus(index_env/'corpus',[record()]);first=vector_index.build(loaded,TestEncoder())
    changed=corpus(index_env/'corpus',[record(text='增加新的规则，熊猫塔需预约。')])
    class Broken(TestEncoder):
        def documents(self,texts):raise EmbeddingError('推理失败')
    with pytest.raises(EmbeddingError):vector_index.build(changed,Broken())
    assert vector_index.read_manifest()['generation']==first['generation']
    rows,reason=vector_index.search(changed,'熊猫',set(changed['parents']),encoder=TestEncoder())
    assert rows==[] and reason=='index_outdated'


def test_dimension_mismatch_degrades(index_env):
    loaded=corpus(index_env/'corpus',[record()]);vector_index.build(loaded,TestEncoder())
    class Different(TestEncoder):
        def query(self,text):return [1.,0.,0.]
    assert vector_index.search(loaded,'熊猫',set(loaded['parents']),encoder=Different())[1]=='dimension_mismatch'


def test_backend_change_invalidates_index(index_env,monkeypatch):
    loaded=corpus(index_env/'corpus',[record()]);vector_index.build(loaded,TestEncoder())
    monkeypatch.setenv('QDRANT_URL','http://localhost:6333')
    assert vector_index.search(loaded,'熊猫',set(loaded['parents']),encoder=TestEncoder())[1]=='index_outdated'


def source():
    return {'id':'guide','city':'成都','title':'官方参观须知','url':'https://example.org/guide',
            'allowed_hosts':['example.org'],'selector':'article','terms':['预约'],'scope':'查询快照','min_chars':20}


def test_collection_failed_source_keeps_previous_valid_body():
    def failed(s):raise TimeoutError()
    rows,report=collect([source()],[record()],failed,'2026-10-08')
    assert rows[0]['text']==record()['text'] and rows[0]['collection_status']=='stale'
    assert report[0]['retained'] is True


def test_collection_missing_selector_does_not_index_navigation():
    rows,report=collect([source()],[],lambda s:('<nav>预约</nav>','https://example.org/guide'),'2026-10-08')
    assert not rows and report[0]['status']=='failed'


def test_collection_changed_version_is_single_document():
    fetch=lambda s:('<article>预约参观需携带有效身份证件，临时开放时间以现场公告为准。</article>','https://example.org/guide')
    rows,_=collect([source()],[],fetch,'2026-10-08')
    changed,_=collect([source()],rows,lambda s:(fetch(s)[0].replace('身份证件','护照'),fetch(s)[1]),'2026-10-09')
    assert len(changed)==1 and changed[0]['source_version']!=rows[0]['source_version']
    assert changed[0]['previous_version']==rows[0]['source_version']


def test_collection_rejects_unreviewed_redirect():
    rows,report=collect([source()],[],lambda s:('<article>预约参观需携带有效身份证件，临时开放时间以现场公告为准。</article>','https://ads.example/'),'2026-10-08')
    assert not rows and report[0]['status']=='failed'


def test_publish_invalid_replacement_preserves_file(tmp_path):
    file=tmp_path/'data.json';publish(file,[record()]);before=file.read_bytes()
    with pytest.raises(knowledge.CorpusError):publish(file,[{'text':'缺字段'}])
    assert file.read_bytes()==before


def test_embedding_api_reorders_and_checks_indices(monkeypatch):
    monkeypatch.setenv('EMBEDDING_PROVIDER','api');monkeypatch.setenv('EMBEDDING_BASE_URL','https://example.org/v1');monkeypatch.setenv('EMBEDDING_API_KEY','test-only')
    class Response:
        status_code=200
        def json(self):return {'data':[{'index':1,'embedding':[0.,1.]},{'index':0,'embedding':[1.,0.]}]}
    import httpx
    monkeypatch.setattr(httpx,'post',lambda *a,**k:Response())
    encoder=Encoder();assert encoder.documents(['a','b'])==[[1.,0.],[0.,1.]]
    monkeypatch.setattr(Response,'json',lambda self:{'data':[{'index':0,'embedding':[1.,0.]},{'index':0,'embedding':[0.,1.]}]})
    with pytest.raises(EmbeddingError):encoder.documents(['a','b'])


def test_mcp_failure_is_distinct_from_empty():
    with pytest.raises(providers.DataError):tools.validate_result('retrieve_guides',{'status':'query_failed','items':[]})
    assert tools.validate_result('retrieve_guides',{'status':'empty','items':[]})['items']==[]
    assert tools.validate_result('calculate_route',{'status':'query_failed','available':False})['available'] is False


def test_place_quality_invalid_coordinate_and_vendor_empty_arrays():
    row=providers.normalize_place({'id':'p','name':'餐厅','location':'nan,30','business':[],'navi':[],'address':[]},{'queried_at':'2026-10-08'},'food')
    assert row['location'] is None and row['address'] is None
    assert row['_data']['location_status']=='unknown' and row['cost'] is None


def test_malformed_poi_list_is_query_failure(monkeypatch):
    import asyncio
    async def bad(*a,**k):return {'data':{'pois':{}},'source':{}}
    monkeypatch.setattr(providers,'amap',bad)
    with pytest.raises(providers.DataError):asyncio.run(providers.search_poi('成都','餐厅','food'))


def test_transport_candidates_exclude_shops_and_platforms(monkeypatch):
    import asyncio
    seen=[]
    async def response(path,params):
        seen.append(params)
        return {'data':{'pois':[{'id':code,'name':'成都东站','typecode':code,'location':'104.1,30.6'} for code in ('150200','150203','150204','050000')]},'source':{}}
    monkeypatch.setattr(providers,'amap',response)
    rows=asyncio.run(providers.search_transport_places('成都','成都东站','station'))
    assert len(rows)==1 and rows[0]['typecode']=='150200'
    assert rows[0]['terminal_confirmed'] is False and rows[0]['match_status']=='candidate'
    rows=asyncio.run(providers.search_transport_places('成都','成都东站','station',True))
    assert len(rows)==2 and rows[1]['endpoint_scope']=='access_point'
    assert seen[0]['city_limit']=='true'


def test_airport_query_keeps_terminal_candidates_but_excludes_other_airports(monkeypatch):
    import asyncio
    async def response(*a,**k):
        return {'data':{'pois':[{'id':str(i),'name':name,'typecode':'150104','location':'104.1,30.6'} for i,name in enumerate(['成都双流国际机场','成都双流国际机场T2航站楼','成都天府国际机场'])]},'source':{}}
    monkeypatch.setattr(providers,'amap',response)
    rows=asyncio.run(providers.search_transport_places('成都','成都双流国际机场','airport'))
    assert len(rows)==2 and rows[1]['endpoint_scope']=='terminal'
    assert all(row['terminal_confirmed'] is False for row in rows)


def test_mcp_configuration_inheritance_is_explicit(monkeypatch):
    from app.data_settings import mcp_environment
    monkeypatch.setenv('QDRANT_URL','http://localhost:6333')
    monkeypatch.setenv('UNRELATED_TEST_SECRET','unrelated')
    env=mcp_environment()
    assert env['QDRANT_URL']=='http://localhost:6333' and 'UNRELATED_TEST_SECRET' not in env
