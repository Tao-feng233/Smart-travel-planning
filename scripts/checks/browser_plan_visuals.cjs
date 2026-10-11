// Synthetic data only; exercise the integrated plan view without changing saved trips.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const path=require('node:path'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'../..'),base='http://127.0.0.1:8767';
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.BROWSER_PATH||'C:/Program Files/Google/Chrome/Application/chrome.exe'});
 const page=await browser.newPage({viewport:{width:1500,height:1000}}),errors=[];
 page.on('pageerror',error=>errors.push(error.message));
 const source={name:'合成来源',queried_at:'2026-10-10'};
 const spot={id:'s',kind:'spot',name:'海滨景点',location:'120.31,36.06',source};
 const events=[
  {kind:'hotel',name:'入住时间待确认',start:'',end:''},
  {kind:'route',name:'前往景点',start:'09:00',end:'09:30',buffer:10,route:{mode:'driving',minutes:20,distance:9000,taxi_cost:30,source}},
  {kind:'spot',name:'海滨景点',start:'09:30',end:'11:30',duration:120,poi:spot},
  {kind:'meal',name:'午餐',start:'12:00',end:'13:00'},
  {kind:'rest',name:'午休',start:'13:00',end:'14:00'}
 ];
 const workspace={id:'plan-visuals-fixture',title:'展示验证',revision:1,requirements:{city:'青岛',start_date:'2026-10-12',days:1,adults:2},catalog:{s:spot},selected_spots:['s'],messages:[],tickets:{},meal_choices:{},trace:[],ui:{view:'plan'},
  plan:{title:'合成计划',created:'2026-10-10T19:00:00',days:[{date:'2026-10-12',theme:'休闲海滨',events}],budget:{hotel_reference:null,known_subtotal:500,unknown:['住宿','门票']},todos:['核对开放时间'],packing:['带雨伞'],warnings:[],guides:[],review:{summary:'合成审核',issues:[]}}};
 await page.route(base+'/**',async route=>{
  const url=new URL(route.request().url());
  if(url.pathname.startsWith('/assets/'))return route.fulfill({path:path.join(root,'frontend',url.pathname.slice('/assets/'.length))});
  if(!url.pathname.startsWith('/api/'))return route.fulfill({path:path.join(root,'frontend/index.html'),contentType:'text/html'});
  if(url.pathname.endsWith('/map-image'))return route.fulfill({status:503,json:{detail:'synthetic map unavailable'}});
  return route.fulfill({json:url.pathname.endsWith('/auth/me')?{user:{id:'qa',nickname:'测试'},csrf_token:'fixture'}:workspace});
 });
 try{
  await page.goto(base);await page.waitForSelector('.book');
  assert.equal(await page.locator('.day-map-content .location-map').count(),0);
  assert.equal(await page.locator('.tl-seg').count(),4,'unknown check-in is not a timed event');
  assert.match(await page.locator('.intensity').innerText(),/轻松/,'driving distance is not walking distance');
  assert.equal(await page.locator('.budget-bar').count(),0,'no invented denominator');
  assert.match(await page.locator('.budget-summary').innerText(),/500.*2项待核实/);
  assert.doesNotMatch(await page.locator('.book').innerHTML(),/NaN|高德实时路线|已确认 ¥/);
  assert.equal(await page.locator('.book > .book-section').count(),6,'sections have balanced details tags');
  await page.locator('.book-nav a[href="#book-todos"]').click();
  assert.equal(await page.locator('#book-todos').evaluate(el=>el.parentElement.open),true);
  const before=await page.locator('.book-section').evaluateAll(elements=>elements.map(el=>el.open));
  await page.evaluate(()=>window.dispatchEvent(new Event('beforeprint')));
  assert.equal(await page.locator('.book-section:not([open])').count(),0);
  await page.evaluate(()=>window.dispatchEvent(new Event('afterprint')));
  assert.deepEqual(await page.locator('.book-section').evaluateAll(elements=>elements.map(el=>el.open)),before);
  await page.locator('.day-map summary').click();await page.waitForSelector('.day-map .location-map');
  await page.locator('#quick-setup').click();assert.equal(await page.locator('#settings').evaluate(el=>el.open),true);
  await page.locator('#close-settings').click();
  await page.evaluate(()=>{workspace.requirements.budget=2000;render()});
  assert.match(await page.locator('.budget-bar-known').getAttribute('style'),/25%/);
  await page.evaluate(()=>{workspace.plan.budget.known_subtotal=0;workspace.requirements.budget=0;render()});
  assert.equal(await page.locator('.budget-bar').count(),0);
  assert.doesNotMatch(await page.locator('.book').innerHTML(),/NaN/);
  assert.deepEqual(errors,[]);
  console.log('PLAN VISUALS, LAZY MAP, NAVIGATION, PRINT AND QUICK SETTINGS PASSED');
 }finally{await browser.close()}
})().catch(error=>{console.error(error);process.exitCode=1});
