"""Dated visit intentions: suggestions are flexible, user requests are checked."""
from datetime import date,timedelta
import re
from .providers import DataError

PERIODS={'any':'时段不限','morning':'上午','afternoon':'下午','evening':'晚上'}

def dates(w):
 r=w['requirements']
 return [(date.fromisoformat(r['start_date'])+timedelta(days=i)).isoformat() for i in range(int(r.get('days') or 1))] if r.get('start_date') else []

def save(w,requests,order=None):
 valid=dates(w);current=dict(w.get('visit_requests',{}));messages=[]
 for req in requests:
  cid=req.get('candidate_id');p=w['catalog'].get(cid)
  if not p or p.get('kind')!='spot':raise DataError('请使用当前候选中的景点设置游玩日期。')
  if req.get('clear'):current.pop(cid,None);continue
  dt=req.get('date');period=req.get('period','any')
  if dt not in valid or period not in PERIODS:raise DataError('请选择游玩日期范围内的日期和有效时段。')
  current[cid]={'date':dt,'period':period};messages.append(p['name']+'：'+dt+' '+PERIODS[period])
 if order is not None:
  if not isinstance(order,list) or any(not isinstance(cid,str) for cid in order) or len(order)!=len(set(order)) or any(cid not in w.get('selected_spots',[]) for cid in order):raise DataError('调整顺序必须使用已选景点的真实ID，且不可重复。')
  w['visit_order']=order
  messages.append('优先顺序：'+' → '.join(w['catalog'][cid]['name'] for cid in order))
 w['visit_requests']=current
 # 景点改期/移除后重算受影响餐次：固定日期餐次不动，明确跟随的只提示不挪期。
 from . import foods
 affected=foods.bindings_clear_or_mark(w)
 messages.extend(affected)
 if w.get('plan'):w['plan']['stale']=True
 return '已记录游玩安排：'+('；'.join(messages) or '恢复由助手安排')+'。生成或重排时会按这些要求核对日期与时段，若时间或交通冲突会说明。'

def from_text(w,text):
 if re.search('吃饭|吃午餐|吃晚餐|吃早餐|用餐|餐厅|餐馆|住宿|酒店|车票|高铁|返程',text) and not re.search('游玩|游览|逛|参观|夜游',text):return []
 if len(re.findall(r'第[一二三四五六七八九十\d]+天|(?:\d{1,2}月)?\d{1,2}[号日]',text))>1:return []
 ds=dates(w)
 if not ds:return []
 match=re.search(r'第([一二三四五六七八九十\d]+)天',text);dt=None
 if match:
  s=match.group(1);num=int(s) if s.isdigit() else {'一':1,'二':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9,'十':10}.get(s,0)
  if 1<=num<=len(ds):dt=ds[num-1]
 else:
  m=re.search(r'(?:(\d{1,2})月)?(\d{1,2})[号日]',text)
  if m:dt=next((d for d in ds if int(d[-2:])==int(m[2]) and (not m[1] or int(d[5:7])==int(m[1]))),None)
 if not dt:return []
 period='evening' if re.search('晚上|晚间|夜游',text) else 'afternoon' if '下午' in text else 'morning' if re.search('上午|早上',text) else 'any'
 matches=[p for p in w['catalog'].values() if p.get('kind')=='spot' and len(p['name'])>1 and p['name'] in text]
 # Parent/sub-place names can overlap: only use the longest explicit match.
 matches=[p for p in matches if not any(p['name']!=q['name'] and p['name'] in q['name'] for q in matches)]
 return [{'candidate_id':p['id'],'date':dt,'period':period} for p in matches]

def meal_refs(w,dt,period):
 ds=dates(w);catalog=w['catalog'];items=[catalog[i] for i in w.get('selected_spots',[]) if i in catalog]
 chosen=[]
 for p in items:
  intent=w.get('visit_requests',{}).get(p['id']) or p.get('visit_suggestion') or {}
  if intent.get('date')==dt:chosen.append((p,intent.get('period','any')))
 if not chosen and dt in ds and items:
  # Provisional grouping only, before the actual plan exists.
  n=max(1,(len(items)+len(ds)-1)//len(ds));index=ds.index(dt);chosen=[(p,'any') for p in items[index*n:(index+1)*n]]
 target=('morning','any') if period=='lunch' else ('afternoon','evening','any')
 return [p for p,s in chosen if s in target] or [p for p,s in chosen]
