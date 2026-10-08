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
        # isolation_level=None: save() issues BEGIN IMMEDIATE itself, so two
        # connections saving against the same expected_revision cannot both win
        # (a read-then-write over two auto-commits would let the later save
        # silently overwrite the earlier one).
        self.c=sqlite3.connect(path,isolation_level=None)
        self.c.execute('CREATE TABLE IF NOT EXISTS workspaces(id TEXT PRIMARY KEY,owner_id TEXT,payload TEXT,revision INTEGER)')
        self.c.execute('CREATE TABLE IF NOT EXISTS versions(id TEXT,revision INTEGER,payload TEXT,PRIMARY KEY(id,revision))')
    def get(self,wid,owner_id):
        row=self.c.execute('SELECT payload,owner_id,revision FROM workspaces WHERE id=?',(wid,)).fetchone()
        if not row or (owner_id is not None and row[1]!=owner_id):return None
        w=json.loads(row[0]);w['owner_id']=row[1];w['revision']=row[2];return w
    def save(self,workspace,expected_revision):
        # One write transaction guards read + write: the revision check, the
        # body, and the undo snapshot all commit together or not at all.
        self.c.execute('BEGIN IMMEDIATE')
        try:
            row=self.c.execute('SELECT owner_id FROM workspaces WHERE id=?',(workspace['id'],)).fetchone()
            if row:
                # Ownership is fixed at creation; a normal save may not move it.
                if workspace.get('owner_id')!=row[0]:
                    raise ContractError('旅行归属不可通过保存变更')
                cur=self.c.execute('UPDATE workspaces SET payload=?,revision=? WHERE id=? AND revision=?',
                                   (json.dumps(workspace,ensure_ascii=False),expected_revision+1,workspace['id'],expected_revision))
                if cur.rowcount!=1:raise RevisionConflict('旅行已更新，请刷新后重试')
                new=expected_revision+1
                self.c.execute('INSERT OR REPLACE INTO versions VALUES(?,?,?)',(workspace['id'],new,json.dumps(workspace,ensure_ascii=False)))
            else:
                if expected_revision!=0:raise RevisionConflict('旅行已更新，请刷新后重试')
                new=1;payload=json.dumps(workspace,ensure_ascii=False)
                self.c.execute('INSERT INTO workspaces VALUES(?,?,?,?)',(workspace['id'],workspace.get('owner_id'),payload,new))
                self.c.execute('INSERT INTO versions VALUES(?,?,?)',(workspace['id'],new,payload))
        except Exception:
            self.c.execute('ROLLBACK');raise
        self.c.execute('COMMIT')
        return new
    def previous(self,wid,owner_id,before_revision):
        # Same rule as get(): a foreign or missing trip is None, never someone
        # else's snapshot. Undo must not become a way to read across accounts.
        owned=self.c.execute('SELECT owner_id FROM workspaces WHERE id=?',(wid,)).fetchone()
        if not owned or (owner_id is not None and owned[0]!=owner_id):return None
        row=self.c.execute('SELECT payload,revision FROM versions WHERE id=? AND revision<? ORDER BY revision DESC LIMIT 1',(wid,before_revision)).fetchone()
        if not row:raise ContractError('没有可撤销的版本')
        w=json.loads(row[0]);w['revision']=row[1];w['owner_id']=owned[0];return w

class SqliteCache:
    def __init__(self,path):
        self.c=sqlite3.connect(path)
        self.c.execute('CREATE TABLE IF NOT EXISTS cache(provider TEXT,key TEXT,payload TEXT,expires REAL,PRIMARY KEY(provider,key))');self.c.commit()
    def get(self,provider,key):
        row=self.c.execute('SELECT payload,expires FROM cache WHERE provider=? AND key=?',(provider,key)).fetchone()
        return json.loads(row[0]) if row and row[1]>time.time() else None
    def put(self,provider,key,payload,ttl_seconds):
        self.c.execute('INSERT OR REPLACE INTO cache VALUES(?,?,?,?)',(provider,key,json.dumps(payload,ensure_ascii=False),time.time()+ttl_seconds));self.c.commit()

class SqliteBudget:
    def __init__(self,path):
        # isolation_level=None: we issue BEGIN IMMEDIATE ourselves, because a
        # read-then-write that runs as two auto-commits lets two callers both
        # count zero and both insert when limit=1.
        self.c=sqlite3.connect(path,isolation_level=None)
        self.c.execute('CREATE TABLE IF NOT EXISTS calls(provider TEXT,time REAL)');self.c.commit()
    def record_and_check(self,provider,limit,window_seconds):
        floor=time.time()-window_seconds
        self.c.execute('BEGIN IMMEDIATE')          # take the write lock before counting
        try:
            used=self.c.execute('SELECT COUNT(*) FROM calls WHERE provider=? AND time>?',(provider,floor)).fetchone()[0]
            if used>=limit:
                self.c.execute('COMMIT');return False
            self.c.execute('INSERT INTO calls VALUES(?,?)',(provider,time.time()))
            self.c.execute('COMMIT');return True
        except Exception:
            self.c.execute('ROLLBACK');raise

class SqliteJobs:
    def __init__(self,path):
        # isolation_level=None: claim() issues BEGIN IMMEDIATE so that picking a
        # row and taking it happen inside one write transaction.
        self.c=sqlite3.connect(path,isolation_level=None)
        self.c.execute('CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,owner_id TEXT,workspace_id TEXT,request_id TEXT,action TEXT,status TEXT,progress TEXT,ui TEXT,worker_id TEXT,lease REAL,created REAL,error TEXT)')
        self.c.execute('CREATE UNIQUE INDEX IF NOT EXISTS job_request ON jobs(owner_id,request_id)')
        self.c.execute('CREATE TABLE IF NOT EXISTS stages(job_id TEXT,key TEXT,payload TEXT,PRIMARY KEY(job_id,key))');self.c.commit()
    def submit(self,job_id,owner_id,workspace_id,request_id,action):
        row=self.c.execute('SELECT id,workspace_id FROM jobs WHERE owner_id=? AND request_id=?',(owner_id,request_id)).fetchone()
        if row:
            if row[1]!=workspace_id:raise RequestConflict('请求编号已用于其他旅行')
            return row[0]
        self.c.execute('INSERT INTO jobs(id,owner_id,workspace_id,request_id,action,status,progress,created) VALUES(?,?,?,?,?,?,?,?)',
                       (job_id,owner_id,workspace_id,request_id,action,C.QUEUED,'',time.time()))
        self.c.commit();return job_id
    # Bracketed on purpose: `id=? AND status='queued' OR (...)` binds the OR
    # branch to nothing, so one claim would repoint every expired job at the new
    # worker. AND binds tighter than OR, so the whole condition needs its own
    # parentheses to stay scoped to the selected id.
    def _claimable(self):return "(status='queued' OR (status='running' AND (lease IS NULL OR lease<?)))"
    def claim(self,worker_id,lease_seconds):
        now=time.time()
        self.c.execute('BEGIN IMMEDIATE')     # one writer at a time: never two winners
        try:
            row=self.c.execute('SELECT id FROM jobs WHERE '+self._claimable()+' ORDER BY created LIMIT 1',(now,)).fetchone()
            if not row:
                self.c.execute('COMMIT');return None
            cur=self.c.execute("UPDATE jobs SET status='running',worker_id=?,lease=?,error=NULL WHERE id=? AND "+self._claimable(),
                               (worker_id,now+lease_seconds,row[0],now))
            self.c.execute('COMMIT')
        except Exception:
            self.c.execute('ROLLBACK');raise
        assert cur.rowcount<=1,'一次领取只能改动一行'
        return self.get_job(row[0]) if cur.rowcount==1 else None
    def get_job(self,jid):
        row=self.c.execute('SELECT id,owner_id,workspace_id,request_id,action,status,progress,worker_id FROM jobs WHERE id=?',(jid,)).fetchone()
        if not row:return None
        return dict(zip(('id','owner_id','workspace_id','request_id','action','status','progress','worker_id'),row))
    def renew(self,job_id,worker_id,lease_seconds):
        now=time.time()
        # A live holder extends before expiry; an already-expired lease must go
        # through the claim path again, never be revived by its old owner.
        cur=self.c.execute("UPDATE jobs SET lease=? WHERE id=? AND worker_id=? AND status='running' AND lease>?",
                           (now+lease_seconds,job_id,worker_id,now))
        self.c.commit()
        if cur.rowcount!=1:raise LeaseLost('任务已由其他执行器接管')
    def _writable(self,worker_id):
        return ("status='running' AND worker_id=? AND lease>?",(worker_id,time.time()))
    def progress(self,job_id,worker_id,text,ui=None):
        # Progress carries the writer's credentials: after a takeover the stale
        # context must not overwrite what the new holder is doing.
        cond,params=self._writable(worker_id)
        cur=self.c.execute('UPDATE jobs SET progress=?,ui=? WHERE id=? AND '+cond,
                           (text,json.dumps(ui,ensure_ascii=False) if ui is not None else None,job_id,*params))
        self.c.commit()
        if cur.rowcount!=1:raise LeaseLost('当前上下文已失去该任务的写权限')
    def stage(self,job_id,key,payload=None,worker_id=None):
        if payload is None:
            row=self.c.execute('SELECT payload FROM stages WHERE job_id=? AND key=?',(job_id,key)).fetchone()
            return json.loads(row[0]) if row else None
        cond,params=self._writable(worker_id)
        cur=self.c.execute('INSERT OR REPLACE INTO stages(job_id,key,payload) SELECT id,?,? FROM jobs WHERE id=? AND '+cond,
                           (key,json.dumps(payload,ensure_ascii=False),job_id,*params))
        self.c.commit()
        if cur.rowcount!=1:raise LeaseLost('当前上下文已失去该任务的写权限')
    def finish(self,job_id,worker_id,status,error=None):
        if status not in C.TERMINAL_STATES:raise ContractError('非法的结束状态')
        now=time.time()
        # One conditional update carries holder, status and a still-valid lease,
        # so a cancel or takeover landing mid-flight is never overwritten.
        cur=self.c.execute("UPDATE jobs SET status=?,error=?,lease=NULL WHERE id=? AND status=? AND worker_id=? AND lease>?",
                           (status,error,job_id,C.RUNNING,worker_id,now))
        self.c.commit()
        if cur.rowcount==1:return
        after=self.c.execute('SELECT status FROM jobs WHERE id=?',(job_id,)).fetchone()
        if after and after[0]==C.CANCELLED:raise FinalAfterCancel('已停止的任务不能再提交最终计划')
        raise LeaseLost('任务已由其他执行器接管')
    def cancel(self,job_id,owner_id):
        cur=self.c.execute("UPDATE jobs SET status='cancelled' WHERE id=? AND owner_id=? AND status IN ('queued','running')",(job_id,owner_id))
        self.c.commit();return cur.rowcount==1

class FixtureJobContext:
    job_id=''
    worker_id=''
    def __init__(self,jobs):self.jobs=jobs
    def is_cancelled(self):
        job=self.jobs.get_job(self.job_id);return bool(job and job['status']==C.CANCELLED)
    def emit_progress(self,text):self.jobs.progress(self.job_id,self.worker_id,text)
    def load_stage(self,key):return self.jobs.stage(self.job_id,key)
    def save_stage(self,key,payload):self.jobs.stage(self.job_id,key,payload,worker_id=self.worker_id)


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
    assert stores['workspaces'].previous('w1','bob',2) is None     # 撤销同样按归属读取
    assert stores['workspaces'].previous('nope','alice',2) is None

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
    ctx=FixtureJobContext(jobs);ctx.job_id='j1';ctx.worker_id='worker-a'
    ctx.save_stage('provider_query',{'trains':['G1']})                       # 阶段结果可复用
    assert ctx.load_stage('provider_query')=={'trains':['G1']}
    ctx.emit_progress('正在整理路线')
    assert jobs.cancel('j1','alice') is True and ctx.is_cancelled() is True
    with pytest.raises(FinalAfterCancel):
        jobs.finish('j1','worker-a',C.COMPLETED)                             # 取消后不能再出最终计划
    assert jobs.get_job('j1')['status']==C.CANCELLED

def test_budget_limit_holds_for_two_writers(tmp_path):
    """Two executors, one limit: the second call must be refused, not counted twice."""
    db=str(tmp_path/'budget.db')
    a=SqliteBudget(db);b=SqliteBudget(db)                          # two connections = two executors
    assert a.record_and_check('amap',limit=1,window_seconds=60) is True
    assert b.record_and_check('amap',limit=1,window_seconds=60) is False
    assert a.c.execute('SELECT COUNT(*) FROM calls').fetchone()[0]==1   # exactly one call recorded

def test_budget_check_and_record_share_one_write_transaction(tmp_path):
    """Counting and inserting must be one critical section, not two auto-commits."""
    db=str(tmp_path/'lock.db')
    a=SqliteBudget(db)
    a.c.execute('BEGIN IMMEDIATE')                                 # a is inside check+record
    other=sqlite3.connect(db,isolation_level=None,timeout=0.2)
    with pytest.raises(sqlite3.OperationalError):                  # b cannot count alongside it
        other.execute('BEGIN IMMEDIATE')
    a.c.execute('ROLLBACK');other.close()

def test_claim_touches_only_the_target_job_when_leases_expire(stores):
    """Once the OR branch is unbracketed, one claim repointed every expired job."""
    jobs=stores['jobs']
    for j in ('j1','j2','j3'):jobs.submit(j,'alice','w1','req-'+j,'plan')
    jobs.claim('worker-a',60)                                      # j1 running, lease valid
    jobs.c.execute("UPDATE jobs SET status='running',worker_id='worker-dead',lease=? WHERE id IN ('j2','j3')",
                   (time.time()-1,));jobs.c.commit()               # j2/j3 crashed workers
    taken=jobs.claim('worker-b',60)
    assert taken is not None and taken['id']=='j2'                 # oldest expired job only
    assert jobs.get_job('j3')['worker_id']=='worker-dead'          # not silently repointed
    assert jobs.get_job('j1')['worker_id']=='worker-a'             # a live lease is untouched

def test_two_workers_never_claim_the_same_job(tmp_path):
    db=str(tmp_path/'claim.db')
    a=SqliteJobs(db);b=SqliteJobs(db)
    a.submit('j1','alice','w1','req-1','plan')
    assert a.claim('worker-a',60)['id']=='j1'
    assert b.claim('worker-b',60) is None                          # second connection loses

def test_finish_rejects_a_worker_that_lost_the_lease(stores):
    jobs=stores['jobs'];jobs.submit('j1','alice','w1','req-1','plan');jobs.claim('worker-a',60)
    jobs.c.execute("UPDATE jobs SET lease=? WHERE id='j1'",(time.time()-1,));jobs.c.commit()
    assert jobs.claim('worker-b',60)['worker_id']=='worker-b'      # expired lease, taken over
    with pytest.raises(LeaseLost):
        jobs.finish('j1','worker-a',C.COMPLETED)                   # old holder may not finish
    assert jobs.get_job('j1')['status']==C.RUNNING                 # and must not move the status

def test_cancelled_job_keeps_its_saved_stages(stores):
    """Cancelling must preserve what the run already produced, and block late results."""
    jobs=stores['jobs'];jobs.submit('j1','alice','w1','req-1','plan');jobs.claim('worker-a',60)
    ctx=FixtureJobContext(jobs);ctx.job_id='j1';ctx.worker_id='worker-a'
    ctx.save_stage('provider_query',{'trains':['G1']})
    assert jobs.cancel('j1','alice') is True
    with pytest.raises(FinalAfterCancel):
        jobs.finish('j1','worker-a',C.COMPLETED)
    assert ctx.load_stage('provider_query')=={'trains':['G1']}     # produced work survives
    assert jobs.get_job('j1')['status']==C.CANCELLED

def test_all_five_repositories_are_declared():
    """The brief asks for five; a missing protocol should fail here, not in review."""
    for name in ('WorkspaceRepository','CacheRepository','ProviderBudgetRepository',
                 'JobRepository','KnowledgeRepository'):
        assert hasattr(C,name),f'missing repository protocol: {name}'
        assert isinstance(getattr(C,name),type)

def test_knowledge_repository_covers_text_parents_and_index_state():
    """It stores what the vector index cannot: raw text, parent blocks, manifest."""
    for member in ('put_document','get_document','put_parents','get_parent','search',
                   'index_state','set_index_state'):
        assert hasattr(C.KnowledgeRepository,member),f'KnowledgeRepository 缺少 {member}'
    # Out of scope on purpose: no chunking and no embedding behind this interface.
    for forbidden in ('embed','chunk','split','vectorize'):
        assert not hasattr(C.KnowledgeRepository,forbidden)

def test_resolve_date_precedence_keeps_suggestions_unconfirmed():
    user=C.resolve_date('return_date','2026-10-15',None,'2026-10-14')
    assert user['value']=='2026-10-15' and user['confirmed'] is True         # 用户明确输入最高
    fact=C.resolve_date('outbound_date',None,'2026-10-12 08:00',None)
    assert fact['source']==C.SOURCE_SHIFT and fact['confirmed'] is True      # 班次事实视为确定
    hint=C.resolve_date('return_date',None,None,'2026-10-14')
    assert hint['source']==C.SOURCE_SUGGESTION and hint['confirmed'] is False# 建议保持未确认
    assert C.resolve_date('return_date',None,None,None) is None


# --- 复核补充的四个契约场景（组长复核第二节） --------------------------------

def test_concurrent_saves_cannot_both_win(tmp_path):
    """两个连接用同一个 expected_revision 保存：恰好一个成功，后者不得覆盖前者。"""
    db=str(tmp_path/'race.db')
    a=SqliteWorkspaces(db);b=SqliteWorkspaces(db)                # 两个连接=两个执行方
    w={'id':'w1','owner_id':'alice','city':'青岛'}
    assert a.save(dict(w),0)==1
    first=dict(w,city='杭州');second=dict(w,city='成都')
    a.save(dict(first),1)                                        # a 先保存
    with pytest.raises(RevisionConflict):                        # b 的旧 revision 必须被拒
        b.save(dict(second),1)
    assert a.get('w1','alice')['city']=='杭州'                    # 后到者没有覆盖先到者
    # 两个连接同时抢当前 revision：恰好一个成功
    c=SqliteWorkspaces(db);d=SqliteWorkspaces(db)
    results=[]
    for store,payload in ((c,dict(w,city='西安')),(d,dict(w,city='洛阳'))):
        try:results.append(store.save(dict(payload),2))
        except RevisionConflict:results.append('conflict')
    assert sorted(r=='conflict' for r in results)==[False,True]  # 一胜一拒
    assert a.get('w1','alice')['city'] in ('西安','洛阳')          # 数据完整，没有合并出脏状态

def test_save_cannot_move_the_owner(stores):
    """归属在创建时固定：普通保存不得把旅行从 Alice 划给 Bob。"""
    ws=stores['workspaces']
    w={'id':'w1','owner_id':'alice','city':'青岛'}
    ws.save(w,0)
    with pytest.raises(ContractError):
        ws.save(dict(w,owner_id='bob',city='杭州'),1)             # 换归属的保存被拒
    assert ws.get('w1','alice')['city']=='青岛'                   # 原内容未动
    assert ws.get('w1','bob') is None                             # bob 从未拥有过它
    assert ws.save(dict(w,city='杭州'),1)==2                      # 正确归属者可以继续保存

def test_expired_lease_blocks_renew_and_finish_by_the_old_holder(stores):
    """租约过期但尚未被接管：旧持有者不能续租或收尾，必须走重新领取。"""
    jobs=stores['jobs'];jobs.submit('j1','alice','w1','req-1','plan');jobs.claim('worker-a',60)
    jobs.c.execute("UPDATE jobs SET lease=? WHERE id='j1'",(time.time()-1,));jobs.c.commit()
    with pytest.raises(LeaseLost):                                # 不能复活自己的过期租约
        jobs.renew('j1','worker-a',60)
    with pytest.raises(LeaseLost):                                # 也不能在过期后收尾
        jobs.finish('j1','worker-a',C.COMPLETED)
    assert jobs.get_job('j1')['status']==C.RUNNING                # 状态未被旧持有者动过
    assert jobs.claim('worker-b',60)['worker_id']=='worker-b'     # 唯一出路是重新领取

def test_stale_context_cannot_write_after_a_takeover(stores):
    """Worker B 接管后，Worker A 的旧上下文不得再写进度或阶段结果。"""
    jobs=stores['jobs'];jobs.submit('j1','alice','w1','req-1','plan')
    assert jobs.claim('worker-a',60)['id']=='j1'
    fresh_ctx=FixtureJobContext(jobs);fresh_ctx.job_id='j1';fresh_ctx.worker_id='worker-a'
    fresh_ctx.emit_progress('worker-a 阶段');fresh_ctx.save_stage('queries',{'rows':1})
    jobs.c.execute("UPDATE jobs SET lease=? WHERE id='j1'",(time.time()-1,));jobs.c.commit()
    assert jobs.claim('worker-b',60)['worker_id']=='worker-b'     # B 接管
    with pytest.raises(LeaseLost):                                # A 的进度被拒
        fresh_ctx.emit_progress('worker-a 幽灵进度')
    with pytest.raises(LeaseLost):                                # A 的阶段写入被拒
        fresh_ctx.save_stage('queries',{'rows':2})
    assert jobs.get_job('j1')['progress']=='worker-a 阶段'         # 旧进度未被覆盖
    assert jobs.stage('j1','queries')=={'rows':1}                 # 阶段数据未被覆盖


def test_cancel_between_stage_permission_read_and_write_is_fenced(stores,tmp_path):
    jobs=stores['jobs'];jobs.submit('j1','alice','w1','req-1','plan');jobs.claim('worker-a',60)
    other=SqliteJobs(str(tmp_path/'contract.db'));connection=jobs.c
    class CancelBeforeInsert:
        fired=False
        def execute(self,sql,args=()):
            if sql.startswith('INSERT OR REPLACE INTO stages') and not self.fired:
                self.fired=True;assert other.cancel('j1','alice')
            return connection.execute(sql,args)
        def commit(self):return connection.commit()
    jobs.c=CancelBeforeInsert()
    with pytest.raises(LeaseLost):jobs.stage('j1','late',{'plan':'must-not-write'},'worker-a')
    assert jobs.stage('j1','late') is None
