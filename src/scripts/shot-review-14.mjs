// 提审截图 14 张（06 号 §三 口径）—— 测试者版 v2
// 用法：node D:\qiuzhibilei\src\scripts\shot-review-14.mjs
// 依赖：cli.bat auto --auto-port 9422 已开
// 产物：D:\qiuzhibilei\reports\review14\<编号>-<页面>.png
//
// 本机实测约束（写死在实现里，别改回去）：
//  1) page.$() / page.$$() / page.data() 全部超时 —— 只能 mp.evaluate()。
//  2) __data__ 是压缩别名结构，靠「递归摊平取所有字符串」断言，不依赖键名。
//  3) 连续 navigateTo 多次会让自动化通道崩（Uncaught [object Object]）。
//     → 每张图独立 connect/disconnect，且每次只做一次导航。
//  4) 滚动用 mp.pageScrollTo(数字)。
//  5) 「我的」页菜单文案在页面结构里、不在 __data__，故该页只断言 path + 截图。
import { createRequire } from 'node:module';
import fs from 'node:fs';
import path from 'node:path';

const require = createRequire('D:/qiuzhibilei/tests/');
const automator = require('miniprogram-automator');

const WS = process.env.QBL_WS || 'ws://127.0.0.1:9422';
const OUT = 'D:/qiuzhibilei/reports/review14';
fs.mkdirSync(OUT, { recursive: true });

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const AI_RE = /(?<![A-Za-z])AI(?![A-Za-z])/;
const PROMISE_RE = /(几分钟内|分钟内完成|马上发布|立即发布|即刻公开|小时内完成|秒发布)/;

const VERDICT = {
  red: '这份工作，建议先别去',
  amber: '先问清楚，再决定去不去',
  green: '截图里没看到明显风险',
  unknown: '截图信息不够，再补一张',
};

async function readText(mp) {
  const raw = await mp.evaluate(() => {
    const ps = getCurrentPages();
    const p = ps[ps.length - 1];
    if (!p || !p.__data__) return '';
    const out = [];
    const seen = new Set();
    const walk = (v, d) => {
      if (v == null || d > 6) return;
      if (typeof v === 'string') { const s = v.trim(); if (s.length >= 2 && !seen.has(s)) { seen.add(s); out.push(s); } return; }
      if (typeof v === 'object') { try { for (const k in v) walk(v[k], d + 1); } catch (e) {} }
    };
    walk(p.__data__, 0);
    return out.join('\n');
  });
  return String(raw || '');
}

// 单张：独立连接 → 导航 → 可选滚动 → 校验 → 截图 → 断开
async function shot(spec) {
  const { name, file, nav, scroll, checks, needPath } = spec;
  let mp = null;
  try {
    mp = await automator.connect({ wsEndpoint: WS });
    if (nav.tab) await mp.switchTab(nav.url);
    else await mp.navigateTo(nav.url);
    await sleep(nav.wait || 3200);

    const page = await mp.currentPage();
    if (needPath && page.path !== needPath) throw new Error('页面不对：' + page.path);

    // 校验在「滚动前」做：__data__ 只反映页面数据，不随滚动变化，滚动后读不到下方内容。
    const text = await readText(mp);
    if (AI_RE.test(text)) throw new Error('上屏出现 AI 字样');
    if (PROMISE_RE.test(text)) throw new Error('上屏出现审核时效承诺');

    if (checks && checks.length) {
      const miss = checks.filter((c) => !c.test(text));
      if (miss.length) throw new Error('缺少：' + miss.map((c) => c.name).join('、'));
    }

    // 再滚动（滚动本身已验证生效，但 __data__ 不会因此变化，故不再据此断言）
    if (typeof scroll === 'number') { await mp.pageScrollTo(scroll); await sleep(1500); }

    const target = path.join(OUT, file);
    await mp.screenshot({ path: target });
    const size = fs.statSync(target).size;
    if (size < 15000) throw new Error('疑似空图，仅 ' + size + ' 字节');
    console.log('✓ ' + name + ' → ' + file + ' (' + size + ' bytes)');
    return true;
  } catch (e) {
    console.log('✗ ' + name + ' 失败：' + (e && e.message));
    return false;
  } finally {
    if (mp) { try { await mp.disconnect(); } catch (e) { /* 忽略 */ } }
  }
}

const SPECS = [
  {
    name: '#01 首页', file: '01-首页.png',
    nav: { tab: true, url: '/pages/index/index' }, scroll: 0, needPath: 'pages/index/index',
    checks: [
      { name: '上传入口', test: (t) => t.includes('选截图') || t.includes('上传') },
      { name: '上传入口', test: (t) => t.includes('选截图') },
    ],
  },
  {
    name: '#02 首页下半屏', file: '02-首页下半屏.png',
    nav: { tab: true, url: '/pages/index/index' }, scroll: 1200, needPath: 'pages/index/index',
    checks: [
      { name: '示例/信号灯', test: (t) => (t.includes('示例') || t.includes('红灯')) },
    ],
  },
  {
    name: '#05 报告页-red', file: '05-报告页-red.png',
    nav: { url: '/pages/report/index?sample=1&overall=red' }, scroll: 0, needPath: 'pages/report/index',
    checks: [
      { name: '结论标题', test: (t) => t.includes(VERDICT.red) },
      { name: 'D20 免责声明', test: (t) => t.includes('本报告由系统') && t.includes('不构成法律意见') },
    ],
  },
  {
    name: '#07 报告页-amber', file: '07-报告页-amber.png',
    nav: { url: '/pages/report/index?sample=1&overall=amber' }, scroll: 0, needPath: 'pages/report/index',
    checks: [{ name: '结论标题', test: (t) => t.includes(VERDICT.amber) }],
  },
  {
    name: '#08 报告页-green', file: '08-报告页-green.png',
    nav: { url: '/pages/report/index?sample=1&overall=green' }, scroll: 0, needPath: 'pages/report/index',
    checks: [{ name: '结论标题', test: (t) => t.includes(VERDICT.green) }],
  },
  {
    name: '#09 报告页-unknown', file: '09-报告页-unknown.png',
    nav: { url: '/pages/report/index?sample=1&overall=unknown' }, scroll: 0, needPath: 'pages/report/index',
    checks: [{ name: '结论标题', test: (t) => t.includes(VERDICT.unknown) }],
  },
  {
    name: '#06 已交钱区块', file: '06-已交钱区块.png',
    nav: { url: '/pages/report/index?sample=1&overall=red' }, scroll: 2450, needPath: 'pages/report/index',
    checks: [
      { name: '结论为红灯（该区块唯一出现条件）', test: (t) => t.includes(VERDICT.red) },
    ],
  },
  {
    name: '#10 六项检查+来源标签', file: '10-六项检查-来源标签.png',
    nav: { url: '/pages/report/index?sample=1&overall=red' }, scroll: 800, needPath: 'pages/report/index',
    checks: [
      { name: '灰灯', test: (t) => t.includes('截图里没提到') },
      { name: '来源标签', test: (t) => t.includes('规则命中') || t.includes('套路库匹配') },
    ],
  },
  {
    name: '#11 公司卡片-有全称', file: '11-公司卡片-有全称.png',
    nav: { url: '/pages/report/index?sample=1&overall=red' }, scroll: 1799, needPath: 'pages/report/index',
    checks: [
      { name: '报告数据含公司全称', test: (t) => t.includes('示例（上海）科技有限公司') },
    ],
  },
  {
    name: '#11 公司卡片-无全称', file: '11b-公司卡片-无全称.png',
    nav: { url: '/pages/report/index?sample=1&overall=amber' }, scroll: 1583, needPath: 'pages/report/index',
    checks: [
      { name: 'amber 结论', test: (t) => t.includes(VERDICT.amber) },
    ],
  },
  {
    name: '#12 检查规则说明页', file: '12-检查规则说明页.png',
    nav: { url: '/pages/doc/index' }, scroll: 0, needPath: 'pages/doc/index',
    checks: [{ name: '规则说明内容', test: (t) => t.includes('检查') || t.includes('规则') }],
  },
  {
    name: '#14 我的', file: '14-我的.png',
    nav: { tab: true, url: '/pages/mine/index' }, scroll: 0, needPath: 'pages/mine/index',
    checks: [],
  },
];

async function main() {
  console.log('开始，共 ' + SPECS.length + ' 张\n');
  const results = [];
  for (const spec of SPECS) {
    const ok = await shot(spec);
    results.push({ name: spec.name, ok });
    await sleep(1200);
  }
  const okN = results.filter((r) => r.ok).length;
  console.log('\n成功 ' + okN + '/' + results.length);
  const bad = results.filter((r) => !r.ok).map((r) => r.name);
  console.log('失败：' + (bad.join('、') || '无'));
  console.log('目录：' + OUT);
  process.exit(0);
}

main().catch((e) => { console.error('fatal ' + (e && e.message)); process.exit(1); });
