"""Contract fixtures and semantic tests for app/contracts.py (batch 1).

The SQLite implementations here are reference fixtures, not the production
repositories: they pin down the semantics (conflict rejection, idempotent
submit, mutually exclusive claim, lease recovery, stage reuse) that the MySQL
implementation in a later batch must reproduce to keep these tests green.
"""
import json,sqlite3,time
import pytest
from app import contracts as C
from app.contracts import (RevisionConflict,RequestConflict,LeaseLost,JobNotClaimable,
                           FinalAfterCancel,ContractError,resolve_date)


class SqliteWorkspaces:
    def __init__(self,path):
        self.c=sqlite3.connect(path)
        self.c.execute('CREATE TABLE workspaces(id TEXT PRIMARY KEY,owner_id TEXT,payload TEXT,revision INTEGER)')
        self.c.execute('CREATE TABLE versions(id TEXT,revision INTEGER,payload TEXT,PRIMARY KEY(id,revision))')
        self.c.commit()
    def get(self,wid,owner_id):
        row=self.c.execute('SELECT payload,owner_id,revision FROM workspaces WHERE id=?',(wid,)).fetchone()
        if not row or (owner_id is not None and row[1]!=owner_id):return None
        w=json.loads(row[0]);w['owner_id']=row[1];w['revision']=row[2];return w
    def save(self,workspace,expected_revision):
        row=self.c.execute('SELECT revision FROM workspaces WHERE id=?',(workspace['id'],)).fetchone()
        if (row[0] if row else 0)!=expected_revision:raise RevisionConflict('旅行已更新，请刷新后重试')
        new=expected_revision+1;payload=json.dumps(workspace,ensure_ascii=False)
        self.c.execute('INSERT OR REPLACE INTO workspaces VALUES(?,?,?,?)',(workspace['id'],workspace.get('owner_id'),payload,new))
        self.c.execute('INSERT OR REPLACE INTO versions VALUES(?,?,?)',(workspace['id'],new,payload));self.c.commit()
        return new
    def previous(self,wid,owner_id,before_revision):
        row=self.c.execute('SELECT payload,revision FROM versions WHERE id=? AND revision<? ORDER BY revision DESC LIMIT 1',(wid,before_revision)).fetchone()
        if not row:raise ContractError('没有可撤销的版本')
        w=json.loads(row[0]);w['revision']=row[1];return w

class SqliteCache:
    def __init__(self,path):
        self.c=sqlite3.connect(path)
        self.c.execute('CREATE TABLE cache(provider TEXT,key TEXT,payload TEXT,expires REAL,PRIMARY KEY(provider,key))');self.c.commit()
    def get(self,provider,key):
        row=self.c.execute('SELECT payload,expires FROM cache WHERE provider=? AND key=?',(provider,key)).fetchone()
        return json.loads(row[0]) if row and row[1]>time.time() else None
    def put(self,provider,key,payload,ttl_seconds):
        self.c.execute('INSERT OR REPLACE INTO cache VALUES(?,?,?,?)',(provider,key,json.dumps(payload,ensure_ascii=False),time.time()+ttl_seconds));self.c.commit()

class SqliteBudget:
    def __init__(self,path):
        self.c=sqlite3.connect(path)
        self.c.execute('CREATE TABLE calls(provider TEXT,time REAL)');self.c.commit()
    def record_and_check(self,provider,limit,window_seconds):
        floor=time.time()-window_seconds
        allowed=self.c.execute('SELECT COUNT(*) FROM calls WHERE provider=? AND time>?',(provider,floor)).fetchone()[0]<limit
        if allowed:self.c.execute('INSERT INTO calls VALUES(?,?)',(provider,time.time()));self.c.commit()
        return allowed

class SqliteJobs:
    def __init__(self,path):
        self.c=sqlite3.connect(path)
        self.c.execute('CREATE TABLE jobs(id TEXT PRIMARY KEY,owner_id TEXT,workspace_id TEXT,request_id TEXT,action TEXT,status TEXT,progress TEXT,ui TEXT,worker_id TEXT,lease REAL,created REAL,error TEXT)')
        self.c.execute('CREATE UNIQUE INDEX job_request ON jobs(owner_id,request_id)')
        self.c.execute('CREATE TABLE stages(job_id TEXT,key TEXT,payload TEXT,PRIMARY KEY(job_id,key))');self.c.commit()
    def submit(self,job_id,owner_id,workspace_id,request_id,action):
        row=self.c.execute('SELECT id,workspace_id FROM jobs WHERE owner_id=? AND request_id=?',(owner_id,request_id)).fetchone()
        if row:
            if row[1]!=workspace_id:raise RequestConflict('请求编号已用于其他旅行')
            return row[0]
        self.c.execute('INSERT INTO jobs(id,owner_id,workspace_id,request_id,action,status,progress,created) VALUES(?,?,?,?,?,?,?,?)',
                       (job_id,owner_id,workspace_id,request_id,action,C.QUEUED,'',time.time()))
        self.c.commit();return job_id
    def _claimable(self):return "status='queued' OR (status='running' AND (lease IS NULL OR lease<?))"
    def claim(self,worker_id,lease_seconds):
        row=self.c.execute('SELECT id FROM jobs WHERE '+self._claimable()+' ORDER BY created LIMIT 1',(time.time(),)).fetchone()
        if not row:return None
        cur=self.c.execute("UPDATE jobs SET status='running',worker_id=?,lease=?,error=NULL WHERE id=? AND "+self._claimable(),
                           (worker_id,time.time()+lease_seconds,row[0],time.time()))
        self.c.commit()
        return self.get_job(row[0]) if cur.rowcount==1 else None
    def get_job(self,jid):
        row=self.c.execute('SELECT id,owner_id,workspace_id,request_id,action,status,progress,worker_id FROM jobs WHERE id=?',(jid,)).fetchone()
        if not row:return None
        return dict(zip(('id','owner_id','workspace_id','request_id','action','status','progress','worker_id'),row))
    def renew(self,job_id,worker_id,lease_seconds):
        cur=self.c.execute("UPDATE jobs SET lease=? WHERE id=? AND worker_id=? AND status='running'",(time.time()+lease_seconds,job_id,worker_id))
        self.c.commit()
        if cur.rowcount!=1:raise LeaseLost('任务已由其他执行器接管')
    def progress(self,job_id,text,ui=None):
        self.c.execute('UPDATE jobs SET progress=?,ui=? WHERE id=?',(text,json.dumps(ui,ensure_ascii=False) if ui is not None else None,job_id));self.c.commit()
    def stage(self,job_id,key,payload=None):
        if payload is None:
            row=self.c.execute('SELECT payload FROM stages WHERE job_id=? AND key=?',(job_id,key)).fetchone()
            return json.loads(row[0]) if row else None
        self.c.execute('INSERT OR REPLACE INTO stages VALUES(?,?,?)',(job_id,key,json.dumps(payload,ensure_ascii=False)));self.c.commit()
    def finish(self,job_id,worker_id,status,error=None):
        if status not in C.TERMINAL_STATES:raise ContractError('非法的结束状态')
        row=self.c.execute('SELECT status,worker_id FROM jobs WHERE id=?',(job_id,)).fetchone()
        if not row or row[0]==C.CANCELLED:raise FinalAfterCancel('已停止的任务不能再提交最终计划')
        if row[0]!=C.RUNNING or row[1]!=worker_id:raise LeaseLost('任务已由其他执行器接管')
        self.c.execute('UPDATE jobs SET status=?,error=?,lease=NULL WHERE id=?',(status,error,job_id));self.c.commit()
    def cancel(self,job_id,owner_id):
        cur=self.c.execute("UPDATE jobs SET status='cancelled' WHERE id=? AND owner_id=? AND status IN ('queued','running')",(job_id,owner_id))
        self.c.commit();return cur.rowcount==1

class FixtureJobContext:
    job_id=''
    def __init__(self,jobs):self.jobs=jobs
    def is_cancelled(self):
        job=self.jobs.get_job(self.job_id);return bool(job and job['status']==C.CANCELLED)
    def emit_progress(self,text):self.jobs.progress(self.job_id,text)
    def load_stage(self,key):return self.jobs.stage(self.job_id,key)
    def save_stage(self,key,payload):self.jobs.stage(self.job_id,key,payload)


@pytest.fixture
def stores(tmp_path):
    db=str(tmp_path/'contract.db')
    return {'workspaces':SqliteWorkspaces(db),'cache':SqliteCache(db),'budget':SqliteBudget(db),
            'jobs':SqliteJobs(db),'context':None}

def test_workspace_is_owner_scoped_and_rejects_stale_revision(stores):
    w={'id':'w1','owner_id':'alice','city':'青岛'}
    assert stores['workspaces'].save(w,0)==1
    assert stores['workspaces'].get('w1','alice')['city']=='青岛'
    assert stores['workspaces'].get('w1','bob') is None          # 跨账户读不到
    w['city']='杭州'
    with pytest.raises(RevisionConflict):                         # 旧 revision 不能静默覆盖
        stores['workspaces'].save(w,0)
    assert stores['workspaces'].get('w1','alice')['city']=='青岛'  # 新选择仍在
    assert stores['workspaces'].save(w,1)==2                      # 带对新 revision 才能保存
    old=stores['workspaces'].previous('w1','alice',2)             # 快照可撤销
    assert old['city']=='青岛' and old['revision']==1

def test_cache_roundtrip_and_expiry(stores):
    stores['cache'].put('amap','k1',{'items':[1,2]},ttl_seconds=60)
    assert stores['cache'].get('amap','k1')=={'items':[1,2]}
    stores['cache'].put('amap','k2',{},ttl_seconds=-1)
    assert stores['cache'].get('amap','k2') is None               # 过期即失效

def test_provider_budget_is_atomic_under_limit(stores):
    assert stores['budget'].record_and_check('amap',limit=2,window_seconds=60) is True
    assert stores['budget'].record_and_check('amap',limit=2,window_seconds=60) is True
    assert stores['budget'].record_and_check('amap',limit=2,window_seconds=60) is False

def test_job_submit_is_idempotent_and_request_scoped(stores):
    first=stores['jobs'].submit('j1','alice','w1','req-1','chat')
    assert stores['jobs'].submit('j2','alice','w1','req-1','chat')==first   # 同请求返回原任务
    with pytest.raises(RequestConflict):
        stores['jobs'].submit('j3','alice','w2','req-1','chat')             # 同请求换旅行=冲突
    assert stores['jobs'].get_job(first)['status']==C.QUEUED                # 新任务先排队

def test_job_claim_is_exclusive_and_lease_recovers_crashes(stores):
    jobs=stores['jobs'];jobs.submit('j1','alice','w1','req-1','plan')
    assert jobs.claim('worker-a',lease_seconds=60)['id']=='j1'
    assert jobs.claim('worker-b',lease_seconds=60) is None                  # 互斥：第二个领不到
    with pytest.raises(LeaseLost):jobs.renew('j1','worker-b',60)            # 他人不能续租
    jobs.renew('j1','worker-a',60)
    with pytest.raises(LeaseLost):                                          # 非持有者不能收尾
        jobs.finish('j1','worker-b',C.COMPLETED)
    # 模拟 worker-a 崩溃：租约过期后 worker-b 可以接管
    jobs.c.execute("UPDATE jobs SET lease=? WHERE id='j1'",(time.time()-1,));jobs.c.commit()
    assert jobs.claim('worker-b',lease_seconds=60)['worker_id']=='worker-b'

def test_cancelled_job_keeps_choices_and_blocks_final_plan(stores):
    jobs=stores['jobs'];jobs.submit('j1','alice','w1','req-1','plan');jobs.claim('worker-a',60)
    ctx=FixtureJobContext(jobs);ctx.job_id='j1'
    ctx.save_stage('provider_query',{'trains':['G1']})                       # 阶段结果可复用
    assert ctx.load_stage('provider_query')=={'trains':['G1']}
    ctx.emit_progress('正在整理路线')
    assert jobs.cancel('j1','alice') is True and ctx.is_cancelled() is True
    with pytest.raises(FinalAfterCancel):
        jobs.finish('j1','worker-a',C.COMPLETED)                             # 取消后不能再出最终计划
    assert jobs.get_job('j1')['status']==C.CANCELLED

def test_resolve_date_precedence_keeps_suggestions_unconfirmed():
    user=C.resolve_date('return_date','2026-10-15',None,'2026-10-14')
    assert user['value']=='2026-10-15' and user['confirmed'] is True         # 用户明确输入最高
    fact=C.resolve_date('outbound_date',None,'2026-10-12 08:00',None)
    assert fact['source']==C.SOURCE_SHIFT and fact['confirmed'] is True      # 班次事实视为确定
    hint=C.resolve_date('return_date',None,None,'2026-10-14')
    assert hint['source']==C.SOURCE_SUGGESTION and hint['confirmed'] is False# 建议保持未确认
    assert C.resolve_date('return_date',None,None,None) is None
