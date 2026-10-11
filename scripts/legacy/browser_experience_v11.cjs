const {chromium}=require('C:/Users/asus/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const assert=require('node:assert/strict'),fs=require('node:fs');
(async()=>{
 const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});const p=await browser.newPage({viewport:{width:1500,height:1000}}),errors=[],calls=[];p.on('pageerror',e=>errors.push(e.stack));
 let w=JSON.parse(fs.readFileSync('data/runtime/browser-v11-fixture.json','utf8')),request,jid=0;
 const svg=(width,height)=>'<svg xmlns="http://www.w3.org/2000/svg" width="'+width+'" height="'+height+'"><rect width="100%" height="100%" fill="#c9dbe8"/></svg>';
 await p.route('**://store.is.autonavi.com/fixture.jpg',r=>r.fulfill({contentType:'image/svg+xml',body:svg(800,600)}));
 await p.route('https://m.tuniucdn.com/**',r=>{if(r.request().url().endsWith('low.jpg'))return r.fulfill({status:404,body:''});const low=r.request().url().includes('_w180_');return r.fulfill({contentType:'image/svg+xml',body:svg(low?180:1200,low?180:800)})});
 await p.route('**/api/**',async r=>{const url=r.request().url();let data;
  if(url.includes('/map-image'))return r.fulfill({contentType:'image/svg+xml',body:svg(1024,768)});
  if(url.includes('/auth/me'))data={user:{id:'qa',nickname:'检查'},csrf_token:'fixture'};
  else if(url.includes('/actions')){request=r.request().postDataJSON();calls.push(request);data={job_id:'j'+(++jid)}}
  else if(url.includes('/events')){await new Promise(resolve=>setTimeout(resolve,140));const a=request.action,args=request.args;w.revision++;w.ui={action:a,status:'ready',view:a==='plan'?'plan':'food'};
   if(a==='meal_choice'){w.meal_choices[args.meal_date+'|'+args.meal_period]={mode:args.meal_mode,food_id:args.food_id};for(const e of w.timeline.entries)if(e.key===args.meal_date+'|'+args.meal_period){e.confirmed=true;e.candidate_id=args.food_id;e.name='用餐 · '+w.catalog[args.food_id]?.name}}
   if(a==='search_foods')w.food_query={ids:['f'],meal_date:args.meal_date,meal_period:args.meal_period,anchor:args.meal_date==='2026-10-13'?'八大关':'栈桥',scope:'周边5公里'};
   if(a==='plan'){w.plan={title:'旅行计划',created:'2026-10-07',stale:false,days:[{date:'2026-10-12',events:[{kind:'route',name:'前往景点',start:'09:00',end:'09:20',options:[],route:{polylines:['120.313,36.061;120.32,36.06'],mode:'walking',minutes:20,distance:1200},buffer:0},{kind:'spot',candidate_id:'a',name:'栈桥',start:'09:20',end:'10:20'}]}],packing:[],warnings:[],todos:[],guides:[],budget:{unknown:[]}};w.next_step={message:'请查看计划书，直接发送消息调整',view:'plan'};w.messages.push({role:'assistant',content:'旅行计划书已生成，请查看右侧。'})}
   return r.fulfill({contentType:'text/event-stream',body:'event: done\ndata: '+JSON.stringify({id:'j'+jid,action:a,status:'completed',ui:w.ui,workspace:w})+'\n\n'});
  }else if(url.endsWith('/workspaces'))data={items:[{id:w.id,title:w.title,updated:'2026-10-07'}]};else data=w;
  await r.fulfill({contentType:'application/json',body:JSON.stringify(data)});
 });
 const idle=()=>p.waitForFunction(()=>!busy);
 try{
  await p.goto('http://127.0.0.1:8767/');await p.waitForSelector('#application:not([hidden])');await p.waitForTimeout(300);
  assert.equal(await p.locator('#selection-minimap').isVisible(),true);assert.match(await p.locator('.food-specialties').innerText(),/青岛菜.*海鲜水饺/);
  assert.equal(await p.locator('#messages [data-action="plan"]').count(),1);
  await p.evaluate(()=>openCandidate('h'));await p.waitForSelector('#candidate-dialog .place-photos img');await p.waitForFunction(()=>document.querySelector('#candidate-dialog .place-photos img').naturalWidth===1200);
  const image=await p.locator('#candidate-dialog .place-photos img').first().evaluate(i=>({src:i.src,w:i.getBoundingClientRect().width,h:i.getBoundingClientRect().height,fit:getComputedStyle(i).objectFit}));assert.ok(!image.src.includes('_w180_'));assert.equal(image.fit,'contain');assert.ok(image.w<=560&&image.h<=290);
  const points=JSON.parse(await p.locator('#candidate-dialog #candidate-modal-body .location-map').getAttribute('data-map-points'));assert.deepEqual(points.map(x=>x.id).sort(),['a','b','h']);assert.equal(await p.locator('#candidate-modal-body .location-map').getAttribute('data-map-focus'),'h');
  assert.equal(await p.locator('#candidate-dialog #selection-minimap').count(),1);
  const before=await p.locator('#selection-minimap').boundingBox(),handle=await p.locator('.mini-handle').boundingBox();await p.mouse.move(handle.x+60,handle.y+12);await p.mouse.down();await p.mouse.move(handle.x+160,handle.y-45,{steps:5});await p.mouse.up();const after=await p.locator('#selection-minimap').boundingBox();assert.ok(after.x-before.x>80);
  await p.click('#mini-collapse');assert.equal(await p.locator('#mini-expand').isVisible(),true);
  const icon=await p.locator('#selection-minimap').boundingBox();assert.equal(icon.width,48);assert.equal(icon.height,48);assert.equal(await p.locator('#mini-expand svg').count(),1);
  await p.mouse.move(icon.x+24,icon.y+24);await p.mouse.down();await p.mouse.move(2,2,{steps:8});await p.mouse.up();await p.waitForTimeout(100);
  assert.equal(await p.locator('#selection-minimap').evaluate(e=>e.classList.contains('collapsed')),true,'拖动结束不能误触展开');let corner=await p.locator('#selection-minimap').boundingBox();assert.equal(corner.x,0);assert.equal(corner.y,0);
  await p.screenshot({path:'.展示检查/地图图标-收起后可拖到顶部.png'});
  await p.mouse.move(corner.x+24,corner.y+24);await p.mouse.down();await p.mouse.move(1498,998,{steps:8});await p.mouse.up();await p.waitForTimeout(100);corner=await p.locator('#selection-minimap').boundingBox();assert.equal(corner.x+corner.width,1500);assert.equal(corner.y+corner.height,1000);assert.equal(await p.locator('#mini-expand').isVisible(),true);
  await p.click('#mini-expand');assert.equal(await p.locator('.mini-body').isVisible(),true);let expanded=await p.locator('#selection-minimap').boundingBox();assert.ok(expanded.x>=0&&expanded.y>=0&&expanded.x+expanded.width<=1500&&expanded.y+expanded.height<=1000);
  const topHandle=await p.locator('.mini-handle').boundingBox();await p.mouse.move(topHandle.x+30,topHandle.y+12);await p.mouse.down();await p.mouse.move(1,1,{steps:8});await p.mouse.up();expanded=await p.locator('#selection-minimap').boundingBox();assert.equal(expanded.x,0);assert.equal(expanded.y,0);
  await p.locator('.mini-handle').focus();await p.keyboard.press('ArrowRight');assert.equal((await p.locator('#selection-minimap').boundingBox()).x,20);
  await p.evaluate(()=>moveMini(88,550));
  await p.screenshot({path:'.展示检查/新版-v11-酒店原图与浮动地图.png'});await p.keyboard.press('Escape');await p.waitForSelector('#application #selection-minimap');assert.equal(await p.locator('#application #selection-minimap').count(),1);
  await p.evaluate(()=>openCandidate('f'));await p.waitForFunction(()=>document.querySelector('#candidate-dialog .place-photos img')?.dataset.photoRetried==='true');await p.waitForFunction(()=>document.querySelector('#candidate-dialog .place-photos img')?.naturalWidth===180);assert.match(await p.locator('#candidate-dialog figcaption').innerText(),/180×180/);const low=await p.locator('#candidate-dialog .place-photos img').boundingBox();assert.ok(low.width<=180);await p.keyboard.press('Escape');
  await p.evaluate(()=>{workspace.catalog.a.photos=['http://store.is.autonavi.com/fixture.jpg'];openCandidate('a')});await p.waitForFunction(()=>document.querySelector('#candidate-dialog .place-photos img')?.naturalWidth===800);await p.keyboard.press('Escape');
  const wb=await p.locator('.workspace').boundingBox();await p.mouse.move(wb.x+150,wb.y+120);await p.waitForTimeout(250);assert.equal(await p.locator('#selection-timeline').evaluate(e=>e.classList.contains('visible')),true);
  await p.locator('[data-timeline-key="2026-10-13|lunch"]').click();await idle();assert.equal(calls.at(-1).action,'search_foods');assert.equal(calls.at(-1).args.meal_date,'2026-10-13');assert.equal(calls.at(-1).args.meal_period,'lunch');assert.match(await p.locator('#content').innerText(),/八大关/);
  await p.screenshot({path:'.展示检查/新版-v11-按饭点餐饮与时间轴.png'});await p.locator('#content [data-food="f"]').click();await p.waitForFunction(()=>mealDate==='2026-10-13'&&mealPeriod==='dinner');await p.waitForTimeout(600);await idle();assert.equal(calls.at(-1).action,'search_foods');assert.equal(calls.at(-1).args.meal_period,'dinner');assert.equal(await p.evaluate(()=>workspace.meal_choices['2026-10-13|lunch'].food_id),'f');
  await p.mouse.move(20,80);await p.waitForTimeout(300);assert.equal(await p.locator('#selection-timeline').evaluate(e=>e.classList.contains('visible')),false);
  await p.evaluate(()=>{workspace.timeline.conflicts=[{date:'2026-10-13',candidate_ids:['b'],direction:'return',level:'error',message:'固定上午安排与返程冲突'}];switchTab('spot')});
  assert.equal(await p.locator('#content [data-candidate="b"] .inline-conflict').count(),1);await p.locator('#content [data-candidate="b"] [data-conflict-jump="transport"]').click();assert.equal(await p.evaluate(()=>transportDirection),'return');
  await p.locator('#messages [data-action="plan"]').click();await idle();await p.waitForTimeout(250);assert.equal(calls.at(-1).action,'plan');assert.equal(await p.locator('#selection-minimap .location-map').getAttribute('data-map-roads'),'["120.313,36.061;120.32,36.06"]');
  await p.screenshot({path:'.展示检查/新版-v11-时间轴与红色路线.png'});assert.deepEqual(errors,[]);
  fs.writeFileSync('data/runtime/browser-experience-v11.json',JSON.stringify({passed:true,fixture:true,checks:['original-photos','http-amap-photo-allowed-by-csp','thumbnail-fallback-no-upscale','shared-selected-detail-map','floating-map-drag-and-collapse-in-modal','collapsed-map-drag-without-click','full-viewport-drag-bounds','edge-expansion-clamp','keyboard-map-movement','timeline-hover-and-jump','chronological-meal-auto-query','inline-conflict-jump','executable-next-step','red-road-overlays'],errors},null,2));console.log('EXPERIENCE V11 PASSED');
 }catch(e){await p.screenshot({path:'.展示检查/experience-v11-failure.png'});console.log('page_errors',errors);throw e}finally{await browser.close()}
})().catch(e=>{console.error(e.stack);process.exitCode=1});
