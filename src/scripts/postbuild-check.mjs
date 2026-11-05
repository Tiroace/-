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
// 第二参数 = 构建模式：review = 提审包（tabBar 两项），缺省 = 开发包（tabBar 三项）
const REVIEW_MODE = String(process.argv[3] || '').trim().toLowerCase() === 'review';

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

  // ---------- 1a. AppID：正式包不得是游客号（2026-11-03 切正式 AppID） ----------
  // 注意：uni-app 不往 app.json 写 appid，AppID 落在产物根目录的 project.config.json 里
  const REAL_APPID = 'wx807821c2d1fb9f3b';
  let builtAppid = appJson.appid || '';
  if (!builtAppid) {
    try {
      const pc = JSON.parse(fs.readFileSync(path.join(DIST, 'project.config.json'), 'utf8'));
      builtAppid = pc.appid || '';
    } catch (e) {
      // 读不到就按空处理，下面会判失败
    }
  }
  builtAppid === REAL_APPID
    ? ok('appid = 正式 AppID（' + builtAppid + '）')
    : bad('appid 不是正式 AppID：' + (builtAppid || '(空)') + '，期望 ' + REAL_APPID);
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
  // 文案在 js 里定义；两版各一份，按引擎选用后集中在 common/docTexts.js
  const docJs = path.join(DIST, 'pages/doc/index.js');
  const docTextsJs = path.join(DIST, 'common/docTexts.js');
  const jsText =
    (fs.existsSync(docJs) ? fs.readFileSync(docJs, 'utf8') : '') +
    (fs.existsSync(docTextsJs) ? fs.readFileSync(docTextsJs, 'utf8') : '');
  jsText.includes('检查规则说明') ? ok('检查规则说明页在包内') : bad('缺检查规则说明页内容');
}
const corpJs = fs.existsSync(reportJs) ? fs.readFileSync(reportJs, 'utf8') : '';
corpJs.includes('国家企业信用信息公示系统') ? ok('公司核实卡在包内') : bad('缺公司核实卡');

// ---------- 6. 页面数与关键页 ----------
if (appJson) {
  // 【D39】会员页已经下架，不再是关键页；它的缺席由第 9 组断言反向锁住
  const must = ['pages/index/index', 'pages/report/index', 'pages/mine/index'];
  const missing = must.filter((p) => !(appJson.pages || []).includes(p));
  missing.length ? bad('缺关键页面：' + missing.join(', ')) : ok('关键页面齐全（' + appJson.pages.length + ' 页）');
}

// ---------- 6b. tabBar：提审包必须只有「检查」「我的」（BUG-20261103-02） ----------
{
  const tb = (appJson && appJson.tabBar) || null;
  const list = (tb && Array.isArray(tb.list) && tb.list) || [];
  const paths = list.map((t) => t.pagePath);
  const texts = list.map((t) => t.text);
  // 这些界面文案里不允许出现「广场」入口字样
  const uiHits = [];
  for (const f of allFiles) {
    if (!/\.(wxml|json)$/.test(f)) continue;
    const txt = fs.readFileSync(f, 'utf8');
    if (txt.includes('广场')) uiHits.push(path.relative(DIST, f));
  }
  const squareWxml = path.join(DIST, 'pages/square/index.wxml');
  const squarePacked = fs.existsSync(squareWxml);

  if (REVIEW_MODE) {
    paths.length === 2 && paths.includes('pages/index/index') && paths.includes('pages/mine/index') && !paths.includes('pages/square/index')
      ? ok('提审包 tabBar 只有 2 项：检查、我的（' + texts.join('、') + '）')
      : bad('提审包 tabBar 不对：' + JSON.stringify(paths));
    !uiHits.includes('app.json') && !uiHits.some((h) => h.startsWith('pages/index/') || h.startsWith('pages/mine/') || h === 'app.json')
      ? ok('提审包首页/我的/tabBar 无「广场」字样')
      : bad('提审包界面仍出现「广场」：' + uiHits.join(', '));
    !squarePacked ? ok('提审包无广场页面') : console.log('  （提示）提审包内仍保留 pages/square 页面文件，仅入口不可达');
  } else {
    paths.includes('pages/square/index')
      ? ok('开发包 tabBar 保留广场（3 项：' + texts.join('、') + '）')
      : bad('开发包 tabBar 丢了广场：' + JSON.stringify(paths));
  }
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

// ---------- 9. 【D39】会员/收费下架：个人主体 + 纯免费 + 流量主 ----------
// 依据：个人主体不能开通微信虚拟支付，收入模式改为纯免费 + 广告。
// 会员页、价格、《会员服务协议》都不许出现在提审包里，否则等于「未开放功能」上架。
{
  // 9a. 会员页不能进包
  const hasMemberPage = (appJson && (appJson.pages || []).includes('pages/member/index'));
  hasMemberPage ? bad('【D39】包内仍有 pages/member/index') : ok('【D39】包内无 pages/member/index');

  const memberDir = path.join(DIST, 'pages', 'member');
  fs.existsSync(memberDir) ? bad('【D39】包内仍有 pages/member 目录') : ok('【D39】包内无 pages/member 目录');

  // 9b. 上屏文案扫价格与收费字样。
  // 只扫 wxml（用户看得见）+ json（配置文案）；js 里有变量名/接口注释，
  // 而且报价字段是服务端下发的，扫 js 会误报。
  const PRICE_PATTERNS = [
    { re: /¥\s*\d/, name: '¥ 价格' },
    { re: /￥\s*\d/, name: '￥ 价格' },
    { re: /\d+(\.\d+)?\s*元\s*\/\s*(月|天|次|年)/, name: '元/月 类价格' },
    { re: /开通会员/, name: '开通会员' },
    { re: /会员服务协议/, name: '《会员服务协议》' },
    { re: /会员卡/, name: '会员卡' },
    { re: /周卡|月卡|季卡|年卡/, name: '会员套餐名' },
    { re: /付费|充值|购买会员/, name: '付费类字样' },
  ];
  const priceHits = [];
  for (const f of allFiles) {
    if (!/\.(wxml|json)$/.test(f)) continue;
    // app.json / project.config.json 是框架配置，不含上屏文案
    const base = path.basename(f);
    if (base === 'app.json' || base === 'project.config.json' || base === 'project.private.config.json') continue;
    const t = fs.readFileSync(f, 'utf8');
    for (const p of PRICE_PATTERNS) {
      if (p.re.test(t)) priceHits.push(path.relative(DIST, f) + ' 含「' + p.name + '」');
    }
  }
  priceHits.length
    ? bad('【D39】包内无价格/会员收费字样', [...new Set(priceHits)].slice(0, 6).join('; '))
    : ok('【D39】包内无价格/会员收费字样（¥价格、开通会员、会员服务协议、周卡月卡、付费充值）');

  // 9c. 配置层开关必须是关的（防有人把 MEMBERSHIP_ENABLED 改回 true 却没走提审）
  // 编译期会把常量折叠掉，产物里没有 MEMBERSHIP_ENABLED 这个名字，
  // 只剩函数体。所以判据是编译后的 isMembershipVisible / canBuyMember 必须恒返回 !1。
  const entFile = allFiles.find((f) => /common[\/\\]entitlement\.js$/.test(f));
  if (!entFile) {
    bad('【D39】包内找不到 entitlement 模块');
  } else {
    const src = fs.readFileSync(entFile, 'utf8');
    const vis = /isMembershipVisible\s*=\s*function\s*\(\)\s*\{\s*return\s*(!1|false)\s*;?\s*\}/.test(src);
    const buy = /canBuyMember\s*=\s*function\s*\(\)\s*\{\s*return\s*(!1|false)\s*;?\s*\}/.test(src);
    vis && buy
      ? ok('【D39】编译后 isMembershipVisible / canBuyMember 恒为 false')
      : bad('【D39】会员可见性开关没关死', 'isMembershipVisible恒false=' + vis + ' canBuyMember恒false=' + buy);
  }

  // 9d. QuotaSheet 的会员卡必须是编译期剔除（#ifdef QBL_MEMBER_ON），不能只靠 v-if：
  //     v-if 只影响渲染，wxml 里的「开通会员 / 周卡 ¥」照样进包，审核能看到。
  const qsWxml = path.join(DIST, 'components', 'QuotaSheet.wxml');
  if (!fs.existsSync(qsWxml)) {
    bad('【D39】包内找不到 QuotaSheet.wxml');
  } else {
    const w = fs.readFileSync(qsWxml, 'utf8');
    /开通会员|周卡|会员服务协议/.test(w)
      ? bad('【D39】QuotaSheet 仍含会员文案', '应改用 #ifdef QBL_MEMBER_ON 编译期剔除')
      : ok('【D39】QuotaSheet 无会员卡文案（编译期已剔除）');
  }

  // 9e. 源码里会员卡必须用条件编译包住（防止后来有人改成 v-if 又混进包）
  const qsSrc = path.join('D:/qiuzhibilei/src/src', 'components', 'QuotaSheet.vue');
  if (fs.existsSync(qsSrc)) {
    const s = fs.readFileSync(qsSrc, 'utf8');
    /#ifdef QBL_MEMBER_ON/.test(s) && /#endif/.test(s)
      ? ok('【D39】源码 QuotaSheet 会员卡已用 #ifdef 包住')
      : bad('【D39】源码 QuotaSheet 会员卡没用条件编译');
  }
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
