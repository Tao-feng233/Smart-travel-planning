// Isolated UI fixtures; no real records, room providers or booking operations.
const {chromium}=require('C:/Users/asus/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..'),base='http://127.0.0.1:8767';
(async()=>{
 const b=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
 const p=await b.newPage({viewport:{width:1500,height:1000}}),errors=[],requests=[];
 p.on('pageerror',e=>errors.push(e.message));
 const source={name:'合成来源',queried_at:'2026-10-08'},room={id:'r',hotel_id:'h',name:'大床房',quantity:1,price:200,room_index:0,rate_index:0};
 const h={id:'h',kind:'hotel',name:'测试酒店',location:'120.30,36.05',address:'青岛测试地址',source,room_choices:[room],detail:{roomTypes:[{roomTypeName:'大床房',maxOccupancy:2,ratePlans:[{rmbPrices:200,count:2}]}]}};
 let w={id:'optional-hotel',title:'住宿可选房型验证',revision:1,requirements:{city:'青岛',origin:'郑州',start_date:'2026-10-12',days:2,adults:2},catalog:{h},selected_spots:[],spots_confirmed:true,hotel:null,selected_room:null,messages:[],tickets:{},meal_choices:{},trace:[],hotel_query:{ids:['h']},ui:{view:'hotel',status:'ready'},timeline:{entries:[],meal_slots:[],conflicts:[]}},request,jid=0;
 await p.route(base+'/**',async r=>{
  const u=new URL(r.request().url());
  if(u.pathname.startsWith('/assets/'))return r.fulfill({path:path.join(root,'frontend',path.basename(u.pathname))});
  if(!u.pathname.startsWith('/api/'))return r.fulfill({path:path.join(root,'frontend/index.html'),contentType:'text/html'});
  if(u.pathname.endsWith('/map-image'))return r.fulfill({contentType:'image/svg+xml',body:'<svg xmlns="http://www.w3.org/2000/svg" width="1024" height="768"/>'});
  if(u.pathname.endsWith('/actions')){request=r.request().postDataJSON();requests.push(request);return r.fulfill({contentType:'application/json',body:JSON.stringify({job_id:'j'+(++jid)})})}
  if(u.pathname.endsWith('/events')){
   if(request.action==='select')w.hotel=h;
   else if(request.action==='complete_hotel')w.stage='交通';
   else if(request.action==='select_room'){assert.equal(request.args.room_id||request.args.id,'r');w.selected_room=room;w.hotel=h}
   else throw Error('Unexpected room dependency: '+request.action);
   w.revision++;w.ui={action:request.action,view:request.action==='complete_hotel'?'transport':'hotel',status:'ready'};
   return r.fulfill({contentType:'text/event-stream',body:'event: done\ndata: '+JSON.stringify({id:'j'+jid,action:request.action,status:'completed',workspace:w,ui:w.ui})+'\n\n'});
  }
  const data=u.pathname.endsWith('/auth/me')?{user:{id:'qa',nickname:'测试'},csrf_token:'fixture'}:u.pathname==='/api/workspaces'?{items:[{id:w.id,title:w.title}],total:1}:w;
  return r.fulfill({contentType:'application/json',body:JSON.stringify(data)});
 });
 try{
  await p.goto(base);await p.waitForSelector('#application:not([hidden])');
  assert.equal(await p.locator('#content [data-action=complete_hotel]').isDisabled(),true);
  await p.locator('#content [data-select=h]').click();await p.waitForFunction(()=>!busy&&workspace.hotel?.id==='h');
  assert.equal(await p.locator('#content [data-action=complete_hotel]').isEnabled(),true);
  assert.match(await p.locator('.current-stay').innerText(),/房型可选/);
  assert.equal(await p.evaluate(()=>workspace.selected_room),null);
  assert.equal(await p.locator('.flow-step[data-tab=hotel]').first().evaluate(el=>el.classList.contains('done')),true);
  await p.locator('#content [data-action=complete_hotel]').click();await p.waitForFunction(()=>!busy&&tab==='transport');
  assert.deepEqual(requests.map(x=>x.action),['select','complete_hotel']);assert.equal(w.selected_room,null);
  await p.evaluate(()=>switchTab('hotel'));await p.locator('#content button[data-open-candidate=h]').click();await p.waitForSelector('#candidate-dialog[open]');
  assert.match(await p.locator('#candidate-modal-body').innerText(),/具体房型（可选）/);
  await p.locator('#candidate-dialog [data-room=r]').click();await p.waitForFunction(()=>!busy&&workspace.selected_room?.id==='r');
  assert.equal(w.hotel.id,'h');assert.equal(requests.at(-1).action,'select_room');assert.deepEqual(errors,[]);
  fs.writeFileSync(path.join(root,'data/runtime/browser-optional-hotel-room.json'),JSON.stringify({passed:true,fixture:true,checks:['hotel-only-enables-continue','no-room-dependency','hotel-navigation-complete','optional-room-still-selectable'],errors},null,2));
  console.log('OPTIONAL HOTEL ROOM BROWSER PASSED');
 }finally{await b.close()}
})().catch(e=>{console.error(e.stack);process.exitCode=1});
