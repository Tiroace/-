// 补拍提审截图里缺的 3 张（#03 上传流程 / #04 分析中 / #13 次数用完弹窗）
//
// 背景：软件测试者的 shot-review-14.mjs 已拍 12 张（#01/02/05/06/07/08/09/10/11a/11b/12/14），
// 规范 docs/06/19 §二 一共 14 张，缺这 3 张。本脚本只补缺的，不重拍别人的。
//
// 沿用测试者实测出来的约束（他写在 shot-review-14.mjs 头部，已验证）：
//  1) page.$() / page.$$() / page.data() 可能超时 —— 用 mp.evaluate() 读 __data__；
//  2) 连续 navigateTo 多次会让通道崩（Uncaught [object Object]）
//     → 每张图独立 connect/disconnect，每次只做一次导航；
//  3) 滚动用 mp.pageScrollTo(数字)；
//  4) 校验在「滚动前」做（__data__ 不随滚动变化）。
//
// 【D39 说明】规范 #13 原本要求「次数用完弹窗 + 会员页」两屏合一，
//   会员页已按 D39 从提审包删除，本脚本只拍弹窗那一屏，并在清单里标注缺会员页的原因。
//
// 职责边界：IDE 的 open/auto 归软件测试者（docs/18）。本脚本只连接 9422。
// 用法：node src/scripts/shot-review-missing3.mjs
import { createRequire } from 'node:module';
import fs from 'node:fs';
import path from 'node:path';
import net from 'node:net';

const WS = process.env.QBL_WS || 'ws://127.0.0.1:9422';
const OUT = 'D:/qiuzhibilei/reports/review14'; // 与测试者同一目录，合成完整 14 张
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const AI_RE = /(?<![A-Za-z])AI(?![A-Za-z])/;
const PROMISE_RE = /(几分钟内|分钟内完成|马上发布|立即发布|即刻公开|小时内完成|秒发布)/;

function portBusy(port) {
  return new Promise((resolve) => {
    const s = net.connect({ host: '127.0.0.1', port }, () => { s.destroy(); resolve(true); });
    s.on('error', () => resolve(false));
    s.setTimeout(1200, () => { s.destroy(); resolve(false); });
  });
}

// 读上屏文字，两个来源都要用：
//   A) __data__：递归摊平所有字符串（测试者验证过，不依赖压缩键名），
//      但页面里普通 const（如 analyzing 页的 STAGES）不在 data 里，读不到；
//   B) 渲染层 <text> 节点：页面真正画出来的字。
// 只读其中一个会漏，实测：只读 A 时「分析中」三段文案读不到。
async function readText(mp) {
  const fromData = await mp.evaluate(() => {
    const ps = getCurrentPages();
    const p = ps[ps.length - 1];
    if (!p || !p.__data__) return '';
    const out = [];
    const walk = (v, d) => {
      if (d > 5 || v == null) return;
      if (typeof v === 'string') { if (v.trim()) out.push(v); return; }
      if (Array.isArray(v)) { v.forEach((x) => walk(x, d + 1)); return; }
      if (typeof v === 'object') {
        for (const k of Object.keys(v)) {
          if (k.startsWith('__') || k.startsWith('$')) continue;
          try { walk(v[k], d + 1); } catch (e) { /* 循环引用等跳过 */ }
        }
      }
    };
    walk(p.__data__, 0);
    return out.join('\n');
  });

  const nodes = [];
  try {
    const page = await mp.currentPage();
    const list = await page.$$('text');
    for (const nd of list) {
      try {
        const t = await nd.text();
        if (t && t.trim()) nodes.push(t.trim());
      } catch (e) { /* 单节点读不到跳过 */ }
    }
  } catch (e) { /* 节点读不到就只用 data */ }

  return fromData + '\n' + nodes.join('\n');
}

async function shotOnce(spec) {
  let mp = null;
  try {
    // 需要人工/真机才能拍的项：不拍、不冒充当通过，如实标 SKIP
    if (spec.manual) {
      console.log('○ ' + spec.name + ' → SKIP（需人工）：' + spec.manual);
      return { ok: null, skip: true, note: '需人工：' + spec.manual };
    }

    mp = await automator.connect({ wsEndpoint: WS });
    await mp.currentPage();

    if (spec.tab) await mp.evaluate((u) => wx.switchTab({ url: u }), spec.url);
    else await mp.navigateTo(spec.url);
    await sleep(spec.wait || 3200);

    const page = await mp.currentPage();
    if (spec.needPath && page.path !== spec.needPath) throw new Error('页面不对：' + page.path);

    if (spec.action) { await spec.action(mp); await sleep(1500); }

    const text = await readText(mp);
    if (AI_RE.test(text)) throw new Error('上屏出现 AI 字样');
    if (PROMISE_RE.test(text)) throw new Error('上屏出现审核时效承诺');

    if (spec.checks && spec.checks.length) {
      const miss = spec.checks.filter((c) => !c.test(text));
      if (miss.length) throw new Error('缺少：' + miss.map((c) => c.name).join('、'));
    }
    if (spec.forbid) {
      const bad = spec.forbid.filter((k) => text.includes(k));
      if (bad.length) throw new Error('D39 不该出现：' + bad.join('、'));
    }

    if (typeof spec.scroll === 'number') { await mp.pageScrollTo(spec.scroll); await sleep(1500); }

    const target = path.join(OUT, spec.file);
    await mp.screenshot({ path: target });
    const size = fs.statSync(target).size;
    if (size < 15000) throw new Error('疑似空图，仅 ' + size + ' 字节');
    console.log('✓ ' + spec.name + ' → ' + spec.file + ' (' + size + ' bytes)');
    return { ok: true, note: size + ' bytes' };
  } catch (e) {
    console.log('✗ ' + spec.name + ' 失败：' + (e && e.message));
    return { ok: false, note: String(e && e.message) };
  } finally {
    if (mp) { try { await mp.disconnect(); } catch (e) { /* 忽略 */ } }
  }
}

const SPECS = [
  {
    name: '#04 分析中', file: '04-分析中.png',
    tab: true, url: '/pages/index/index', needPath: 'pages/analyzing/index', wait: 2000,
    // 分析页是过渡态，直接 navigateTo 进去会弹「没有检查任务」（实测拍到过空态）。
    // 正确做法：先建一个真实任务拿 task_id，再进分析页，进去后立刻截图。
    //
    // 页面实例上拿不到服务模块（实测 $vm.$scope 只有生命周期，没有 api），
    // 所以走「在页面上下文里直接调 mock 的建任务接口」这条路：
    // mock 把任务存在 state.tasks，接口是同一份代码，这里用 __QBL_DEV_TASK 钩子不可靠，
    // 改为「跳到报告页示例 → 再进分析页」不成立。
    // 最终方案：直接构造 task_id 并写入 mock 状态不可行（页面拿不到模块引用）。
    // ——因此这张只能靠真实上传链路，脚本里如实标注为需要人工/真机执行。
    manual: '分析中需要真实上传后才有 task_id（mock 模块未向页面暴露，无法脚本注入）。'
      + '真机录屏时由人点「检查」自然进入，此时截图即可。',
    checks: [],
  },
  {
    name: '#03 上传流程', file: '03-上传流程.png',
    // 规范要求的是「点选图后」的画面，要真机选图才会出现预览与上传提示。
    // 脚本只能到首页，拍出来和 #01 一模一样（同字节数），属重复图，不交。
    manual: '需真机点「选截图」选中 1-3 张后才出现预览与「截图仅用于本次分析」提示。'
      + '脚本只能停在首页，拍出来与 #01 重复，故标为需人工。',
    checks: [],
  },
  {
    name: '#13 次数用完弹窗（仅弹窗部分）', file: '13-次数用完弹窗.png',
    // 弹窗需要「次数真的用完」才出现，脚本造不出这个状态：
    // 上一版用「还能免费查」这种宽松匹配硬凑，拍出来其实是首页、没有弹窗——属于误报，已改严。
    // 真机录屏时把次数用完、点「检查」自然弹出，那时截图。
    manual: '需真实把次数消耗到 0 才会弹出，脚本无法制造该状态。'
      + '真机录屏时点「检查」触发弹窗后截图；提审说明写「当前版本暂未开放付费」。',
    checks: [],
  },
];

let automator = null;

async function main() {
  console.log('=== 补拍 3 张（规范 14 张里缺的）===\n');

  const port = Number((WS.match(/:(\d+)$/) || [])[1] || 9422);
  if (!(await portBusy(port))) {
    console.error('✗ 连不上自动化端口 ' + port + '。IDE 的 open/auto 归软件测试者（docs/18），请先让对方拉起。');
    return 2;
  }

  const require = createRequire('D:/qiuzhibilei/tests/');
  automator = require('miniprogram-automator');
  fs.mkdirSync(OUT, { recursive: true });

  const results = [];
  for (const spec of SPECS) {
    results.push({ spec, r: await shotOnce(spec) });
    await sleep(1200);
  }

  const okN = results.filter((x) => x.r.ok === true).length;
  const skipN = results.filter((x) => x.r.skip).length;
  const bad = results.filter((x) => x.r.ok === false).map((x) => x.spec.name);
  console.log('\n成功 ' + okN + '，跳过 ' + skipN + '（需人工），失败 ' + bad.length);
  console.log('失败：' + (bad.join('、') || '无'));
  // 有跳过但没失败，不算成功退出：需人工的项要如实暴露出来，不能当全绿
  return bad.length ? 1 : (skipN ? 3 : 0);
}

main().then((c) => process.exit(c)).catch((e) => { console.error('fatal ' + (e && e.message)); process.exit(1); });
