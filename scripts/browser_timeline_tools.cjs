// UI request/response fixtures. Server tool validation is tested in test_timeline_tools.py.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const path=require('node:path'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..'),base='http://127.0.0.1:8767';
(async()=>{
 const b=await chromium.launch({headless:true,executablePath:process.env.BROWSER_PATH||'C:/Program Files/Google/Chrome/Application/chrome.exe'});
 const p=await b.newPage({viewport:{width:1500,height:1000}}),errors=[],requests=[];p.on('pageerror',e=>errors.push(e.message));
 const dt='2026-10-14',h={id:'h',kind:'hotel',name:'酒店',location:'120.30,36.05'},a={id:'a',kind:'spot',name:'五四广场',location:'120.35,36.06'};
 let w={id:'timeline-fixture',title:'时间轴工具验证',revision:1,requirements:{city:'青岛',start_date:dt,days:1},catalog:{h,a},selected_spots:['a'],hotel:h,messages:[],tickets:{},meal_choices:{},trace:[],ui:{view:'spot',status:'ready'},spot_coverage:{active_ids:['a']},
 timeline:{provisional:true,route_status:'pending',entries:[{key:'pending',date:dt,time:'',kind:'unknown_route',name:'酒店 → 五四广场',route_minutes:null,route_status:'unknown'},{key:'spot',date:dt,time:'09:00',end:'11:30',kind:'spot',name:'五四广场',candidate_id:'a',duration:150}],meal_slots:[],conflicts:[]}},request;
 await p.route(base+'/**',async r=>{
  const u=new URL(r.request().url());
  if(u.pathname.startsWith('/assets/'))return r.fulfill({path:path.join(root,'frontend',path.basename(u.pathname))});
  if(!u.pathname.startsWith('/api/'))return r.fulfill({path:path.join(root,'frontend/index.html'),contentType:'text/html'});
  if(u.pathname.endsWith('/map-image'))return r.fulfill({contentType:'image/svg+xml',body:'<svg xmlns="http://www.w3.org/2000/svg" width="1024" height="768"/>'});
  if(u.pathname.endsWith('/actions')){request=r.request().postDataJSON();requests.push(request);assert.equal(request.action,'adjust_timeline');return r.fulfill({contentType:'application/json',body:'{"job_id":"j"}'})}
  if(u.pathname.endsWith('/events')){
   w.timeline.route_status='checked';w.timeline.entries=[{key:'road',date:dt,time:'09:00',end:'09:50',kind:'route',name:'酒店 → 五四广场',mode:'driving',route_minutes:40,buffer_minutes:10},
    {key:'spot',date:dt,time:'10:15',end:'11:15',kind:'spot',candidate_id:'a',name:'五四广场',duration:60}];
   w.messages.push({role:'assistant',content:'已通过时间轴工具调整建议时间，保留已选地点。'});w.revision++;
   return r.fulfill({contentType:'text/event-stream',body:'event: done\ndata: '+JSON.stringify({id:'j',action:request.action,status:'completed',workspace:w,ui:w.ui})+'\n\n'});
  }
  const data=u.pathname.endsWith('/auth/me')?{user:{id:'qa',nickname:'测试'},csrf_token:'fixture'}:u.pathname==='/api/workspaces'?{items:[{id:w.id,title:w.title}],total:1}:w;
  return r.fulfill({contentType:'application/json',body:JSON.stringify(data)});
 });
 try{
  await p.goto(base);await p.waitForSelector('#application:not([hidden])');
  await p.locator('.workspace').hover();await p.waitForSelector('#selection-timeline.visible');
  assert.match(await p.locator('[data-timeline-key=pending]').innerText(),/出发时间待查询[\s\S]*交通方式待查询[\s\S]*交通耗时待查询/);
  assert.match(await p.locator('[data-timeline-key=spot]').innerText(),/建议游玩 150 分钟/);
  await p.evaluate(()=>selectTimelineSlot(timelineEntries()[0]));assert.match(await p.locator('#info-content').innerText(),/出发、抵达时间待路线查询/);
  await p.locator('#info-dialog [data-close=info-dialog]').click();
  await p.locator('.workspace').hover();await p.waitForSelector('#selection-timeline.visible');await p.locator('#timeline-optimize').click();
  await p.waitForFunction(()=>!busy&&workspace.timeline.route_status==='checked');
  assert.match(await p.locator('[data-timeline-key=road]').innerText(),/09:00 出发[\s\S]*09:50 预计抵达[\s\S]*驾车／打车参考[\s\S]*路程预计 40 分钟/);
  assert.match(await p.locator('[data-timeline-key=spot]').innerText(),/10:15[\s\S]*建议游玩 60 分钟/);
  assert.deepEqual(w.selected_spots,['a']);assert.deepEqual(requests.map(x=>x.action),['adjust_timeline']);assert.deepEqual(errors,[]);
  console.log('TIMELINE TOOL AND TRAVEL DISPLAY BROWSER PASSED');
 }finally{await b.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
