// Isolated interface fixtures: no user records or supplier requests.
// Install Playwright locally, or set PLAYWRIGHT_MODULE to an existing module path.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const path=require('node:path'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..'),base='http://127.0.0.1:8767';
(async()=>{
 const b=await chromium.launch({headless:true,...(process.env.BROWSER_PATH?{executablePath:process.env.BROWSER_PATH}:{})});
 const p=await b.newPage({viewport:{width:1500,height:1000}}),errors=[];p.on('pageerror',e=>errors.push(e.message));
 const source={name:'合成来源',queried_at:'2026-10-09'},spots=[
  {id:'unknown',name:'未知费用景点',kind:'spot',rating:'4.7'},
  {id:'free',name:'免费入园景点',kind:'spot',rating:'4.5',price_hint:{label:'免费入园',basis:'official_free_admission',note:'普通入园免费，附加服务另行核实。'}},
  {id:'paid',name:'参考消费景点',kind:'spot',rating:'4.6',cost:'80'},
 ];
 let w={id:'cards-fixture',title:'推荐验证',revision:1,requirements:{city:'青岛',days:3},catalog:{},selected_spots:[],messages:[],tickets:{},meal_choices:{},trace:[],ui:{view:'spot',status:'ready'},spot_preference:{city:'青岛',status:'awaiting'},timeline:{entries:[],meal_slots:[],conflicts:[]}},request;
 await p.route(base+'/**',async r=>{
  const u=new URL(r.request().url());
  if(u.pathname.startsWith('/assets/'))return r.fulfill({path:path.join(root,'frontend',path.basename(u.pathname))});
  if(!u.pathname.startsWith('/api/'))return r.fulfill({path:path.join(root,'frontend/index.html'),contentType:'text/html'});
  if(u.pathname.endsWith('/map-image'))return r.fulfill({contentType:'image/svg+xml',body:'<svg xmlns="http://www.w3.org/2000/svg" width="1024" height="768"/>'});
  if(u.pathname.endsWith('/actions')){request=r.request().postDataJSON();return r.fulfill({contentType:'application/json',body:'{"job_id":"j"}'})}
  if(u.pathname.endsWith('/events')){
   assert.equal(request.action,'search_spots');
   if(request.args.expand_spots){
    assert.equal(request.args.expand_spots,true);w.selected_spots=['free'];
    w.catalog.more={id:'more',kind:'spot',name:'新增相关景点',source};w.spot_search.ids=['more'];w.spot_page.ids=['more'];
   }else{
   assert.equal(request.args.preference_mode,'default');
   w.catalog=Object.fromEntries(spots.map(s=>[s.id,{...s,source}]));w.spot_preference.status='default';w.spot_search={city:'青岛',ids:spots.map(s=>s.id),page:1};w.spot_page={ids:spots.map(s=>s.id),page:1,pages:1};w.revision++;w.ui={view:'spot',action:'search_spots',status:'ready'};
   w.timeline.route_status='checked';w.timeline.entries=[{key:'2026-10-12|road',date:'2026-10-12',time:'08:30',end:'09:10',kind:'route',mode:'driving',route_minutes:25,buffer_minutes:15,name:'酒店前往景点',reason:'道路预计时间，等候为建议预留。',estimated:true},{key:'2026-10-12|midday_rest',date:'2026-10-12',time:'13:15',end:'14:15',kind:'rest',rest_type:'midday',name:'午休与放松',estimated:true}];
   }
   return r.fulfill({contentType:'text/event-stream',body:'event: done\ndata: '+JSON.stringify({id:'j',action:'search_spots',status:'completed',workspace:w,ui:w.ui})+'\n\n'});
  }
  const data=u.pathname.endsWith('/auth/me')?{user:{id:'qa',nickname:'测试'},csrf_token:'fixture'}:u.pathname==='/api/workspaces'?{items:[{id:w.id,title:w.title}],total:1}:w;
  return r.fulfill({contentType:'application/json',body:JSON.stringify(data)});
 });
 try{
  await p.goto(base);await p.waitForSelector('#application:not([hidden])');
  assert.equal(await p.locator('.compact-place').count(),0);
  await p.getByRole('button',{name:'暂无偏好，查看代表景点',exact:true}).click();
  await p.waitForSelector('[data-candidate=unknown] .price-hint');
  assert.match(await p.locator('[data-candidate=unknown]').innerText(),/4.7 分[\s\S]*费用待核实/);
  assert.match(await p.locator('[data-candidate=free]').innerText(),/免费入园/);
  assert.match(await p.locator('[data-candidate=paid]').innerText(),/参考消费 ¥80\/人/);
  await p.locator('[data-candidate=paid] h3').click();
  assert.match(await p.locator('#candidate-modal-body').innerText(),/不是实际报价/);
  assert.equal(await p.evaluate(()=>priceHintHTML({kind:'food',cost:'94'}).includes('参考人均 ¥94')),true);
  await p.locator('#candidate-dialog [data-close=candidate-dialog]').click();
  assert.equal(await p.locator('.timeline-entry.midday-rest').count(),1);
  assert.match(await p.locator('.timeline-entry.travel-leg').textContent(),/预计 25 分钟 \+ 15 分钟缓冲/);
  await p.evaluate(()=>document.querySelector('.timeline-entry.travel-leg').click());
  assert.match(await p.locator('#info-content').innerText(),/道路预计 25 分钟/);
  await p.locator('#info-dialog [data-close=info-dialog]').click();
  assert.match(await p.locator('.timeline-entry.midday-rest').textContent(),/午休与放松[\s\S]*14:15/);
  await p.getByRole('button',{name:'继续推荐相关景点',exact:true}).click();
  await p.waitForSelector('[data-candidate=more]');
  assert.deepEqual(await p.evaluate(()=>workspace.selected_spots),['free']);
  await p.evaluate(()=>{
   workspace.catalog.sea={id:'sea',kind:'spot',name:'海滨风景区'};
   workspace.catalog.eight={id:'eight',kind:'spot',name:'八大关风景区',parent_id:'sea'};
   workspace.catalog.house={id:'house',kind:'spot',name:'花石楼',parent_id:'eight'};
   workspace.selected_spots=['sea','eight'];workspace.spot_search.ids=['eight','house'];
   workspace.spot_page={page:1,pages:1,ids:['sea','eight','house']};
   workspace.spot_groups=[{key:'sea',title:'海滨风景区',parent_id:'sea',ids:['eight','house'],basis:'地图父子关系'}];
   workspace.spot_coverage={parent_coverage:{sea:['eight']}};referenceFocus=null;render();
  });
  assert.equal(await p.locator('#content [data-candidate=eight]').count(),1);
  assert.match(await p.locator('#content [data-candidate=sea]').innerText(),/景区范围介绍[\s\S]*父项不另计游玩时长/);
  assert.deepEqual(errors,[]);console.log('Preference fallback, score/price labels, detail notes and restaurant reference passed.');
 }finally{await b.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
