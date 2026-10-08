import json, logging, sqlite3, threading, uuid, hashlib, time
from datetime import datetime, timezone, timedelta
from .config import ROOT

RUNTIME = ROOT / 'data/runtime'
RUNTIME.mkdir(parents=True, exist_ok=True)
DB = RUNTIME / 'travel.db'
WELCOME='欢迎使用识途。\n\n**您想去哪里？目的地是否已经确定？**\n也可以先告诉我大致预算、出游时间和旅行偏好，我会帮您比较目的地，再逐步安排景点、住宿、交通与餐饮。'

def now():
    return datetime.now(timezone(timedelta(hours=8))).isoformat(timespec='seconds')

LOCAL = threading.local()

def connect():
    """One connection per thread, reused rather than left to the garbage collector.

    ``with sqlite3.connect(...)`` commits and rolls back but never closes, so the old
    one-line version leaked a connection on every call. CPython closed them at random
    moments, and on Windows that final close truncates the -wal file -- if another
    thread is writing at that instant SQLite reports "attempt to write a readonly
    database" instead of "database is locked".

    Closing per call would be equally wrong: it deletes -wal/-shm every time, and
    recreating those files on Windows costs ~89 ms versus 2.6 ms for a reused
    connection, which alone doubled the test suite's runtime.

    A thread-local connection keeps check_same_thread satisfied and still returns the
    raw Connection, so every existing ``with connect() as c:`` keeps its exact
    commit-on-success / rollback-on-error semantics.
    """
    key = str(DB)
    c = getattr(LOCAL, 'c', None)
    if c is not None and getattr(LOCAL, 'key', None) != key:
        # Tests swap storage.DB per case; never hand out another database's connection.
        try: c.close()
        except sqlite3.Error: pass
        c = None
    elif c is not None:
        try: c.execute('PRAGMA foreign_keys=ON')
        except sqlite3.Error:
            try: c.close()
            except sqlite3.Error: pass
            c = None
    if c is None:
        c = sqlite3.connect(DB, timeout=10)
        c.execute('PRAGMA journal_mode=WAL')
        c.execute('PRAGMA foreign_keys=ON')
        LOCAL.c, LOCAL.key = c, key
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
        c.execute('CREATE TABLE IF NOT EXISTS llm_calls (id INTEGER PRIMARY KEY AUTOINCREMENT,time REAL NOT NULL,label TEXT NOT NULL DEFAULT \'\',model TEXT NOT NULL DEFAULT \'\',prompt_tokens INTEGER NOT NULL DEFAULT 0,completion_tokens INTEGER NOT NULL DEFAULT 0,total_tokens INTEGER NOT NULL DEFAULT 0,elapsed_ms INTEGER NOT NULL DEFAULT 0,ok INTEGER NOT NULL DEFAULT 1,error TEXT)')
        c.execute('CREATE INDEX IF NOT EXISTS llm_calls_time ON llm_calls(time)')
        c.execute('CREATE INDEX IF NOT EXISTS llm_calls_label ON llm_calls(label,time)')
        c.execute('PRAGMA user_version=5')

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

def record_llm_call(label,model,usage,elapsed_ms,ok=True,error=None,limit=5000):
    """Observability only: never let a logging failure break the user request."""
    usage=usage if isinstance(usage,dict) else {}
    try:
        with connect() as c:
            c.execute('INSERT INTO llm_calls(time,label,model,prompt_tokens,completion_tokens,total_tokens,elapsed_ms,ok,error) VALUES(?,?,?,?,?,?,?,?,?)',
                      (time.time(),(label or '')[:40],(model or '')[:60],int(usage.get('prompt_tokens') or 0),
                       int(usage.get('completion_tokens') or 0),int(usage.get('total_tokens') or 0),
                       int(elapsed_ms),1 if ok else 0,(error or None) and str(error)[:200]))
            if c.execute('SELECT COUNT(*) FROM llm_calls').fetchone()[0]>limit:
                c.execute('DELETE FROM llm_calls WHERE id NOT IN (SELECT id FROM llm_calls ORDER BY id DESC LIMIT ?)',(limit,))
    except Exception as e:
        logging.getLogger(__name__).warning('llm call log skipped: %s',type(e).__name__)

def usage_summary(days=0):
    """Aggregate token/latency/call counts. days=0 means all time."""
    since=time.time()-days*86400 if days else 0
    with connect() as c:
        c.row_factory=sqlite3.Row
        rows=c.execute('SELECT label,COUNT(*) calls,SUM(total_tokens) tokens,SUM(prompt_tokens) prompt_tokens,'
                       'SUM(completion_tokens) completion_tokens,CAST(AVG(elapsed_ms) AS INTEGER) avg_ms,'
                       'MAX(elapsed_ms) max_ms,SUM(CASE WHEN ok=0 THEN 1 ELSE 0 END) failed '
                       'FROM llm_calls WHERE time>=? GROUP BY label ORDER BY tokens DESC',(since,)).fetchall()
    by_label=[dict(r) for r in rows]
    return {'llm_calls':sum(x['calls'] for x in by_label),'total_tokens':sum(x['tokens'] or 0 for x in by_label),
            'prompt_tokens':sum(x['prompt_tokens'] or 0 for x in by_label),
            'completion_tokens':sum(x['completion_tokens'] or 0 for x in by_label),
            'failed':sum(x['failed'] or 0 for x in by_label),'by_label':by_label,'days':days}

init()
