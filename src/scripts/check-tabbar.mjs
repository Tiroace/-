// 两套小程序配置是否真的分开（BUG-20261103-02 · 产品要求第 3 条）
//
// 只做静态检查，不构建：
//   - src/pages.json         开发配置：tabBar 三项（检查 / 广场 / 我的）
//   - src/pages.review.json  提审配置：tabBar 两项（检查 / 我的），且不引用广场
//   - 两者必须是两个独立文件（不是同一份文件里的开关），且 vite.config.js 按 QBL_BUILD_TARGET 选择
//   - 广场页面文件仍保留（代码不删），只是不进提审 tabBar
//
// 用法：node scripts/check-tabbar.mjs（在 src/ 下）或 npm run verify:tabs
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '..');
const DEV_CFG = path.join(ROOT, 'src', 'pages.json');
const REVIEW_CFG = path.join(ROOT, 'src', 'pages.review.json');
const SQUARE_PAGE = path.join(ROOT, 'src', 'pages', 'square', 'index.vue');
const VITE_CFG = path.join(ROOT, 'vite.config.js');

const rows = [];
const ok = (n, d) => rows.push({ n, pass: true, d: d || '' });
const bad = (n, d) => rows.push({ n, pass: false, d: d || '' });

function readJson(p) {
  return JSON.parse(fs.readFileSync(p, 'utf8'));
}

const tabList = (cfg) => ((cfg && cfg.tabBar && Array.isArray(cfg.tabBar.list)) ? cfg.tabBar.list : []);
const tabTexts = (cfg) => tabList(cfg).map((t) => t.text);
const tabPaths = (cfg) => tabList(cfg).map((t) => t.pagePath);

try {
  // 1. 两套配置是两个独立文件
  const bothExist = fs.existsSync(DEV_CFG) && fs.existsSync(REVIEW_CFG);
  bothExist
    ? ok('两套配置分开：src/pages.json 与 src/pages.review.json 各自存在')
    : bad('缺少配置文件：' + [!fs.existsSync(DEV_CFG) ? 'pages.json' : '', !fs.existsSync(REVIEW_CFG) ? 'pages.review.json' : ''].filter(Boolean).join('、'));

  const dev = fs.existsSync(DEV_CFG) ? readJson(DEV_CFG) : {};
  const review = fs.existsSync(REVIEW_CFG) ? readJson(REVIEW_CFG) : {};

  // 2. 开发配置：三项（含广场）
  const dp = tabPaths(dev);
  dp.length === 3 && dp.includes('pages/square/index')
    ? ok('开发配置 tabBar 三项（' + tabTexts(dev).join('、') + '）')
    : bad('开发配置 tabBar 不对：' + JSON.stringify(dp));

  // 3. 提审配置：两项，且不含广场
  const rp = tabPaths(review);
  rp.length === 2 && rp.includes('pages/index/index') && rp.includes('pages/mine/index') && !rp.includes('pages/square/index')
    ? ok('提审配置 tabBar 两项（' + tabTexts(review).join('、') + '）')
    : bad('提审配置 tabBar 不对：' + JSON.stringify(rp));

  // 4. 提审配置全文不出现广场
  const reviewText = fs.existsSync(REVIEW_CFG) ? fs.readFileSync(REVIEW_CFG, 'utf8') : '';
  reviewText.includes('广场') || reviewText.includes('pages/square/index')
    ? bad('提审配置里仍出现广场')
    : ok('提审配置全文无广场');

  // 5. 页面文件保留（代码不删）
  fs.existsSync(SQUARE_PAGE) ? ok('广场页面文件保留（仅不进提审 tabBar）') : bad('广场页面文件被删了，产品要求保留');

  // 6. 提审配置的其他字段与开发配置一致（配色/样式不能被悄悄改掉）
  const colorKeys = ['color', 'selectedColor', 'backgroundColor', 'borderStyle'];
  const colorSame = colorKeys.every((k) => (dev.tabBar || {})[k] === (review.tabBar || {})[k]);
  colorSame ? ok('两套 tabBar 配色一致') : bad('两套 tabBar 配色不一致');

  // 7. vite.config.js 必须按构建目标选择配置
  const vite = fs.existsSync(VITE_CFG) ? fs.readFileSync(VITE_CFG, 'utf8') : '';
  vite.includes('QBL_BUILD_TARGET') && vite.includes('pages.review.json') && vite.includes('pagesJsonPath')
    ? ok('vite.config.js 按 QBL_BUILD_TARGET 选择 pages 配置')
    : bad('vite.config.js 没有按构建目标选择 pages 配置');

  // 8. 提审配置里声明的页面样式与开发配置一致（只差 tabBar）
  const devPages = JSON.stringify(dev.pages || null);
  const reviewPages = review.pages === undefined ? devPages : JSON.stringify(review.pages);
  devPages === reviewPages ? ok('提审配置不覆盖 pages 清单（页面文件都保留）') : bad('提审配置改动了 pages 清单');
} catch (e) {
  bad('检查异常', e && e.message ? e.message : String(e));
}

let failed = 0;
console.log('');
for (const r of rows) {
  if (r.pass) console.log('  ✓ ' + r.n + (r.d ? '  -- ' + r.d : ''));
  else {
    failed += 1;
    console.log('  ✗ ' + r.n + (r.d ? '  -- ' + r.d : ''));
  }
}
console.log('');
if (failed) {
  console.log('✗ tabBar 两套配置检查失败（' + failed + '/' + rows.length + '）');
  process.exit(1);
}
console.log('✓ tabBar 两套配置检查全部通过（' + rows.length + ' 项）');
