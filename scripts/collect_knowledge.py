"""Small, reproducible official-source collection. No generated facts."""
import json, sys, re, time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import httpx
from bs4 import BeautifulSoup
from app.config import ROOT
from app.storage import now

SOURCES=[
 ('青岛市政府：旅游景点','https://www.qingdao.gov.cn/yfqd/qdwl/cjfw/wyqtsjd/',['栈桥','八大关','五四广场','小鱼山','奥帆','博物馆','崂山','海水浴场']),
 ('青岛市博物馆：参观指南','https://www.qingdaomuseum.com/visit',['博物馆','开放','预约','入馆','周一','闭馆','票']),
 ('青岛市博物馆：免费开放服务','https://www.qingdaomuseum.com/service/free',['博物馆','开放','预约','入馆','周一','闭馆','票']),
 ('崂山风景区：官方信息','https://qdlaoshan.cn/Index-index.html',['崂山','开放','预约','门票','游览','景区']),
]

def main():
    records=[]; log=[]
    for title,url,terms in SOURCES:
        try:
            r=httpx.get(url,timeout=20,follow_redirects=True)
            r.raise_for_status()
            r.encoding='utf-8'
            soup=BeautifulSoup(r.text,'html.parser')
            for x in soup(['script','style','nav','header','footer']): x.decompose()
            main=soup.find('article') or soup
            lines=[re.sub(r'\s+',' ',x).strip() for x in main.get_text('\n',strip=True).splitlines()]
            seen=set(); kept=0
            for i,line in enumerate(lines):
                if any(t in line for t in terms):
                    text=' '.join(lines[max(0,i-1):i+4])[:550]
                    if text in seen or len(text)<20: continue
                    seen.add(text); kept+=1
                    records.append({'id':f'qd-{len(records)+1}','city':'青岛','title':title,'url':str(r.url),
                                    'fetched_at':now(),'published_at':None,'text':text,
                                    'category':'官方页面片段','date_scope':'页面快照，出游当日规则仍需核实'})
                    if kept>=12: break
            log.append({'url':url,'status':r.status_code,'chunks':kept})
        except Exception as e: log.append({'url':url,'error_type':type(e).__name__})
    dest=ROOT/'data/knowledge'; dest.mkdir(parents=True,exist_ok=True)
    (dest/'qingdao.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'sources':log,'chunks':len(records)},ensure_ascii=False))

if __name__=='__main__':main()
