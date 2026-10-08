"""Isolated live intent checks; calls only the LLM, never travel suppliers."""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import agent,storage
from app.goal_agent import mission,start,observation,continue_goal
from app.request_cache import close


async def main():
    storage.DB=storage.RUNTIME/'goal-intent-check.db';storage.init()
    cases=[('直接给我在合理的情况下随机生成一份旅游计划','delegate'),
           ('我不想逐项挑了，按我的要求把剩下的细节安排妥当','delegate'),
           ('先给我一些方向参考，我自己挑，暂时别帮我决定','consult')]
    results=[]
    try:
        for text,expected in cases:
            w={'id':'isolated-intent','requirements':{},'catalog':{},'selected_spots':[],'messages':[]}
            try:
                value=await agent.understand({'workspace':w,'text':text,'progress':lambda _:None})
                goal=mission(value.get('intent') or {})
                result={'text':text,'expected':expected,'mode':goal['mode'] if goal else None,
                        'action':(value.get('intent') or {}).get('action'),'passed':bool(goal and goal['mode']==expected)}
            except Exception as error:result={'text':text,'expected':expected,'passed':False,'error_type':type(error).__name__}
            results.append(result);print(json.dumps(result,ensure_ascii=False),flush=True)
        calls=[];decisions=[]
        w={'id':'isolated-tool-loop','requirements':{'city':'青岛','start_date':'2026-10-12','days':3,'adults':1},
           'catalog':{'s':{'id':'s','kind':'spot','name':'栈桥','location':'120.3,36.0'}},'selected_spots':['s'],
           'last_question':'核对10月12日天气，然后查询栈桥附近的午餐餐厅。这里只做接口流程验证。'}
        start(w,{'mission':{'mode':'query','objective':w['last_question'],'multi_step':True}})
        first=observation(w,'weather',{},'合成验证结果：所问日期超出预报覆盖，不能提供该日天气；仍可以查询午餐。')
        async def fixture_handle(workspace,name,args,progress):
            if name!='search_foods':raise agent.DataError('此验证仅提供合成餐饮查询，其他能力没有合成结果。')
            calls.append(name);workspace['catalog']['f']={'id':'f','kind':'food','name':'验证餐厅A','source':{'name':'合成测试数据'}}
            workspace['food_query']={'ids':['f'],'meal_date':'2026-10-12','meal_period':'lunch'}
            return '合成查询返回验证餐厅A，特色是本地菜；价格、营业状态未提供，未保存餐厅选择。'
        async def live_decide(*args,**kwargs):
            value=await agent.llm(*args,**kwargs)
            decisions.extend(c['function']['name'] for c in value[0].get('tool_calls',[]))
            return value
        try:
            await continue_goal(w,first,live_decide,fixture_handle,lambda _:None)
            result={'case':'live-LLM-synthetic-tool-continuation','supplier_data':'fixture','tools':calls,
                    'decisions':decisions,'status':w['assistant_goal']['status'],
                    'passed':calls==['search_foods'] and decisions[-1:] == ['finish_request'] and w['assistant_goal']['status'] in ('partial','needs_info')}
        except Exception as error:result={'case':'live-LLM-synthetic-tool-continuation','passed':False,'error_type':type(error).__name__}
        results.append(result);print(json.dumps(result,ensure_ascii=False),flush=True)
    finally:await close()
    (storage.RUNTIME/'goal-intent-check.json').write_text(json.dumps({'isolated':True,'results':results},ensure_ascii=False,indent=2),encoding='utf-8')
    if not all(r['passed'] for r in results):raise SystemExit(1)


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    asyncio.run(main())
