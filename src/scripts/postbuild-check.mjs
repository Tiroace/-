// 正式包守卫：构建完成后自动跑的一组断言（D17 纪律：构建产物类断言必须每次构建后重跑）
//
// 为什么单独做成脚本：
// 之前「无 AI 字样」「无开发自测」这类断言只挂在 check:r1 里，要人记得跑。
// 现在直接接进 build:mp-weixin，构建完自动执行，不过就让构建失败。
//
// 用法：node scripts/postbuild-check.mjs [dist目录]
import fs from 'node:fs';
import path from 'node:path';

const DIST = process.argv[2] || 'dist/build/mp-weixin';

const rows = [];
const ok = (n, d) => rows.push({ n, pass: true, d: d || '' });
const bad = (n, d) => rows.push({ n, pass: false, d: d || '' });

if (!fs.existsSync(DIST)) {
  console.log('✗ 找不到产物目录：' + DIST);
  process.exit(1);
}

function walk(dir, out = []) {
  for (const f of fs.readdirSync(dir)) {
    const p = path.join(dir, f);
    if (fs.statSync(p).isDirectory()) walk(p, out);
    else out.push(p);
  }
  return out;
}

const allFiles = walk(DIST);

// ---------- 1. 无「开发自测」页与文案（D-05 / D-06） ----------
let appJson = null;
try {
  appJson = JSON.parse(fs.readFileSync(path.join(DIST, 'app.json'), 'utf8'));
} catch (e) {
  bad('读不到 app.json');
}
if (appJson) {
  (appJson.pages || []).includes('pages/dev/index')
    ? bad('【D-05】app.json 仍含 pages/dev/index')
    : ok('【D-05】app.json 无 pages/dev/index');
}
fs.existsSync(path.join(DIST, 'pages', 'dev'))
  ? bad('【D-05】仍有 pages/dev 目录')
  : ok('【D-05】无 pages/dev 目录');

const devHits = allFiles.filter((f) => /\.(js|wxml|json|wxss|ttss)$/.test(f) && fs.readFileSync(f, 'utf8').includes('开发自测'));
devHits.length ? bad('【D-06】含「开发自测」：' + devHits.map((f) => path.relative(DIST, f)).join(', ')) : ok('【D-06】无「开发自测」文案');

// ---------- 2. 上屏文案无 AI 字样（路线调整令） ----------
// 口径：正则 (?<![A-Za-z])AI(?![A-Za-z])，只扫用户能看到的部分
const AI_RE = /(?<![A-Za-z])AI(?![A-Za-z])/;
const stripTags = (t) => t.replace(/<[^>]*>/g, '\n');
const aiHits = [];
for (const f of allFiles) {
  const rel = path.relative(DIST, f);
  if (/\.wxml$/.test(f)) {
    if (AI_RE.test(stripTags(fs.readFileSync(f, 'utf8')))) aiHits.push(rel + '（上屏文字）');
  } else if (/\.json$/.test(f) && !/^project[^/\\]*\.json$/.test(rel) && !/sitemap/.test(rel)) {
    const texts = (fs.readFileSync(f, 'utf8').match(/"[^"]*"/g) || []).join('\n');
    if (AI_RE.test(texts)) aiHits.push(rel + '（配置文案）');
  }
}
aiHits.length ? bad('【路线令】上屏文案仍有「AI」：' + aiHits.slice(0, 5).join(', ')) : ok('【路线令】上屏文案无「AI」字样');

// 反向自检：确认正则真能抓到（防止写成永不报的假绿）
AI_RE.test('本报告由 AI 生成') ? ok('AI 正则有效（能抓到真实用例）') : bad('AI 正则失效');

// ---------- 3. D20 免责声明在包内 ----------
const D20 = '本报告由系统根据截图文字和规则库自动生成，仅供参考，不构成法律意见，也不代表对任何企业的评价；截图不完整或内容不实都会影响判断，重要事项请自行核实。';
const hasD20 = allFiles.some((f) => /\.js$/.test(f) && fs.readFileSync(f, 'utf8').includes(D20));
hasD20 ? ok('D20 免责声明在包内') : bad('D20 免责声明不在包内');

// ---------- 4. D21：12333 是文字不是拨号键 ----------
const reportJs = path.join(DIST, 'pages/report/index.js');
const reportWxml = path.join(DIST, 'pages/report/index.wxml');
if (fs.existsSync(reportWxml)) {
  const wxml = fs.readFileSync(reportWxml, 'utf8');
  wxml.includes('12333') ? ok('报告页有 12333') : bad('报告页缺 12333');
  wxml.includes('劳动权益') ? ok('12333 标注劳动权益') : bad('12333 缺劳动权益口径');
}
if (fs.existsSync(reportJs)) {
  const js = fs.readFileSync(reportJs, 'utf8');
  /12333/.test(js) && /makePhoneCall|callPhone/.test(js)
    ? (/(callPhone|makePhoneCall)[^;]*12333|12333[^;]*(callPhone|makePhoneCall)/.test(js)
        ? bad('【D21】12333 仍可拨号')
        : ok('【D21】12333 不是拨号键'))
    : ok('【D21】12333 未绑定拨号');
}

// ---------- 5. 检查规则说明页 + 公司核实卡 ----------
const docWxml = path.join(DIST, 'pages/doc/index.wxml');
if (fs.existsSync(docWxml)) {
  const w = fs.readFileSync(docWxml, 'utf8');
  // 页面文案在 js 里定义
  const docJs = path.join(DIST, 'pages/doc/index.js');
  const jsText = fs.existsSync(docJs) ? fs.readFileSync(docJs, 'utf8') : '';
  jsText.includes('检查规则说明') ? ok('检查规则说明页在包内') : bad('缺检查规则说明页内容');
}
const corpJs = fs.existsSync(reportJs) ? fs.readFileSync(reportJs, 'utf8') : '';
corpJs.includes('国家企业信用信息公示系统') ? ok('公司核实卡在包内') : bad('缺公司核实卡');

// ---------- 6. 页面数与关键页 ----------
if (appJson) {
  const must = ['pages/index/index', 'pages/report/index', 'pages/mine/index', 'pages/member/index'];
  const missing = must.filter((p) => !(appJson.pages || []).includes(p));
  missing.length ? bad('缺关键页面：' + missing.join(', ')) : ok('关键页面齐全（' + appJson.pages.length + ' 页）');
}

// ---------- 7. 版本字段口径：只有 rules_version，没有 prompt_version（D1 引擎契约） ----------
const pvHits = [];
for (const f of allFiles) {
  if (!/\.(js|wxml|json)$/.test(f)) continue;
  if (fs.readFileSync(f, 'utf8').includes('prompt_version')) {
    pvHits.push(path.relative(DIST, f));
  }
}
pvHits.length ? bad('包内仍有 prompt_version：' + pvHits.join(', ')) : ok('包内无 prompt_version（已改 rules_version）');
allFiles.some((f) => /\.js$/.test(f) && fs.readFileSync(f, 'utf8').includes('rules_version'))
  ? ok('包内有 rules_version 字段')
  : bad('包内缺 rules_version 字段');

// ---------- 8. 一期不用大模型：不展示模型名/备案号 ----------
const reportWxmlEarly = path.join(DIST, 'pages/report/index.wxml');
if (fs.existsSync(reportWxmlEarly)) {
  const w = fs.readFileSync(reportWxmlEarly, 'utf8');
  /模型：|备案号|deepseek/i.test(w) ? bad('报告页仍展示模型名/备案号') : ok('报告页不展示模型名与备案号');
}

// 输出
let failed = 0;
console.log('');
for (const r of rows) {
  if (!r.pass) failed += 1;
  console.log((r.pass ? '  ✓ ' : '  ✗ ') + r.n + (r.d ? '  → ' + r.d : ''));
}
console.log('');
if (failed) {
  console.log('✗ 构建后检查失败 ' + failed + ' 项，正式包不可用');
  process.exit(1);
}
console.log('✓ 构建后检查全部通过（' + rows.length + ' 项）');
