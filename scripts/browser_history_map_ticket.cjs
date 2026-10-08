// Isolated product regression: all API responses below are synthetic fixtures.
const {chromium}=require('C:/Users/asus/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..'),base='http://127.0.0.1:8767';
(async()=>{
 const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
 const p=await browser.newPage({viewport:{width:1450,height:950}}),errors=[];p.on('pageerror',e=>errors.push(e.message));
 const source={name:'高德地图',url:'https://www.amap.com/',queried_at:'2026-10-08'};
 const spot=(id,name)=>({id,name,kind:'spot',location:'120.34,36.05',source,place_detail_status:'available'});
 function trip(id){const a=spot(id+'-current','当前查看景点'),b=spot(id+'-candidate','尚未选择的候选');return {id,title:'合成旅行',revision:0,requirements:{city:'青岛',start_date:'2026-10-12',days:3,adults:1},catalog:{[a.id]:a,[b.id]:b},selected_spots:[],messages:[],tickets:{},trace:[],ui:{view:'spot',status:'ready'},next_step:{message:'选择景点',view:'spot'},meal_choices:{}}}
 let w=trip('first');const svg='<svg xmlns="http://www.w3.org/2000/svg" width="800" height="440"><rect width="800" height="440" fill="#f4f7fa"/></svg>';
 await p.route(base+'/**',async route=>{
  const u=new URL(route.request().url());
  if(u.pathname.startsWith('/assets/'))return route.fulfill({path:path.join(root,'frontend',path.basename(u.pathname))});
  if(!u.pathname.startsWith('/api/'))return route.fulfill({path:path.join(root,'frontend/index.html'),contentType:'text/html'});
  if(u.pathname.endsWith('/map-image'))return route.fulfill({contentType:'image/svg+xml',body:svg});
  if(u.pathname.endsWith('/actions')){
   assert.equal(route.request().postDataJSON().action,'analyze_visits');
   return route.fulfill({contentType:'application/json',body:JSON.stringify({job_id:'analyze-fixture'})});
  }
  if(u.pathname.endsWith('/events')){
   w.timeline={analysis_status:'model',provisional:true,entries:[{key:'2026-10-12|second-current',kind:'spot',candidate_id:'second-current',date:'2026-10-12',time:'09:00',duration:300,name:'当前查看景点',reason:'大型景区安排半天，平衡每日负担'}],meal_slots:[],conflicts:[]};
   w.ui={action:'analyze_visits',view:'spot',status:'ready'};w.revision++;
   return route.fulfill({contentType:'text/event-stream',body:'event: done\ndata: '+JSON.stringify({id:'analyze-fixture',action:'analyze_visits',status:'completed',workspace:w,ui:w.ui})+'\n\n'});
  }
  const body=u.pathname.endsWith('/auth/me')?{user:{id:'qa',nickname:'界面检查'},csrf_token:'test'}:
   u.pathname==='/api/workspaces'?{items:[{id:w.id,title:w.title,city:'青岛',date:'2026-10-12',days:3,messages:0}],total:1}:w;
  return route.fulfill({contentType:'application/json',body:JSON.stringify(body)});
 });
 try{
  await p.goto(base);await p.waitForSelector('#application:not([hidden])');await p.waitForFunction(()=>workspace?.id==='first');
  await p.evaluate(()=>openHistory());await p.waitForSelector('.trip-open');
  const colors=await p.locator('.trip-open').evaluate(e=>({background:getComputedStyle(e).backgroundColor,color:getComputedStyle(e).color}));
  assert.equal(colors.background,'rgb(255, 255, 255)','历史按钮应白底，不应像文本框选');
  assert.notEqual(colors.color,'rgb(255, 255, 255)','历史按钮应蓝字');
  await p.evaluate(()=>{closeHistory();openCandidate('first-current')});
  let points=JSON.parse(await p.locator('#candidate-modal-body .location-map').first().getAttribute('data-map-points'));
  assert.deepEqual(points.map(x=>x.id),['first-current'],'未选景点时，详情地图只显示当前地点');
  await p.keyboard.press('Escape');w=trip('second');w.catalog['first-current']=spot('first-current','相同POI在新旅行中仅为候选');
  await p.evaluate(async t=>{await loadWorkspace(t.id,t)},w);
  assert.equal(await p.locator('#selection-minimap').isVisible(),false,'同一个POI在新旅行仅为候选时，旧焦点不能继续显示');
  await p.evaluate(()=>openCandidate('second-current'));
  points=JSON.parse(await p.locator('#candidate-modal-body .location-map').first().getAttribute('data-map-points'));
  assert.deepEqual(points.map(x=>x.id),['second-current'],'切换旅行后不能显示旧标记或其他候选');
  await p.keyboard.press('Escape');
  await p.evaluate(()=>{workspace.selected_spots=['second-candidate'];openCandidate('second-current')});
  points=JSON.parse(await p.locator('#candidate-modal-body .location-map').first().getAttribute('data-map-points'));
  assert.deepEqual(new Set(points.map(x=>x.id)),new Set(['second-current','second-candidate']),'详情地图保留当前旅行已选地点');
  // Independent reference: Amap-rendered cross pixel centres captured using
  // scale=1 on 2026-10-08. This catches overlay drift rather than mirroring it.
  const calibrated=await p.evaluate(()=>{
   const a=mapWorld(120.349,36.0508),b=mapWorld(120.35,36.051);
   return [[13,522.5,382.5],[15,557,373],[17,696.5,338]].map(([z,x,y])=>Math.hypot(512+(b[0]-a[0])*MAP_WORLD_PIXELS*2**z-x,384+(b[1]-a[1])*MAP_WORLD_PIXELS*2**z-y));
  });
  assert.ok(calibrated.every(error=>error<3),'标记投影应与高德实际底图位置一致');
  const html=await p.evaluate(()=>ticketsHTML({source:{name:'途牛 MCP',url:'https://open.tuniu.com/',queried_at:'2026-10-08'},requested_date:'2026-10-12',status:'available',items:[{resName:'合成成人门票',startPrice:169,departsDate:'2026-12-31',product_group:'admission',advanceBookDay:0,advanceBookHour:0}]}));
  assert.match(html,/所选日期报价尚未确认/);assert.match(html,/途牛 MCP/);assert.match(html,/区间起价/);
  const missing=await p.evaluate(()=>ticketsHTML({requested_date:'2026-10-12',items:[{resName:'缺字段门票',product_group:'admission'}]}));
  assert.doesNotMatch(missing,/提前量[^<]*0天/,'缺少提前量不能补成0');
  await p.keyboard.press('Escape');
  await p.evaluate(()=>{$('#selection-timeline').classList.add('visible')});
  await p.click('#timeline-optimize');
  await p.waitForFunction(()=>!busy&&workspace.timeline?.analysis_status==='model');
  assert.match(await p.locator('.timeline-entries').innerText(),/建议 300 分钟/);
  assert.match(await p.locator('.timeline-entry').getAttribute('title'),/平衡每日负担/);
  assert.deepEqual(errors,[]);
  await p.keyboard.press('Escape');await p.evaluate(()=>openHistory());await p.screenshot({path:path.join(root,'.展示检查/history-map-ticket-fixed.png')});
  const receipt={passed:true,fixture:true,checks:['history-white-background','detail-only-current-before-selection','trip-isolation','current-trip-selected-context','ticket-price-scope','missing-fields-remain-unknown','provider-pixel-calibration','timeline-optimize-action'],errors};
  fs.writeFileSync(path.join(root,'data/runtime/browser-history-map-ticket.json'),JSON.stringify(receipt,null,2));console.log('HISTORY MAP TICKET PASSED');
 }finally{await browser.close()}
})().catch(e=>{console.error(e.stack);process.exitCode=1});
