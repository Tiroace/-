// 正式包清理：把只在开发环境用的东西从构建产物里摘掉。
//
// 为什么要有这个脚本：
// uni-app 的 pages.json 是静态的，`v-if` 只影响渲染、不影响打包。
// 所以「开发自测」页和它的入口文案会原样进正式包，违反 §9「正式包里看不到开发自测」。
//
// 做三件事：
// 1. 从 app.json 的 pages 里删掉开发页；
// 2. 删掉对应的产物目录（并清理其他页面 json 里的分包/引用，如果有）；
// 3. 扫全包，若仍出现被禁文案则报错退出（CI 能挡住）。
//
// 用法：
//   node scripts/strip-dev-build.mjs dist/build/mp-weixin           开发包清理模式
//   node scripts/strip-dev-build.mjs dist/build/mp-weixin review    提审包模式（额外去掉广场 tab）
import fs from 'node:fs';
import path from 'node:path';

const DIST = process.argv[2] || 'dist/build/mp-weixin';
const MODE = String(process.argv[3] || '').trim().toLowerCase();
const IS_REVIEW = MODE === 'review';

// 只在正式包里该消失的页面
const DEV_ONLY_PAGES = ['pages/dev/index'];

// 提审包（BUG-20261103-02）：tabBar 只保留「检查」「我的」，广场不进 tabBar。
// 页面文件不删，代码不删——只是入口不可达。
const REVIEW_TAB_ALLOW = ['pages/index/index', 'pages/mine/index'];

// 正式包里不该出现的用户可见文案（这些是开发调试相关）
const FORBIDDEN_STRINGS = ['开发自测（仅开发环境）', '开发自测', '开发环境'];

function readJson(p) {
  return JSON.parse(fs.readFileSync(p, 'utf8'));
}

function writeJson(p, obj) {
  fs.writeFileSync(p, JSON.stringify(obj, null, 2), 'utf8');
}

function walk(dir, out = []) {
  for (const f of fs.readdirSync(dir)) {
    const p = path.join(dir, f);
    if (fs.statSync(p).isDirectory()) walk(p, out);
    else out.push(p);
  }
  return out;
}

let changed = 0;

// ---- 1. 从 app.json 删页面 ----
const appJsonPath = path.join(DIST, 'app.json');
if (!fs.existsSync(appJsonPath)) {
  console.log('✗ 找不到 ' + appJsonPath + '，先构建');
  process.exit(1);
}
const appJson = readJson(appJsonPath);
const before = (appJson.pages || []).length;
appJson.pages = (appJson.pages || []).filter((p) => !DEV_ONLY_PAGES.includes(p));
if (appJson.pages.length !== before) {
  writeJson(appJsonPath, appJson);
  changed += 1;
  console.log('  · app.json 移除页面 ' + (before - appJson.pages.length) + ' 个');
}

// 分包里也可能有（preloadRule / subPackages 不涉及，防御性处理）
if (Array.isArray(appJson.subPackages)) {
  appJson.subPackages.forEach((sp) => {
    if (Array.isArray(sp.pages)) {
      sp.pages = sp.pages.filter((p) => !DEV_ONLY_PAGES.includes((sp.root || '') + '/' + p));
    }
  });
}

// ---- 1b. 提审包：tabBar 只保留「检查」「我的」（BUG-20261103-02）----
if (IS_REVIEW && appJson.tabBar && Array.isArray(appJson.tabBar.list)) {
  const beforeList = appJson.tabBar.list;
  const kept = beforeList.filter((t) => REVIEW_TAB_ALLOW.includes(t.pagePath));
  const dropped = beforeList.filter((t) => !REVIEW_TAB_ALLOW.includes(t.pagePath));
  if (dropped.length) {
    appJson.tabBar.list = kept;
    writeJson(appJsonPath, appJson);
    changed += 1;
    console.log('  · 提审包 tabBar 移除 ' + dropped.map((t) => t.text || t.pagePath).join('、'));
  }
  const paths = kept.map((t) => t.pagePath).sort().join(',');
  if (paths !== REVIEW_TAB_ALLOW.slice().sort().join(',')) {
    console.log('✗ 提审包 tabBar 不是「检查」「我的」两项：' + paths);
    process.exit(1);
  }
  console.log('  · 提审包 tabBar = ' + kept.map((t) => t.text || t.pagePath).join(' / '));
}

// ---- 2. 删产物目录 ----
for (const page of DEV_ONLY_PAGES) {
  const dir = path.join(DIST, path.dirname(page));
  if (fs.existsSync(dir)) {
    fs.rmSync(dir, { recursive: true, force: true });
    changed += 1;
    console.log('  · 删除目录 ' + path.relative(DIST, dir));
  }
}

// ---- 3. 扫残留下 ----
const hits = [];
for (const f of walk(DIST)) {
  if (!/\.(js|wxml|json|wxss|ttss)$/.test(f)) continue;
  const text = fs.readFileSync(f, 'utf8');
  for (const s of FORBIDDEN_STRINGS) {
    if (text.includes(s)) {
      hits.push(path.relative(DIST, f) + ' 含「' + s + '」');
      break;
    }
  }
}

if (hits.length) {
  console.log('✗ 正式包里仍有开发相关文案：');
  hits.forEach((h) => console.log('    ' + h));
  process.exit(1);
}

console.log('✓ 正式包已清理（改动 ' + changed + ' 处），全包无「开发自测」');
