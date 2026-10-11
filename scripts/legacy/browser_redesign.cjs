const {chromium}=require('C:/Users/asus/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('fs');
(async()=>{
 const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
 const page=await browser.newPage({baseURL:'http://127.0.0.1:8767',viewport:{width:1440,height:1000}});const errors=[];page.on('pageerror',e=>errors.push(e.message));
 const done=async()=>{await page.waitForSelector('#progress[hidden]',{state:'attached',timeout:240000});if(await page.locator('#error:not([hidden])').count())throw Error(await page.locator('#error').textContent())};
 const state=async()=>await(await page.request.get('/api/workspaces/latest')).json();
 await page.goto('/');await page.waitForSelector('#workflow .flow-step');let w=await state();
 if(await page.locator('.flow-step').count()!==4)throw Error('步骤缺失');
 await page.locator('.tabs [data-tab="plan"]').click();
 if(!process.argv.includes('--ui-only')){await page.locator('#content [data-action="plan"]').click();await done();w=await state();}
 if(w.plan.review.status!=='completed'||!w.plan.review.summary)throw Error('独立审核未完成');
 await page.evaluate(()=>scrollTo(0,0));await page.screenshot({path:'.展示检查/真实-重新设计-计划书.png',fullPage:false});
 const composer=await page.locator('#send').boundingBox();if(composer.y+composer.height>1000)throw Error('桌面聊天输入被首屏遮挡');
 await page.locator('#conditions').click();await page.click('#close-settings');
 if(await page.locator('.book-nav a[href^="#day-"]').count()!==w.plan.days.length)throw Error('每日目录不完整');
 await page.locator('.book-nav a[href="#book-todos"]').click();if(!(await page.locator('#book-todos').isVisible()))throw Error('待办目录失效');
 await page.locator('.tabs [data-tab="hotel"]').click();
 if(!(await page.locator('.room').count()))throw Error('房型未转换成可读内容');
 if(await page.locator('.room-details pre').count())throw Error('仍显示原始房型JSON');
 await page.evaluate(()=>scrollTo(0,0));await page.screenshot({path:'.展示检查/真实-重新设计-住宿.png',fullPage:false});
 await page.locator('.tabs [data-tab="spot"]').click();
 await page.locator(`#content [data-select="${w.selected_spots[0]}"]`).click();await done();
 await page.locator('.tabs [data-tab="plan"]').click();
 if(await page.locator('#print').count()||await page.locator('.book').count())throw Error('旧计划仍可被使用');
 if((await page.request.get(`/api/workspaces/${w.id}/export`)).status()!==409)throw Error('旧计划导出未拦截');
 await page.locator('#content [data-action="undo"]').click();await done();w=await state();
 if(w.plan.stale||(await page.request.get(`/api/workspaces/${w.id}/export`)).status()!==200)throw Error('撤销未恢复计划');
 await page.reload();await page.waitForSelector('.book');
 if(process.argv.includes('--intent')){
  await page.fill('#message','帮我更新这次旅行的天气预报。');await page.click('#send');await done();
  if(!(await page.locator('.tabs [data-tab="weather"]').getAttribute('class')||'').includes('active'))throw Error('自然语言查询没有展示对应内容');
  await page.locator('.tabs [data-tab="plan"]').click();await page.locator('#content [data-action="undo"]').click();await done();w=await state();
 }
 await page.pdf({path:'data/runtime/青岛旅行计划书-重新设计.pdf',format:'A4',printBackground:true});
 for(const width of [390,768,1440]){await page.setViewportSize({width,height:1000});if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw Error('宽度'+width+'存在横向溢出')}
 await page.setViewportSize({width:390,height:844});await page.screenshot({path:'.展示检查/真实-重新设计-手机.png',fullPage:false});
 const fixture=JSON.parse(JSON.stringify(w));fixture.plan=null;fixture.hotel=null;fixture.messages=[];fixture.selected_transport=null;fixture.selected_return=null;
 await page.route('**/api/workspaces/latest',r=>r.fulfill({json:fixture}));
 fixture.requirements={};fixture.selected_spots=[];fixture.catalog={};await page.reload();await page.waitForSelector('#mission h3');
 if(!(await page.locator('#mission').textContent()).includes('先聊聊'))throw Error('初次使用引导错误');
 await page.locator('#mission [data-open-settings]').click();if(!(await page.locator('#settings').evaluate(d=>d.open)))throw Error('条件编辑入口失效');if(await page.locator('[name="city"]').inputValue())throw Error('新旅行沿用了旧条件');await page.click('#close-settings');
 fixture.requirements={city:'青岛',start_date:'2026-10-08',days:1,adults:1};fixture.selected_spots=w.selected_spots;fixture.catalog=w.catalog;await page.reload();await page.waitForSelector('#mission h3');
 if(!(await page.locator('#mission').textContent()).includes('一日游'))throw Error('一日游被强制选住宿');
 fixture.requirements={city:'青岛',days:3};await page.reload();await page.waitForSelector('#mission h3');if(!(await page.locator('#mission').textContent()).includes('补上时间和人数'))throw Error('缺失条件引导错误');
 await page.unroute('**/api/workspaces/latest');await page.reload();await page.waitForSelector('.book');
 console.log(JSON.stringify({checks:['四步流程','真实计划生成及独立审核','完整计划目录','房型易读展示','选择变化阻止旧计划展示和导出','撤销恢复','刷新保留','打印PDF','390/768/1440无横向溢出','首次使用/一日游/缺失条件界面分支'],review:w.plan.review.status,page_errors:errors}));
 if(errors.length)throw Error('页面发生JS错误');
 fs.writeFileSync('data/runtime/browser-redesign.json',JSON.stringify({workspace_id:w.id,review:w.plan.review.status,page_errors:errors,intent_checked:process.argv.includes('--intent'),passed:true},null,2));
 await browser.close();
})().catch(e=>{console.error(e.message);process.exit(1)});
