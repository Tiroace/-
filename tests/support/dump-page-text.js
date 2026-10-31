// 抓取当前各页面的真实文案与结构，用于校正断言
const automator = require('miniprogram-automator');
const WS = process.argv[2] || 'ws://127.0.0.1:9422';

function withTimeout(p, ms, label) {
  return Promise.race([p, new Promise((_, rej) => setTimeout(() => rej(new Error('TIMEOUT:' + label)), ms))]);
}

function flattenStrings(obj, out = [], depth = 0) {
  if (depth > 8 || obj == null) return out;
  if (typeof obj === 'string') out.push(obj);
  else if (Array.isArray(obj)) obj.forEach((v) => flattenStrings(v, out, depth + 1));
  else if (typeof obj === 'object') Object.values(obj).forEach((v) => flattenStrings(v, out, depth + 1));
  return out;
}

(async () => {
  const mp = await automator.connect({ wsEndpoint: WS });
  for (const [name, url] of [
    ['index', '/pages/index/index'],
    ['report', '/pages/report/index'],
    ['mine', '/pages/mine/index'],
  ]) {
    try {
      await withTimeout(mp.reLaunch(url), 15000, 'reLaunch ' + url);
      await new Promise((r) => setTimeout(r, 1500));
      const data = await withTimeout(
        mp.evaluate(() => {
          const pages = getCurrentPages();
          const cur = pages[pages.length - 1];
          return cur ? { route: cur.route, data: cur.data } : null;
        }),
        8000,
        'readPage'
      );
      const texts = flattenStrings(data.data).filter((t) => /[\u4e00-\u9fff]/.test(t));
      console.log(`\n===== ${name} (${data.route}) =====`);
      console.log(texts.slice(0, 30).join(' | '));
    } catch (e) {
      console.log(`\n===== ${name} FAILED: ${e.message}`);
    }
  }
  await mp.disconnect();
  process.exit(0);
})().catch((e) => {
  console.log('ERR', e && e.message);
  process.exit(1);
});
