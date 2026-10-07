import json, sqlite3, uuid, hashlib, time
from datetime import datetime, timezone, timedelta
from .config import ROOT

RUNTIME = ROOT / 'data/runtime'
RUNTIME.mkdir(parents=True, exist_ok=True)
DB = RUNTIME / 'travel.db'
WELCOME='欢迎使用识途。\n\n**您想去哪里？目的地是否已经确定？**\n也可以先告诉我大致预算、出游时间和旅行偏好，我会帮您比较目的地，再逐步安排景点、住宿、交通与餐饮。'

def now():
    return datetime.now(timezone(timedelta(hours=8))).isoformat(timespec='seconds')

def connect():
    c = sqlite3.connect(DB, timeout=10)
    c.execute('PRAGMA journal_mode=WAL')
    c.execute('PRAGMA foreign_keys=ON')
    return c

def init():
    with connect() as c:
        c.execute('CREATE TABLE IF NOT EXISTS workspaces (id TEXT PRIMARY KEY, updated TEXT, payload TEXT)')
        columns={r[1] for r in c.execute('PRAGMA table_info(workspaces)')}
        for name,definition in [('owner_id','TEXT'),('title',"TEXT NOT NULL DEFAULT ''"),('archived','INTEGER NOT NULL DEFAULT 0')]:
            if name not in columns:c.execute(f'ALTER TABLE workspaces ADD COLUMN {name} {definition}')
        c.execute('CREATE INDEX IF NOT EXISTS workspace_owner ON workspaces(owner_id,archived,updated)')
        c.execute('CREATE TABLE IF NOT EXISTS versions (id TEXT, revision INTEGER, payload TEXT, PRIMARY KEY(id,revision))')
        c.execute('CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, expires REAL, payload TEXT)')
        c.execute('CREATE TABLE IF NOT EXISTS calls (provider TEXT, time REAL)')
        c.execute('CREATE TABLE IF NOT EXISTS users (id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL, nickname TEXT NOT NULL, password_hash TEXT NOT NULL, recovery_hash TEXT NOT NULL, created TEXT NOT NULL)')
        c.execute('CREATE TABLE IF NOT EXISTS sessions (token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE, csrf TEXT NOT NULL, expires REAL NOT NULL, created TEXT NOT NULL)')
        c.execute('CREATE TABLE IF NOT EXISTS auth_attempts (bucket TEXT NOT NULL,time REAL NOT NULL)')
        c.execute('CREATE INDEX IF NOT EXISTS auth_attempt_time ON auth_attempts(bucket,time)')
        c.execute('CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY,owner_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,request_id TEXT NOT NULL,status TEXT NOT NULL,progress TEXT NOT NULL,error TEXT,created TEXT NOT NULL,updated TEXT NOT NULL,UNIQUE(owner_id,request_id))')
        c.execute('CREATE INDEX IF NOT EXISTS job_workspace ON jobs(workspace_id,status)')
        if 'action' not in {r[1] for r in c.execute('PRAGMA table_info(jobs)')}:c.execute("ALTER TABLE jobs ADD COLUMN action TEXT NOT NULL DEFAULT ''")
        if 'ui' not in {r[1] for r in c.execute('PRAGMA table_info(jobs)')}:c.execute("ALTER TABLE jobs ADD COLUMN ui TEXT NOT NULL DEFAULT '{}'")
        c.execute('CREATE TABLE IF NOT EXISTS feedback (id TEXT PRIMARY KEY,owner_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,category TEXT NOT NULL,content TEXT NOT NULL,created TEXT NOT NULL,status TEXT NOT NULL)')
        c.execute('PRAGMA user_version=4')

def new_workspace(owner_id=None):
    w = dict(id=uuid.uuid4().hex, owner_id=owner_id, title='',archived=False, revision=0, updated=now(), requirements={}, candidates=[], selected_spots=[], hotel=None,
             weather=None, transport=None, tickets={}, plan=None, messages=[{'role':'assistant','content':WELCOME,'time':now(),'type':'welcome'}], trace=[], warnings=[], stage='需求',catalog={})
    save(w)
    return w

def default_title(w):
    r=w.get('requirements',{})
    if r.get('city'):return (r['city']+'旅行'+(' · '+r['start_date'] if r.get('start_date') else ''))[:80]
    user=next((m['content'] for m in w.get('messages',[]) if m['role']=='user'),'')
    return user.replace('\n',' ')[:30] or '新的旅行'

def save(w):
    w['updated']=now()
    with connect() as c:
        old=c.execute('SELECT title,owner_id,archived FROM workspaces WHERE id=?',(w['id'],)).fetchone()
        if old and old[1]!=w.get('owner_id'):raise ValueError('旅行所属账户不能通过保存改变')
        title=old[0] if old else ''
        w['title']=title or default_title(w);w['archived']=bool(old[2]) if old else bool(w.get('archived'))
        payload=json.dumps(w,ensure_ascii=False)
        c.execute('INSERT INTO workspaces(id,updated,payload,owner_id,title,archived) VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET updated=excluded.updated,payload=excluded.payload',
                  (w['id'],w['updated'],payload,w.get('owner_id'),title,int(w['archived'])))
        c.execute('INSERT OR REPLACE INTO versions VALUES(?,?,?)',(w['id'],w['revision'],payload))

def get(wid,owner_id=None):
    with connect() as c:
        r=c.execute('SELECT payload,owner_id,title,archived FROM workspaces WHERE id=?'+(' AND owner_id=?' if owner_id is not None else ''),
                    (wid,owner_id) if owner_id is not None else (wid,)).fetchone()
    if not r:return None
    w=json.loads(r[0]);w.update(owner_id=r[1],title=r[2] or default_title(w),archived=bool(r[3]));return w

def latest(owner_id=None):
    with connect() as c:
        r=c.execute('SELECT id FROM workspaces WHERE archived=0'+(' AND owner_id=?' if owner_id is not None else '')+' ORDER BY updated DESC LIMIT 1',
                    (owner_id,) if owner_id is not None else ()).fetchone()
    return get(r[0],owner_id) if r else new_workspace(owner_id)

def list_workspaces(owner_id,q='',archived=False,offset=0,limit=30):
    with connect() as c:
        rows=c.execute('SELECT id FROM workspaces WHERE owner_id=? AND archived=? ORDER BY updated DESC',(owner_id,int(archived))).fetchall()
    items=[]
    for row in rows:
        w=get(row[0],owner_id);r=w['requirements']
        if q and q.casefold() not in (w['title']+' '+r.get('city','')).casefold():continue
        j=active_job(w['id'])
        items.append(dict(id=w['id'],title=w['title'],updated=w['updated'],archived=w['archived'],city=r.get('city'),date=r.get('start_date'),days=r.get('days'),
                          messages=len(w['messages']),has_plan=bool(w['plan']),stale=bool((w['plan'] or {}).get('stale')),running=bool(j)))
    return {'items':items[offset:offset+limit],'total':len(items),'offset':offset,'limit':limit}

def previous(w):
    with connect() as c:
        r=c.execute('SELECT payload FROM versions WHERE id=? AND revision<? ORDER BY revision DESC LIMIT 1',(w['id'],w['revision'])).fetchone()
    if not r:raise ValueError('没有可撤销的版本')
    old=json.loads(r[0]);old.update(revision=w['revision']+1,owner_id=w.get('owner_id'),title=w['title'],archived=w.get('archived',False))
    return old

def metadata(w,title=None,archived=None):
    with connect() as c:
        if title is not None:c.execute('UPDATE workspaces SET title=? WHERE id=? AND owner_id=?',(title,w['id'],w['owner_id']))
        if archived is not None:c.execute('UPDATE workspaces SET archived=? WHERE id=? AND owner_id=?',(int(archived),w['id'],w['owner_id']))
    w=get(w['id'],w['owner_id']);w['revision']+=1;save(w);return w

def delete_workspace(wid,owner_id):
    with connect() as c:
        if not c.execute('SELECT 1 FROM workspaces WHERE id=? AND owner_id=?',(wid,owner_id)).fetchone():return False
        c.execute('DELETE FROM versions WHERE id=?',(wid,));c.execute('DELETE FROM workspaces WHERE id=?',(wid,));return True

def active_job(wid):
    with connect() as c:
        r=c.execute("SELECT id,progress,action,ui FROM jobs WHERE workspace_id=? AND status='running' ORDER BY created DESC LIMIT 1",(wid,)).fetchone()
    return {'id':r[0],'progress':r[1],'action':r[2],'ui':json.loads(r[3])} if r else None

def update_job(jid,**patch):
    fields={k:json.dumps(v,ensure_ascii=False) if k=='ui' else v for k,v in patch.items() if k in {'status','progress','error','ui'}};fields['updated']=now()
    with connect() as c:c.execute('UPDATE jobs SET '+','.join(k+'=?' for k in fields)+' WHERE id=?',(*fields.values(),jid))

def job(jid,owner_id):
    with connect() as c:
        c.row_factory=sqlite3.Row;r=c.execute('SELECT * FROM jobs WHERE id=? AND owner_id=?',(jid,owner_id)).fetchone()
    if not r:return None
    result=dict(r);result['ui']=json.loads(result['ui']);return result

def interrupt_jobs():
    with connect() as c:c.execute("UPDATE jobs SET status='interrupted',progress='任务已中断',error='服务重启使任务中断，已保存的对话和选择仍可继续。',updated=? WHERE status='running'",(now(),))

def cache_key(provider,args):return hashlib.sha256(json.dumps([provider,args],sort_keys=True,ensure_ascii=False).encode()).hexdigest()

def cached(key):
    with connect() as c:r=c.execute('SELECT payload,expires FROM cache WHERE key=?',(key,)).fetchone()
    return json.loads(r[0]) if r and r[1]>time.time() else None

def put_cache(key,value,ttl):
    with connect() as c:c.execute('INSERT OR REPLACE INTO cache VALUES(?,?,?)',(key,time.time()+ttl,json.dumps(value,ensure_ascii=False)))

init()
