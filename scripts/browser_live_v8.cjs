const {chromium}=require('C:/Users/asus/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const assert=require('node:assert/strict'),crypto=require('node:crypto'),fs=require('node:fs');
(async()=>{
 const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
 const p=await browser.newPage({viewport:{width:1600,height:1000}}),base='http://127.0.0.1:8767',password=crypto.randomBytes(24).toString('base64url'),headers={Origin:base,'Content-Type':'application/json'},errors=[];
 p.on('pageerror',e=>errors.push(e.message));let session,wid;
 const state=async()=>await(await p.request.get(base+'/api/workspaces/'+wid)).json();
 const act=async(action,args={})=>{const w=await state(),r=await p.request.post(base+'/api/workspaces/'+wid+'/actions',{headers,data:{revision:w.revision,action,args,request_id:crypto.randomUUID()}});assert.equal(r.status(),202);const {job_id}=await r.json();for(let i=0;i<2400;i++){const j=await(await p.request.get(base+'/api/jobs/'+job_id)).json();if(j.status!=='running'){assert.equal(j.status,'completed',j.error||'任务失败');return j.workspace}await p.waitForTimeout(100)}throw Error('任务等待超时')};
 const chat=async text=>{await p.fill('#message',text);await p.click('#send');await p.waitForSelector('#progress[hidden]',{state:'attached',timeout:240000});assert.equal(await p.locator('#error:not([hidden])').count(),0);return state()};
 try{
  const r=await p.request.post(base+'/api/auth/register',{headers,data:{username:'qa_v8_'+Date.now().toString(36),nickname:'新版检查',password}});assert.equal(r.status(),201);session=await r.json();headers['X-CSRF-Token']=session.csrf_token;
  await p.goto(base);await p.waitForSelector('#application:not([hidden])');wid=(await(await p.request.get(base+'/api/workspaces')).json()).items[0].id;
  await act('requirements',{patch:{city:'杭州',origin:'杭州',start_date:'2026-10-10',days:3,adults:1}});await p.reload();await p.waitForSelector('#application:not([hidden])');
  let w=await chat('请推荐杭州适合轻松游玩的代表景点，结合10月10日至12日分为白天和晚上，简单说一下适合的日期时段和原因。');
  assert.equal(w.messages[0].type,'welcome');assert.match(await p.locator('#messages').innerText(),/欢迎使用识途/);
  const spots=Object.values(w.catalog).filter(s=>s.kind==='spot'&&s.location),s=spots.find(s=>s.photos?.length)||spots[0];assert.ok(s);assert.ok(spots.some(s=>s.visit_suggestion));
  await act('select',{id:s.id});await p.reload();await p.waitForSelector('#application:not([hidden])');
  w=await chat('我想第二天上午去'+s.name+'，请记录这个安排，暂时不用重新查询景点。');assert.deepEqual(w.visit_requests[s.id],{date:'2026-10-11',period:'morning'});assert.equal(w.requirements.start_date,'2026-10-10');
  await p.evaluate(id=>openCandidate(id),s.id);await p.waitForSelector('#candidate-dialog[open]');const image=await p.request.get(base+'/api/workspaces/'+wid+'/map-image?focus='+encodeURIComponent(s.id));assert.equal(image.status(),200);assert.match(image.headers()['content-type'],/image/);await p.screenshot({path:'.展示检查/真实-v8-景点详情与底图.png'});await p.keyboard.press('Escape');
  w=await act('plan');const e=w.plan.days.find(d=>d.date==='2026-10-11').events.find(e=>e.candidate_id===s.id);assert.ok(e);assert.ok(e.start<'12:00');assert.match(w.messages.at(-1).content,/查看|调整/);assert.doesNotMatch(w.messages.at(-1).content,/下一步[：:]*.*生成.*计划/);
  await p.reload();await p.waitForSelector('#application:not([hidden])');await p.click('#map-button');await p.selectOption('#map-day','2026-10-11');await p.screenshot({path:'.展示检查/真实-v8-每日地图.png'});
  w=await act('search_foods',{meal_date:'2026-10-11',meal_period:'lunch'});assert.ok(w.food_query.anchors.some(a=>a.id===s.id));assert.ok(w.food_query.ids.every(id=>w.catalog[id].recommendation_basis));
  assert.deepEqual(errors,[]);fs.writeFileSync('data/runtime/browser-live-v8.json',JSON.stringify({passed:true,real_calls:['llm-intent','amap-poi','llm-recommendation','native-streamed-reply','amap-static-map','plan-proposal-and-review','amap-food-near-dated-spot'],checks:['persistent-welcome','dated-suggestions','explicit-visit-day','unchanged-trip-start','actual-day-and-morning-plan','review-guidance','authenticated-main-and-detail-map','day-lunch-anchor'],errors},null,2));console.log('LIVE V8 PASSED');
 }finally{
  if(session){if(wid){const w=await state();if(w.active_job){await p.request.post(base+'/api/jobs/'+w.active_job.id+'/cancel',{headers,data:{}});await p.waitForTimeout(1500)}}const d=await p.request.delete(base+'/api/account',{headers,data:{password}});assert.equal(d.status(),200)}await browser.close();
 }
})().catch(e=>{console.error(e.message);process.exitCode=1});
