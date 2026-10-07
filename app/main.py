import asyncio,json,sys,uuid,logging,sqlite3,hashlib,time
from contextlib import asynccontextmanager,AsyncExitStack
from urllib.parse import urlsplit
from fastapi import FastAPI,HTTPException,Depends,Request,Query
from fastapi.responses import FileResponse,Response,JSONResponse,StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel,Field
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
from . import tools,storage,auth,guidance,discovery
from .text import readable
from . import replies
from .config import ROOT,configured,setting
from .providers import DataError
from .data_settings import mcp_environment
from .agent import handle,run_chat

LOCKS={};TASKS={};CANCELLED=set();SHUTTING_DOWN=False
ORIGIN=setting('APP_PUBLIC_ORIGIN','http://127.0.0.1:8767').rstrip('/')
ORIGINS={ORIGIN}|({'http://localhost:8767'} if ORIGIN=='http://127.0.0.1:8767' else set())
HOSTS={urlsplit(o).netloc for o in ORIGINS}
PROJECT_ID=hashlib.sha256(str(ROOT.resolve()).casefold().encode()).hexdigest()[:16]
ASSET_VERSIONS={name:hashlib.sha256((ROOT/'frontend'/name).read_bytes()).hexdigest()[:12] for name in ('style.css','workspace.css','account.js','app.js','workbench.js','product.css','details.js','interactive-map.js','experience.js')}

@asynccontextmanager
async def lifespan(app):
    global SHUTTING_DOWN
    SHUTTING_DOWN=False;storage.interrupt_jobs()
    async with AsyncExitStack() as stack:
        params=StdioServerParameters(command=sys.executable,args=[str(ROOT/'app/mcp_server.py')],cwd=str(ROOT),env=mcp_environment())
        read,write=await stack.enter_async_context(stdio_client(params))
        session=await stack.enter_async_context(ClientSession(read,write))
        await session.initialize();tools.SESSION=session
        app.state.tool_names=[t.name for t in (await session.list_tools()).tools]
        yield
        SHUTTING_DOWN=True
        for t in list(TASKS.values()):t.cancel()
        if TASKS:await asyncio.gather(*list(TASKS.values()),return_exceptions=True)
        tools.SESSION=None
        from . import maps
        await maps.close()

app=FastAPI(title='识途',lifespan=lifespan,docs_url=None,redoc_url=None,openapi_url=None)
app.include_router(auth.router)
app.mount('/assets',StaticFiles(directory=ROOT/'frontend'),name='assets')

@app.middleware('http')
async def security(request:Request,call_next):
    if request.url.netloc not in HOSTS:return JSONResponse({'detail':'不允许的访问域名'},status_code=400)
    if request.method not in ('GET','HEAD','OPTIONS') and request.url.path.startswith('/api/'):
        if request.headers.get('origin') not in ORIGINS:return JSONResponse({'detail':'请求来源校验失败'},status_code=403)
        if 'application/json' not in request.headers.get('content-type',''):return JSONResponse({'detail':'请求必须使用JSON'},status_code=415)
        try:
            if int(request.headers.get('content-length','0'))>65536:return JSONResponse({'detail':'提交内容过大，请缩短后重试'},status_code=413)
        except ValueError:return JSONResponse({'detail':'请求长度无效'},status_code=400)
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Referrer-Policy']='strict-origin-when-cross-origin'
    response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob: https: http://store.is.autonavi.com; connect-src 'self'; base-uri 'self'; object-src 'none'; frame-ancestors 'none'; form-action 'self'"
    if request.url.path=='/' or request.url.path.startswith(('/api/','/assets/')):
        response.headers['Cache-Control']='no-store'
        if request.url.path.endswith('/map-image') and response.status_code==200:
            response.headers['Cache-Control']='private, max-age=300';response.headers['Vary']='Cookie'
    return response

@app.exception_handler(RequestValidationError)
async def validation_error(request,exc):
    return JSONResponse({'detail':'填写内容不符合要求，请检查长度、日期、密码或数字范围。'},status_code=422)

@app.get('/')
def home():
    html=(ROOT/'frontend/index.html').read_text(encoding='utf-8')
    for name,version in ASSET_VERSIONS.items():
        html=html.replace(f'/assets/{name}"',f'/assets/{name}?v={version}"')
    return Response(html,media_type='text/html')

@app.get('/api/healthz')
def health():
    with storage.connect() as c:c.execute('SELECT 1').fetchone()
    return {'status':'ok','service':'shitu','project_id':PROJECT_ID}

@app.get('/api/status')
def status(user=Depends(auth.current_user)):
    from .rag import corpus
    knowledge=corpus()
    return {'configured':configured(),'tools':getattr(app.state,'tool_names',[]),
            'knowledge_cities':sorted({p['city'] for p in knowledge['parents'].values()}),
            'knowledge_records':knowledge['records'],
            'knowledge_scope':'已收录的官方特色、历史背景及部分运营快照；出游日适用性需核实'}

def owned(wid,user):
    w=storage.get(wid,user['id'])
    if not w:raise HTTPException(404,'未找到这次旅行')
    return w

def present(w):
    from .choices import room_choices
    for p in w.get('catalog',{}).values():
        if p.get('kind')=='hotel' and p.get('detail') and not p.get('stale'):p['room_choices']=room_choices(p,w['requirements'])
    active=storage.active_job(w['id'])
    if not active and w.get('ui',{}).get('status')=='loading':guidance.finish(w,'interrupted')
    from .journey import next_step
    from .journey import selection_assessment,is_local
    from .schedule import build
    return {**w,'timeline':build(w),'active_job':active,'next_step':next_step(w),'selection_assessment':selection_assessment(w),'local_trip':is_local(w['requirements']),**({'spot_page':discovery.page_info(w),'spot_groups':discovery.groups(w)} if w.get('spot_search') else {})}

@app.get('/api/workspaces/{wid}/map-image')
async def workspace_map(wid:str,day:str='',focus:str='',zoom:int|None=Query(None,ge=1,le=17),lng:float|None=Query(None,ge=-180,le=180),lat:float|None=Query(None,ge=-85,le=85),base:bool=False,user=Depends(auth.current_user)):
    from . import maps
    w=owned(wid,user)
    if focus and focus not in w['catalog']:raise HTTPException(404,'未找到这个地点')
    if (lng is None)!=(lat is None):raise HTTPException(422,'地图中心需要同时提供经度和纬度。')
    try:
        image,mime=await maps.image(maps.points(w,day,focus),ordered=bool(day) and not focus,**({'zoom':zoom} if zoom is not None else {}),**({'center':(lng,lat)} if lng is not None else {}),**({'overlays':False} if base else {}))
        return Response(image,media_type=mime,headers={'Cache-Control':'private, max-age=300'})
    except DataError as e:raise HTTPException(422,str(e)) from None

@app.get('/api/workspaces/latest')
def latest(user=Depends(auth.current_user)):return present(storage.latest(user['id']))

@app.get('/api/workspaces')
def listing(q:str=Query(default='',max_length=80),archived:bool=False,offset:int=Query(default=0,ge=0),limit:int=Query(default=30,ge=1,le=100),user=Depends(auth.current_user)):
    return storage.list_workspaces(user['id'],q.strip(),archived,offset,limit)

@app.post('/api/workspaces',status_code=201)
def create(user=Depends(auth.current_user)):return present(storage.new_workspace(user['id']))

@app.get('/api/workspaces/{wid}')
def workspace(wid,user=Depends(auth.current_user)):return present(owned(wid,user))

class Metadata(BaseModel):
    title:str|None=Field(default=None,min_length=1,max_length=80)
    archived:bool|None=None
    revision:int=Field(ge=0)

@app.patch('/api/workspaces/{wid}')
def edit(wid,body:Metadata,user=Depends(auth.current_user)):
    w=owned(wid,user)
    if storage.active_job(wid):raise HTTPException(409,'这次旅行还有任务在执行，请完成或停止后再修改')
    if w['revision']!=body.revision:raise HTTPException(409,'旅行已更新，请刷新后重试')
    title=body.title.strip() if body.title is not None else None
    if title is not None and not title:raise HTTPException(400,'旅行名称不能为空')
    return present(storage.metadata(w,title,body.archived))

@app.delete('/api/workspaces/{wid}')
def delete(wid,user=Depends(auth.current_user)):
    owned(wid,user)
    if storage.active_job(wid):raise HTTPException(409,'请先停止这次旅行的任务，再删除')
    storage.delete_workspace(wid,user['id']);return {'ok':True}

class Action(BaseModel):
    revision:int=Field(ge=0)
    action:str=Field(max_length=40)
    text:str=Field(default='',max_length=3000)
    args:dict=Field(default_factory=dict)
    request_id:uuid.UUID

@app.post('/api/workspaces/{wid}/actions',status_code=202)
async def action(wid:str,body:Action,user=Depends(auth.current_user)):
    w=owned(wid,user)
    if w['archived']:raise HTTPException(409,'这次旅行已归档，请恢复后再继续规划')
    if body.action not in {'chat','requirements','discover_destinations','choose_destination','search_spots','spots_page','dismiss_spot','complete_spots','complete_hotel','skip_hotel','search_hotels','search_foods','meal_choice','complete_food','visit_schedule','select','select_room','hotel_detail','place_detail','weather','train','flight','ticket','plan','undo'}:
        raise HTTPException(400,'不支持的操作')
    if body.action=='chat' and not body.text.strip():raise HTTPException(400,'请先输入旅行想法')
    jid=uuid.uuid4().hex
    with storage.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        previous=c.execute('SELECT id,workspace_id FROM jobs WHERE owner_id=? AND request_id=?',(user['id'],str(body.request_id))).fetchone()
        if previous:
            if previous[1]!=wid:raise HTTPException(409,'请求编号已用于其他旅行')
            return {'job_id':previous[0]}
        if c.execute("SELECT 1 FROM jobs WHERE workspace_id=? AND status='running'",(wid,)).fetchone():raise HTTPException(409,'这次旅行正在处理，请等待或停止当前任务')
        if c.execute("SELECT COUNT(*) FROM jobs WHERE owner_id=? AND status='running'",(user['id'],)).fetchone()[0]>=2:raise HTTPException(429,'最多同时处理两次旅行，请稍后再试')
        if c.execute("SELECT COUNT(*) FROM jobs WHERE status='running'").fetchone()[0]>=4:raise HTTPException(503,'服务当前繁忙，请稍后再试')
        if w['revision']!=body.revision:raise HTTPException(409,'旅行已更新，请刷新后重试')
        if c.execute('SELECT COUNT(*) FROM jobs WHERE owner_id=? AND created>?',(user['id'],storage.now()[:10])).fetchone()[0]>=120:raise HTTPException(429,'今日处理次数较多，请明天再试')
        c.execute('INSERT INTO jobs(id,owner_id,workspace_id,request_id,status,progress,error,created,updated,action) VALUES(?,?,?,?,?,?,?,?,?,?)',(jid,user['id'],wid,str(body.request_id),'running','正在准备任务',None,storage.now(),storage.now(),body.action))
    def finished(t):
        TASKS.pop(jid,None)
        if t.cancelled():storage.update_job(jid,status='cancelled',progress='已停止')
    task=asyncio.create_task(perform(wid,body,jid,user['id']));TASKS[jid]=task;task.add_done_callback(finished)
    return {'job_id':jid}

async def perform(wid,body,jid,owner_id):
    async with LOCKS.setdefault(wid,asyncio.Lock()):
        w=storage.get(wid,owner_id)
        if not w or w['revision']!=body.revision:
            storage.update_job(jid,status='failed',error='旅行已被更新，请刷新后重试');return
        trace=[];reply_buffer=[];last_flush=0
        before_ready=all((w.get(k) or {}).get('selection_status')=='confirmed' for k in ('selected_transport','selected_return'))
        def emit(chunk):
            nonlocal last_flush
            reply_buffer.append(chunk)
            if time.monotonic()-last_flush>=.08:
                last_flush=time.monotonic();publish()
        def publish():
            ui={**w.get('ui',{}),'requirements':w['requirements'],'root_action':body.action,'reply_text':''.join(reply_buffer),'process_steps':[x['text'] for x in trace]}
            storage.update_job(jid,ui=ui)
        sink_token=replies.SINK.set(emit);prefix_token=replies.PREFIX.set('')
        trace=[];w['ui']=guidance.describe(w,body.action,body.args,status='loading')
        def progress(text):
            trace.append({'time':storage.now(),'text':text});storage.update_job(jid,progress=text);publish()
        progress(w['ui']['title'])
        error=None;status='completed';error_context=None
        if body.action=='chat':
            w['messages'].append({'role':'user','content':body.text.strip(),'time':storage.now()})
            w['revision']+=1;storage.save(w)
        try:
            async with asyncio.timeout(600):
                if body.action=='undo':w=storage.previous(w);answer='已恢复上一版选择和安排。'
                elif body.action=='chat':answer=await run_chat(w,body.text,progress)
                else:
                    w['turn_action']=body.action;w['turn_is_chat']=False;w['turn_weather_updated']=False;w['turn_food_updated']=False
                    if body.action=='requirements':
                        from .agent import update_requirements
                        update_requirements(w,body.args.get('patch',{}))
                    answer=await handle(w,body.action,body.args,progress)
                    if body.action=='requirements':
                        from .agent import ensure_weather
                        await ensure_weather(w,progress)
                    if body.action not in ('select','select_room','meal_choice','dismiss_spot','spots_page','requirements','undo','train','flight','weather','hotel_detail','place_detail','search_foods','ticket','search_hotels','search_spots'):
                        answer=await replies.compose(w,answer)
        except asyncio.CancelledError:
            status='interrupted' if SHUTTING_DOWN else 'cancelled'
            answer='任务已中断，已保存的对话和选择可以继续。' if SHUTTING_DOWN else '已停止本轮处理，当前选择已保留。'
        except DataError as e:error=str(e);answer=error;status='failed';error_context=e.context
        except ValueError as e:
            error='没有可撤销的版本' if body.action=='undo' else '本轮处理数据不完整，请检查条件后重试';answer=error;status='failed'
        except TimeoutError:error='本轮处理超时，已保存当前选择，请稍后重试。';answer=error;status='failed'
        except Exception as e:
            logging.getLogger(__name__).error('Action failed: %s',type(e).__name__)
            error='本轮处理出现异常，已有选择已保留，请重试。';answer=error;status='failed'
        finally:
            CANCELLED.discard(jid);replies.SINK.reset(sink_token);replies.PREFIX.reset(prefix_token)
        ui=guidance.finish(w,'ready' if status=='completed' else status,error)
        if error_context:ui['conflict']=error_context
        from .journey import next_step
        newly_ready=status=='completed' and not before_ready and all((w.get(k) or {}).get('selection_status')=='confirmed' for k in ('selected_transport','selected_return'))
        if newly_ready:ui['suggested_view']=next_step(w)['view']
        if status=='completed' and body.action in ('complete_hotel','skip_hotel') and next_step(w)['view']=='food':ui['suggested_view']='food'
        quiet=body.action=='place_detail' or status=='completed' and body.action in ('select','select_room','meal_choice','visit_schedule','dismiss_spot','spots_page','requirements','train','flight','weather','hotel_detail','place_detail','search_foods','ticket','search_hotels','search_spots')
        if quiet:
            w['feedback']={'id':jid,'text':f'已选{len(w["selected_spots"])}个景点' if body.action=='select' and w['catalog'].get(body.args.get('id'),{}).get('kind')=='spot' else '旅行信息已更新' if body.action=='requirements' else '选择已更新' if body.action in ('select','select_room') else '推荐列表已更新'}
            if body.action in ('select_room','meal_choice') or body.action=='select' and w['catalog'].get(body.args.get('id'),{}).get('kind')!='spot':w['feedback']['text']=readable(answer).split('\n')[0]
            if body.action in ('train','flight','weather','hotel_detail','place_detail','search_foods','ticket','search_hotels','search_spots'):w['feedback']['text']='查询结果已更新，请在右侧查看。'
            from .journey import selection_assessment
            assessment=selection_assessment(w);key=('dense' if assessment['count']>max(5,assessment['days']*3) else '')+('wide' if assessment['spread_km']>=50 else '')
            if assessment['level']=='warning' and key!=w.get('selection_warning_key'):
                w['messages'].append({'role':'assistant','content':'**行程安排提醒**\n'+ '\n'.join(assessment['messages']),'time':storage.now()});w['selection_warning_key']=key
            if assessment['level']=='normal':w['selection_warning_key']=''
        if quiet and newly_ready:w['messages'].append({'role':'assistant','content':'**往返班次已确认。**\n**下一步：**'+next_step(w)['message'],'time':storage.now()})
        elif not quiet:w['messages'].append({'role':'assistant','content':readable(answer),'time':storage.now(),'ui':ui,'process_steps':[x['text'] for x in trace]})
        if body.action!='undo':w['revision']+=1
        w['trace']=(w.get('trace',[])+trace)[-30:];storage.save(w)
        storage.update_job(jid,status=status,progress='已停止' if status=='cancelled' else '任务已中断' if status=='interrupted' else '完成',error=error,ui={**ui,'reply_text':'' if quiet else readable(answer),'process_steps':[x['text'] for x in trace]})

@app.get('/api/jobs/{jid}')
def job(jid,user=Depends(auth.current_user)):
    j=storage.job(jid,user['id'])
    if not j:raise HTTPException(404,'未找到这个任务')
    result={k:j[k] for k in ('id','workspace_id','status','progress','error','created','updated','action','ui')}
    if j['status']!='running':result['workspace']=present(owned(j['workspace_id'],user))
    return result

@app.get('/api/jobs/{jid}/events')
async def events(jid,request:Request,user=Depends(auth.current_user)):
    if not storage.job(jid,user['id']):raise HTTPException(404,'未找到这个任务')
    async def stream():
        sent='';last_ui='';heartbeat=time.monotonic()
        def event(kind,data):return 'event: '+kind+'\ndata: '+json.dumps(data,ensure_ascii=False)+'\n\n'
        while not await request.is_disconnected():
            j=storage.job(jid,user['id'])
            if not j:return
            ui=j.get('ui') or {};value=ui.get('reply_text','')
            if value!=sent:
                if value.startswith(sent):yield event('delta',{'text':value[len(sent):]})
                else:yield event('replace',{'text':value})
                sent=value
            signature=json.dumps({k:v for k,v in ui.items() if k!='reply_text'},ensure_ascii=False)
            if signature!=last_ui:yield event('progress',{'ui':ui,'progress':j['progress']});last_ui=signature
            if j['status']!='running':
                yield event('done',job(jid,user));return
            if time.monotonic()-heartbeat>10:yield ': keepalive\n\n';heartbeat=time.monotonic()
            await asyncio.sleep(.05)
    return StreamingResponse(stream(),media_type='text/event-stream',headers={'Cache-Control':'no-store','X-Accel-Buffering':'no'})

@app.post('/api/jobs/{jid}/cancel')
async def cancel(jid,user=Depends(auth.current_user)):
    j=storage.job(jid,user['id'])
    if not j:raise HTTPException(404,'未找到这个任务')
    if j['status']=='running':
        task=TASKS.get(jid)
        if task:CANCELLED.add(jid);task.cancel()
        else:storage.update_job(jid,status='interrupted',error='任务已中断，请重新发起')
    return {'ok':True}

@app.get('/api/workspaces/{wid}/export')
def export(wid,user=Depends(auth.current_user)):
    from .report import markdown
    w=owned(wid,user)
    if not w.get('plan'):raise HTTPException(400,'请先生成计划书')
    if w['plan'].get('stale'):raise HTTPException(409,'当前选择已变化，请重新生成计划书后再导出')
    return Response(markdown(w),media_type='text/markdown; charset=utf-8',headers={'Content-Disposition':'attachment; filename="travel-plan.md"'})

class Feedback(BaseModel):
    category:str=Field(default='product',max_length=20)
    content:str=Field(min_length=5,max_length=3000)

@app.post('/api/feedback',status_code=201)
def feedback(body:Feedback,user=Depends(auth.current_user)):
    if body.category not in {'product','data','bug','other'}:raise HTTPException(400,'请选择反馈类型')
    content=body.content.strip()
    if len(content)<5:raise HTTPException(400,'请补充至少5个字的反馈')
    with storage.connect() as c:
        if c.execute('SELECT COUNT(*) FROM feedback WHERE owner_id=? AND created>?',(user['id'],storage.now()[:10])).fetchone()[0]>=10:raise HTTPException(429,'今天反馈较多，请明天再提交')
        fid=uuid.uuid4().hex;c.execute('INSERT INTO feedback VALUES(?,?,?,?,?,?)',(fid,user['id'],body.category,content,storage.now(),'received'))
    return {'id':fid,'status':'received'}

@app.get('/api/feedback')
def feedback_list(user=Depends(auth.current_user)):
    with storage.connect() as c:
        c.row_factory=sqlite3.Row;rows=c.execute('SELECT id,category,content,created,status FROM feedback WHERE owner_id=? ORDER BY created DESC LIMIT 30',(user['id'],)).fetchall()
    return {'items':[dict(r) for r in rows]}

@app.get('/api/account/export')
def account_export(user=Depends(auth.current_user)):
    with storage.connect() as c:ids=[r[0] for r in c.execute('SELECT id FROM workspaces WHERE owner_id=?',(user['id'],))]
    data={'user':auth.public_user(user),'exported_at':storage.now(),'workspaces':[storage.get(wid,user['id']) for wid in ids],'feedback':feedback_list(user)['items']}
    return Response(json.dumps(data,ensure_ascii=False,indent=2),media_type='application/json',headers={'Content-Disposition':'attachment; filename="shitu-account-data.json"'})

@app.delete('/api/account')
def delete_account(body:auth.Confirmation,request:Request,user=Depends(auth.current_user)):
    auth.throttle(request,user['username'])
    if not auth.verify_password(body.password,user['password_hash']):raise HTTPException(400,'密码不正确')
    with storage.connect() as c:
        if c.execute("SELECT 1 FROM jobs WHERE owner_id=? AND status='running'",(user['id'],)).fetchone():raise HTTPException(409,'请先停止所有旅行任务，再注销账户')
        ids=[r[0] for r in c.execute('SELECT id FROM workspaces WHERE owner_id=?',(user['id'],))]
        for wid in ids:c.execute('DELETE FROM versions WHERE id=?',(wid,))
        c.execute('DELETE FROM workspaces WHERE owner_id=?',(user['id'],));c.execute('DELETE FROM users WHERE id=?',(user['id'],))
    response=JSONResponse({'ok':True});response.delete_cookie(auth.COOKIE,path='/');return response
