// 截取 green / unknown 两套示例报告截图（D3 收尾，docs/22 §8）
// 每套两张：首页的示例入口 + 报告页（带「示例报告 · 内容是虚构的，不指向任何公司」标记）
// 用法：node src/scripts/shot-examples.mjs
// 依赖：cli.bat auto --auto-port 9422 已启动；automator 装在 tests/node_modules
//
// 为什么每张图单独连一次：automator 走一条长连接，一旦某次调用超时，
// 后续调用全部报 "timeout waiting for automator response"。分开连互不拖累。
import { createRequire } from 'node:module';
import fs from 'node:fs';
import path from 'node:path';

const require = createRequire('D:/qiuzhibilei/tests/');
const automator = require('miniprogram-automator');

const WS = process.env.QBL_WS || 'ws://127.0.0.1:9422';
const OUT = 'D:/qiuzhibilei/reports/rebrand';
fs.mkdirSync(OUT, { recursive: true });

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// 报告页示例入口：?sample=1&overall=<overall>（见 pages/report/index.vue onLoad）
const CASES = [
  { overall: 'green', label: 'green（绿灯·正常岗位）' },
  { overall: 'unknown', label: 'unknown（灰灯·信息不足）' },
];

// 一次连接一张图；冷启动那次经常超时，失败就重试（最多 3 次）
async function shotOnce(name, action, file) {
  for (let attempt = 1; attempt <= 3; attempt++) {
    let mp = null;
    try {
      mp = await automator.connect({ wsEndpoint: WS });
      // 连接刚建立时先探一下，探不通说明这条连接还没就绪，直接重连
      await mp.currentPage();
      await action(mp);
      const target = path.join(OUT, file);
      await mp.screenshot({ path: target });
      console.log('✓ ' + name + ' → ' + target + ' (' + fs.statSync(target).size + ' bytes)');
      return true;
    } catch (e) {
      const reason = e.message;
      console.log('  … ' + name + ' 第 ' + attempt + ' 次失败：' + reason);
      if (attempt === 3) {
        console.log('✗ ' + name + ' 失败（已重试 3 次）');
        return false;
      }
      await sleep(2500);
    } finally {
      if (mp) {
        try { await mp.disconnect(); } catch (e) { /* 连接已断就忽略 */ }
      }
    }
  }
  return false;
}

async function main() {
  console.log('连接 ' + WS + '\n');
  let ok = 0;

  // —— 首页示例入口（两个 overall 共用同一张首页，各存一份便于对照）——
  for (const c of CASES) {
    const done = await shotOnce('首页入口 ' + c.label, async (mp) => {
      await mp.evaluate(() => wx.switchTab({ url: '/pages/index/index' }));
      await sleep(2600);
      const page = await mp.currentPage();
      if (page.path !== 'pages/index/index') throw new Error('没回首页，实际 ' + page.path);
      // 确认示例入口文案在
      const hit = await page.$('.sample-entry') || await page.$('.example-entry') || await page.$('.sample-card');
      console.log('  首页示例入口节点：' + (hit ? '有' : '按类名没匹配到，整页截'));
    }, '示例-首页入口-' + c.overall + '.png');
    if (done) ok += 1;
    await sleep(600);
  }

  // —— 报告页 ——
  for (const c of CASES) {
    const done = await shotOnce('报告页 ' + c.label, async (mp) => {
      await mp.evaluate(
        (o) => wx.navigateTo({ url: '/pages/report/index?sample=1&overall=' + o }),
        c.overall
      );
      await sleep(3200);
      const page = await mp.currentPage();
      if (page.path !== 'pages/report/index') throw new Error('没进报告页，实际 ' + page.path);
      await sleep(1200);
      // 不看 page.data()（automator 对 setup 里 ref 的解包不可靠，实测拿到 undefined），
      // 直接读上屏节点：示例标记 + 结论标题，这才是用户真正看到的东西。
      const sampleChip = await page.$('.chip-sample');
      const chipText = sampleChip ? (await sampleChip.text()) : '';
      const verdictEl = await page.$('.verdict-title');
      const verdict = verdictEl ? (await verdictEl.text()) : '';
      const fullText = await mp.evaluate(() => {
        const pages = getCurrentPages();
        const cur = pages[pages.length - 1];
        return (cur.$el && cur.$el.innerText) || document.body.innerText || '';
      }).catch(() => '');
      console.log('  示例标记：' + (chipText || '（没找到 .chip-sample）'));
      console.log('  结论标题：' + (verdict || '（没找到 .verdict-title）'));
      // 用页面里 VERDICT_TITLE 的原文做判定（见 pages/report/index.vue）
      const WANT_WORD = { green: '截图里没看到明显风险', unknown: '截图信息不够，再补一张' };
      if (!chipText.includes('示例报告')) throw new Error('示例标记没显示：' + chipText);
      if (!verdict.includes(WANT_WORD[c.overall])) {
        throw new Error('结论标题「' + verdict + '」不含 「' + WANT_WORD[c.overall] + '」，不是 ' + c.overall + ' 示例');
      }
    }, '示例-报告页-' + c.overall + '.png');
    if (done) ok += 1;
    await sleep(600);
  }

  console.log('\n成功 ' + ok + '/4 张，目录：' + OUT);
  process.exit(ok === 4 ? 0 : 1);
}

main().catch((e) => {
  console.error('截图失败：' + e.message);
  process.exit(1);
});
