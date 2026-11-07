const automator = require('miniprogram-automator');
(async () => {
  const mp = await automator.connect({ wsEndpoint: 'ws://127.0.0.1:9421' });
  const page = await mp.currentPage();
  console.log('PAGE:', page.path);
  // 尝试截图
  try {
    const r = await mp.screenshot({ path: 'D:\\程序上线资料准备\\测试截图_试1.png' });
    console.log('screenshot result:', JSON.stringify(r).slice(0, 200));
  } catch (e) { console.log('screenshot err:', e.message); }
  // 页面数据键
  const data = await page.data();
  console.log('data keys:', Object.keys(data || {}).join(','));
  const html = await page.evaluate(() => document.body ? document.body.innerHTML.slice(0,300) : 'no body');
  console.log('body slice:', String(html).slice(0,200));
  process.exit(0);
})().catch(e => { console.error('ERR', e.message); process.exit(1); });
