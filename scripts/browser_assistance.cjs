// UI regression with synthetic API fixtures; no real user records or providers.
const {chromium}=require('C:/Users/asus/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..'),base='http://127.0.0.1:8767';
(async()=>{
 const b=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
 const p=await b.newPage({viewport:{width:1500,height:1000}}),errors=[],requests=[];p.on('pageerror',e=>errors.push(e.message));
 const source={name:'合成来源',queried_at:'2026-10-08'},s={id:'s',name:'栈桥',kind:'spot',location:'120.3,36.0',source};
 let w={id:'fixture',title:'合成旅行',revision:1,requirements:{city:'青岛',start_date:'2026-10-12',days:2,adults:1},catalog:{s,f:{id:'f',name:'已选餐厅',kind:'food',source}},selected_spots:['s'],messages:[],tickets:{},trace:[],meal_choices:{'2026-10-12|lunch':{mode:'chosen',food_id:'f'}},ui:{view:'spot',status:'ready'},next_step:{view:'food',message:'继续餐饮'},timeline:{entries:[],meal_slots:[],conflicts:[]}};
 let request,jid=0,releasePreview=false;
 const preview={id:'fixture',catalog:{newspot:{id:'newspot',name:'提前到达的景点资料',kind:'spot',location:'120.31,36.02',source}},spot_search:{ids:['newspot']},spot_page:{page:1,pages:1,ids:['newspot']},discovery_mode:false};
 await p.route(base+'/**',async r=>{
  const u=new URL(r.request().url());
  if(u.pathname.startsWith('/assets/'))return r.fulfill({path:path.join(root,'frontend',path.basename(u.pathname))});
  if(!u.pathname.startsWith('/api/'))return r.fulfill({path:path.join(root,'frontend/index.html'),contentType:'text/html'});
  if(u.pathname.endsWith('/map-image'))return r.fulfill({contentType:'image/svg+xml',body:'<svg xmlns="http://www.w3.org/2000/svg" width="1024" height="768"><rect width="100%" height="100%" fill="#eff3f6"/></svg>'});
  if(u.pathname.endsWith('/actions')){request=r.request().postDataJSON();requests.push(request);return r.fulfill({contentType:'application/json',body:JSON.stringify({job_id:'j'+(++jid)})})}
  if(u.pathname.endsWith('/events')){
   if(request.action==='search_spots')return r.fulfill({contentType:'text/event-stream',body:'event: progress\ndata: '+JSON.stringify({ui:{view:'spot',status:'loading',workspace_preview:preview}})+'\n\n'});
   let status='completed',error;w.revision++;w.ui={action:request.action,view:'food',status:'ready'};
   if(request.action==='chat'){
    w.pending_auto_selection={id:'consent-'+jid,mode:request.text.includes('重新')?'replace':'remaining',categories:['food'],description:request.text.includes('重新')?'重新选择并替换已有的餐饮':'保留已有选择，补齐尚未安排的餐饮',notice:'车票、机票由你手动确认；只用于规划，不进行预订。'};
    if(request.text.includes('全程'))Object.assign(w.pending_auto_selection,{proposed_requirements:{start_date:'2026-10-12',days:3,adults:1},generate_plan_default:true});
    w.ui.action='request_auto_selection';w.messages.push({role:'assistant',content:'请核对弹窗中的代选范围。'});
   }else if(request.action==='approve_auto_selection'){
    assert.equal(request.args.approval_id,w.pending_auto_selection.id);assert.equal(request.args.confirmed,true);
    if(w.pending_auto_selection.proposed_requirements){assert.equal(request.args.requirements.start_date,'2026-10-20');assert.equal(request.args.generate_plan,true);w.requirements={...w.requirements,...request.args.requirements}}
    delete w.pending_auto_selection;w.meal_choices['2026-10-12|dinner']={mode:'chosen',food_id:'f'};
   }else if(request.action==='cancel_auto_selection'){delete w.pending_auto_selection}
   else if(request.action==='meal_choice'&&request.args.mode==='remove'){
    delete w.meal_choices[request.args.meal_date+'|'+request.args.meal_period];
   }
   else if(request.action==='approve_plan_warning'){
    assert.equal(request.args.approval_id,w.pending_plan_warning.id);assert.equal(request.args.confirmed,true);w.plan=w.pending_plan_warning.plan;delete w.pending_plan_warning;w.plan.warnings=['每日负担分配提醒：已确认继续生成'];w.plan.warning_acceptance={confirmed:true};w.ui={action:'plan',view:'plan',status:'ready'};w.messages.push({role:'assistant',content:'已按确认生成带警告的旅行草稿。',ui:w.ui});
   }else if(request.action==='cancel_plan_warning'){delete w.pending_plan_warning}
   else if(request.action==='plan'&&request.args?.advisory){
    w.pending_plan_warning={id:'warning-'+jid,issues:[{code:'unbalanced_estimate',level:'warning',date:'2026-10-13',message:'2026-10-13建议游玩及转场约280分钟，2026-10-12约80分钟，前者更密集。可优化分配，也可保留当前节奏；不要求填满休息时间或增加游玩天数。'}],plan:{...w.plan,title:'确认后的提醒草稿'}};w.ui={action:'plan',view:'plan',status:'ready'};w.messages.push({role:'assistant',content:'请查看规划提醒后选择继续或调整。',ui:w.ui});
   }else if(request.action==='optimize_plan'){
    w.ui={action:'optimize_plan',view:'plan',status:'ready'};w.plan={title:'修订计划',created:'2026-10-08T12:00:00',stale:false,days:[{date:'2026-10-13',theme:'按可用时段游览',events:[{kind:'spot',candidate_id:'s',name:'栈桥',start:'09:00',end:'10:00',duration:60,note:'调整到更充裕的一天',poi:s}]}],guides:[],budget:{hotel_reference:null,unknown:[]},todos:[],packing:[],warnings:[],review:{summary:'待核实',issues:[]}};w.timeline.entries=[{key:'2026-10-13|s',date:'2026-10-13',time:'09:00',end:'10:00',name:'栈桥',kind:'spot',candidate_id:'s'}];w.timeline.provisional=false;w.messages.push({role:'assistant',content:'旅行计划书已重新核对并更新，栈桥调整至10月13日。',ui:w.ui});
   }else if(request.action==='plan'){
    status='failed';error='这次安排有需要核对的时间条件，已有选择保留。';
    w.ui={action:'plan',view:'plan',status:'failed',conflict:{date:'2026-10-12',view:'spot',candidate_ids:['s'],issues:[{code:'day_capacity',optimize:true,date:'2026-10-12',view:'spot',candidate_ids:['s'],direction:'return',message:'10月12日栈桥的游玩安排超出了所选返程班次G2留下的可用时间，请调整日期或返程班次。'}]}};
    w.messages.push({role:'assistant',content:error,ui:w.ui});
   }
   return r.fulfill({contentType:'text/event-stream',body:'event: done\ndata: '+JSON.stringify({id:'j'+jid,status,action:request.action,error,workspace:w,ui:w.ui})+'\n\n'});
  }
  if(/^\/api\/jobs\/j\d+$/.test(u.pathname)&&request.action==='search_spots'){
   if(releasePreview){w.catalog={...w.catalog,...preview.catalog};w.spot_page=preview.spot_page;w.spot_search=preview.spot_search;w.ui={view:'spot',status:'ready'}}
   return r.fulfill({contentType:'application/json',body:JSON.stringify({id:'j'+jid,status:releasePreview?'completed':'running',progress:'补充推荐中',ui:{view:'spot',status:releasePreview?'ready':'loading',workspace_preview:preview},workspace:releasePreview?w:undefined})});
  }
  const data=u.pathname.endsWith('/auth/me')?{user:{id:'qa',nickname:'检查'},csrf_token:'test'}:u.pathname==='/api/workspaces'?{items:[{id:w.id,title:w.title}],total:1}:w;
  return r.fulfill({contentType:'application/json',body:JSON.stringify(data)});
 });
 try{
  await p.goto(base);await p.waitForSelector('#application:not([hidden])');
  await p.evaluate(()=>action('chat',{},'其他时候的餐饮你自动帮我选一下吧'));
  await p.waitForSelector('#auto-selection-dialog[open]');
  assert.match(await p.locator('.auto-selection-scope').innerText(),/保留已有选择/);
  assert.equal(requests.length,1,'确认前只能提交意图，不能启动代选');
  assert.equal(w.meal_choices['2026-10-12|dinner'],undefined);
  await p.screenshot({path:path.join(root,'.展示检查/自动配置-确认弹窗.png')});
  await p.click('#auto-selection-confirm');await p.waitForFunction(()=>!busy&&!workspace.pending_auto_selection);
  assert.equal(requests.at(-1).action,'approve_auto_selection');assert.equal(requests.at(-1).args.generate_plan,false);
  await p.evaluate(()=>action('chat',{},'餐饮重新全部选一遍'));await p.waitForSelector('#auto-selection-dialog[open]');
  assert.match(await p.locator('.auto-selection-scope').innerText(),/重新选择并替换/);
  const meals=JSON.stringify(w.meal_choices);await p.keyboard.press('Escape');await p.waitForFunction(()=>!busy&&!workspace.pending_auto_selection);
  assert.equal(requests.at(-1).action,'cancel_auto_selection');assert.equal(JSON.stringify(w.meal_choices),meals);
  await p.evaluate(()=>action('plan'));await p.waitForFunction(()=>!busy&&workspace.ui?.conflict?.issues?.length);
  assert.match(await p.locator('#messages .planning-diagnostics').innerText(),/10月12日栈桥.*G2/);
  assert.match(await p.locator('#error').innerText(),/已定位 1 项/);
  // A freely positioned map can cover a conversation link; collapse it through
  // the actual control before following the link, as a user would.
  if(await p.locator('#mini-collapse').isVisible())await p.click('#mini-collapse');
  await p.locator('#messages [data-diagnostic-candidate="s"]').click();await p.waitForSelector('#candidate-dialog[open]');
  assert.equal(await p.locator('#candidate-dialog h2').innerText(),'栈桥');
  await p.keyboard.press('Escape');await p.locator('#messages [data-conflict-jump="transport"]').click();
  assert.equal(await p.evaluate(()=>transportDirection),'return');assert.equal(await p.evaluate(()=>tab),'transport');
  await p.screenshot({path:path.join(root,'.展示检查/规划错误-具体诊断与跳转.png')});
  await p.locator('#messages [data-action="optimize_plan"]').click();await p.waitForFunction(()=>!busy&&workspace.plan&&!workspace.plan.stale);
  assert.equal(requests.at(-1).action,'optimize_plan');assert.equal(await p.evaluate(()=>tab),'plan');assert.match(await p.locator('#content').innerText(),/2026-10-13/);assert.match(await p.locator('#messages').innerText(),/重新核对并更新/);await p.screenshot({path:path.join(root,'.展示检查/计划书-智能修订入口.png')});
  const originalTitle=w.plan.title;await p.evaluate(()=>action('plan',{advisory:true}));await p.waitForSelector('#plan-warning-dialog[open]');
  assert.equal(w.plan.title,originalTitle);assert.match(await p.locator('.plan-warning-issues').innerText(),/2026-10-13.*2026-10-12/);assert.equal(await p.locator('#error').isVisible(),false);await p.screenshot({path:path.join(root,'.展示检查/规划提醒-继续生成确认.png')});
  await p.keyboard.press('Escape');await p.waitForFunction(()=>!busy&&!workspace.pending_plan_warning);assert.equal(requests.at(-1).action,'cancel_plan_warning');assert.equal(w.plan.title,originalTitle);
  await p.evaluate(()=>action('plan',{advisory:true}));await p.waitForSelector('#plan-warning-dialog[open]');await p.locator('#plan-warning-dialog button[type=submit]').click();await p.waitForFunction(()=>!busy&&!workspace.pending_plan_warning);assert.equal(requests.at(-1).action,'approve_plan_warning');assert.equal(w.plan.title,'确认后的提醒草稿');assert.equal(w.plan.warning_acceptance.confirmed,true);
  await p.evaluate(()=>action('chat',{},'全程帮我安排'));await p.waitForSelector('#auto-selection-dialog[open]');
  assert.equal(w.requirements.start_date,'2026-10-12');assert.equal(await p.locator('#auto-generate-plan').isChecked(),true);
  await p.locator('[data-auto-requirement=start_date]').fill('2026-10-20');await p.click('#auto-selection-confirm');await p.waitForFunction(()=>!busy&&!workspace.pending_auto_selection);
  assert.equal(w.requirements.start_date,'2026-10-20');
  await p.evaluate(()=>{action('search_spots')});await p.waitForFunction(()=>busy&&document.querySelector('#content').textContent.includes('提前到达的景点资料'));
  assert.deepEqual(await p.evaluate(()=>workspace.selected_spots),['s']);
  await p.evaluate(()=>applyWorkspacePreview({id:'different-trip',catalog:{foreign:{id:'foreign',name:'另一会话',kind:'spot'}}}));
  assert.equal(await p.evaluate(()=>workspace.catalog.foreign),undefined);
  releasePreview=true;await p.waitForFunction(()=>!busy);
  w.meal_mode='optional';w.meal_choices={'2026-10-20|lunch':{mode:'chosen',food_id:'f'},'2026-10-20|dinner':{mode:'chosen',food_id:'f'}};
  w.food_query={ids:['f'],meal_date:'2026-10-20',meal_period:'lunch',scope:'周边5公里',anchor:'栈桥'};w.ui={view:'food',status:'ready'};
  w.timeline.meal_slots=[{date:'2026-10-20',period:'lunch'},{date:'2026-10-20',period:'dinner'},{date:'2026-10-21',period:'breakfast'}];
  await p.evaluate(value=>{workspace=value;mealDate='2026-10-20';mealPeriod='lunch';switchTab('food')},w);
  const requestCount=requests.length;await p.locator('#content [data-meal-remove]').click();await p.waitForFunction(()=>!busy);
  await p.waitForTimeout(450);
  assert.equal(requests.length,requestCount+1);assert.equal(requests.at(-1).args.mode,'remove');
  assert.equal(w.meal_choices['2026-10-20|lunch'],undefined);assert.equal(w.meal_choices['2026-10-20|dinner'].food_id,'f');
  assert.deepEqual(await p.evaluate(()=>[mealDate,mealPeriod]),['2026-10-20','lunch']);
  assert.deepEqual(errors,[]);fs.writeFileSync(path.join(root,'data/runtime/browser-assistance.json'),JSON.stringify({passed:true,fixture:true,checks:['consent-before-selection','explicit-replace','cancel-preserves-choices','actionable-diagnostics','place-jump','return-jump','smart-revision-updates-book','advisory-confirmation','advisory-cancel-keeps-plan'],errors},null,2));console.log('ASSISTANCE BROWSER PASSED');
 }finally{await b.close()}
})().catch(e=>{console.error(e.stack);process.exitCode=1});
