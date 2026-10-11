// UI recovery scenario uses mocked job responses; account and permission calls use the real service.
const {chromium}=require('C:/Users/asus/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const crypto=require('crypto'),fs=require('fs');
(async()=>{
 const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
 const page=await browser.newPage({baseURL:'http://127.0.0.1:8767',viewport:{width:1440,height:1000}}),password=crypto.randomBytes(18).toString('base64url'),headers={Origin:'http://127.0.0.1:8767','Content-Type':'application/json'},errors=[];page.on('pageerror',e=>errors.push(e.message));let session;
 try{
  const r=await page.request.post('/api/auth/register',{headers,data:{username:'qa_resume_'+Date.now().toString(36),password,nickname:'一二三四五六七八九十一二三四五六七八九十一二三四五六七八九十'}});if(r.status()!==201)throw Error('测试注册失败');session=await r.json();headers['X-CSRF-Token']=session.csrf_token;
  const created=await page.request.post('/api/workspaces',{headers,data:{}});let w=await created.json();
  const ack=await page.request.post('/api/workspaces/'+w.id+'/actions',{headers,data:{revision:0,action:'requirements',args:{patch:{city:'青岛'}},request_id:crypto.randomUUID()}});const jid=(await ack.json()).job_id;
  let j;for(let i=0;i<30;i++){j=await(await page.request.get('/api/jobs/'+jid)).json();if(j.status!=='running')break;await new Promise(r=>setTimeout(r,100))}
  if(j.status!=='completed'||j.action!=='requirements')throw Error('真实任务状态未持久保存');w=j.workspace;
  const pending={...w,active_job:{id:'ui-recovery-fixture',progress:'正在恢复任务进度'}};let reads=0;
  await page.route('**/api/workspaces/latest',r=>r.fulfill({json:pending}));await page.route('**/api/jobs/ui-recovery-fixture',r=>r.fulfill({json:++reads<3?{status:'running',progress:'正在读取已保存的进度'}:{status:'completed',action:'weather',workspace:{...w,active_job:null}}}));
  await page.goto('/');await page.waitForSelector('#progress:not([hidden])');await page.waitForSelector('.tabs [data-tab="weather"].active',{timeout:15000});
  for(const width of [390,768,1440]){await page.setViewportSize({width,height:1000});if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw Error('长昵称造成横向溢出')}
  if(errors.length)throw Error('页面脚本异常');console.log('PERSISTENT JOB + RELOAD UI + LONG NICKNAME CHECKS PASSED');fs.writeFileSync('data/runtime/browser-recovery.json',JSON.stringify({passed:true,page_errors:errors,real_job_storage:true,reload_ui_fixture:true,long_nickname_widths:[390,768,1440]},null,2));
 }finally{if(session)await page.request.delete('/api/account',{headers,data:{password}});await browser.close()}
})().catch(e=>{console.error(e.message);process.exit(1)});
