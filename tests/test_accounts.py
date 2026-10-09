import asyncio,uuid,time,secrets
from contextlib import asynccontextmanager
import pytest
from fastapi.testclient import TestClient
from app import main,storage,auth

PASSWORD='Aa-test-'+secrets.token_urlsafe(24)

@pytest.fixture
def client(monkeypatch,tmp_path):
    monkeypatch.setattr(storage,'DB',tmp_path/'test.db');storage.init()
    # API orchestration fixtures keep the new read-only audit offline.
    from app import timeline_review
    original_audit=timeline_review.refresh
    async def offline_model(*args,**kwargs):return {'content':'{"summary":"合成审核","issues":[]}'},{}
    async def offline_audit(w,model,progress,**kwargs):return await original_audit(w,offline_model,progress,**kwargs)
    monkeypatch.setattr(timeline_review,'refresh',offline_audit)
    @asynccontextmanager
    async def lifespan(app):
        main.SHUTTING_DOWN=False;main.TASKS.clear();main.LOCKS.clear()
        yield
        for task in list(main.TASKS.values()):task.cancel()
        if main.TASKS:await asyncio.gather(*list(main.TASKS.values()),return_exceptions=True)
    monkeypatch.setattr(main.app.router,'lifespan_context',lifespan)
    with TestClient(main.app,base_url='http://127.0.0.1:8767',headers={'Origin':'http://127.0.0.1:8767','Content-Type':'application/json'}) as c:yield c

def signup(client,name='alice'):
    response=client.post('/api/auth/register',json={'username':name,'password':PASSWORD,'nickname':name})
    assert response.status_code==201
    data=response.json();client.headers['X-CSRF-Token']=data['csrf_token'];return data

def create(client):
    response=client.post('/api/workspaces',json={});assert response.status_code==201;return response.json()

def submit(client,w,action='requirements',args=None,request_id=None):
    return client.post('/api/workspaces/'+w['id']+'/actions',json={'revision':w['revision'],'action':action,'args':args or {},'request_id':request_id or str(uuid.uuid4())})

def wait(client,jid):
    for _ in range(100):
        j=client.get('/api/jobs/'+jid).json()
        if j['status']!='running':return j
        time.sleep(.01)
    raise AssertionError('任务未完成')

def test_anonymous_access_never_returns_global_history(client):
    assert client.get('/api/workspaces/latest').status_code==401
    assert client.get('/api/workspaces').status_code==401
    assert client.get('/api/account/export').status_code==401


def test_followup_optimization_keeps_previous_conflict_through_loading_ui(client,monkeypatch):
    import json
    from app import agent,replies
    signup(client);w=create(client)
    w['requirements']={'city':'青岛','start_date':'2026-10-12','days':2}
    w['catalog']={'s':{'id':'s','kind':'spot','name':'崂山风景区','location':'120.6,36.2'}}
    w['selected_spots']=['s']
    w['ui']={'status':'failed','action':'plan','conflict':{'phase':'proposal','issues':[{'code':'day_capacity','date':'2026-10-12','candidate_ids':['s'],'message':'440分钟超过435分钟'}]}}
    storage.save(w);actions=[]
    async def model(messages,**kwargs):
        return {'tool_calls':[{'function':{'name':'submit_intent','arguments':json.dumps({'action':'analyze_visits','patch':{}})}}]},{}
    async def handle(workspace,action,args,progress):actions.append((action,args));return '已修订'
    async def weather(*args):pass
    async def compose(w,result):return result
    monkeypatch.setattr(agent,'llm',model);monkeypatch.setattr(agent,'handle',handle)
    monkeypatch.setattr(agent,'ensure_weather',weather);monkeypatch.setattr(replies,'compose',compose)
    response=client.post('/api/workspaces/'+w['id']+'/actions',json={'revision':w['revision'],'action':'chat','text':'那你帮我优化一下吧','request_id':str(uuid.uuid4())})
    assert response.status_code==202
    assert wait(client,response.json()['job_id'])['status']=='completed'
    assert actions[0][0]=='optimize_plan' and actions[0][1]['conflict']['issues'][0]['date']=='2026-10-12'


def test_plan_warning_is_completed_request_with_explicit_approval_before_publication(client,monkeypatch):
    from app import agent,replies
    signup(client);w=create(client);w['requirements']={'city':'青岛','start_date':'2026-10-12','days':1}
    w['catalog']={'s':{'id':'s','kind':'spot','name':'崂山风景区','location':'120.6,36.2'}};w['selected_spots']=['s'];storage.save(w)
    calls=[]
    async def generate(*args):
        calls.append(True)
        return {'title':'带提醒的草稿','days':[],'warnings':[],'stale':False,'planning_issues':[{'code':'estimated_capacity','level':'warning','message':'估算440分钟，可用435分钟','date':'2026-10-12','candidate_ids':['s'],'view':'spot'}]}
    async def compose(w,result):return result
    monkeypatch.setattr(agent,'generate',generate);monkeypatch.setattr(replies,'compose',compose)
    response=submit(client,w,'plan');assert response.status_code==202
    job=wait(client,response.json()['job_id']);assert job['status']=='completed' and not job['error']
    current=job['workspace'];assert not current.get('plan')
    nonce=current['pending_plan_warning']['id']
    approved=submit(client,current,'approve_plan_warning',{'approval_id':nonce,'confirmed':True})
    result=wait(client,approved.json()['job_id']);assert result['status']=='completed'
    assert result['workspace']['plan']['warning_acceptance']['confirmed'] and len(calls)==1

def test_login_page_assets_are_versioned_and_not_cached(client):
    page=client.get('/')
    assert page.status_code==200 and 'id="auth-gate"' in page.text
    assert page.headers['cache-control']=='no-store'
    for name,version in main.ASSET_VERSIONS.items():
        path=f'/assets/{name}?v={version}'
        assert path in page.text
        assert client.get(path).headers['cache-control']=='no-store'
    refreshed=client.get('/',headers={'If-None-Match':'"old-page"'})
    assert refreshed.status_code==200 and 'id="auth-gate"' in refreshed.text
    health=client.get('/api/healthz').json()
    assert health['service']=='shitu' and health['project_id']==main.PROJECT_ID

def test_chat_topic_is_exposed_before_query_finishes_and_saved_with_reply(client,monkeypatch):
    from app import guidance
    signup(client);w=create(client)
    async def slow(w,text,progress):
        w['ui']=guidance.describe(w,'search_hotels',status='loading');progress('正在查询酒店候选')
        await asyncio.sleep(.3)
        w['catalog']['h1']={'id':'h1','name':'测试酒店','kind':'hotel'}
        w['last_action']='search_hotels';return '住宿候选已返回'
    monkeypatch.setattr(main,'run_chat',slow)
    ack=client.post('/api/workspaces/'+w['id']+'/actions',json={'revision':0,'action':'chat','text':'看看住宿','request_id':str(uuid.uuid4())}).json()
    for _ in range(30):
        j=client.get('/api/jobs/'+ack['job_id']).json()
        if j['ui'].get('view')=='hotel':break
        time.sleep(.01)
    assert j['status']=='running' and j['ui']['view']=='hotel'
    assert client.get('/api/workspaces/'+w['id']).json()['active_job']['ui']['view']=='hotel'
    j=wait(client,ack['job_id'])
    assert j['status']=='completed' and j['ui']['cta']=={'label':'查看住宿','view':'hotel'}
    assert j['workspace']['messages'][-1]['ui']['view']=='hotel'

def test_registration_hashes_password_and_protects_cookie(client):
    data=signup(client)
    user=auth.user_by_name('alice')
    assert user['password_hash'].startswith('scrypt$') and PASSWORD not in user['password_hash']
    assert user['recovery_hash']!=data['recovery_code']
    response=client.post('/api/auth/login',json={'username':'alice','password':PASSWORD})
    cookie=response.headers['set-cookie'].lower()
    assert 'httponly' in cookie and 'samesite=strict' in cookie

def test_csrf_and_origin_are_checked(client):
    signup(client)
    assert client.post('/api/workspaces',json={},headers={'X-CSRF-Token':'wrong'}).status_code==403
    assert client.post('/api/workspaces',json={},headers={'Origin':'https://another.example'}).status_code==403
    assert client.get('/api/workspaces',headers={'Host':'attacker.example'}).status_code==400

def test_cross_account_access_is_blocked_everywhere(client):
    signup(client,'alice');w=create(client)
    job=submit(client,w,args={'patch':{'city':'青岛'}}).json()['job_id'];wait(client,job)
    signup(client,'bob')
    for path in ['/api/workspaces/'+w['id'],'/api/workspaces/'+w['id']+'/export','/api/jobs/'+job]:assert client.get(path).status_code==404
    assert submit(client,w).status_code==404
    assert client.patch('/api/workspaces/'+w['id'],json={'title':'窃取','revision':1}).status_code==404
    assert client.delete('/api/workspaces/'+w['id']).status_code==404
    assert client.post('/api/jobs/'+job+'/cancel',json={}).status_code==404
    assert client.get('/api/workspaces').json()['total']==0

def test_new_trip_history_rename_archive_restore_delete(client):
    signup(client);a=create(client);b=create(client)
    assert a['id']!=b['id'] and len(b['messages'])==1 and b['messages'][0]['type']=='welcome'
    a=client.patch('/api/workspaces/'+a['id'],json={'revision':a['revision'],'title':'爸妈的青岛旅行'}).json()
    listing=client.get('/api/workspaces?q=爸妈').json();assert listing['total']==1
    a=client.patch('/api/workspaces/'+a['id'],json={'revision':a['revision'],'archived':True}).json()
    assert client.get('/api/workspaces').json()['total']==1
    assert client.get('/api/workspaces?archived=true').json()['total']==1
    assert submit(client,a).status_code==409
    a=client.patch('/api/workspaces/'+a['id'],json={'revision':a['revision'],'archived':False}).json()
    assert client.delete('/api/workspaces/'+a['id']).status_code==200
    assert client.get('/api/workspaces/'+a['id']).status_code==404
    with storage.connect() as c:assert not c.execute('SELECT 1 FROM versions WHERE id=?',(a['id'],)).fetchone()

def test_request_idempotency_does_not_repeat_action(client,monkeypatch):
    signup(client);w=create(client);calls=[]
    async def fake(w,action,args,progress):calls.append(action);return '已执行'
    monkeypatch.setattr(main,'handle',fake);request_id=str(uuid.uuid4())
    first=submit(client,w,request_id=request_id).json()['job_id'];wait(client,first)
    second=submit(client,w,request_id=request_id).json()['job_id']
    assert first==second and len(calls)==1

def test_stop_prevents_delete_race_and_keeps_user_message(client,monkeypatch):
    signup(client);w=create(client)
    async def slow(w,text,progress):progress('测试处理中');await asyncio.sleep(60);return '不能到达'
    monkeypatch.setattr(main,'run_chat',slow)
    response=client.post('/api/workspaces/'+w['id']+'/actions',json={'revision':0,'action':'chat','text':'想去青岛','request_id':str(uuid.uuid4())})
    jid=response.json()['job_id']
    for _ in range(50):
        if any(m['role']=='user' for m in client.get('/api/workspaces/'+w['id']).json()['messages']):break
        time.sleep(.01)
    assert client.delete('/api/workspaces/'+w['id']).status_code==409
    assert client.post('/api/jobs/'+jid+'/cancel',json={}).status_code==200
    j=wait(client,jid);assert j['status']=='cancelled'
    assert next(m['content'] for m in j['workspace']['messages'] if m['role']=='user')=='想去青岛'

def test_recovery_code_is_one_time_and_revokes_previous_sessions(client):
    first=signup(client);old_cookie=client.cookies.get(auth.COOKIE)
    response=client.post('/api/auth/recover',json={'username':'alice','recovery_code':first['recovery_code'],'new_password':PASSWORD+'new'})
    assert response.status_code==200;new=response.json()
    assert new['recovery_code']!=first['recovery_code']
    assert client.post('/api/auth/recover',json={'username':'alice','recovery_code':first['recovery_code'],'new_password':PASSWORD}).status_code==400
    assert client.get('/api/auth/me',headers={'Cookie':auth.COOKIE+'='+old_cookie}).status_code==401

def test_logout_invalidates_cookie(client):
    signup(client);token=client.cookies.get(auth.COOKIE)
    assert client.post('/api/auth/logout',json={}).status_code==200
    assert client.get('/api/auth/me',headers={'Cookie':auth.COOKIE+'='+token}).status_code==401

def test_feedback_and_personal_export_do_not_include_credentials(client):
    signup(client);create(client)
    assert client.post('/api/feedback',json={'category':'product','content':'希望住宿能比较全部景点'}).status_code==201
    data=client.get('/api/account/export').json()
    assert len(data['workspaces'])==1 and len(data['feedback'])==1
    assert 'password_hash' not in str(data) and 'recovery_hash' not in str(data) and 'csrf' not in str(data)
    signup(client,'bob');assert not client.get('/api/feedback').json()['items']

def test_account_deletion_requires_password_and_removes_owned_data(client):
    first=signup(client);w=create(client)
    assert client.request('DELETE','/api/account',json={'password':'wrong'}).status_code==400
    assert client.request('DELETE','/api/account',json={'password':PASSWORD}).status_code==200
    assert auth.user_by_name('alice') is None and storage.get(w['id']) is None
    assert client.get('/api/auth/me').status_code==401

def test_unowned_legacy_records_are_preserved_but_not_public(client):
    legacy=storage.new_workspace();signup(client)
    assert client.get('/api/workspaces/'+legacy['id']).status_code==404
    assert client.get('/api/workspaces').json()['total']==0
    assert storage.get(legacy['id']) is not None

def test_restart_marks_unfinished_job_interrupted_and_keeps_saved_conversation(client,monkeypatch):
    from app import guidance
    user=signup(client);w=create(client);w['messages']=[{'role':'user','content':'下次继续我的旅行'}];w['ui']=guidance.describe(w,'search_hotels',status='loading');storage.save(w)
    jid=uuid.uuid4().hex
    with storage.connect() as c:c.execute('INSERT INTO jobs(id,owner_id,workspace_id,request_id,status,progress,created,updated,action) VALUES(?,?,?,?,?,?,?,?,?)',(jid,user['user']['id'],w['id'],str(uuid.uuid4()),'running','正在整理',storage.now(),storage.now(),'chat'))
    storage.interrupt_jobs();j=client.get('/api/jobs/'+jid).json()
    assert j['status']=='interrupted' and j['action']=='chat'
    assert j['workspace']['messages'][0]['content']=='下次继续我的旅行'
    assert j['workspace']['ui']['status']=='interrupted'

def test_card_selection_updates_feedback_without_appending_chat(client):
 signup(client);w=create(client);w['catalog']={i:{'id':i,'kind':'spot','name':i} for i in ('s1','s2')};storage.save(w)
 j=wait(client,submit(client,w,'select',{'id':'s1'}).json()['job_id']);w=j['workspace']
 assert len(w['messages'])==1 and w['messages'][0]['type']=='welcome' and w['feedback']['text']=='已选1个景点'
 j=wait(client,submit(client,w,'select',{'id':'s2'}).json()['job_id']);w=j['workspace']
 assert len(w['messages'])==1 and w['messages'][0]['type']=='welcome' and w['feedback']['text']=='已选2个景点'

def test_streamed_reply_is_available_before_task_finishes_and_events_are_owner_only(client,monkeypatch):
 from app import replies
 signup(client);w=create(client)
 async def streamed(w,text,progress):
  replies.emit('已收到。');await asyncio.sleep(.2);replies.emit('查询结果');await asyncio.sleep(.2);return '已收到。查询结果'
 monkeypatch.setattr(main,'run_chat',streamed)
 ack=client.post('/api/workspaces/'+w['id']+'/actions',json={'revision':0,'action':'chat','text':'流式测试','request_id':str(uuid.uuid4())}).json();jid=ack['job_id']
 for _ in range(25):
  j=client.get('/api/jobs/'+jid).json()
  if j['ui'].get('reply_text'):break
  time.sleep(.01)
 assert j['status']=='running' and j['ui']['reply_text']=='已收到。'
 done=wait(client,jid);assert done['workspace']['messages'][-1]['content']=='已收到。查询结果'
 response=client.get('/api/jobs/'+jid+'/events');assert response.headers['content-type'].startswith('text/event-stream')
 assert 'event: delta' in response.text and 'event: done' in response.text
 signup(client,'stream_other');assert client.get('/api/jobs/'+jid+'/events').status_code==404


def test_manual_ticket_query_only_updates_workbench(client,monkeypatch):
 from app import agent
 signup(client);w=create(client);stored=storage.get(w['id']);stored['requirements']={'city':'杭州','origin':'郑州','start_date':'2026-10-10','days':3,'adults':1};storage.save(stored)
 async def provider(*args):return {'data':{'data':[]},'source':{}}
 monkeypatch.setattr(agent,'tuniu',provider)
 response=submit(client,stored,'train',{'time_start':'11:00','time_end':'14:00','train_type':'highspeed'})
 result=wait(client,response.json()['job_id'])
 assert result['status']=='completed' and len(result['workspace']['messages'])==1 and result['workspace']['messages'][0]['type']=='welcome'
 assert result['ui']['controls']['time_start']=='11:00'


def test_final_transport_selection_has_one_needed_message_and_dining_target(client):
 signup(client);w=create(client);stored=storage.get(w['id']);stored.update(requirements={'city':'杭州','origin':'郑州','start_date':'2026-10-10','days':3,'adults':1},selected_spots=['s'],spots_confirmed=True,stay_skipped=True,selected_transport={'id':'g','name':'G1','kind':'train','selection_status':'confirmed','arrival':'2026-10-10 12:00'})
 stored['catalog']={'s':{'id':'s','kind':'spot','name':'西湖'},'b':{'id':'b','name':'G2','kind':'train','direction':'return','departure':'2026-10-13 18:00','arrival':'2026-10-13 22:00','seats':99}};storage.save(stored)
 result=wait(client,submit(client,stored,'select',{'id':'b'}).json()['job_id']);assert result['ui']['suggested_view']=='food'
 assert '往返班次已确认' in result['workspace']['messages'][-1]['content']
 assert any('时间安排提醒' in m['content'] for m in result['workspace']['messages'])
 result2=wait(client,submit(client,result['workspace'],'select',{'id':'b'}).json()['job_id'])
 assert len(result2['workspace']['messages'])==len(result['workspace']['messages'])

def test_map_image_requires_owner_and_uses_provider_coordinates(client,monkeypatch):
 from app import maps
 assert client.get('/api/workspaces/unknown/map-image').status_code==401
 signup(client);w=create(client);w['catalog']={'s':{'id':'s','name':'西湖','location':'120.14,30.25'}};w['selected_spots']=['s'];storage.save(w);seen=[]
 async def image(points,ordered):seen.extend(points);return b'png-test','image/png'
 monkeypatch.setattr(maps,'image',image)
 r=client.get('/api/workspaces/'+w['id']+'/map-image?focus=s')
 assert r.status_code==200 and r.content==b'png-test' and seen[0]['location']=='120.14,30.25'
 signup(client,'map_other');assert client.get('/api/workspaces/'+w['id']+'/map-image?focus=s').status_code==404

def test_national_basemap_is_owner_only_and_privately_cached(client,monkeypatch):
 from app import maps
 signup(client);w=create(client);seen=[]
 async def image(points,**args):seen.append(args);return b'base-map','image/png'
 monkeypatch.setattr(maps,'image',image)
 path='/api/workspaces/'+w['id']+'/map-image'
 r=client.get(path+'?base=true&zoom=3&lng=104.1954&lat=35.8617')
 assert r.status_code==200 and r.headers['cache-control'].startswith('private') and r.headers['vary']=='Cookie'
 assert seen[-1]['overlays'] is False and seen[-1]['center']==(104.1954,35.8617)
 assert client.get(path+'?base=true&lng=104').status_code==422
 signup(client,'national_other');assert client.get(path+'?base=true&zoom=3').status_code==404


def test_place_detail_is_quiet_and_keeps_current_map(client,monkeypatch):
    from app import agent
    signup(client);w=create(client)
    w['requirements'].update(city='成都',start_date='2026-10-20',days=3,adults=1)
    w['catalog']['amap:B1']={'id':'amap:B1','kind':'food','name':'午餐店'}
    storage.save(w)
    async def tool(name,args):return {'items':[{'id':'amap:B1','kind':'food','cost':'60','telephone':'123','source':{'name':'高德地图'}}]}
    async def model(*args,**kwargs):pytest.fail('Manual detail must not compose a model reply')
    monkeypatch.setattr(agent,'local_tool',tool);monkeypatch.setattr(main.replies,'compose',model)
    j=wait(client,submit(client,w,'place_detail',{'id':'amap:B1','view':'map'}).json()['job_id'])
    assert j['status']=='completed' and j['ui']['view']=='map' and j['ui']['reply_text']==''
    assert j['workspace']['messages']==w['messages']
    assert j['workspace']['catalog']['amap:B1']['cost']=='60'


def test_failed_place_detail_is_quiet_and_retains_snapshot(client,monkeypatch):
    from app import agent
    from app.providers import DataError
    signup(client);w=create(client)
    w['catalog']['amap:B1']={'id':'amap:B1','kind':'food','name':'午餐店','cost':'60'}
    storage.save(w)
    async def tool(*args):raise DataError('高德连接失败或超时')
    monkeypatch.setattr(agent,'local_tool',tool)
    j=wait(client,submit(client,w,'place_detail',{'id':'amap:B1','view':'food'}).json()['job_id'])
    assert j['status']=='failed' and j['ui']['reply_text']=='' and j['workspace']['messages']==w['messages']
    p=j['workspace']['catalog']['amap:B1'];assert p['place_detail_status']=='query_failed' and p['cost']=='60'


def test_security_headers_keep_scripts_strict_while_allowing_map_photo_origin(client):
    """回归：图片源需放行高德照片域名（http），但脚本、基础URI、外域访问必须保持收紧。"""
    headers=client.get('/').headers
    csp=headers.get('Content-Security-Policy','')
    assert "img-src 'self' data: blob: https: http://store.is.autonavi.com" in csp
    assert "script-src 'self'" in csp and 'unsafe-inline' not in csp and 'unsafe-eval' not in csp
    assert "object-src 'none'" in csp and "frame-ancestors 'none'" in csp and "base-uri 'self'" in csp
    assert headers.get('X-Content-Type-Options')=='nosniff'
    assert TestClient(main.app,base_url='http://evil.example').get('/').status_code==400
