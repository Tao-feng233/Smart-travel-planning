const { chromium } = require('C:/Users/asus/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const assert = require('node:assert/strict');
(async () => {
  const browser = await chromium.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    const response = await page.goto('http://127.0.0.1:8767/?refresh=login-20261005');
    assert.equal(response.headers()['cache-control'], 'no-store');
    await page.waitForSelector('#auth-gate:not([hidden])');
    assert.equal(await page.locator('#application').isVisible(), false);
    assert.equal(await page.locator('#auth-submit').innerText(), '登录并继续');
    await page.click('#auth-register-tab');
    assert.equal(await page.locator('#auth-nickname').isVisible(), true);
    assert.equal(await page.locator('#auth-password').getAttribute('minlength'), '12');
    await page.reload();
    await page.waitForSelector('#auth-gate:not([hidden])');
    assert.equal(await page.locator('script[src*="?v="]').count(), 2);
    assert.equal(await page.getByText('后端尚未连接', { exact: true }).count(), 0);
    await page.screenshot({ path: '.展示检查/真实-账户-登录刷新修复.png' });
    assert.deepEqual(errors, []);
    console.log('通过：登录入口、注册切换、刷新恢复、资源版本、页面禁用缓存；无浏览器脚本异常。');
  } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exitCode = 1; });
