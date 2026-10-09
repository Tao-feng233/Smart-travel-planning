// Isolated browser fixtures; no real users, records or suppliers.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const path=require('node:path'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..'),base='http://127.0.0.1:8767';
(async()=>{
 const b=await chromium.launch({headless:true,executablePath:process.env.BROWSER_PATH||'C:/Program Files/Google/Chrome/Application/chrome.exe'});
 const p=await b.newPage({viewport:{width:1500,height:1000}}),errors=[],requests=[];
 p.on('pageerror',e=>errors.push(e.message));
 const D1='2026-10-12',D2='2026-10-13',h={id:'h',kind:'hotel',name:'第一晚酒店',location:'120.30,36.05'},h2={id:'h2',kind:'hotel',name:'第二晚酒店',location:'120.35,36.06'};
 let w={id:'nightly-fixture',title:'逐晚与审核验证',revision:1,requirements:{city:'青岛',start_date:D1,days:2,adults:2},catalog:{h,h2},selected_spots:[],hotel:h,stay_hotels:{[D1]:'h'},selected_room:null,messages:[],tickets:{},meal_choices:{},trace:[],ui:{view:'hotel',status:'ready'},
 stay_plan:{rows:[{date:D1,anchor_name:'海边',candidate_ids:['h'],hotel_id:'h',hotel_source:'explicit'},{date:D2,anchor_name:'市区',candidate_ids:['h2'],hotel_source:'unset'}],assignments:{[D1]:{hotel_id:'h',source:'explicit'},[D2]:{hotel_id:null,source:'unset'}},unassigned:[D2]},timeline:{entries:[],meal_slots:[],conflicts:[]}},request,jid=0;
 await p.route(base+'/**',async r=>{
  const u=new URL(r.request().url());
  if(u.pathname.startsWith('/assets/'))return r.fulfill({path:path.join(root,'frontend',path.basename(u.pathname))});
  if(!u.pathname.startsWith('/api/'))return r.fulfill({path:path.join(root,'frontend/index.html'),contentType:'text/html'});
  if(u.pathname.endsWith('/map-image'))return r.fulfill({contentType:'image/svg+xml',body:'<svg xmlns="http://www.w3.org/2000/svg" width="1024" height="768"/>'});
  if(u.pathname.endsWith('/actions')){request=r.request().postDataJSON();requests.push(request);return r.fulfill({contentType:'application/json',body:JSON.stringify({job_id:'j'+(++jid)})})}
  if(u.pathname.endsWith('/events')){
   if(request.action==='select'){
    assert.equal(request.args.stay_date,D2);w.hotel=h2;w.stay_hotels[D2]='h2';w.stay_plan.assignments[D2]={hotel_id:'h2',source:'explicit'};w.stay_plan.unassigned=[];
   }else if(request.action==='review_timeline'){
    const issue={code:'late_arrival',level:'warning',date:D1,candidate_ids:['h'],view:'hotel',message:'下午抵达后首日窗口较短，建议入住休息并调整可移动活动。',optimize:true};
    w.timeline_review={status:'completed',issues:[issue]};w.messages.push({role:'assistant',content:'时间安排提醒',ui:{conflict:{issues:[issue]}}});
   }else throw Error('Unexpected action '+request.action);
   w.revision++;w.ui={view:'hotel',status:'ready'};
   return r.fulfill({contentType:'text/event-stream',body:'event: done\ndata: '+JSON.stringify({id:'j'+jid,action:request.action,status:'completed',workspace:w,ui:w.ui})+'\n\n'});
  }
  const data=u.pathname.endsWith('/auth/me')?{user:{id:'qa',nickname:'测试'},csrf_token:'fixture'}:u.pathname==='/api/workspaces'?{items:[{id:w.id,title:w.title}],total:1}:w;
  return r.fulfill({contentType:'application/json',body:JSON.stringify(data)});
 });
 try{
  await p.goto(base);await p.waitForSelector('#application:not([hidden])');
  assert.equal(await p.locator(`[data-stay-date="${D1}"] .stay-candidates`).getAttribute('open'),null);
  await p.locator(`[data-stay-date="${D2}"] [data-select=h2]`).click();await p.waitForFunction(()=>!busy&&workspace.stay_hotels['2026-10-13']==='h2');
  assert.equal(w.stay_hotels[D1],'h');assert.equal(w.selected_room,null);
  assert.equal(await p.locator('#candidate-dialog').evaluate(d=>d.open),false);
  assert.equal(await p.locator(`[data-stay-date="${D2}"] .stay-candidates`).getAttribute('open'),null);
  assert.deepEqual(await p.evaluate(()=>miniPoints().map(p=>p.id).sort()),['h','h2']);
  await p.evaluate(()=>action('review_timeline'));await p.waitForFunction(()=>!busy&&workspace.timeline_review?.status==='completed');
  assert.match(await p.locator('#messages').innerText(),/首日窗口较短/);
  assert.equal(await p.locator('#messages [data-diagnostic-candidate=h]').count()>0,true);
  await p.locator('#messages [data-diagnostic-candidate=h]').click();await p.waitForSelector('#candidate-dialog[open]');assert.equal(await p.locator('#candidate-modal-title').innerText(),'第一晚酒店');
  assert.deepEqual(requests.map(r=>r.action),['select','review_timeline']);assert.deepEqual(errors,[]);
  console.log('NIGHTLY STAYS AND TIMELINE AUDIT BROWSER PASSED');
 }finally{await b.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
