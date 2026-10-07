"""Source-preserving parent/child corpus and lexical retrieval primitives."""
import hashlib,json,math,re,unicodedata
from collections import Counter,defaultdict
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit
from .config import ROOT

SCHEMA_VERSION=2
class CorpusError(ValueError):pass

def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def city_key(value):return re.sub(r'[市县区]+$','',unicodedata.normalize('NFKC',str(value or '')).strip())

def tokens(text):
    s=''.join(re.findall(r'[\w\u4e00-\u9fff]+',str(text).lower()))
    return [s[i:i+2] for i in range(max(0,len(s)-1))]+re.findall(r'[a-z0-9_]{2,}',str(text).lower())

def clean_text(value):
    if not isinstance(value,str):raise CorpusError('资料正文必须是文本')
    return re.sub(r'[ \t]+',' ',value.replace('\r\n','\n')).strip()

def normalize_record(row):
    if not isinstance(row,dict):raise CorpusError('资料记录必须是对象')
    for key in ('id','city','title','url','text'):
        if not isinstance(row.get(key),str) or not row[key].strip():raise CorpusError('资料缺少字段：'+key)
    url=urlsplit(row['url'])
    if url.scheme not in ('http','https') or not url.hostname or url.username or url.password:raise CorpusError('资料来源地址无效')
    value=dict(row);value.update(text=clean_text(row['text']),city=city_key(row['city']),title=clean_text(row['title']))
    for key in ('valid_from','valid_to'):
        if value.get(key):
            try:date.fromisoformat(value[key])
            except (ValueError,TypeError):raise CorpusError('资料适用日期无效') from None
    if value.get('valid_from') and value.get('valid_to') and value['valid_from']>value['valid_to']:raise CorpusError('资料适用日期倒置')
    for key in ('entity_ids','entity_names'):
        if not isinstance(value.get(key,[]),list) or any(not isinstance(x,str) for x in value.get(key,[])):raise CorpusError('资料实体列表无效')
        value[key]=list(dict.fromkeys(value.get(key,[])))
    value['date_scope']=value.get('date_scope') or value.get('scope') or '查询资料快照，出游日适用性待核实'
    value['scope']=value.get('scope') or value['date_scope']
    value['source_kind']=value.get('source_kind') or ('background' if '背景' in value.get('category','')+value['scope'] else 'official_snapshot')
    return value

def split_text(text,max_chars=360,overlap=50):
    """Paragraph/sentence boundaries first; hard-length split only as a fallback."""
    if not 0<=overlap<max_chars:raise ValueError('重叠长度必须小于片段长度')
    sentences=re.findall(r'[^。！？；\n]+[。！？；\n]?|[。！？；\n]',text)
    pieces=[]
    for s in sentences:
        for at in range(0,len(s),max_chars):
            piece=s[at:at+max_chars].strip()
            if piece:pieces.append(piece)
    chunks=[];current=''
    for piece in pieces:
        if current and len(current)+len(piece)>max_chars:
            chunks.append(current)
            tail=current[-overlap:] if overlap else ''
            current=(tail+piece) if len(tail)+len(piece)<=max_chars else piece
        else:current+=piece
    if current:chunks.append(current)
    return chunks or ([text] if text else [])

def merge_snippets(texts):
    """Reconstruct overlapping legacy windows before parent/child splitting."""
    result=''
    for text in dict.fromkeys(texts):
        if text in result:continue
        if result and result in text:result=text;continue
        overlap=next((n for n in range(min(len(result),len(text)),19,-1) if result.endswith(text[:n])),0)
        result=result+text[overlap:] if overlap else result+('\n' if result else '')+text
    return result

def load_corpus(directory=None):
    directory=Path(directory or ROOT/'data/knowledge');records=[];ids={}
    for file in sorted(directory.glob('*.json')):
        try:rows=json.loads(file.read_text(encoding='utf-8-sig'))
        except (OSError,ValueError):raise CorpusError('资料文件读取或格式错误：'+file.name) from None
        if not isinstance(rows,list):raise CorpusError('资料文件应为记录列表：'+file.name)
        for raw in rows:
            row=normalize_record(raw)
            if row['id'] in ids:
                if digest(ids[row['id']])!=digest(row):raise CorpusError('重复资料ID内容不一致：'+row['id'])
                continue
            ids[row['id']]=row;records.append(row)
    groups=defaultdict(list)
    for row in records:
        # Never combine different notices, applicability intervals or versions.
        key=(row['city'],row['url'],row['title'],row['scope'],row.get('valid_from'),row.get('valid_to'),row.get('published_at'),row.get('source_version') or row.get('fetched_at'))
        groups[key].append(row)
    parents={};children=[]
    for key,rows in groups.items():
        joined=merge_snippets(r['text'] for r in rows)
        parent_parts=split_text(joined,1400,0)
        for i,text in enumerate(parent_parts):
            base=rows[0];pid=base['id'] if len(rows)==1 and len(parent_parts)==1 else 'parent:'+digest([key,i])[:24]
            parent={**base,'id':pid,'text':text,'record_ids':[r['id'] for r in rows],
                    'entity_ids':list(dict.fromkeys(x for r in rows for x in r['entity_ids'])),
                    'entity_names':list(dict.fromkeys(x for r in rows for x in r['entity_names']))}
            parent['content_version']=digest([text,parent['title'],parent['scope'],parent.get('valid_from'),parent.get('valid_to')])
            parents[pid]=parent
            for j,body in enumerate(split_text(text)):
                cid='child:'+digest([pid,j,body])[:28]
                children.append({'id':cid,'parent_id':pid,'text':body,'index_text':parent['city']+' '+parent['title']+' '+body,
                                 'city':parent['city'],'entity_ids':parent['entity_ids'],'valid_from':parent.get('valid_from'),
                                 'valid_to':parent.get('valid_to'),'content_version':parent['content_version']})
    fingerprint=digest({'schema':SCHEMA_VERSION,'records':records,'split':{'parent':1400,'child':360,'overlap':50}})
    return {'fingerprint':fingerprint,'parents':parents,'children':children,'records':len(records)}

def applicable(parent,city='',visit_date=None,entity_ids=None,end_date=None):
    if city and city_key(parent['city'])!=city_key(city):return False
    if entity_ids and not set(entity_ids).intersection(parent.get('entity_ids',[])):return False
    if not visit_date and parent['source_kind']=='historical_notice':return False
    if visit_date:
        if parent.get('valid_from') and (end_date or visit_date)<parent['valid_from']:return False
        if parent.get('valid_to') and visit_date>parent['valid_to']:return False
    return True

def validity(parent,visit_date=None):
    if parent['source_kind']=='background':return 'background_only'
    if parent.get('collection_status')=='stale':return 'stale_snapshot'
    if visit_date and (parent.get('valid_from') or parent.get('valid_to')):return 'within_declared_scope'
    return 'visit_date_unverified'

def bm25(children,query):
    terms=tokens(query)
    if not terms or not children:return []
    counts=[Counter(tokens(c['index_text'])) for c in children];df=Counter(t for c in counts for t in c)
    avg=sum(sum(c.values()) for c in counts)/len(counts) or 1;scores=[]
    for child,count in zip(children,counts):
        length=sum(count.values());score=0
        for term in set(terms):
            frequency=count[term]
            if frequency:
                idf=math.log(1+(len(counts)-df[term]+.5)/(df[term]+.5))
                score+=idf*frequency*2.5/(frequency+1.5*(.25+.75*length/avg))
        if score>0:scores.append((child['id'],score))
    return sorted(scores,key=lambda x:(-x[1],x[0]))

def fuse(lexical,dense,k=60):
    totals=defaultdict(float)
    for results in (lexical,dense):
        for rank,(cid,_) in enumerate(results,1):totals[cid]+=1/(k+rank)
    return sorted(totals.items(),key=lambda x:(-x[1],x[0]))
