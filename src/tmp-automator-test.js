const automator = require('miniprogram-automator');
(async () => {
  try {
    const mp = await automator.connect({ wsEndpoint: 'ws://127.0.0.1:9421' });
    console.log('CONNECTED');
    try { await mp.reLaunch('/pages/index/index'); console.log('reLaunch ok'); } catch (e) { console.log('reLaunch err:', e.message); }
    await new Promise(r => setTimeout(r, 5000));
    try { const page = await mp.currentPage(); console.log('PAGE:', page && page.path); } catch (e) { console.log('currentPage err:', e.message); }
    try { const sys = await mp.systemInfo(); console.log('systemInfo:', JSON.stringify(sys).slice(0,200)); } catch (e) { console.log('sys err:', e.message); }
    process.exit(0);
  } catch (e) { console.error('ERR:', e && e.message); process.exit(1); }
})();
