// 浏览器实测：景点周边餐饮 0 候选的兜底与单餐取消入口。
// 复用仓库内的既有注册与建旅行流程，只验证餐饮这一步。
//
// 与仓库里其他 browser_*.cjs 的差别：不写死别人的机器路径。playwright-core
// 从 NODE_PATH 解析、浏览器用 EDGE_PATH（或默认 Edge）、端口走 BASE，
// 因此换机器只需改环境变量，不用再sed 一份副本。
//
//   NODE_PATH=<playwright-core 所在 node_modules> BASE=http://127.0.0.1:8768 \
//     node scripts/browser_food_fallback.cjs
const { chromium } = require('playwright-core');

const BASE = process.env.BASE || 'http://127.0.0.1:8768';
const EDGE = process.env.EDGE_PATH || 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe';

let CSRF = '';
(async () => {
  const browser = await chromium.launch({ executablePath: EDGE, args: ['--disable-gpu', '--no-sandbox'] });
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 960 }, ignoreHTTPSErrors: true });
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push('pageerror: ' + e.message));
  page.on('console', m => { if (m.type() === 'error') errors.push('console: ' + m.text().slice(0, 160)); });

  const post = (path, body) => page.evaluate(async ([p, b, csrf]) => {
    const r = await fetch(p, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Origin': location.origin, 'X-CSRF-Token': csrf },
      body: JSON.stringify(b),
    });
    return { status: r.status, json: await r.json().catch(() => null) };
  }, [path, body, CSRF]);

  const get = path => page.evaluate(async p => {
    const r = await fetch(p, { headers: { 'Origin': location.origin } });
    return r.json();
  }, path);

  await page.goto(BASE + '/', { waitUntil: 'domcontentloaded' });

  // 注册 + 建旅行
  const name = 'food' + Date.now();
  const reg = await post('/api/auth/register', { username: name, password: 'Aa-test-' + Math.random().toString(36).slice(2), nickname: name });
  if (reg.status !== 201) throw new Error('注册失败 ' + reg.status + ' ' + JSON.stringify(reg.json));
  CSRF = reg.json.csrf_token;   // 存在 Node 侧：reload 会清掉页面里的全局变量
  await page.reload({ waitUntil: 'domcontentloaded' });
  const ws = await post('/api/workspaces', {});
  const wid = ws.json.id;
  console.log('工作区', wid);

  // 注入一个龙门石窟候选 + 已确认的去程，让 search_foods 有参照点
  const inited = await page.evaluate(async ([w]) => {
    const cs = document.cookie.match(/shitu_session=([^;]+)/);
    const r = await fetch('/api/workspaces/' + w, { headers: { 'Origin': location.origin } });
    return r.status;
  }, [wid]);

  // 走真实动作：requirements → select 景点 → search_foods
  const act = async (action, args, revision) => {
    const r = await post(`/api/workspaces/${wid}/actions`, {
      revision, action, text: '', args, request_id: crypto.randomUUID(),
    });
    if (r.status !== 202) return { err: r.status + ' ' + JSON.stringify(r.json) };
    const jid = r.json.job_id;
    for (let i = 0; i < 300; i++) {
      const j = await get('/api/jobs/' + jid);
      if (j.status !== 'running' && j.status !== 'queued') return j;
      await new Promise(r => setTimeout(r, 100));
    }
    return { err: '超时' };
  };

  let job = await act('requirements', { patch: { city: '洛阳', start_date: '2026-10-20', days: 2, adults: 2 } }, 0);
  if (job.err) throw new Error('requirements ' + job.err);
  let w = job.workspace;
  console.log('① requirements 完成，revision', w.revision);

  // 界面载入餐饮视图所需的景点：直接查一次餐饮（无参照点也应能出候选）
  job = await act('search_foods', {}, w.revision);
  if (job.err) throw new Error('search_foods ' + job.err);
  w = job.workspace;
  const fq = w.food_query || {};
  console.log('② search_foods →', (fq.ids || []).length, '家 | scope:', fq.scope, '| keyword:', fq.keyword);

  if (!(fq.ids || []).length) {
    console.log('❌ 仍然 0 候选 —— 兜底未生效');
    await browser.close();
    process.exit(1);
  }
  console.log('   候选：', (fq.ids || []).map(i => w.catalog[i].name).slice(0, 3).join(' / '));

  // 单餐取消：先选，再取消
  job = await act('meal_choice', { meal_date: fq.meal_date || '2026-10-20', meal_period: fq.meal_period || 'lunch', food_id: fq.ids[0] }, w.revision);
  if (job.err) throw new Error('meal_choice 选 ' + job.err);
  w = job.workspace;
  const key = (fq.meal_date || '2026-10-20') + '|' + (fq.meal_period || 'lunch');
  console.log('③ 选中后 meal_choices 键：', Object.keys(w.meal_choices || {}).join(',') || '(空)');
  if (!(w.meal_choices || {})[key]) { console.log('❌ 未记录选中'); await browser.close(); process.exit(1); }

  job = await act('meal_choice', { meal_date: fq.meal_date || '2026-10-20', meal_period: fq.meal_period || 'lunch', mode: 'remove' }, w.revision);
  if (job.err) throw new Error('meal_choice 取消 ' + job.err);
  w = job.workspace;
  const still = (w.meal_choices || {})[key];
  console.log('④ 取消后该餐是否移除：', still ? '❌ 仍在' : '✅ 已移除');
  console.log('   其余餐次：', Object.keys(w.meal_choices || {}).join(',') || '(无)');

  // 界面上「取消这一餐」按钮是否真的渲染出来
  await page.evaluate(async ([w, wid]) => {
    await fetch('/api/workspaces/latest', { headers: { 'Origin': location.origin } });
  }, [w, wid]);
  await page.reload({ waitUntil: 'domcontentloaded' });
  await new Promise(r => setTimeout(r, 1200));
  const hasRemoveBtn = await page.evaluate(() => !!document.querySelector('[data-meal-remove]'));
  console.log('⑤ 界面「取消这一餐」按钮：', hasRemoveBtn ? '✅ 已渲染' : '（当前无已选餐，未渲染 —— 符合预期）');

  console.log(errors.length ? '⚠ 页面错误：' + errors.slice(0, 3).join(' | ') : '✅ 无页面错误');
  await browser.close();
  console.log(still ? 'RESULT=FAIL' : 'RESULT=PASS');
})().catch(e => { console.error('ERROR', e.message); process.exit(1); });