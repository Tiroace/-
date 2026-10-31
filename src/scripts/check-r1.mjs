// R1 改版自检：改名残留、写死色值、禁项（蓝色/渐变/卡片阴影/emoji）、关键页面结构。
// 用法：node miniprogram/scripts/check-r1.mjs
import fs from 'node:fs';
import path from 'node:path';

const SRC = 'D:/qiuzhibilei/src/src';
const rows = [];
const fail = (name, detail) => rows.push({ name, pass: false, detail });
const pass = (name, detail) => rows.push({ name, pass: true, detail: detail || '' });

function walk(dir, exts, out = []) {
  for (const f of fs.readdirSync(dir)) {
    const p = path.join(dir, f);
    if (fs.statSync(p).isDirectory()) walk(p, exts, out);
    else if (exts.some((e) => f.endsWith(e))) out.push(p);
  }
  return out;
}

const files = walk(SRC, ['.vue', '.js', '.json', '.scss']);

// 1. 改名残留
const residues = [];
for (const f of files) {
  const t = fs.readFileSync(f, 'utf8');
  if (t.includes('求职避雷')) residues.push(path.relative(SRC, f));
}
residues.length ? fail('改名残留（求职避雷）', residues.join(', ')) : pass('改名残留（求职避雷）= 0');

// 2. 写死色值（只看 <style> 块）
const hardColors = [];
for (const f of files.filter((x) => x.endsWith('.vue'))) {
  const t = fs.readFileSync(f, 'utf8');
  const m = t.match(/<style[^>]*>([\s\S]*?)<\/style>/);
  if (!m) continue;
  m[1].split(/\r?\n/).forEach((line, i) => {
    if (/^\s*\/\//.test(line)) return;
    if (/#[0-9A-Fa-f]{3,8}\b|rgba?\(/.test(line)) {
      hardColors.push(path.relative(SRC, f) + ':' + (i + 1) + ' ' + line.trim());
    }
  });
}
hardColors.length ? fail('写死色值', hardColors.join(' | ')) : pass('页面写死色值 = 0（全部用 uni.scss 变量）');

// 3. 禁项：蓝色、渐变、卡片阴影、emoji
const bans = [
  { name: '禁用蓝色', re: /#2[bB]6[cC][fF]6|#4[aA]8[cC][fF][fF]|blue|#[0-9a-fA-F]{0,2}[0-9a-fA-F]{2}ccff/i },
  { name: '禁用渐变', re: /linear-gradient|radial-gradient/i },
];
for (const b of bans) {
  const hits = [];
  for (const f of files.filter((x) => x.endsWith('.vue') || x.endsWith('.scss'))) {
    const t = fs.readFileSync(f, 'utf8');
    const inStyle = (t.match(/<style[^>]*>([\s\S]*?)<\/style>/) || [, t])[1];
    if (b.re.test(inStyle)) hits.push(path.relative(SRC, f));
  }
  hits.length ? fail(b.name, hits.join(', ')) : pass(b.name);
}

// 4. 卡片阴影：只允许灯用 box-shadow（灯的写法是 $red/$amber/$green 或带 -soft 的组合）
const shadowHits = [];
for (const f of files.filter((x) => x.endsWith('.vue'))) {
  const t = fs.readFileSync(f, 'utf8');
  const inStyle = (t.match(/<style[^>]*>([\s\S]*?)<\/style>/) || [, ''])[1];
  inStyle.split(/\r?\n/).forEach((line, i) => {
    if (!/box-shadow/.test(line)) return;
    // 允许：灯的发光。判定标准是值里出现灯色变量（$red/$amber/$green）
    if (/\$(red|amber|green)(-soft)?\b/.test(line)) return;
    shadowHits.push(path.relative(SRC, f) + ':' + (i + 1) + ' ' + line.trim());
  });
}
shadowHits.length ? fail('卡片阴影（只允许灯发光）', shadowHits.join(' | ')) : pass('卡片阴影 = 0（只有灯发光）');

// 5. emoji（粗略：常见 emoji 区段）
const emojiHits = [];
for (const f of files.filter((x) => x.endsWith('.vue'))) {
  const t = fs.readFileSync(f, 'utf8');
  if (/[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]/u.test(t)) emojiHits.push(path.relative(SRC, f));
}
emojiHits.length ? fail('使用了 emoji', emojiHits.join(', ')) : pass('emoji = 0');

// 6. 品牌名与常量
const brand = fs.readFileSync(path.join(SRC, 'common/brand.js'), 'utf8');
brand.includes('APP_NAME = \'面试请等等\'') ? pass('APP_NAME = 面试请等等') : fail('APP_NAME 未改名');

// 7. pages.json 深色配置
const pages = JSON.parse(fs.readFileSync(path.join(SRC, 'pages.json'), 'utf8'));
const darkBg = (pages.pages || []).every((p) => (p.style || {}).backgroundColor === '#0E1620');
darkBg ? pass('每页 backgroundColor = #0E1620') : fail('有页面没设深色背景');
const whiteText = (pages.pages || []).every((p) => (p.style || {}).navigationBarTextStyle === 'white');
whiteText ? pass('每页 navigationBarTextStyle = white') : fail('有页面导航栏文字不是白色');
const tb = pages.tabBar || {};
const tbOk = tb.backgroundColor === '#121C27' && tb.color === '#8090A0' && tb.selectedColor === '#FFC93C';
tbOk ? pass('tabBar 配色 #121C27 / #8090A0 / #FFC93C') : fail('tabBar 配色不对：' + JSON.stringify(tb));

// 8. tabBar 图标存在且 81×81
const iconOk = (tb.list || []).every((t) => {
  const a = path.join(SRC, t.iconPath || '');
  const b = path.join(SRC, t.selectedIconPath || '');
  return fs.existsSync(a) && fs.existsSync(b);
});
iconOk ? pass('tabBar 两套图标都存在') : fail('tabBar 图标缺失');
const iconBuf = fs.readFileSync(path.join(SRC, tb.list[0].iconPath));
const w = iconBuf.readUInt32BE(16);
const h = iconBuf.readUInt32BE(20);
w === 81 && h === 81 ? pass('tabBar 图标 81×81') : fail('tabBar 图标尺寸 ' + w + 'x' + h);

// 9. 「我的」页：无退出登录、菜单 4 项
const mine = fs.readFileSync(path.join(SRC, 'pages/mine/index.vue'), 'utf8');
mine.includes('退出登录') ? fail('「我的」页还有退出登录') : pass('「我的」页无退出登录');
const menuCount = (mine.match(/class="menu-item/g) || []).length;
menuCount === 4 ? pass('「我的」菜单 4 项') : fail('菜单项数 = ' + menuCount);

// 10. 「我的」页底部安全区
/calc\([^)]*env\(safe-area-inset-bottom\)/.test(mine) ? pass('「我的」页留了底部安全区') : fail('「我的」页未留底部安全区');

// 11. 会员页：一次性购买、无「免广告」（只查用户可见文案，注释不算）
const member = fs.readFileSync(path.join(SRC, 'pages/member/index.vue'), 'utf8');
member.includes('一次性购买，到期不自动续费') ? pass('会员页保留「一次性购买，不自动续费」') : fail('会员页缺一次性购买说明');

// 去掉 HTML 注释和 JS 注释后再查文案里的「免广告」
function stripComments(t) {
  return t.replace(/<!--[\s\S]*?-->/g, '').replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '');
}
const visibleText = files
  .filter((x) => x.endsWith('.vue'))
  .map((x) => stripComments(fs.readFileSync(x, 'utf8')))
  .join('\n');
visibleText.includes('免广告') ? fail('用户可见文案出现「免广告」') : pass('用户可见文案无「免广告」');

// 12. 次数用完弹窗 iOS 隐藏会员卡
const sheet = fs.readFileSync(path.join(SRC, 'components/QuotaSheet.vue'), 'utf8');
sheet.includes('v-if="memberAvailable"') ? pass('弹窗会员卡按 iOS 可用性整块隐藏') : fail('弹窗会员卡没做隐藏');

// 13. 分析中：三灯动画 + 路线令的三段真实阶段
const ana = fs.readFileSync(path.join(SRC, 'pages/analyzing/index.vue'), 'utf8');
// 只看 STAGES 那个常量本身，避免被注释里的说明误伤
const stagesLine = (ana.match(/const STAGES\s*=\s*\[[^\]]*\]/) || [''])[0];
/正在读截图/.test(stagesLine) && /正在比对套路库/.test(stagesLine) && /正在逐项检查/.test(stagesLine)
  ? pass('分析中三段真实阶段文案齐全（读截图→比对套路库→逐项检查）')
  : fail('分析中阶段文案缺失');
/正在写报告/.test(stagesLine) ? fail('分析中阶段仍有第四段「正在写报告」') : pass('分析中阶段无第四段（路线令改三段）');

// 14. 首页：品牌标识、大标题、免单措辞
const idx = fs.readFileSync(path.join(SRC, 'pages/index/index.vue'), 'utf8');
idx.includes('去面试之前') ? pass('首页大标题正确') : fail('首页大标题缺失');
idx.includes('没查出结果，不扣次数') ? pass('首页「没查出结果，不扣次数」') : fail('首页缺免单说明');
idx.includes('NavBar') ? pass('首页用自定义导航栏（名字只出现一次）') : fail('首页没用自定义导航栏');

// 14b. 首页必须有服务说明入口（派书 §3；路线令后改叫「检查规则说明」，不再出现 AI）
{
  const hasText = /查看检查规则说明/.test(idx);
  hasText ? pass('首页有检查规则说明入口') : fail('首页缺检查规则说明入口（派书 §3）');
  /gotoAiDoc/.test(idx) && /\/pages\/doc\/index\?type=ai/.test(idx)
    ? pass('说明入口跳检查规则说明页')
    : fail('说明入口没链到 doc 页面');
  // 必须是低调一行，不能做成卡片（不准抢主视觉）
  const noticeBlock = (idx.match(/<view class="ai-notice-row"[\s\S]*?<\/view>/) || [''])[0];
  /class="card/.test(noticeBlock) ? fail('AI 公示做成了卡片，要求低调一行') : pass('AI 公示是低调一行（非卡片）');
}

// 15. 【D-05 / D-06】正式包不得含开发自测页与文案（构建后必跑）
// 必须直接读构建产物，不靠源码推断——v-if 只影响渲染，不影响打包。
const DIST = 'D:/qiuzhibilei/src/dist/build/mp-weixin';
if (!fs.existsSync(DIST)) {
  fail('正式包不存在，先跑 build:mp-weixin');
} else {
  let appBuilt = {};
  try {
    appBuilt = JSON.parse(fs.readFileSync(path.join(DIST, 'app.json'), 'utf8'));
  } catch (e) {
    fail('读不到构建产物 app.json');
  }
  const hasDevPage = (appBuilt.pages || []).includes('pages/dev/index');
  hasDevPage ? fail('【D-05】正式包 app.json 仍含 pages/dev/index') : pass('【D-05】正式包 app.json 无 pages/dev/index');

  const devDir = path.join(DIST, 'pages/dev');
  fs.existsSync(devDir) ? fail('【D-05】正式包仍有 pages/dev 目录') : pass('【D-05】正式包无 pages/dev 目录');

  // 全包扫「开发自测」文案
  const devStringHits = [];
  const walkDist = (d) => {
    for (const f of fs.readdirSync(d)) {
      const p = path.join(d, f);
      if (fs.statSync(p).isDirectory()) walkDist(p);
      else if (/\.(js|wxml|json|wxss|ttss)$/.test(f)) {
        const t = fs.readFileSync(p, 'utf8');
        if (t.includes('开发自测')) devStringHits.push(path.relative(DIST, p));
      }
    }
  };
  walkDist(DIST);
  devStringHits.length
    ? fail('【D-06】正式包含「开发自测」文案：' + devStringHits.join(', '))
    : pass('【D-06】正式包全文案无「开发自测」');
}

// 16. 模板属性里的写死色值（整文件扫，不只 style 块——测试者提的口径差异）
const templateColorHits = [];
for (const f of files.filter((x) => x.endsWith('.vue'))) {
  const t = fs.readFileSync(f, 'utf8');
  // 只看 <template> 部分
  const tpl = (t.match(/<template>([\s\S]*?)<\/template>/) || [, ''])[1];
  tpl.split(/\r?\n/).forEach((line, i) => {
    if (/(color|background|border-color)="#[0-9A-Fa-f]{3,8}"/.test(line)) {
      templateColorHits.push(path.relative(SRC, f) + ':' + (i + 1) + ' ' + line.trim());
    }
  });
}
templateColorHits.length
  ? fail('模板属性写死色值', templateColorHits.join(' | '))
  : pass('模板属性写死色值 = 0（含 switch color= 这类）');

// 17. 【路线调整令】只扫「上屏文案」里有没有独立的 AI 两个字
// 口径由产品给：正则 (?<![A-Za-z])AI(?![A-Za-z])，且只扫用户能看到的部分。
// 为什么不扫整个产物：fail / main / detail / aiNotice 这类标识符会误命中。
//
// 「上屏文案」= .wxml 里标签之间的文本 + .json 的页面标题。JS 里的变量名不算。
if (!fs.existsSync(DIST)) {
  fail('正式包不存在，无法检查 AI 字样');
} else {
  const AI_RE = /(?<![A-Za-z])AI(?![A-Za-z])/;
  // 去掉 wxml 标签，只留标签之间的文字
  const textOfWxml = (t) => t.replace(/<[^>]*>/g, '\n');
  const aiHits = [];
  const walkAi = (d) => {
    for (const f of fs.readdirSync(d)) {
      const p = path.join(d, f);
      if (fs.statSync(p).isDirectory()) walkAi(p);
      else if (/\.wxml$/.test(f)) {
        const body = textOfWxml(fs.readFileSync(p, 'utf8'));
        if (AI_RE.test(body)) aiHits.push(path.relative(DIST, p) + '（上屏文字）');
      } else if (/\.json$/.test(f) && !/[\/\\](project|sitemap)[^\/\\]*\.json$/.test(p)) {
        // 页面标题等配置文案
        const raw = fs.readFileSync(p, 'utf8');
        const texts = (raw.match(/"[^"]*"/g) || []).join('\n');
        if (AI_RE.test(texts)) aiHits.push(path.relative(DIST, p) + '（配置文案）');
      }
    }
  };
  walkAi(DIST);
  aiHits.length
    ? fail('【路线令】上屏文案仍有「AI」：' + aiHits.slice(0, 6).join(', ') + (aiHits.length > 6 ? ' 等 ' + aiHits.length + ' 处' : ''))
    : pass('【路线令】上屏文案无「AI」字样（(?<![A-Za-z])AI(?![A-Za-z])）');

  // 反向自检：确认这个正则真的能抓到 AI（防止写成永远不报）
  AI_RE.test('本报告由 AI 生成') ? pass('AI 检测正则有效（能抓到真实用例）') : fail('AI 检测正则失效，永远不报');
}

// 18. 免责声明 = D20 定稿（带后半句）
{
  const D20 =
    '本报告由系统根据截图文字和规则库自动生成，仅供参考，不构成法律意见，也不代表对任何企业的评价；截图不完整或内容不实都会影响判断，重要事项请自行核实。';
  const constantsSrc = fs.readFileSync(path.join(SRC, 'common/constants.js'), 'utf8');
  constantsSrc.includes(D20) ? pass('免责声明 = D20 定稿原文') : fail('免责声明不是 D20 原文');
  constantsSrc.includes('本报告由 AI') ? fail('constants.js 仍含旧版免责声明') : pass('constants.js 无旧版免责声明');
}

// 19. 来源标签只留两种
{
  const brandSrc = fs.readFileSync(path.join(SRC, 'common/brand.js'), 'utf8');
  const srcBlock = (brandSrc.match(/SOURCE_LABEL = \{([\s\S]*?)\};/) || [, ''])[1];
  const hasLlm = /llm\s*:/.test(srcBlock);
  hasLlm ? fail('来源标签仍有 llm/AI 推理') : pass('来源标签只剩 rule / pattern 两种');
  /规则命中/.test(srcBlock) && /套路库匹配/.test(srcBlock) ? pass('两种来源标签文案正确') : fail('来源标签文案缺失');
}

// 20. 报告页公司核实卡片
{
  const reportSrc = fs.readFileSync(path.join(SRC, 'pages/report/index.vue'), 'utf8');
  reportSrc.includes('corp-card') ? pass('报告页有公司核实卡片') : fail('报告页缺公司核实卡片');
  reportSrc.includes('国家企业信用信息公示系统') ? pass('含国家企业信用信息公示系统引导') : fail('缺工商查询引导');
  reportSrc.includes('黑猫投诉') ? pass('含黑猫投诉引导') : fail('缺黑猫投诉引导');
  /copyCompany/.test(reportSrc) ? pass('公司名可一键复制') : fail('公司名不能复制');
  // 不接第三方数据接口：不能出现 http 抓取类调用
  /uni\.request\([^)]*gsxt|fetch\([^)]*heimao/.test(reportSrc) ? fail('公司核实接了第三方数据') : pass('公司核实不接第三方数据（只复制+引导）');
}

// 21. 检查规则说明页替代 AI 服务说明
{
  const docSrc = fs.readFileSync(path.join(SRC, 'pages/doc/index.vue'), 'utf8');
  docSrc.includes('检查规则说明') ? pass('有「检查规则说明」页') : fail('缺检查规则说明页');
  AI_RE_TEST(docSrc) ? fail('检查规则说明页仍含 AI 字样') : pass('检查规则说明页无 AI 字样');
}

// 22. 示例报告与引擎契约对齐（D3）：版本号不写死，必须等于 engine/prompts.py 的 RULES_VERSION
{
  const exSrc = fs.readFileSync(path.join(SRC, 'common/exampleReports.js'), 'utf8');
  const engineVer = (fs.readFileSync('D:/qiuzhibilei/engine/prompts.py', 'utf8').match(/^RULES_VERSION\s*=\s*"([^"]+)"/m) || [])[1];
  if (!engineVer) {
    fail('读取引擎 RULES_VERSION', 'engine/prompts.py 里没找到 RULES_VERSION');
  } else {
    const versions = [...exSrc.matchAll(/"rules_version":\s*"([^"]*)"/g)].map((m) => m[1]);
    const bad = [...new Set(versions.filter((v) => v !== engineVer))];
    if (!versions.length) fail('示例报告带 rules_version', '一条都没有');
    else if (bad.length) fail('示例报告版本与引擎一致（' + engineVer + '）', '不一致：' + bad.join(', '));
    else pass('示例报告版本与引擎一致（' + engineVer + '，共 ' + versions.length + ' 份）');
    exSrc.includes('prompt_version') ? fail('示例报告有 prompt_version') : pass('示例报告无 prompt_version');
    // 示例必须是引擎现跑的，不能退化成读 data/examples 里的旧标准示例
    ["red", "amber", "green", "unknown"].every((o) => versions.length && exSrc.includes('"' + o + '"'))
      ? pass('示例报告 4 种 overall 齐全')
      : fail('示例报告缺 overall');
  }
  const repSrc = fs.readFileSync(path.join(SRC, 'pages/report/index.vue'), 'utf8');
  /rules_version:\s*'v\d/.test(repSrc)
    ? fail('报告页未写死版本号', "发现 rules_version: 'v...'")
    : pass('报告页未写死版本号');
}

function AI_RE_TEST(t) {
  return /(^|[^A-Za-z])AI([^A-Za-z]|$)/.test(t);
}

// 输出
let failed = 0;
for (const r of rows) {
  if (!r.pass) failed += 1;
  console.log((r.pass ? '  ✓ ' : '  ✗ ') + r.name + (r.detail ? '  → ' + r.detail : ''));
}
console.log('\n共 ' + rows.length + ' 项，通过 ' + (rows.length - failed) + ' 项，失败 ' + failed + ' 项');
process.exit(failed === 0 ? 0 : 1);
