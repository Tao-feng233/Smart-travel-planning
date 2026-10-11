const {chromium}=require('C:/Users/asus/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('fs');
(async()=>{
 const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
 const page=await browser.newPage({baseURL:'http://127.0.0.1:8767',viewport:{width:1440,height:1000}});
 const failures=[];page.on('pageerror',e=>failures.push(e.message));
 await page.goto('http://127.0.0.1:8767');await page.waitForSelector('#connection:has-text("真实接口")');
 await page.click('#new');await page.waitForTimeout(500);
 await page.fill('#message','我和一位朋友，两位成年人，10月8日从上海去青岛玩三天，总预算6000元，想轻松一些、少走路。先介绍栈桥、八大关、五四广场这些地方，让我选。');
 await page.click('#send');await page.waitForSelector('#progress[hidden]',{timeout:240000,state:'attached'});
 if(await page.locator('#error:not([hidden])').count())throw Error(await page.locator('#error').textContent());
 const first=await page.request.get('/api/workspaces/latest');const initial=await first.json();
 console.log('INTENT',JSON.stringify(initial.requirements),'CANDIDATES',Object.keys(initial.catalog||{}).length);
 for(const name of ['栈桥','八大关','五四广场']){
  const card=page.locator('.card').filter({has:page.locator('h3').filter({hasText:name})}).first();
  if(!await card.count())throw Error('缺少请求的候选：'+name);
  await card.locator('[data-select]').click();await page.waitForSelector('#progress[hidden]',{timeout:240000,state:'attached'});
 }
 await page.screenshot({path:'.展示检查/真实-景点.png',fullPage:true});
 await page.click('[data-tab="hotel"]');await page.locator('#content button[data-action="search_hotels"]').click();
 await page.waitForSelector('#progress[hidden]',{timeout:240000,state:'attached'});
 if(await page.locator('#error:not([hidden])').count())throw Error(await page.locator('#error').textContent());
 const beforeHotel=await (await page.request.get('/api/workspaces/latest')).json();
 const hotels=Object.values(beforeHotel.catalog).filter(p=>p.kind==='hotel');
 console.log('HOTELS',JSON.stringify(hotels.map(h=>({name:h.name,location:!!h.location,route:h.anchor_route?.minutes}))));
 const chosen=hotels.find(h=>h.location)||hotels[0];
 await page.locator(`button[data-select="${chosen.id}"]`).click();await page.waitForSelector('#progress[hidden]',{timeout:240000,state:'attached'});
 await page.screenshot({path:'.展示检查/真实-住宿.png',fullPage:true});
 await page.click('[data-tab="weather"]');await page.locator('#content button[data-action="weather"]').click();await page.waitForSelector('#progress[hidden]',{timeout:240000,state:'attached'});
 await page.click('[data-tab="plan"]');await page.locator('#content button[data-action="plan"]').click();await page.waitForSelector('#progress[hidden]',{timeout:240000,state:'attached'});
 if(await page.locator('#error:not([hidden])').count())throw Error(await page.locator('#error').textContent());
 await page.waitForSelector('.book');await page.screenshot({path:'.展示检查/真实-计划书.png',fullPage:true});
 const final=await (await page.request.get('/api/workspaces/latest')).json();
 console.log('PLAN',JSON.stringify({days:final.plan.days.length,selected:final.selected_spots.length,routes:final.plan.days.flatMap(d=>d.events).filter(e=>e.kind==='route').length,review:final.plan.review.status,warnings:final.plan.warnings.length}));
 const exportR=await page.request.get(`/api/workspaces/${final.id}/export`);console.log('EXPORT',exportR.status(),(await exportR.text()).length);
 await page.reload();await page.waitForSelector('#connection:has-text("真实接口")');
 const restored=await (await page.request.get('/api/workspaces/latest')).json();if(restored.id!==final.id||restored.selected_spots.length!==final.selected_spots.length)throw Error('持久化恢复失败');
 await page.setViewportSize({width:390,height:844});await page.click('[data-tab="plan"]');await page.screenshot({path:'.展示检查/真实-手机.png',fullPage:true});
 console.log('MOBILE_OVERFLOW',await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth));console.log('PAGE_ERRORS',JSON.stringify(failures));
 fs.writeFileSync('data/runtime/browser-result.json',JSON.stringify({workspace_id:final.id,errors:failures,checks:['自然语言意图','景点查询选择','按景点查询住宿','酒店选择','天气查询','真实路线','主助手生成','审核助手','计划书导出','刷新恢复','移动端']},null,2));
 await browser.close();
})().catch(e=>{console.error(e.message);process.exit(1)});

