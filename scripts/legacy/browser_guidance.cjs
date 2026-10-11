// Real account + one real LLM topic conversation; query/result scenarios below are explicit UI fixtures.
const { chromium } = require('C:/Users/asus/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const assert = require('node:assert/strict'), crypto = require('node:crypto'), fs = require('node:fs');
const delay = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  const browser = await chromium.launch({ executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe', headless:true });
  const page = await browser.newPage({ baseURL:'http://127.0.0.1:8767', viewport:{width:1440,height:1000} });
  const password = crypto.randomBytes(20).toString('base64url');
  const headers = {Origin:'http://127.0.0.1:8767','Content-Type':'application/json'};
  const errors=[];page.on('pageerror',e=>errors.push(e.message));let session,realJob;
  try {
    const reg=await page.request.post('/api/auth/register',{headers,data:{username:'qa_guide_'+Date.now().toString(36),nickname:'引导体验检查',password}});
    assert.equal(reg.status(),201);session=await reg.json();headers['X-CSRF-Token']=session.csrf_token;
    await page.goto('/');await page.waitForSelector('#application:not([hidden])');
    let w=await(await page.request.get('/api/workspaces/latest')).json();
    await page.fill('#message','这里只解释怎么选酒店，不要查询任何外部数据。请讲两句住宿位置该怎么考虑，下一步由我选择景点。');await page.click('#send');
    await page.waitForSelector('#progress:not([hidden])');
    await page.waitForSelector('#progress[hidden]',{state:'attached',timeout:240000});
    w=await(await page.request.get('/api/workspaces/'+w.id)).json();
    realJob=w.active_job?.id;
    assert.equal(w.ui.view,'hotel','真实模型解释住宿时应声明住宿主题');
    assert.equal(await page.locator('.tabs [data-tab="hotel"]').getAttribute('class'),'active');
    assert.match(await page.locator('#messages .reply-guide').innerText(),/先选景点/);
    console.log('通过：一次真实LLM解释对话，工作台跟随住宿话题，回复附带下一步按钮。');
    w.requirements={city:'青岛',origin:'上海',days:3,adults:2,start_date:new Date(Date.now()+2*86400000).toISOString().slice(0,10)};
    w.ui=null;w.messages=[];w.selected_spots=[];w.catalog={};w.active_job=null;
    let fixtureJob=null,reads=0,number=0;
    const guide=(view,title,message,cta,status='ready',action='chat')=>({view,title,message,cta,status,action});
    await page.route('**/api/workspaces/'+w.id,r=>r.fulfill({json:w}));
    await page.route('**/api/workspaces/'+w.id+'/actions',async route=>{
      const body=route.request().postDataJSON();let action=body.action;
      if(action==='chat')action=body.text.includes('天气')?'weather':'search_spots';
      const args=body.args||{};let view={search_spots:'spot',search_hotels:'hotel',train:'transport',weather:'weather',ticket:'spot',plan:'plan'}[action];
      if(action==='select')view={hotel:'hotel',spot:'spot',train:'transport'}[w.catalog[args.id].kind];
      const pending=guide(view,'正在查询'+view,'正在处理本轮需求；已有选择保留。',null,'loading',action);
      if(body.text)w.messages.push({role:'user',content:body.text});
      fixtureJob={id:'ui-guide-'+(++number),status:'running',progress:'正在读取数据并比较',action:body.action,ui:pending};reads=0;
      fixtureJob.complete=()=>{
        let ui;
        if(action==='search_spots'){
          for(const [id,name] of [['s1','栈桥'],['s2','八大关']])w.catalog[id]={id,name,kind:'spot',address:'界面测试地址'};
          ui=guide('spot','一起选想去的地方','在{位置}景点卡片点“想去这里”，选好后再比较住宿。',{label:'去选景点',view:'spot'},'ready',action);
        }else if(action==='select'){
          const p=w.catalog[args.id];
          if(p.kind==='hotel'){w.hotel=p;ui=guide('hotel','住宿已选定','住宿已保存，下一步比较往返交通。',{label:'比较往返交通',view:'transport'},'ready',action)}
          else if(p.kind==='spot'){w.selected_spots.push(p.id);ui=guide('spot','已选 '+w.selected_spots.length+' 个景点','可以继续比较景点，选好后再查住宿。',{label:'选好了，比较住宿',action:'search_hotels'},'ready',action)}
          else{w[p.direction==='return'?'selected_return':'selected_transport']=p;ui=guide('transport','班次选择已保存','可以继续比较另一方向班次，或整理计划。',w.selected_transport&&w.selected_return?{label:'整理计划书',action:'plan'}:{label:'继续比较往返交通',view:'transport'},'ready',action)}
        }else if(action==='search_hotels'){
          w.catalog.h1={id:'h1',name:'测试住宿',kind:'hotel',address:'仅为界面测试',price:300};
          ui=guide('hotel','比较适合这趟旅行的住宿','在{位置}比较酒店，点“选这家住宿”。',{label:'去选住宿',view:'hotel'},'ready',action);
        }else if(action==='train'){
          const id=args.direction==='return'?'t2':'t1';w.catalog[id]={id,kind:'train',direction:args.direction||'outbound',name:'测试列车',departure:'09:00',arrival:'13:00',seat_label:'界面测试状态'};w.transport={items:[w.catalog[id]]};
          ui=guide('transport','比较往返时间与班次','在{位置}交通卡片点“选这个班次”。',{label:'查看往返交通',view:'transport'},'ready',action);
        }else if(action==='weather'){
          w.weather={days:[],alerts:[],attributions:[]};ui=guide('weather','查看旅行日期的天气','在{位置}核对预报覆盖日期。',{label:'查看天气',view:'weather'},'ready',action);
        }else if(action==='ticket'){
          ui=guide('spot','本轮尚未完成','日期尚未确认，请先补充条件。',{label:'检查旅行条件',settings:true},'failed',action);
        }else if(action==='plan'){
          w.plan={title:'界面检查旅行计划书',summary:'测试场景，不是真实行程',created:new Date().toISOString(),days:[{date:w.requirements.start_date,theme:'界面测试',events:[]}],budget:{hotel_reference:300,unknown:[]},todos:[],packing:[],warnings:[],guides:[],review:{summary:'界面检查',issues:[]}};
          ui=guide('plan','一起确认旅行计划书','在{位置}查看每日安排，不合适的地方可以在对话中告诉我。',{label:'查看完整计划书',view:'plan'},'ready',action);
        }
        w.ui=ui;w.last_action=action;w.revision++;w.messages.push({role:'assistant',content:'本轮处理结果（界面测试）',ui});
        return {status:ui.status==='failed'?'failed':'completed',action:body.action,ui,workspace:w,error:ui.status==='failed'?ui.message:null};
      };
      await route.fulfill({json:{job_id:fixtureJob.id}});
    });
    await page.route('**/api/jobs/ui-guide-*',r=>r.fulfill({json:++reads<4?fixtureJob:fixtureJob.complete()}));
    await page.reload();await page.waitForSelector('#application:not([hidden])');
    const finished=async()=>{await page.waitForSelector('#progress[hidden]',{state:'attached',timeout:15000});await page.waitForSelector('#messages .reply-guide');};
    await page.locator('.tabs [data-tab="hotel"]').click();
    await page.fill('#message','请介绍景点供我选择');await page.click('#send');
    await page.waitForSelector('.tabs [data-tab="spot"].active');
    assert.equal(await page.locator('#progress').isVisible(),true,'景点查询结束前就应切换场景');
    assert.match(await page.locator('#scene-feedback').innerText(),/正在/);await finished();
    assert.equal(await page.locator('[data-candidate]').count(),2);
    assert.match(await page.locator('#messages .reply-guide').innerText(),/右侧.*想去这里/);
    await page.click('[data-select="s1"]');await finished();
    assert.equal(await page.locator('.tabs [data-tab="spot"].active').count(),1,'选一个景点不能自动离开景点页');
    assert.match(await page.locator('#scene-feedback').innerText(),/已选 1/);
    await page.locator('#messages .reply-guide [data-action="search_hotels"]').click();
    assert.equal(await page.locator('.tabs [data-tab="hotel"].active').count(),1);
    assert.match(await page.locator('#scene-feedback').innerText(),/正在/);await finished();
    assert.match(await page.locator('#messages .reply-guide').innerText(),/选这家住宿/);
    await page.screenshot({path:'.展示检查/真实-引导-住宿场景.png'});
    await page.click('[data-select="h1"]');await finished();
    await page.locator('#messages .reply-guide [data-tab="transport"]').click();
    await page.locator('#content [data-action="train"]').first().click();await finished();
    assert.equal(await page.locator('.tabs [data-tab="transport"].active').count(),1);
    await page.click('[data-select="t1"]');await finished();
    await page.locator('#content [data-action="train"][data-direction="return"]').click();await finished();
    await page.click('[data-select="t2"]');await finished();
    assert.equal(await page.locator('#messages .reply-guide [data-action="plan"]').count(),1);
    await page.fill('#message','看看天气');await page.click('#send');await page.waitForSelector('.tabs [data-tab="weather"].active');assert.equal(await page.locator('#progress').isVisible(),true);await finished();
    await page.reload();await page.waitForSelector('.tabs [data-tab="weather"].active');
    await page.locator('.tabs [data-tab="spot"]').click();await page.locator('[data-ticket="s1"]').click();await finished();
    assert.match(await page.locator('#scene-feedback').innerText(),/本轮尚未完成/);
    await page.locator('#messages .reply-guide [data-open-settings]').click();assert.equal(await page.locator('#settings').isVisible(),true);await page.click('#close-settings');
    for(const width of [390,768,1440]){await page.setViewportSize({width,height:1000});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'不能出现横向溢出');}
    await page.locator('.tabs [data-tab="plan"]').click();await page.locator('#content [data-action="plan"]').click();
    assert.match(await page.locator('#scene-feedback').innerText(),/正在/);await finished();
    assert.match(await page.locator('#messages .reply-guide').innerText(),/每日安排/);
    await page.reload();await page.waitForSelector('.tabs [data-tab="plan"].active');
    assert.deepEqual(errors,[]);
    fs.writeFileSync('data/runtime/browser-guidance.json',JSON.stringify({passed:true,real_llm_topic:true,ui_fixtures:['pending-topic-switch','spot-selection','hotel-selection','transport-selection','weather','plan','refresh','failure-recovery'],widths:[390,768,1440],page_errors:errors},null,2));
    console.log('通过：查询期间场景切换、回复按钮、景点选择反馈、住宿与交通引导、天气、刷新、失败恢复、手机布局（UI模拟查询场景）。');
  }finally{
    await page.unrouteAll({behavior:'wait'});
    if(session){
      const list=await(await page.request.get('/api/workspaces')).json();
      for(const item of list.items||[]){const w=await(await page.request.get('/api/workspaces/'+item.id)).json();if(w.active_job){await page.request.post('/api/jobs/'+w.active_job.id+'/cancel',{headers,data:{}});await delay(1500);}}
      const deleted=await page.request.delete('/api/account',{headers,data:{password}});assert.equal(deleted.status(),200,'测试账户必须清理');
    }
    await browser.close();
  }
})().catch(e=>{console.error(e.message);process.exitCode=1});
