const {chromium}=require('C:/Users/asus/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const assert=require('node:assert/strict'),crypto=require('node:crypto'),fs=require('node:fs');
(async()=>{
 const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
 const p=await browser.newPage({viewport:{width:1600,height:1000}}),base='http://127.0.0.1:8767',password=crypto.randomBytes(24).toString('base64url'),headers={Origin:base,'Content-Type':'application/json'},errors=[];let session;
 p.on('pageerror',e=>errors.push(e.message));const responses=[];p.on('response',r=>{if(r.url().includes('/map-image'))responses.push({status:r.status(),cache:r.headers()['cache-control']})});
 try{
  const r=await p.request.post(base+'/api/auth/register',{headers,data:{username:'qa_map9_'+Date.now().toString(36),nickname:'地图回归',password}});assert.equal(r.status(),201);session=await r.json();headers['X-CSRF-Token']=session.csrf_token;
  await p.goto(base);await p.waitForSelector('#application:not([hidden])');await p.click('#map-button');const m=p.locator('#content .location-map');await p.waitForFunction(()=>document.querySelector('#content .map-update-text')?.textContent==='',{},{timeout:25000});
  assert.equal(Number(await m.getAttribute('data-map-zoom')),3);assert.ok(responses.some(r=>r.status===200&&r.cache?.includes('private')));await p.screenshot({path:'.展示检查/真实-v9-全国交互地图.png'});
  const rect=await m.locator('canvas').boundingBox(),point={x:Math.round(rect.x+rect.width/2),y:Math.round(rect.y+rect.height/2)},origin=await m.getAttribute('data-map-center');await p.mouse.move(point.x,point.y);await p.mouse.down();await p.mouse.move(point.x+60,point.y+20,{steps:8});assert.notEqual(await m.getAttribute('data-map-center'),origin);await p.mouse.up();await p.waitForFunction(()=>document.querySelector('#content .map-update-text')?.textContent==='',{},{timeout:25000});
  await p.mouse.wheel(0,-120);await p.waitForTimeout(60);assert.equal(Number(await m.getAttribute('data-map-zoom')),4);await m.locator('[data-map-zoom-action="center"]').click();assert.equal(await m.getAttribute('data-map-center'),origin);assert.equal(Number(await m.getAttribute('data-map-zoom')),4);await m.locator('[data-map-zoom-action="reset"]').click();assert.equal(await m.locator('.map-zoom-level').innerText(),'100%');
  assert.deepEqual(errors,[]);fs.writeFileSync('data/runtime/browser-live-map-v9.json',JSON.stringify({passed:true,real_amap_basemap:true,checks:['blank-trip-national-map','authenticated-private-cache','drag','wheel','center-only-reset','fit-reset'],responses,errors},null,2));console.log('LIVE INTERACTIVE MAP V9 PASSED');
 }finally{if(session){const d=await p.request.delete(base+'/api/account',{headers,data:{password}});assert.equal(d.status(),200)}await browser.close()}
})().catch(e=>{console.error(e.message);process.exitCode=1});
