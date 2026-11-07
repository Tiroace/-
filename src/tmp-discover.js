const automator = require('miniprogram-automator');
(async () => {
  const mp = await automator.connect({ wsEndpoint: 'ws://127.0.0.1:9421' });
  const page = await mp.currentPage();
  console.log('PAGE:', page.path);
  // textarea 输入测试
  const ta = await page.$('textarea');
  if (ta) { try { await ta.input('测试输入'); console.log('textarea input OK'); } catch (e) { console.log('input err', e.message); } }
  // 找可点击元素
  const views = await page.$$('view');
  const list = [];
  for (const v of views) {
    try { const t = (await v.text()) || ''; if (t && t.length < 40) list.push(t.trim()); } catch (e) {}
  }
  console.log('view texts:', JSON.stringify([...new Set(list)].slice(0, 40)));
  const btns = await page.$$('button');
  console.log('button count:', btns.length);
  process.exit(0);
})().catch(e => { console.error('ERR', e.message); process.exit(1); });
