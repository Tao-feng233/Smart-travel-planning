"""Parent/child BM25 + Qdrant semantic retrieval with explicit degradation."""
import threading
from datetime import date
from .config import ROOT
from .knowledge import load_corpus,bm25,fuse,applicable,validity,CorpusError,tokens
from . import vector_index

_CORPUS=None
_STAMP=None
_LOCK=threading.RLock()

def corpus():
    global _CORPUS,_STAMP
    paths=sorted((ROOT/'data/knowledge').glob('*.json'));stamp=tuple((str(p),p.stat().st_mtime_ns,p.stat().st_size) for p in paths)
    with _LOCK:
        if _CORPUS is None or _STAMP!=stamp:_CORPUS=load_corpus();_STAMP=stamp
        return _CORPUS

def retrieve_result(city,query,limit=5,visit_date=None,entity_ids=None,context_chars=6000,end_date=None):
    if visit_date:
        try:date.fromisoformat(visit_date)
        except (ValueError,TypeError):return {'items':[],'status':'query_failed','error_code':'invalid_date','reason':'资料检索日期无效'}
    if end_date:
        try:
            date.fromisoformat(end_date)
            if not visit_date or end_date<visit_date:raise ValueError()
        except (ValueError,TypeError):return {'items':[],'status':'query_failed','error_code':'invalid_date','reason':'资料检索日期区间无效'}
    if not isinstance(query,str) or not query.strip():return {'items':[],'status':'empty','retrieval':'none','degraded_reason':None}
    limit=max(1,min(int(limit),10));query=query[:1000]
    try:loaded=corpus()
    except CorpusError:return {'items':[],'status':'query_failed','error_code':'invalid_corpus','reason':'资料库格式无效，请检查采集记录'}
    parents=loaded['parents'];allowed={pid for pid,p in parents.items() if applicable(p,city,visit_date,entity_ids,end_date)}
    children=[c for c in loaded['children'] if c['parent_id'] in allowed]
    lexical=bm25(children,query)[:20];dense,reason=vector_index.search(loaded,query,allowed)
    order=fuse(lexical,dense);by_id={c['id']:c for c in children};lex_scores=dict(lexical);dense_scores=dict(dense)
    mode='BM25 + Qdrant语义检索 + RRF + 父块上下文' if reason is None else 'BM25关键词检索（语义检索降级）'
    grouped={}
    for cid,score in order:
        if cid not in by_id:continue
        child=by_id[cid];pid=child['parent_id']
        if pid not in grouped:grouped[pid]={'score':score,'matches':[],'lexical_score':0,'dense_score':None}
        group=grouped[pid];group['matches'].append(child['text']);group['score']=max(group['score'],score)
        group['lexical_score']=max(group['lexical_score'],lex_scores.get(cid,0))
        if cid in dense_scores:group['dense_score']=max(group['dense_score'] or -1,dense_scores[cid])
    output=[];remaining=max(500,min(int(context_chars),16000))
    for pid,group in sorted(grouped.items(),key=lambda x:(-x[1]['score'],x[0])):
        parent=parents[pid];text=parent['text']
        if len(text)>remaining:
            match=group['matches'][0];at=text.find(match);start=max(0,at-150) if at>=0 else 0
            text=text[start:start+remaining]
        if remaining<150:break
        output.append({**parent,'text':text,'score':round(group['score'],6),'matched_texts':group['matches'][:3],
                       'lexical_score':round(group['lexical_score'],4),'dense_score':group['dense_score'],'retrieval':mode,
                       'validity':validity(parent,visit_date),'retrieval_date':visit_date,'retrieval_end_date':end_date,'context_truncated':text!=parent['text']})
        remaining-=len(text)
        if len(output)>=limit:break
    return {'items':output,'status':'degraded' if reason else 'available' if output else 'empty','retrieval':mode,
            'degraded_reason':reason,'corpus_version':loaded['fingerprint'],'context_characters':sum(len(p['text']) for p in output)}

def retrieve(city,query,limit=5,visit_date=None,entity_ids=None):
    return retrieve_result(city,query,limit,visit_date,entity_ids)['items']

def status():
    loaded=corpus();manifest=vector_index.read_manifest()
    ready=bool(manifest and manifest.get('fingerprint')==loaded['fingerprint'] and manifest.get('embedding_identity')==vector_index.identity() and manifest.get('backend_identity')==vector_index.backend_identity())
    return {'records':loaded['records'],'parents':len(loaded['parents']),'children':len(loaded['children']),
            'cities':sorted(set(p['city'] for p in loaded['parents'].values())),
            'dense_index_ready':ready,'backend':(manifest or {}).get('backend'),'model':(manifest or {}).get('model'),
            'indexed_at':(manifest or {}).get('indexed_at'),'corpus_version':loaded['fingerprint']}
