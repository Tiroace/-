const automator = require('miniprogram-automator');
(async () => {
  const mp = await automator.connect({ wsEndpoint: 'ws://127.0.0.1:9421' });
  const page = await mp.currentPage();
  const protoNames = (o) => Object.getOwnPropertyNames(Object.getPrototypeOf(o) || {});
  console.log('MP methods:', protoNames(mp).join(','));
  console.log('PAGE methods:', protoNames(page).join(','));
  const ta = await page.$('textarea');
  console.log('textarea:', !!ta, ta ? Object.getOwnPropertyNames(Object.getPrototypeOf(ta)).join(',') : '');
  const btn = await page.$('.check-btn') || await page.$('button');
  console.log('button found:', !!btn, btn ? (await btn.text && await btn.text().catch(()=>'')) : '');
  process.exit(0);
})().catch(e => { console.error('ERR', e.message); process.exit(1); });
