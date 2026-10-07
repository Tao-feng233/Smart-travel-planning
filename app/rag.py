"""Local character TF-IDF vector retrieval + keyword score, with provenance.

No external embedding key required. These lexical vectors do not claim semantic
embedding quality. Swap this retriever once actual retrieval failures justify it.
"""
import json, re, math
from collections import Counter
from functools import lru_cache
from .config import ROOT

def tokens(text):
    s=''.join(re.findall(r'[\w\u4e00-\u9fff]+',text.lower()))
    return [s[i:i+2] for i in range(max(0,len(s)-1))]

@lru_cache(maxsize=1)
def index():
    docs=[]
    for p in (ROOT/'data/knowledge').glob('*.json'): docs+=json.loads(p.read_text(encoding='utf-8'))
    counts=[Counter(tokens(d['text']+' '+d['title'])) for d in docs]
    df=Counter(t for c in counts for t in c)
    idf={t:math.log((len(docs)+1)/(n+1))+1 for t,n in df.items()}
    vectors=[{t:(1+math.log(n))*idf[t] for t,n in c.items()} for c in counts]
    norms=[math.sqrt(sum(v*v for v in c.values())) for c in vectors]
    return docs,idf,vectors,norms

def retrieve(city,query,limit=5):
    docs,idf,vectors,norms=index()
    q={t:(1+math.log(n))*idf.get(t,1) for t,n in Counter(tokens(query)).items()}
    norm=math.sqrt(sum(x*x for x in q.values())) or 1
    words=[x for x in re.split(r'[\s，、；。]+',query) if len(x)>1]
    scored=[]
    for d,v,n in zip(docs,vectors,norms):
        if city and d['city'] not in city and city not in d['city']: continue
        score=sum(val*v.get(t,0) for t,val in q.items())/(norm*(n or 1))
        score+=min(0.3,sum(0.06 for w in words if w in d['text']))
        if score>0.035: scored.append({**d,'score':round(score,3),'retrieval':'本地 TF-IDF 向量 + 关键词重排'})
    return sorted(scored,key=lambda x:-x['score'])[:limit]
