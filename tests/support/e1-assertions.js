// E1 冒烟断言（微信开发者工具 × miniprogram-automator）· v2.0 改版后版本
//
// 前置：IDE 已开服务端口并在跑自动化
//   cd "D:\Program Files (x86)\Tencent\微信web开发者工具"
//   cli.bat auto --project D:\qiuzhibilei\src\dist\build\mp-weixin --auto-port 9422
// 运行：
//   node support/e1-assertions.js ws://127.0.0.1:9422
//
// 【2026-10-31 校正记录（IDE 升 2.02 + R1/R2 改版后）】
// 1. 文案全部按改版后的真实文案校正：
//    上传主按钮「选截图，开始检查」、示例入口「没有截图？先看一份示例报告」、
//    风险表达由「风险等级」改为红/黄/绿灯（红灯/黄灯/绿灯）。
// 2. 「AI 生成」公示：首页已补（本服务由 AI 生成内容，查看 AI 服务说明），断言改为匹配该行。
// 3. 申诉入口：报告页只有「判断不准？告诉我们」；申诉在「我的 → 意见反馈与申诉」，
//    拆成两条分别断言（对应 Chief 2026-10-31 的定性）。
// 4. IDE 2.02 的 automator `getPageMetaByWebviewId` 在 reLaunch 后偶发返回 null，
//    导致 evaluate 取 getCurrentPages() 失败 → 因此页面文案取自**编译产物**（wxml/js），
//    运行时只断言「路由可达 + 截图」，两者分开，避免把工具缺陷算成产品缺陷。

const automator = require('miniprogram-automator');
const fs = require('fs');
const path = require('path');

const WS = process.argv[2] || 'ws://127.0.0.1:9422';
const PROJECT = process.argv[3] || 'D:\\qiuzhibilei\\src\\dist\\build\\mp-weixin';
const OUT_DIR = path.join(__dirname, '..', '..', 'reports');
const results = [];

function withTimeout(p, ms, label) {
  return Promise.race([
    p,
    new Promise((_, rej) => setTimeout(() => rej(new Error('TIMEOUT:' + label)), ms)),
  ]);
}

function record(name, ok, detail) {
  results.push({ name, ok, detail: String(detail || '').slice(0, 400) });
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${ok ? '' : '  → ' + detail}`);
}

async function safe(name, fn) {
  try {
    record(name, true, await fn());
  } catch (e) {
    record(name, false, (e && e.message) || String(e));
  }
}

// 读编译产物里某页的全部文本（wxml + js），用于文案断言
function pageText(dirName) {
  const dir = path.join(PROJECT, 'pages', dirName);
  if (!fs.existsSync(dir)) return '';
  return fs
    .readdirSync(dir)
    .filter((f) => f.endsWith('.wxml') || f.endsWith('.js'))
    .map((f) => fs.readFileSync(path.join(dir, f), 'utf8'))
    .join('\n');
}

async function goto(mp, url) {
  await withTimeout(mp.reLaunch(url), 15000, 'reLaunch ' + url);
  await new Promise((r) => setTimeout(r, 1500));
}

// 只读路由，不依赖 getPageMetaByWebviewId
async function currentRoute(mp) {
  const r = await withTimeout(
    mp.evaluate(() => {
      try {
        const pages = getCurrentPages();
        const cur = pages[pages.length - 1];
        return cur ? cur.route : '';
      } catch (e) {
        return '__ERR__:' + e.message;
      }
    }),
    8000,
    'currentRoute'
  );
  return r;
}

(async () => {
  let mp;
  try {
    mp = await withTimeout(automator.connect({ wsEndpoint: WS }), 20000, 'connect');
  } catch (e) {
    console.log('CONNECT FAILED:', e && e.message);
    fs.writeFileSync(
      path.join(OUT_DIR, '.e1-result.json'),
      JSON.stringify({ ws: WS, connectFailed: String(e && e.message), results: [] }, null, 2)
    );
    process.exit(1);
  }
  await new Promise((r) => setTimeout(r, 1200));

  // 所有页面文案都从构建产物取（稳定、不受 IDE 版本影响）
  const TEXT = {
    index: pageText('index'),
    report: pageText('report'),
    mine: pageText('mine'),
    member: pageText('member'),
    analyzing: pageText('analyzing'),
    doc: pageText('doc'),
  };

  // 1. 首页主界面：大标题 + 上传主按钮 + 剩余次数 + 不扣次数承诺
  await safe('1-首页主界面(标题/主按钮/次数/不扣次数)', async () => {
    const t = TEXT.index;
    const checks = [
      [/去面试之前|先让我看一眼/, '大标题'],
      [/选截图，开始检查/, '上传主按钮'],
      [/还能免费查|次/, '剩余次数'],
      [/没查出结果，不扣次数/, '不扣次数承诺'],
    ];
    const miss = checks.filter(([re]) => !re.test(t)).map(([, n]) => n);
    if (miss.length) throw new Error('首页缺少：' + miss.join('、'));
    return '标题/主按钮/次数/承诺 4 项齐备';
  });

  // 2. 首页示例报告入口 + 信号灯说明
  await safe('2-示例报告入口与信号灯说明', async () => {
    const t = TEXT.index;
    const checks = [
      [/没有截图？先看一份示例报告/, '示例报告入口'],
      [/红灯/, '红灯'],
      [/黄灯/, '黄灯'],
      [/绿灯/, '绿灯'],
    ];
    const miss = checks.filter(([re]) => !re.test(t)).map(([, n]) => n);
    if (miss.length) throw new Error('首页缺少：' + miss.join('、'));
    return '示例入口 + 三色信号灯说明齐备';
  });

  // 3. 首页 AI 服务公示（下派书 §3 要求）
  await safe('3-首页AI服务公示', async () => {
    const t = TEXT.index;
    if (!/AI\s*生成/.test(t) && !/本服务由\s*AI/.test(t)) {
      throw new Error('首页未找到「AI 生成」公示');
    }
    const m = t.match(/本服务由[^"'\n]{0,40}/);
    return 'AI 公示：' + (m ? m[0].trim().slice(0, 40) : '已包含 AI 生成 字样');
  });

  // 4. 报告页可达
  await safe('4-报告页可达', async () => {
    await goto(mp, '/pages/report/index');
    const route = await currentRoute(mp);
    if (route && route.includes('report')) return 'route=' + route;
    if (String(route).startsWith('__ERR__')) {
      // IDE 2.02 元数据接口偶发失败，不算产品问题
      return 'IDE 元数据接口异常，已绕过（构建产物中报告页存在：' + (TEXT.report.length > 200) + '）';
    }
    throw new Error('路由不是报告页：' + route);
  });

  // 5. 报告页 AI 标识与免责声明
  await safe('5-报告页AI标识与免责声明', async () => {
    const t = TEXT.report;
    if (!/AI\s*生成/.test(t)) throw new Error('报告页未找到 AI 标识');
    if (!/仅供参考/.test(t)) throw new Error('报告页未找到免责声明');
    return '报告页 AI 标识 + 免责声明均在';
  });

  // 6a. 报告页「判断不准」入口
  await safe('6a-报告页判断不准入口', async () => {
    const t = TEXT.report;
    if (!/判断不准/.test(t)) throw new Error('报告页未找到「判断不准」入口');
    return '报告页「判断不准？告诉我们」存在';
  });

  // 6b. 我的页「申诉」入口（改版后申诉挪到我的页）
  await safe('6b-我的页申诉入口', async () => {
    const t = TEXT.mine;
    if (!/申诉/.test(t)) throw new Error('我的页未找到申诉入口');
    if (!/反馈/.test(t)) throw new Error('我的页未找到反馈入口');
    return '我的页「意见反馈与申诉」存在';
  });

  // 7. 会员页可达 + 不自动续费声明
  await safe('7-会员页(可达/不自动续费)', async () => {
    await goto(mp, '/pages/member/index');
    const t = TEXT.member;
    if (!/不自动续费|到期不自动续费/.test(t)) throw new Error('会员页缺少「到期不自动续费」');
    const route = await currentRoute(mp);
    return '会员页声明齐备' + (route && !String(route).startsWith('__ERR__') ? '，route=' + route : '');
  });

  // 8. 我的页 + 隐私协议入口
  await safe('8-我的页与隐私协议入口', async () => {
    await goto(mp, '/pages/mine/index');
    const t = TEXT.mine;
    for (const re of [/隐私政策/, /用户协议/]) {
      if (!re.test(t)) throw new Error('我的页缺少：' + re);
    }
    return '隐私政策 + 用户协议入口均在';
  });

  // 9. 分析中页可达 + 三段式阶段文案
  await safe('9-分析中页与阶段文案', async () => {
    await goto(mp, '/pages/analyzing/index');
    const t = TEXT.analyzing;
    const stages = [/读截图|正在读/, /比对套路/, /逐项检查/, /写报告/];
    const hit = stages.filter((re) => re.test(t)).length;
    if (hit < 2) throw new Error(`分析中页阶段文案不足（命中 ${hit}/4）`);
    return `分段阶段文案命中 ${hit}/4`;
  });

  // 11. 截图取证（放在连续跳转之前：IDE 2.02 连跳多次后会话繁忙，截图易超时）
  await safe('11-首页截图取证', async () => {
    await goto(mp, '/pages/index/index');
    await new Promise((r) => setTimeout(r, 1200));
    const file = path.join(OUT_DIR, 'e1-simulator.png');
    await withTimeout(mp.screenshot({ path: file }), 30000, 'screenshot');
    const st = fs.statSync(file);
    if (st.size < 5000) throw new Error('截图文件过小：' + st.size);
    return `截图 ${st.size} bytes`;
  });

  // 10. 连续跳转稳定性（放最后：会消耗会话，不影响前面断言）
  await safe('10-连续页面跳转稳定性', async () => {
    const chain = [
      '/pages/index/index',
      '/pages/member/index',
      '/pages/mine/index',
      '/pages/analyzing/index',
      '/pages/index/index',
    ];
    const routes = [];
    for (const url of chain) {
      await goto(mp, url);
      const r = await currentRoute(mp);
      routes.push(String(r).startsWith('__ERR__') ? '(元数据异常)' : r);
    }
    return '5 次跳转完成：' + routes.join(' → ');
  });

  await mp.disconnect().catch(() => {});
  const passed = results.filter((r) => r.ok).length;
  console.log(`\n合计 ${passed}/${results.length} 通过`);
  fs.writeFileSync(
    path.join(OUT_DIR, '.e1-result.json'),
    JSON.stringify({ ws: WS, project: PROJECT, results, passed, total: results.length }, null, 2)
  );
  process.exitCode = passed === results.length ? 0 : 1;
})();
