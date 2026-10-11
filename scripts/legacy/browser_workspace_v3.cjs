// Real account, LLM destination discovery, Amap POIs and selection. Hotel/transport layout checks use explicit UI fixtures.
const {chromium}=require('C:/Users/asus/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const assert=require('node:assert/strict'),crypto=require('node:crypto'),fs=require('node:fs');
const delay=ms=>new Promise(r=>setTimeout(r,ms));
(async()=>{
 const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
 const page=await browser.newPage({baseURL:'http://127.0.0.1:8767',viewport:{width:1440,height:1000}}),errors=[];
 page.on('pageerror',e=>errors.push(e.message));let session;
 const password=crypto.randomBytes(20).toString('base64url'),headers={Origin:'http://127.0.0.1:8767','Content-Type':'application/json'};
 const finish=async()=>{await page.waitForSelector('#progress[hidden]',{state:'attached',timeout:240000});const e=page.locator('#error:not([hidden])');if(await e.count())throw Error(await e.innerText());};
 const state=async()=>{const list=await(await page.request.get('/api/workspaces')).json();return await(await page.request.get('/api/workspaces/'+list.items[0].id)).json();};
 try{
  const reg=await page.request.post('/api/auth/register',{headers,data:{username:'qa_workbench_'+Date.now().toString(36),nickname:'新版工作台验证',password}});
  assert.equal(reg.status(),201);session=await reg.json();headers['X-CSRF-Token']=session.csrf_token;
  await page.goto('/');await page.waitForSelector('#application:not([hidden])');
  assert.equal(await page.locator('#suggestions').count(),0);
  assert.ok(await page.locator('.chat-panel').evaluate(el=>el.clientWidth)>await page.locator('.workspace').evaluate(el=>el.clientWidth),'桌面对话区应大于候选区');
  assert.match(await page.locator('.overview-note').innerText(),/自动更新/);
  await page.fill('#message','还没有确定目的地。请推荐几个不同类型的城市供我比较，先不要替我决定。');await page.click('#send');await finish();
  let w=await state();assert.equal(w.discovery_mode,true);assert.ok(w.destinations.length>=4);assert.ok(!w.requirements.city,'推荐城市不能自动替用户确定城市');
  assert.equal(await page.locator('.destination-card').count(),2);
  await page.locator('[data-destination-page="2"]').first().click();assert.equal(await page.locator('.destination-card').count(),2);
  await page.locator('[data-destination-page="1"]').first().click();
  assert.equal(await page.locator('#messages').innerText().then(t=>t.includes('\\n')),false);
  await page.screenshot({path:'.展示检查/重做-目的地推荐.png'});
  const qingdao=w.destinations.findIndex(d=>d.name==='青岛');
  if(qingdao>=2)await page.locator(`[data-destination-page="${Math.floor(qingdao/2)+1}"]`).first().click();
  await page.click('[data-destination="city:qingdao"]');await finish();
  w=await state();assert.equal(w.requirements.city,'青岛');assert.ok(w.spot_page.ids.length>0);assert.ok(w.spot_page.pages>=2,'真实候选应可翻页');
  const first=[...w.spot_page.ids];
  const displayed=await page.locator('[data-candidate]').evaluateAll(els=>els.map(e=>e.dataset.candidate));assert.deepEqual(displayed,first);
  assert.equal(await page.locator('.candidate-reason').allTextContents().then(rows=>rows.some(t=>/classic\s*[:=]|recommendation_rank/.test(t))),false,'推荐理由不能显示内部字段');
  assert.equal(await page.locator('#content [data-action="complete_spots"]').isDisabled(),true,'未选景点不可完成');
  await page.locator('[data-spots-page="2"]').first().click();await finish();w=await state();assert.ok(!first.some(id=>w.spot_page.ids.includes(id)),'下一页不能重复上一页');
  await page.locator('[data-spots-page="1"]').first().click();await finish();
  await page.locator(`[data-select="${first[0]}"]`).click();await finish();w=await state();assert.ok(w.selected_spots.includes(first[0]));
  assert.equal(await page.locator('.tabs [data-tab="spot"].active').count(),1);
  await page.screenshot({path:'.展示检查/重做-景点选择.png'});
  const rejectedBefore=w.spot_page.ids.filter(id=>!w.selected_spots.includes(id));
  await page.fill('#message','换一些，这一页其他景点我都不想去，已选的景点保留。');await page.click('#send');await finish();
  w=await state();assert.ok(w.selected_spots.includes(first[0]));assert.ok(rejectedBefore.every(id=>w.rejected_spots.includes(id)),'模型换一批动作应排除明确拒绝的候选');
  assert.ok(!rejectedBefore.some(id=>w.spot_page.ids.includes(id)));
  await page.locator('#content [data-action="complete_spots"]').click();await finish();
  w=await state();assert.equal(w.spots_confirmed,true);assert.equal(await page.locator('.tabs [data-tab="hotel"].active').count(),1);
  assert.match(await page.locator('#messages .message').last().innerText(),/已确认景点/);
  assert.match(await page.locator('.inline-requirements').innerText(),/出游日期/);
  await page.locator('[data-edit-field="start_date"]').click();assert.equal(await page.locator('#settings').isVisible(),true);
  assert.match(await page.locator('#settings h2').innerText(),/旅行信息/);await page.click('#close-settings');
  await page.reload();await page.waitForSelector('.tabs [data-tab="hotel"].active');
  console.log('通过：真实目的地推荐、选择青岛、高德景点排序/分页、自然语言换一批、保留已选、完成景点后进入住宿并说明缺项。');
  // Preserve the real workspace; these fixtures are displayed only in this isolated browser context.
  const fixture=JSON.parse(JSON.stringify(w));fixture.requirements={city:'青岛',origin:'上海',start_date:'2026-10-08',days:3,adults:2,budget:6000};
  fixture.catalog.h1={id:'h1',kind:'hotel',name:'布局检查住宿',address:'仅用于界面验证',price:320,anchor_name:'栈桥',anchor_route:{mode:'transit',minutes:20},recommendation:'界面测试：比较住宿位置与所选景点。'};
  fixture.ui={view:'hotel',status:'ready',title:'住宿推荐',message:'比较位置与房型',cta:{label:'查看住宿',view:'hotel'}};
  fixture.messages.push({role:'assistant',content:'第一段\\n\\n第二段：这是用于检查换行的界面响应。',ui:fixture.ui});
  fixture.active_job=null;
  await page.route('**/api/workspaces/'+w.id,r=>r.fulfill({json:fixture}));
  await page.reload();await page.waitForSelector('#application:not([hidden])');
  assert.equal(await page.locator('#messages').innerText().then(t=>t.includes('\\n')),false);
  for(const width of [390,768,1440]){
   await page.setViewportSize({width,height:1000});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'不能出现横向溢出');
   await page.screenshot({path:`.展示检查/重做-住宿-${width}.png`});
  }
  assert.deepEqual(errors,[]);
  fs.writeFileSync('data/runtime/browser-workspace-v3.json',JSON.stringify({passed:true,real_calls:['llm-discover','amap-spots','llm-ranking','llm-replace-intent'],real_steps:['destination','pagination','selection','replacement','completion','missing-information','refresh'],ui_fixture:['escaped-newlines','hotel-layout'],widths:[390,768,1440],page_errors:errors},null,2));
  console.log('通过：换行兼容、对话优先布局、旅行信息入口、390/768/1440宽度；无页面脚本异常。');
 }finally{
  await page.unrouteAll({behavior:'wait'});
  if(session){const list=await(await page.request.get('/api/workspaces')).json();for(const i of list.items||[]){const w=await(await page.request.get('/api/workspaces/'+i.id)).json();if(w.active_job){await page.request.post('/api/jobs/'+w.active_job.id+'/cancel',{headers,data:{}});await delay(1500);}}const deleted=await page.request.delete('/api/account',{headers,data:{password}});assert.equal(deleted.status(),200,'测试账户需清理');}
  await browser.close();
 }
})().catch(e=>{console.error(e.message);process.exitCode=1});
