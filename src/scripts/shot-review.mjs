// 提审截图（D38 个人主体 / 工具口径），一次拍齐后台提审要用的图
//
// 每张截图前都做上屏校验，不满足就判定失败、不保存：
//   - 上屏文案不得出现「AI」字样（(?<![A-Za-z])AI(?![A-Za-z])）
//   - 不得出现审核时效承诺（几分钟内 / 马上发布 / 立即发布 …）
//   - 报告页必须能看到「示例报告 · 内容是虚构的」标记
//   - 报告页必须能看到 D20 免责声明（本报告由系统…）
//
// 用法：node src/scripts/shot-review.mjs
// 依赖：cli.bat auto --auto-port 9422；automator 在 tests/node_modules
import { createRequire } from 'node:module';
import fs from 'node:fs';
import path from 'node:path';

const require = createRequire('D:/qiuzhibilei/tests/');
const automator = require('miniprogram-automator');

const WS = process.env.QBL_WS || 'ws://127.0.0.1:9422';
// 提审截图单独放一个目录，和日常改版截图分开，避免混杂
const OUT = 'D:/qiuzhibilei/reports/review';
fs.mkdirSync(OUT, { recursive: true });

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const AI_RE = /(?<![A-Za-z])AI(?![A-Za-z])/;
// 审核时效承诺（项目约定：文案里一律不出现）
const PROMISE_RE = /(几分钟内|分钟内完成|马上发布|立即发布|即刻公开|小时内完成|秒发布)/;

// 结论标题原文（pages/report/index.vue 的 VERDICT_TITLE）
const VERDICT = {
  red: '这份工作，建议先别去',
  amber: '先问清楚，再决定去不去',
  green: '截图里没看到明显风险',
  unknown: '截图信息不够，再补一张',
};

/** 读当前页上屏文字。
 *  踩过的坑（两条，都实测过）：
 *   1. 读 getCurrentPages()[...].data 拿不到 uni-app 的 ref（键名全是压缩后的别名）；
 *   2. page.$vm.$el.innerText 返回空。
 *  可用的办法是 automator 的 page.$$('text') —— 它读的是渲染层真实节点，
 *  拿到的就是用户看到的东西，正是提审截图该校验的对象。 */
async function screenText(mp) {
  const page = await mp.currentPage();
  const out = [];
  // 优先取所有 <text> 节点（文案都在这），再补 view 节点兜底
  for (const sel of ['text', 'view']) {
    try {
      const nodes = await page.$$(sel);
      for (const n of nodes) {
        const t = await n.text();
        if (t && t.trim()) out.push(t.trim());
      }
    } catch (e) { /* 单个节点读不到就跳过 */ }
    if (out.length) break;
  }
  return out.join('\n');
}

async function shotOnce(name, action, file, checks) {
  for (let attempt = 1; attempt <= 3; attempt++) {
    let mp = null;
    try {
      mp = await automator.connect({ wsEndpoint: WS });
      await mp.currentPage();
      const ctx = await action(mp);
      const text = await screenText(mp);

      // —— 上屏合规校验，任何一条不过都不保存 ——
      if (AI_RE.test(text)) throw new Error('上屏出现 AI 字样');
      if (PROMISE_RE.test(text)) throw new Error('上屏出现审核时效承诺：' + text.match(PROMISE_RE)[1]);
      if (checks) {
        const miss = checks.filter((c) => !c.test(text, ctx));
        if (miss.length) throw new Error('缺少：' + miss.map((c) => c.name).join('、'));
      }

      const target = path.join(OUT, file);
      await mp.screenshot({ path: target });
      const size = fs.statSync(target).size;
      if (size < 20000) throw new Error('截图疑似空图，仅 ' + size + ' 字节');
      console.log('✓ ' + name + ' → ' + file + ' (' + size + ' bytes)');
      return true;
    } catch (e) {
      console.log('  … ' + name + ' 第 ' + attempt + ' 次失败：' + e.message);
      if (attempt === 3) {
        console.log('✗ ' + name + ' 失败（已重试 3 次）');
        return false;
      }
      await sleep(2500);
    } finally {
      if (mp) { try { await mp.disconnect(); } catch (e) { /* 已断开 */ } }
    }
  }
  return false;
}

// 校验项：test(上屏文字, 动作返回的上下文)
const NEED_SAMPLE_CHIP = {
  name: '示例报告标记',
  test: (t) => t.includes('示例报告') && t.includes('内容是虚构的'),
};
const NEED_DISCLAIMER = {
  name: 'D20 免责声明',
  test: (t) => t.includes('本报告由系统') && t.includes('不构成法律意见'),
};
const NEED_12333 = {
  name: '12333 文字行（仅红灯）',
  // 12333 只出现在「已经交了钱？」卡片里，该卡片外层是 v-if="overall === 'red'"，
  // 所以黄/绿/灰报告本来就没有这行 —— 早先把它当成每张必检是校验写错了，不是页面缺内容。
  test: (t, ctx) => (ctx && ctx.overall === 'red' ? t.includes('12333') : true),
};

async function main() {
  console.log('连接 ' + WS + '\n');
  let ok = 0;
  let total = 0;

  // 1) 首页（含上传入口、剩余次数、示例入口）
  total += 1;
  if (await shotOnce('01-首页', async (mp) => {
    await mp.evaluate(() => wx.switchTab({ url: '/pages/index/index' }));
    await sleep(2800);
    const page = await mp.currentPage();
    if (page.path !== 'pages/index/index') throw new Error('没回首页，实际 ' + page.path);
    // 必须回到页面顶部：提审截图要展示主视觉 + 上传入口，
    // 之前因为上一步滚过页面，首页被截在中段，主视觉整个没了。
    await mp.evaluate(() => wx.pageScrollTo({ scrollTop: 0, duration: 0 }));
    await sleep(1200);
    return { path: page.path };
  }, '01-首页.png', [
    { name: '上传入口', test: (t) => t.includes('上传') || t.includes('截图') },
    { name: '示例报告入口', test: (t) => t.includes('示例') },
  ])) ok += 1;

  // 2) 四种示例报告页
  for (const k of ['red', 'amber', 'green', 'unknown']) {
    total += 1;
    const label = { red: '红', amber: '黄', green: '绿', unknown: '未知' }[k];
    const done = await shotOnce('0' + (2 + ['red', 'amber', 'green', 'unknown'].indexOf(k)) + '-报告页-' + label,
      async (mp) => {
        await mp.evaluate(
          (o) => wx.navigateTo({ url: '/pages/report/index?sample=1&overall=' + o }),
          k
        );
        await sleep(3200);
        const page = await mp.currentPage();
        if (page.path !== 'pages/report/index') throw new Error('没进报告页，实际 ' + page.path);
        await sleep(800);
        return { path: page.path, overall: k };
      }, '0' + (2 + ['red', 'amber', 'green', 'unknown'].indexOf(k)) + '-报告页-' + label + '.png',
      [
        NEED_SAMPLE_CHIP,
        NEED_DISCLAIMER,
        NEED_12333,
        { name: '结论标题（' + VERDICT[k] + '）', test: (t) => t.includes(VERDICT[k]) },
      ]);
    if (done) ok += 1;
    await sleep(600);
  }

  // 3) 示例入口：从首页进「先看一份示例报告」
  total += 1;
  if (await shotOnce('06-示例入口-首页内', async (mp) => {
    await mp.evaluate(() => wx.switchTab({ url: '/pages/index/index' }));
    await sleep(2600);
    const page = await mp.currentPage();
    // 滚到示例入口区，让整屏都展示示例入口
    await mp.evaluate(() => wx.pageScrollTo({ scrollTop: 9999, duration: 0 }));
    await sleep(1200);
    return { path: page.path };
  }, '06-示例入口-首页内.png', [
    { name: '示例入口文案', test: (t) => t.includes('示例') },
  ])) ok += 1;

  console.log('\n成功 ' + ok + '/' + total + ' 张，目录：' + OUT);
  process.exit(ok === total ? 0 : 1);
}

main().catch((e) => {
  console.error('截图失败：' + e.message);
  process.exit(1);
});
