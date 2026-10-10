import json
import pytest
import httpx
from app.public_directory import decode_nuxt,mct_shandong_records
from app.public_fetch import PublicFetcher
from app.knowledge import CorpusError,normalize_record,applicable
from app.knowledge_collection import collect,extract
from app import discovery
from app.config import ROOT


def serialized(body):
    return '<script>window.__NUXT__=(function(a,b){return '+body+'}("测试景区",370100));</script>'


def test_static_nuxt_literal_decoder_does_not_execute_code():
    result=decode_nuxt(serialized('{title:a,code:b,path:"\\u002Fview",enabled:false,items:[null,1.5]}'))
    assert result=={'title':'测试景区','code':370100,'path':'/view','enabled':False,'items':[None,1.5]}
    with pytest.raises(CorpusError):decode_nuxt(serialized('{title:fetch("https://other.example/")}'))
    with pytest.raises(CorpusError):decode_nuxt(serialized('{title:unknown}'))


def directory_html():
    places=[{'id':i,'province_name':'山东','city_name':'济宁市','name':'三孔景区'+str(i),
             'introduce':'孔府、孔庙、孔林是儒家文化与历史建筑的代表性景观。',
             'address':'山东省济宁市曲阜市神道路','weather':{'temperature':30},
             'longitude':'116.9','latitude':'35.6'} for i in range(10)]
    body=json.dumps({'data':[{'markers':[[],places,[]]}]},ensure_ascii=False)
    return serialized(body)


def test_public_directory_excludes_live_weather_and_unverified_coordinates():
    rows=mct_shandong_records(directory_html(),{'id':'mct-shandong','url':'https://example.org/page'},'2026-10-08')
    assert len(rows)==10 and rows[0]['city']=='济宁' and rows[0]['city_aliases']==['曲阜']
    assert 'weather' not in rows[0] and 'location' not in rows[0] and 'longitude' not in rows[0]
    assert rows[0]['source_kind']=='background'
    assert applicable(rows[0],'曲阜市') and not applicable(rows[0],'泰安')


def test_failed_directory_keeps_all_previous_valid_entries():
    source={'id':'mct-shandong','format':'mct_directory','url':'https://example.org/page','allowed_hosts':['example.org']}
    old=mct_shandong_records(directory_html(),source,'2026-10-08')
    rows,report=collect([source],old,lambda s:('<html>加载失败</html>',s['url']),'2026-10-09')
    assert len(rows)==10 and all(row['collection_status']=='stale' for row in rows)
    assert report[0]['retained'] is True


def test_city_alias_schema_rejects_string_instead_of_list():
    record={'id':'1','city':'济宁','title':'三孔','url':'https://example.org','text':'参观介绍','city_aliases':'曲阜'}
    with pytest.raises(CorpusError):normalize_record(record)


def test_robots_denial_prevents_page_fetch(monkeypatch):
    seen=[]
    with PublicFetcher() as fetch:
        def request(url):
            seen.append(url)
            return httpx.Response(200,text='User-agent: *\nDisallow: /\n',request=httpx.Request('GET',url))
        monkeypatch.setattr(fetch,'request',request)
        with pytest.raises(CorpusError):fetch({'url':'https://example.org/page','allowed_hosts':['example.org']})
    assert seen==['https://example.org/robots.txt']


def test_unreviewed_redirect_is_rejected_before_network_read(monkeypatch):
    seen=[]
    with PublicFetcher() as fetch:
        def request(url):
            seen.append(url)
            if url.endswith('/robots.txt'):return httpx.Response(404,request=httpx.Request('GET',url))
            return httpx.Response(302,headers={'location':'https://unreviewed.example/page'},request=httpx.Request('GET',url))
        monkeypatch.setattr(fetch,'request',request)
        with pytest.raises(CorpusError):fetch({'url':'https://example.org/page','allowed_hosts':['example.org']})
    assert seen==['https://example.org/robots.txt','https://example.org/page']


def test_http_declared_encoding_is_used(monkeypatch):
    html='<article>中文景区介绍。</article>'
    with PublicFetcher() as fetch:
        def request(url):
            if url.endswith('/robots.txt'):return httpx.Response(404,request=httpx.Request('GET',url))
            return httpx.Response(200,content=html.encode('gb18030'),headers={'content-type':'text/html; charset=gb18030'},request=httpx.Request('GET',url))
        monkeypatch.setattr(fetch,'request',request)
        body,url=fetch({'url':'https://example.org/page','allowed_hosts':['example.org']})
    assert body==html


def test_selected_article_section_excludes_unrelated_history_and_old_meal_claims():
    html='<title>聊城景区资料</title><article>经济统计\n聊城景观起始\n'+('光岳楼与东昌湖历史景观。'*12)+'\n特色美食\n不应入库的食疗说法</article>'
    source={'selector':'article','terms':['光岳楼'],'start_at':'聊城景观起始','stop_before':'特色美食'}
    text=extract(html,source)
    assert text.startswith('聊城景观起始') and '光岳楼' in text
    assert '经济统计' not in text and '食疗' not in text
    with pytest.raises(CorpusError):extract(html,{**source,'start_at':'未提供的段落'})


def test_shandong_catalogue_is_source_backed_and_keeps_existing_destinations():
    items=discovery.destinations()
    cities={'济南','青岛','淄博','枣庄','东营','烟台','潍坊','济宁','泰安','威海','日照','临沂','德州','聊城','滨州','菏泽'}
    assert cities <= {d['name'] for d in items}
    assert {'成都','杭州','西安'} <= {d['name'] for d in items}
    assert len(items)==len({d['id'] for d in items})==20
    assert discovery.classic_names('济南市')==['趵突泉','大明湖','千佛山','九如山']
    original=json.loads((ROOT/'data/catalog/destinations.json').read_text('utf-8'))
    assert next(d for d in items if d['name']=='青岛')==original[0]
    rows={r['id']:r for r in json.loads((ROOT/'data/knowledge/shandong.json').read_text('utf-8'))}
    assert {r['city'] for r in rows.values()}==cities
    for destination in items:
        if destination.get('province')!='山东':continue
        records=[rows[i] for i in destination['source']['record_ids']]
        assert all(r['city']==destination['name'] for r in records)
        assert all(any(name in r['title']+' '+r['text'] for r in records) for name in destination['highlights'])


def test_directory_city_override_is_explicit_and_does_not_invent_an_introduction():
    html=directory_html().replace('"city_name": "济宁市"','"city_name": ""').replace('"introduce": "孔府、孔庙、孔林是儒家文化与历史建筑的代表性景观。"','"introduce": ""')
    source={'id':'mct-shandong','url':'https://example.org/page','city_overrides':{str(i):'济宁' for i in range(10)}}
    rows=mct_shandong_records(html,source,'2026-10-08')
    assert all(r['city']=='济宁' and '未提供详细介绍' in r['text'] for r in rows)


def test_status_reports_actual_corpus_coverage():
    from app.main import status
    result=status(user={'id':'test'})
    # 目的地新增洛阳（河南）后 19 → 20 个城市。
    assert len(result['knowledge_cities'])==20 and '日照' in result['knowledge_cities']
    # 记录数随采集增长（新增成都官方来源后 90 → 105）。这里与语料实际数量比对，
    # 不写死数字，避免每次扩采都要改测试。
    from app.rag import corpus
    assert result['knowledge_records']==corpus()['records']
