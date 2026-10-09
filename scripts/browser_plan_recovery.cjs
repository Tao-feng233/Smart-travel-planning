// Saved-plan compatibility, navigation and session restoration use synthetic HTTP fixtures.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const path=require('node:path'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..'),base='http://127.0.0.1:8767';
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.BROWSER_PATH||'C:/Program Files/Google/Chrome/Application/chrome.exe'});
 const page=await browser.newPage({viewport:{width:1500,height:1000}}),errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 const route={mode:'driving',minutes:25,distance:5000,taxi_cost:18.5,steps:[{instruction:'向南步行1米右转'}]};
 const w={id:'plan-recovery-fixture',title:'页面回归',revision:1,requirements:{city:'青岛',start_date:'2026-10-12',days:1},catalog:{},selected_spots:[],messages:[],tickets:{},meal_choices:{},trace:[],ui:{view:'weather'},weather:{days:[],alerts:[],attributions:[]},
  plan:{title:'计划书',created:'2026-10-09T09:00:00',days:[{date:'2026-10-12',theme:'海滨',events:[{kind:'route',name:'从酒店前往景点',start:'09:00',end:'09:40',route,buffer:15}]}],budget:{hotel_reference:null,unknown:[]},todos:[],warnings:[],packing:[],guides:[]}};
 let disconnected=false,lastRequest;let current=w;
 await page.route(base+'/**',async r=>{
  const u=new URL(r.request().url());
  if(u.pathname.startsWith('/assets/'))return r.fulfill({path:path.join(root,'frontend',path.basename(u.pathname))});
  if(!u.pathname.startsWith('/api/'))return r.fulfill({path:path.join(root,'frontend/index.html'),contentType:'text/html'});
  if(disconnected)return r.fulfill({status:503,json:{detail:'temporary outage'}});
  if(u.pathname.endsWith('/actions')){lastRequest=r.request().postDataJSON();assert.equal(lastRequest.action,'transport_arrangement');assert.equal(lastRequest.args.mode,'self_drive');return r.fulfill({json:{job_id:'self-drive'}})}
  if(u.pathname.endsWith('/events')){current={...current,requirements:{...current.requirements,intercity_mode:'self_drive',transport_mode:'driving'},ui:{view:'food'}};return r.fulfill({contentType:'text/event-stream',body:'event: done\ndata: '+JSON.stringify({id:'self-drive',status:'completed',action:lastRequest.action,workspace:current,ui:current.ui})+'\n\n'})}
  const data=u.pathname.endsWith('/auth/me')?{user:{id:'qa',nickname:'测试'},csrf_token:'fixture'}:current;
  return r.fulfill({json:data});
 });
 try{
  await page.goto(base);await page.waitForSelector('#application:not([hidden])');
  for(const view of ['spot','hotel','transport','food','weather']){
   await page.locator('#workflow [data-tab="'+view+'"]').click();
   await page.locator('#workflow [data-tab=plan]').click();
   assert.equal(await page.locator('.book').count(),1,view+' → plan');
  }
  assert.match(await page.locator('.book').innerText(),/打车预估.*18.5/);
  assert.match(await page.locator('.book').innerText(),/25 分钟/);
  assert.doesNotMatch(await page.locator('.book').innerText(),/通行步骤与换乘|向南步行1米右转/);
  await page.reload();await page.waitForSelector('#application:not([hidden])');
  assert.equal(await page.locator('#auth-gate').isVisible(),false);
  disconnected=true;await page.reload();await page.waitForSelector('#connection-recovery:not([hidden])');
  assert.equal(await page.locator('#auth-gate').isVisible(),false);
  disconnected=false;await page.locator('#retry-connection').click();await page.waitForSelector('#application:not([hidden])');
  assert.equal(await page.locator('#auth-gate').isVisible(),false);
  await page.locator('#workflow [data-tab=transport]').click();await page.locator('[data-trip-transport=self_drive]').click();
  await page.waitForFunction(()=>!busy&&workspace.requirements.intercity_mode==='self_drive');
  await page.locator('#workflow [data-tab=transport]').click();assert.match(await page.locator('#content').innerText(),/已设为自驾游/);
  await page.evaluate(()=>{workspace.discovery_mode=true;tab='spot';workspace.destinations=['青岛','成都','杭州','西安','济南'].map((name,i)=>({id:'d'+i,name,tags:[],highlights:[],summary:'已有资料'}));render()});
  assert.equal(await page.locator('.destination-card').count(),4);
  assert.equal(await page.locator('[data-destination-page]').count(),0);
  await page.locator('.covered-destinations summary').click();
  assert.match(await page.locator('.covered-destinations').innerText(),/济南/);
  assert.match(await page.locator('#content').innerText(),/已有资料覆盖 5 个城市/);
  assert.deepEqual(errors,[]);
  console.log('PLAN NAVIGATION, LEGACY ROUTE AND SESSION RECOVERY PASSED');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
