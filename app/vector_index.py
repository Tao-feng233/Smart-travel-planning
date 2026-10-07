"""Versioned Qdrant generations, atomically published after complete indexing."""
import json,os,re,threading,uuid
from .data_settings import index_root,option,model_name
from .knowledge import digest
from .embeddings import get_encoder

class VectorIndexError(RuntimeError):pass
_CLIENT=None
_LOCK=threading.RLock()

def identity():return digest([model_name(),option('EMBEDDING_PROVIDER','local'),option('EMBEDDING_BASE_URL')])

def backend_identity():return digest([option('QDRANT_URL') or 'local',str(index_root()) if not option('QDRANT_URL') else 'server'])

def read_manifest():
    try:
        value=json.loads((index_root()/'manifest.json').read_text(encoding='utf-8'))
        if not isinstance(value,dict) or not re.fullmatch('[0-9a-f]{32}',value.get('generation','')):return None
        return value
    except (OSError,ValueError,TypeError):return None

def client_for(manifest):
    global _CLIENT
    from qdrant_client import QdrantClient
    with _LOCK:
        key=(manifest['generation'],option('QDRANT_URL'),str(index_root()))
        if _CLIENT is None or _CLIENT[0]!=key:
            if _CLIENT:_CLIENT[1].close()
            client=QdrantClient(url=key[1],api_key=option('QDRANT_API_KEY') or None,timeout=8) if key[1] else QdrantClient(path=str(index_root()/manifest['generation']/'qdrant'),force_disable_check_same_thread=True)
            _CLIENT=(key,client)
        return _CLIENT[1]

def close():
    global _CLIENT
    with _LOCK:
        if _CLIENT:_CLIENT[1].close();_CLIENT=None

def build(corpus,encoder=None,force=False):
    import portalocker
    root=index_root();root.mkdir(parents=True,exist_ok=True)
    with portalocker.Lock(str(root/'build.lock'),timeout=2):
        return _build(corpus,encoder,force)

def _build(corpus,encoder=None,force=False):
    root=index_root();root.mkdir(parents=True,exist_ok=True);old=read_manifest()
    if not force and old and old.get('fingerprint')==corpus['fingerprint'] and old.get('embedding_identity')==identity() and old.get('backend_identity')==backend_identity():return {**old,'rebuilt':False}
    encoder=encoder or get_encoder();generation=uuid.uuid4().hex;folder=root/generation;folder.mkdir()
    model_identity=identity();cache_path=root/('embeddings-'+model_identity[:16]+'.json')
    try:cache=json.loads(cache_path.read_text(encoding='utf-8'))
    except (OSError,ValueError):cache={}
    texts=[c['index_text'] for c in corpus['children']];keys=[digest(x) for x in texts]
    missing=list(dict.fromkeys(key for key in keys if key not in cache));by_key=dict(zip(keys,texts))
    if missing:cache.update(dict(zip(missing,encoder.documents([by_key[k] for k in missing]))))
    if not keys:raise VectorIndexError('没有可索引的资料子块')
    vectors=[cache[k] for k in keys];dim=len(vectors[0])
    if any(len(v)!=dim for v in vectors):raise VectorIndexError('Embedding维度不一致')
    from qdrant_client import QdrantClient,models
    collection='shitu_guides_'+generation
    client=QdrantClient(url=option('QDRANT_URL'),api_key=option('QDRANT_API_KEY') or None,timeout=20) if option('QDRANT_URL') else QdrantClient(path=str(folder/'qdrant'))
    try:
        client.create_collection(collection,vectors_config={'dense':models.VectorParams(size=dim,distance=models.Distance.COSINE)})
        if option('QDRANT_URL'):
            for field in ('city','parent_id','content_version'):client.create_payload_index(collection,field_name=field,field_schema=models.PayloadSchemaType.KEYWORD,wait=True)
        points=[models.PointStruct(id=str(uuid.uuid5(uuid.NAMESPACE_URL,c['id'])),vector={'dense':v},payload={**c}) for c,v in zip(corpus['children'],vectors)]
        for at in range(0,len(points),32):client.upsert(collection,points=points[at:at+32],wait=True)
        if client.count(collection,exact=True).count!=len(points):raise VectorIndexError('Qdrant索引记录数量不一致')
    finally:client.close()
    (folder/'parents.json').write_text(json.dumps(corpus['parents'],ensure_ascii=False),encoding='utf-8')
    from .storage import now
    manifest={'generation':generation,'collection':collection,'fingerprint':corpus['fingerprint'],'embedding_identity':model_identity,'backend_identity':backend_identity(),
              'model':model_name(),'provider':option('EMBEDDING_PROVIDER','local'),'backend':'server' if option('QDRANT_URL') else 'local_persistent',
              'dimensions':dim,'records':corpus['records'],'parents':len(corpus['parents']),'children':len(points),'indexed_at':now()}
    cache_tmp=cache_path.with_suffix('.'+generation+'.tmp');cache_tmp.write_text(json.dumps(cache),encoding='utf-8');os.replace(cache_tmp,cache_path)
    tmp=root/('manifest-'+generation+'.tmp');tmp.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8');os.replace(tmp,root/'manifest.json')
    return {**manifest,'rebuilt':True}

def search(corpus,query,allowed_parents,limit=20,encoder=None):
    manifest=read_manifest()
    if not manifest:return [],'index_not_ready'
    if manifest.get('fingerprint')!=corpus['fingerprint'] or manifest.get('embedding_identity')!=identity() or manifest.get('backend_identity')!=backend_identity():return [],'index_outdated'
    if not allowed_parents:return [],None
    try:
        from qdrant_client import models
        with _LOCK:
            vector=(encoder or get_encoder()).query(query)
            if len(vector)!=manifest['dimensions']:return [],'dimension_mismatch'
            result=client_for(manifest).query_points(collection_name=manifest['collection'],query=vector,using='dense',
                query_filter=models.Filter(must=[models.FieldCondition(key='parent_id',match=models.MatchAny(any=list(allowed_parents)))]),
                limit=limit,score_threshold=float(option('RAG_DENSE_MIN_SCORE','0.58')),with_payload=True)
        return [(p.payload['id'],float(p.score)) for p in result.points if p.payload and p.payload.get('parent_id') in allowed_parents],None
    except Exception:return [],'dense_query_failed'
