const {chromium}=require('C:/Users/asus/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('node:fs'),assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
 const page=await browser.newPage({viewport:{width:1500,height:1000}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
 page.setDefaultTimeout(15000);
 const w=JSON.parse(fs.readFileSync('data/runtime/browser-v11-fixture.json','utf8'));let request;
 Object.assign(w.catalog.h,{location:null,address:null,match_status:'未找到名称与地址一致的地图地点，暂不标注坐标',location_checked_at:'2026-10-07',access:{status:'unknown',message:'缺少地点坐标，实际通行待核实'}});w.hotel={...w.catalog.h};
 w.hotel_query={ids:['h'],excluded:[{id:'excluded',name:'示例不适合酒店',message:'当前已核对的方式均未返回该路段方案'}]};
 await page.route('**/api/**',async r=>{
  const url=r.request().url();let data;
  if(url.includes('/map-image'))return r.fulfill({contentType:'image/svg+xml',body:'<svg xmlns="http://www.w3.org/2000/svg" width="800" height="440"><rect width="100%" height="100%" fill="#ccd"/></svg>'});
  if(url.includes('/auth/me'))data={user:{id:'qa',nickname:'检查'},csrf_token:'fixture'};
  else if(url.includes('/actions')){request=r.request().postDataJSON();data={job_id:'j'}}
  else if(url.includes('/events')){
   assert.equal(request.action,'place_detail');assert.equal(request.args.id,'h');
   Object.assign(w.catalog.h,{location:'120.388233,36.065221',address:'香港中路28号',location_status:'verified',match_status:'已核对地图地点与街道门牌'});w.hotel={...w.catalog.h};w.revision++;w.ui={action:'place_detail',status:'ready',view:'hotel'};
   return r.fulfill({contentType:'text/event-stream',body:'event: done\ndata: '+JSON.stringify({id:'j',status:'completed',workspace:w,ui:w.ui,action:'place_detail'})+'\n\n'});
  }else if(url.endsWith('/api/workspaces'))data={items:[{id:w.id,title:'位置检查',city:'青岛'}],total:1};
  else if(url.includes('/api/workspaces'))data=w;
  else data={};
  return r.fulfill({contentType:'application/json',body:JSON.stringify(data)});
 });
 try{
  await page.goto('http://127.0.0.1:8767');await page.waitForSelector('#application:not([hidden])');await page.evaluate(()=>switchTab('hotel'));
  assert.match(await page.locator('#content').innerText(),/实际通行待核实/);
  assert.equal(await page.locator('#content .excluded-candidates').count(),1);
  await page.locator('#content [data-place-detail="h"]').click();await page.waitForFunction(()=>!busy&&workspace.catalog.h.location);
  assert.match(await page.locator('#content .candidate-location').innerText(),/香港中路28号/);
  assert.equal(await page.locator('#selection-minimap .location-map').evaluate(el=>JSON.parse(el.dataset.mapPoints).filter(p=>p.id==='h').length),1);
  await page.evaluate(()=>openCandidate('h'));assert.match(await page.locator('#candidate-dialog .detail-address').innerText(),/香港中路28号/);
  assert.equal(await page.locator('#candidate-dialog #candidate-modal-body .location-map').evaluate(el=>JSON.parse(el.dataset.mapPoints).filter(p=>p.id==='h').length),1);
  await page.screenshot({path:'.展示检查/新版-酒店位置恢复与地图标注.png'});
  assert.deepEqual(errors,[]);console.log('HOTEL POSITION + CARD + BOTH MAPS + FILTER NOTICE PASSED');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
