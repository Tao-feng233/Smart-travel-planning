"""Public business contracts for the v12 platform batch (batch 1 of the member-two brief).

Interfaces only: no storage engine, no HTTP layer, no business logic. Other
contributors code against these shapes and against the fixture implementations in
tests/test_contracts.py; a later batch binds them to MySQL with versioned migrations.
Date-field names are DRAFT and must be aligned with member three in review -- one
shared time vocabulary, this file stays the single source. Nothing here imports the
current SQLite storage on purpose: the contract must outlive any single backend.
"""
from typing import Protocol, runtime_checkable

# --- job lifecycle ----------------------------------------------------------
# queued -> running -> completed | failed | cancelled | interrupted
# A crashed worker's running job becomes claimable again once its lease expires;
# recovery must reuse saved stages instead of rerunning the whole model round.
QUEUED='queued'; RUNNING='running'; COMPLETED='completed'
FAILED='failed'; CANCELLED='cancelled'; INTERRUPTED='interrupted'
JOB_STATES=(QUEUED,RUNNING,COMPLETED,FAILED,CANCELLED,INTERRUPTED)
TERMINAL_STATES=(COMPLETED,FAILED,CANCELLED,INTERRUPTED)


class ContractError(Exception):
    """Base class so callers can catch every contract violation at once."""

class RevisionConflict(ContractError):
    """Save rejected because the stored revision moved: never silently overwrite."""

class RequestConflict(ContractError):
    """Same request_id reused for a different workspace."""

class JobNotClaimable(ContractError):
    """Claim rejected: the job is owned by another worker or already finished."""

class LeaseLost(ContractError):
    """The claiming worker's lease expired and another worker took the job."""

class FinalAfterCancel(ContractError):
    """A cancelled job must not publish a final plan or overwrite user choices."""


@runtime_checkable
class WorkspaceRepository(Protocol):
    """Per-owner trip workspaces with optimistic locking and undo snapshots."""

    def get(self,wid:str,owner_id:str|None)->dict|None:
        """Read one workspace scoped to its owner; None when absent or foreign."""
    def save(self,workspace:dict,expected_revision:int)->int:
        """Persist and return the new revision. Raise RevisionConflict when the
        stored revision no longer equals expected_revision."""
    def previous(self,wid:str,owner_id:str,before_revision:int)->dict:
        """Return the newest snapshot strictly before before_revision for undo;
        raise ContractError when there is nothing to restore."""

@runtime_checkable
class CacheRepository(Protocol):
    """Provider result cache; keeps the current key/expiry semantics."""

    def get(self,provider:str,key:str)->dict|None:
        """Cached payload or None when missing or expired."""
    def put(self,provider:str,key:str,payload:dict,ttl_seconds:int)->None:
        """Store with an absolute expiry computed from ttl_seconds."""

@runtime_checkable
class ProviderBudgetRepository(Protocol):
    """Atomic provider-call accounting, moved out of providers.py direct SQL."""

    def record_and_check(self,provider:str,limit:int,window_seconds:int)->bool:
        """Record one call and report whether the provider stays under limit for
        the sliding window. Must be atomic: record+check is one step."""

@runtime_checkable
class JobRepository(Protocol):
    """Durable job table shared by the API process and independent workers."""

    def submit(self,job_id:str,owner_id:str,workspace_id:str,request_id:str,action:str)->str:
        """Idempotent on (owner_id, request_id): return the existing job_id without
        creating a second row. Raise RequestConflict when request_id maps to a
        different workspace. New jobs start in QUEUED, never RUNNING."""
    def claim(self,worker_id:str,lease_seconds:int)->dict|None:
        """Claim one QUEUED job (or a RUNNING job whose lease expired) exclusively
        for this worker: set RUNNING, stamp lease deadline, return the job row.
        Return None when nothing is claimable. Two workers must never both win."""
    def renew(self,job_id:str,worker_id:str,lease_seconds:int)->None:
        """Extend the lease; raise LeaseLost when this worker no longer owns it."""
    def progress(self,job_id:str,text:str,ui:dict|None=None)->None:
        """Persist progress text and the latest ui snapshot for SSE readers."""
    def stage(self,job_id:str,key:str,payload:dict|None=None)->dict|None:
        """Read (payload=None) or write one reusable stage result, e.g. provider
        queries or a plan proposal, so a retry skips finished stages."""
    def finish(self,job_id:str,worker_id:str,status:str,error:str|None=None)->None:
        """Move a RUNNING job to a terminal state; only the lease owner may finish
        it and only into TERMINAL_STATES. Raise FinalAfterCancel when trying to
        publish a final result for a cancelled job."""
    def cancel(self,job_id:str,owner_id:str)->bool:
        """Owner-requested cancel: mark CANCELLED unless already terminal."""

@runtime_checkable
class KnowledgeRepository(Protocol):
    """Durable home for guide text: raw documents, parent blocks and index state.

    Storage only. Chunking and embedding stay in app/knowledge.py and
    app/vector_index.py -- this protocol must never grow a splitter or a model
    call. Qdrant keeps child-block vectors plus the payload a query needs; the
    raw text and the parent blocks that restore context live here, so a vector
    rebuild can never lose the corpus. Field names follow the data service
    (data/knowledge/*.json, app/data_contracts.py) so member one's loader and
    this repository describe the same objects.
    """

    def put_document(self,doc:dict)->str:
        """Store one raw document and return its doc_id.

        doc carries id, city, title, url, text, fetched_at, scope or date_scope
        and source_kind. Re-storing the same id replaces the effective version:
        source_version is the digest of the text, previous_version keeps the
        version it replaced, and the superseded text is archived rather than
        dropped. A failed collection run keeps the old text; only a changed
        source_version moves the effective version forward.
        """
    def get_document(self,doc_id:str)->dict|None:
        """Effective version of one document, or None when it was never stored."""
    def put_parents(self,doc_id:str,content_version:str,parents:list[dict])->None:
        """Store the parent blocks produced for one content version.

        Each parent carries its parent_id, city, entity_ids and applicable date
        scope. Replacing a content version replaces its parents; the previous
        blocks stay readable until the new index is switched in, so a rebuild
        that fails halfway cannot leave queries with dangling parent_id values.
        """
    def get_parent(self,parent_id:str)->dict|None:
        """One parent block by id: how a hit on a child block regains its context."""
    def search(self,city:str,query:str,visit_date:str|None=None,end_date:str|None=None,
               entity_ids:list[str]|None=None,limit:int=5)->dict:
        """Retrieve guide material and return the data-service envelope: items plus
        status, retrieval, degraded_reason and corpus_version.

        visit_date alone means a single day; with end_date it is an interval and
        results intersect it. entity_ids filter by strict intersection -- an empty
        list means no filter, never "matches nothing". Callers must keep each
        item's validity (background_only, stale_snapshot, visit_date_unverified,
        within_declared_scope, degraded, query_failed) and surface it: a hit is
        material for the trip, not proof that a rule is in force that day.
        """
    def index_state(self)->dict|None:
        """Current manifest: corpus digest, model identity, backend identity and
        collection name. None when no index has been published yet."""
    def set_index_state(self,manifest:dict)->None:
        """Publish a new manifest only after its collection is written and counted.

        The switch is atomic: a failed build keeps the previous manifest rather
        than pointing queries at a half-written collection. When the vector index
        is unusable or stale, retrieval degrades to lexical results and says so
        through degraded_reason -- it never mixes old vectors with new text.
        """

@runtime_checkable
class JobContext(Protocol):
    """What task code receives instead of touching the job table directly."""

    job_id:str
    def is_cancelled(self)->bool:...
    def emit_progress(self,text:str)->None:...
    def load_stage(self,key:str)->dict|None:...
    def save_stage(self,key:str,payload:dict)->None:...


# --- draft date semantics (align with member three before implementation) ----
# Three distinct origins; unconfirmed suggestions must keep their confirmation
# status and must never overwrite a user-explicit value on later saves.
SOURCE_USER='user_explicit'          # 用户明确输入
SOURCE_SHIFT='shift_fact'            # 班次事实（查询结果带来的确定时刻）
SOURCE_SUGGESTION='system_suggestion'# 系统建议（未确认）
DATE_ROLE_START='visit_start'        # 游玩开始日（区间含首尾日）
DATE_ROLE_END='visit_end'            # 游玩结束日
DATE_ROLE_OUTBOUND='outbound_date'   # 去程日期
DATE_ROLE_RETURN='return_date'       # 返程日期（独立字段，不再由 start+days 推定）

class DateField(dict):
    """One resolved date field: value plus provenance and confirmation status."""

def resolve_date(role:str,user_value:str|None,source_value:str|None,suggestion:str|None)->DateField|None:
    """Precedence: user-explicit > shift fact > system suggestion.

    A suggestion alone stays confirmed=False; callers must surface it as a
    proposal, never as the user's stated condition. None when nothing is known.
    """
    if user_value:return DateField(role=role,value=user_value,source=SOURCE_USER,confirmed=True)
    if source_value:return DateField(role=role,value=source_value,source=SOURCE_SHIFT,confirmed=True)
    if suggestion:return DateField(role=role,value=suggestion,source=SOURCE_SUGGESTION,confirmed=False)
    return None
