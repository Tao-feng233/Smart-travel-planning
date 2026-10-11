const {chromium}=require('C:/Users/asus/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const assert=require('node:assert/strict'),fs=require('node:fs');
(async()=>{
 const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
 const p=await browser.newPage({viewport:{width:1500,height:1000}}),errors=[],calls=[];
 p.on('pageerror',e=>errors.push(e.message));
 const source={name:'高德地图',url:'https://developer.amap.com/',queried_at:'2026-10-07'};
 const food={id:'amap:f',name:'景区附近海鲜店',kind:'food',location:'104.06,30.66',address:'示例街道',cost:'80',recommendation_basis:'午餐前景区周边',source};
 const spot={id:'amap:s',name:'杜甫草堂博物馆',kind:'spot',location:'104.056,30.66',source,place_detail_status:'available'};
 const h={id:'h',kind:'hotel',name:'示例酒店',source,price:200,detail:{starName:'四星',brandName:'示例品牌',reviews:{count:120},roomTypes:[{roomTypeName:'悦享大床房',roomSize:'30㎡',floor:'3-5层',bedType:'大床',maxOccupancy:2,images:['https://example.invalid/room.jpg'],ratePlans:[{rmbPrices:200,mealText:'无早餐',cancelDesc:'入住前可取消',count:0},{rmbPrices:240,mealText:'含早餐',cancelDesc:'入住前可取消',count:2}]}]},room_choices:[{id:'r0',room_index:0,rate_index:0},{id:'r1',room_index:0,rate_index:1}]};
 let w={id:'v10',title:'数据补全验证',revision:0,requirements:{city:'成都',start_date:'2026-10-20',days:3,adults:1},catalog:{[food.id]:food,[spot.id]:spot,h},selected_spots:[spot.id],messages:[{role:'assistant',content:'欢迎使用识途。'}],tickets:{},trace:[],ui:{view:'food',status:'ready'},hotel_query:{ids:['h']},next_step:{message:'查看餐饮',view:'food'},meal_choices:{'2026-10-20|lunch':{food_id:food.id}},visit_requests:{[spot.id]:{date:'2026-10-21',period:'afternoon'}},food_query:{ids:[food.id]}};
 let request,jid=0,failDetails=false;
 const svg='<svg xmlns="http://www.w3.org/2000/svg" width="800" height="440"><rect width="800" height="440" fill="#e8edf5"/></svg>';
 await p.route('https://example.invalid/**',r=>r.fulfill({status:404,body:''}));
 await p.route('**/api/**',async r=>{
  const url=r.request().url();let data;
  if(url.includes('/map-image'))return r.fulfill({contentType:'image/svg+xml',body:svg});
  if(url.includes('/auth/me'))data={user:{id:'qa',nickname:'检查'},csrf_token:'test'};
  else if(url.includes('/actions')){request=r.request().postDataJSON();calls.push(request);data={job_id:'j'+(++jid)}}
  else if(url.includes('/events')){
   await new Promise(resolve=>setTimeout(resolve,180));const a=request.action;w.revision++;w.ui={action:a,status:'ready',view:request.args.view||({ticket:'spot',hotel_detail:'hotel'})[a]};
   if(a==='place_detail')Object.assign(w.catalog[request.args.id],failDetails?{place_detail_status:'query_failed'}:{telephone:'028-12345678',tags:['海鲜','川菜'],opening_today:'11:00-21:00',opening_week:'每天11:00-21:00',business_area:'景区商圈',photos:['https://example.invalid/food.jpg'],place_detail_status:'available',place_detail_checked_at:'2026-10-07',place_detail_source:source});
   if(a==='ticket')w.tickets[request.args.id]={items:[{resName:'成人门票',personTypeName:'成人票',startPrice:'50',departsDate:'2026-12-31',startDate:'2026-10-07',endDate:'2026-12-31',product_group:'admission',lossName:'有条件退',admissionVoucherDesc:'凭证件入园',date_status:'in_sales_window'},{resName:'文创纪念品',startPrice:'22',product_group:'addon'}],requested_date:request.args.visit_date,query_name:'杜甫草堂',candidate_name:spot.name,status:'available',source};
   w.feedback={id:'j'+jid,text:'查询结果已更新，请在右侧查看。'};const failed=a==='place_detail'&&failDetails;
   return r.fulfill({contentType:'text/event-stream',body:'event: done\ndata: '+JSON.stringify({id:'j'+jid,action:a,status:failed?'failed':'completed',error:failed?'详情查询失败':null,ui:{...w.ui,reply_text:''},workspace:w})+'\n\n'});
  }else if(url.endsWith('/workspaces'))data={items:[{id:w.id,title:w.title,updated:'2026-10-07'}]};
  else data=w;
  await r.fulfill({contentType:'application/json',body:JSON.stringify(data)});
 });
 const idle=()=>p.waitForSelector('#progress[hidden]',{state:'attached'});
 try{
  await p.goto('http://127.0.0.1:8767/');await p.waitForSelector('#application:not([hidden])');
  await p.locator('#content [data-candidate="amap:f"] h3').click();await p.waitForFunction(()=>workspace.catalog['amap:f'].place_detail_status==='available');await idle();
  assert.equal(calls.filter(c=>c.action==='place_detail').length,1);assert.equal(await p.locator('#candidate-dialog').evaluate(e=>e.open),true);
  assert.match(await p.locator('#candidate-modal-body').innerText(),/海鲜[\s\S]*川菜/);assert.match(await p.locator('#candidate-modal-body').innerText(),/028-12345678/);
  assert.equal(await p.locator('#messages .assistant').count(),0);assert.equal(await p.evaluate(()=>workspace.messages.length),1);
  assert.equal(await p.evaluate(()=>workspace.meal_choices['2026-10-20|lunch'].food_id),'amap:f');
  await p.screenshot({path:'.展示检查/新版-v10-餐厅详情.png'});await p.keyboard.press('Escape');
  await p.locator('#content [data-candidate="amap:f"] h3').click();await p.waitForTimeout(250);assert.equal(calls.filter(c=>c.action==='place_detail').length,1);await p.keyboard.press('Escape');
  await p.click('#map-button');await p.waitForTimeout(300);await p.evaluate(()=>openCandidate('amap:f'));await p.click('#candidate-dialog [data-place-detail]');await idle();assert.match(await p.locator('#workspace-title').innerText(),/地图/);
  failDetails=true;await p.click('#candidate-dialog [data-place-detail]');await idle();assert.match(await p.locator('#candidate-modal-body').innerText(),/详情查询失败，可重试/);assert.equal(await p.evaluate(()=>workspace.messages.length),1);failDetails=false;await p.keyboard.press('Escape');
  await p.click('#workflow [data-tab="spot"]');await p.locator('#content [data-candidate="amap:s"] h3').click();assert.equal(await p.locator('[data-ticket-date]').inputValue(),'2026-10-21');
  await p.fill('[data-ticket-date]','2026-10-22');await p.click('#candidate-dialog [data-ticket]');await idle();assert.equal(calls.at(-1).args.visit_date,'2026-10-22');
  assert.match(await p.locator('.ticket-results').innerText(),/2026-12-31[\s\S]*不作为所选游玩日期的报价/);assert.match(await p.locator('.ticket-results').innerText(),/有条件退/);
  assert.equal(await p.locator('.ticket-results details').first().evaluate(e=>e.open),false);await p.screenshot({path:'.展示检查/新版-v10-门票日期与分类.png'});await p.keyboard.press('Escape');
  await p.click('#workflow [data-tab="hotel"]');await p.locator('#content [data-candidate="h"] h3').click();
  await p.waitForFunction(()=>!busy&&workspace.catalog.h.place_detail_status==='available');await p.locator('.room-details summary').click();assert.match(await p.locator('#candidate-modal-body').innerText(),/四星[\s\S]*示例品牌/);assert.match(await p.locator('.room').innerText(),/30㎡[\s\S]*3-5层/);assert.match(await p.locator('.room').innerText(),/入住前可取消/);
  assert.equal(await p.locator('[data-room="r0"]').isDisabled(),true);assert.equal(await p.locator('[data-room="r1"]').isDisabled(),false);await p.keyboard.press('Escape');
  await p.evaluate(()=>{workspace.plan={stale:false,days:[{date:'2026-10-21',events:[{kind:'route',route:{polylines:['104.056,30.66;104.058,30.661;104.06,30.66']}},{kind:'spot',candidate_id:'amap:s'},{kind:'meal',candidate_id:'amap:f'}]}]};mapDay='2026-10-21';switchTab('map')});
  assert.deepEqual(JSON.parse(await p.locator('#content .location-map').getAttribute('data-map-roads')),['104.056,30.66;104.058,30.661;104.06,30.66']);assert.match(await p.locator('#content .map-caption').innerText(),/实线为已查询的高德通行路线/);
  assert.deepEqual(errors,[]);fs.writeFileSync('data/runtime/browser-enrichment-v10.json',JSON.stringify({passed:true,fixture:true,checks:['automatic-place-detail','quiet-success-and-failure','no-repeat-query','meal-selection-retained','map-view-retained','ticket-visit-date','interval-minimum-warning','product-classification','hotel-room-fields-and-sold-out','actual-road-geometry'],errors},null,2));console.log('DATA ENRICHMENT V10 PASSED');
 }catch(e){await p.screenshot({path:'.展示检查/enrichment-v10-failure.png'});throw e}finally{await browser.close()}
})().catch(e=>{console.error(e.stack);process.exitCode=1});
