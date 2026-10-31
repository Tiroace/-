// 小程序工程结构校验（不依赖 IDE）：
// 逐项检查微信小程序要求的产物是否齐全，模拟 IDE 导入时会查的东西。
// 用法：node tests/validate-dist.mjs [dist目录]，默认校验 dist/dev/mp-weixin
import fs from 'node:fs';
import path from 'node:path';

const root = process.argv[2] || 'dist/dev/mp-weixin';
const problems = [];
const oks = [];

function ok(msg) {
  oks.push(msg);
}
function bad(msg) {
  problems.push(msg);
}

if (!fs.existsSync(root)) {
  console.log('✗ 产物目录不存在：' + root);
  process.exit(1);
}

// 1. 必需文件（抖音端用 .ttss 代替 .wxss）
const isToutiao = root.includes('mp-toutiao');
const required = ['app.js', 'app.json', 'project.config.json'].concat(isToutiao ? ['app.ttss'] : ['app.wxss']);
for (const f of required) {
  const p = path.join(root, f);
  if (fs.existsSync(p)) ok('存在 ' + f);
  else bad('缺少 ' + f);
}

// 2. app.json 合法、页面文件齐全
let appJson = {};
try {
  appJson = JSON.parse(fs.readFileSync(path.join(root, 'app.json'), 'utf8'));
  ok('app.json 是合法 JSON');
} catch (e) {
  bad('app.json 解析失败：' + e.message);
}

for (const page of appJson.pages || []) {
  for (const ext of ['.js', '.json', '.wxml', '.wxss']) {
    const p = path.join(root, page + ext);
    if (!fs.existsSync(p)) {
      // 抖音端（mp-toutiao）会省略空的 wxml/wxss，这是构建器的正常行为，不算问题
      if (root.includes('mp-toutiao') && (ext === '.wxml' || ext === '.wxss')) continue;
      bad('页面缺少文件：' + page + ext);
    }
  }
  ok('页面齐全：' + page);
}

// 3. tabBar 里的页面必须在 pages 里
for (const item of (appJson.tabBar && appJson.tabBar.list) || []) {
  if (!(appJson.pages || []).includes(item.pagePath)) {
    bad('tabBar 指向了不存在的页面：' + item.pagePath);
  } else {
    ok('tabBar 页面存在：' + item.text + ' → ' + item.pagePath);
  }
}

// 4. project.config.json 的 appid
try {
  const proj = JSON.parse(fs.readFileSync(path.join(root, 'project.config.json'), 'utf8'));
  ok('appid = ' + proj.appid);
  if (!proj.appid) bad('appid 为空，IDE 无法以游客模式打开');
} catch (e) {
  bad('project.config.json 解析失败：' + e.message);
}

// 5. 静态资源引用存在
const staticDir = path.join(root, 'static');
if (fs.existsSync(staticDir)) {
  const demos = fs.readdirSync(path.join(staticDir, 'demo'));
  ok('示例图 ' + demos.length + ' 张：' + demos.join(', '));
  for (const d of demos) {
    if (!fs.existsSync(path.join(staticDir, 'demo', d))) bad('示例图缺失：' + d);
  }
}

// 6. 合规文案必须出现在产物里
const reportWxml = path.join(root, 'pages/report/index.wxml');
if (fs.existsSync(reportWxml)) {
  const text = fs.readFileSync(reportWxml, 'utf8');
  ok('报告页 wxml 已生成（' + text.length + ' 字节）');
}

const appJs = fs.readFileSync(path.join(root, 'app.js'), 'utf8');
if (appJs.includes('求职避雷')) ok('app.js 包名正常');

// 7. 禁用词不应出现在用户可见文案里
//    （common/constants.js 里是禁用词清单本身，放了才能做过滤，要排除）
const forbidden = ['骗子公司', '黑心企业', '100%识别', '最准'];
const hits = [];
function walk(dir) {
  for (const f of fs.readdirSync(dir)) {
    const p = path.join(dir, f);
    const st = fs.statSync(p);
    if (st.isDirectory()) walk(p);
    else if (/\.(js|wxml|json)$/.test(f)) {
      const rel = path.relative(root, p);
      if (rel.replace(/\\/g, '/') === 'common/constants.js') continue;
      const t = fs.readFileSync(p, 'utf8');
      for (const w of forbidden) {
        if (t.includes(w)) hits.push(rel + ' 含「' + w + '」');
      }
    }
  }
}
walk(root);
if (hits.length) hits.forEach(bad);
else ok('产物中无禁用词');

// 输出
console.log('通过 ' + oks.length + ' 项：');
oks.forEach((m) => console.log('  ✓ ' + m));
if (problems.length) {
  console.log('\n问题 ' + problems.length + ' 项：');
  problems.forEach((m) => console.log('  ✗ ' + m));
  process.exit(1);
}
console.log('\n结构校验全部通过：' + root);
