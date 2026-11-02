// 真机全流程录屏脚本（第 2 关准备）
//
// 用途：正式 AppID 到手后，按固定顺序自动走一遍主流程，每一步都留截图 + 文字记录，
//       作为「真机录屏」的证据链。人手动录屏时对着这份脚本的步骤走，不会漏步骤。
//
// 覆盖的 5 步（派单要求）：
//   1 登录            2 上传截图          3 出报告
//   4 看激励视频换次数  5 次数用完弹窗
//
// 职责边界（Chief 2026-11-03）：IDE 的 open / auto 归软件测试者。
// 本脚本只「连接」已有自动化端口，不启动 IDE、不占端口。
// 端口没人监听时直接 exit 2 并提示，不会自己去拉起 IDE。
//
// 用法：
//   node src/scripts/record-flow.mjs                 走流程并逐步截图到 reports/record/
//   node src/scripts/record-flow.mjs --dry-run       只打印步骤清单，不连自动化
//
// 前置：软件测试者按 docs/18 拉起自动化（cli.bat auto --port 9420 --auto-port 9422）
import { createRequire } from 'node:module';
import fs from 'node:fs';
import path from 'node:path';
import net from 'node:net';

const DRY = process.argv.includes('--dry-run');
const WS = process.env.QBL_WS || 'ws://127.0.0.1:9422';
const OUT = 'D:/qiuzhibilei/reports/record';

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// 上报文案里的违禁项，每步都查一遍（沿用提审截图的口径）
const AI_RE = /(?<![A-Za-z])AI(?![A-Za-z])/;
const PROMISE_RE = /(几分钟内|分钟内完成|马上发布|立即发布|即刻公开|小时内完成|秒发布)/;

// 5 步主流程。每步：名字 / 怎么到这一步 / 到了之后必须看到什么
const STEPS = [
  {
    n: 1,
    name: '登录',
    desc: '进入「我的」，触发登录，确认拿到用户信息与剩余次数',
    goto: () => wx.switchTab({ url: '/pages/mine/index' }),
    expect: ['我的'],
    // 登录态判定：页面出现「剩余次数」或用户昵称，两者有一个即算登录成功
    expectAny: ['剩余', '次数', '检查记录'],
    shot: '01-登录.png',
  },
  {
    n: 2,
    name: '上传截图',
    desc: '回首页，确认上传入口与剩余次数可见（真机上由人点选 1-3 张截图）',
    goto: () => wx.switchTab({ url: '/pages/index/index' }),
    expect: ['上传', '截图'],
    shot: '02-上传入口.png',
    // 真机上这一步需要人点「选择图片」，脚本只验证入口在、并留时间给人操作
    humanWait: 15000,
  },
  {
    n: 3,
    name: '出报告',
    desc: '报告页必须能看到结论、6 项检查、免责声明；示例报告标记也要在',
    goto: () => wx.navigateTo({ url: '/pages/report/index?sample=1&overall=red' }),
    expect: ['示例报告', '本报告由系统', '12333'],
    shot: '03-报告页.png',
  },
  {
    n: 4,
    name: '看广告换次数',
    desc: '次数用完弹窗里「看广告」按钮可见可点（真机上人点一次，确认到账 +1）',
    goto: () => wx.switchTab({ url: '/pages/index/index' }),
    expectAny: ['看广告', '广告'],
    shot: '04-看广告入口.png',
    humanWait: 20000,
  },
  {
    n: 5,
    name: '次数用完弹窗',
    desc: '弹窗只提供「看广告」与「明天再来」，不得出现任何会员或价格字样',
    goto: () => wx.switchTab({ url: '/pages/index/index' }),
    expectAny: ['次数用完', '免费次数用完', '明天再来'],
    forbid: ['开通会员', '会员服务协议', '¥', '周卡', '月卡'],
    shot: '05-次数用完弹窗.png',
  },
];

function portBusy(port) {
  return new Promise((resolve) => {
    const s = net.connect({ host: '127.0.0.1', port }, () => { s.destroy(); resolve(true); });
    s.on('error', () => resolve(false));
    s.setTimeout(1200, () => { s.destroy(); resolve(false); });
  });
}

async function screenText(mp) {
  const page = await mp.currentPage();
  const out = [];
  for (const sel of ['text', 'view']) {
    try {
      const nodes = await page.$$(sel);
      for (const nd of nodes) {
        const t = await nd.text();
        if (t && t.trim()) out.push(t.trim());
      }
    } catch (e) { /* 读不到就跳过 */ }
    if (out.length) break;
  }
  return out.join('\n');
}

async function main() {
  console.log('=== 真机全流程（5 步）===');
  STEPS.forEach((s) => console.log('  ' + s.n + '. ' + s.name + ' —— ' + s.desc));

  if (DRY) {
    console.log('\n[dry-run] 只列步骤，不连自动化。');
    return 0;
  }

  const port = Number((WS.match(/:(\d+)$/) || [])[1] || 9422);
  if (!(await portBusy(port))) {
    console.error(
      '\n✗ 连不上自动化端口 ' + port + '。\n' +
      '  IDE 的 open/auto 归软件测试者（docs/18 手册），请先让对方拉起：\n' +
      '  cli.bat auto --project "...\\dist\\build\\mp-weixin" --port 9420 --auto-port 9422\n'
    );
    return 2;
  }

  const require = createRequire('D:/qiuzhibilei/tests/');
  const automator = require('miniprogram-automator');
  fs.mkdirSync(OUT, { recursive: true });

  const log = [];
  let mp = null;
  let failed = 0;

  try {
    mp = await automator.connect({ wsEndpoint: WS });
    await mp.currentPage();
    console.log('已连接 ' + WS + '\n');

    for (const step of STEPS) {
      const row = { step: step.n, name: step.name, pass: false, note: '' };
      try {
        await mp.evaluate(step.goto);
        await sleep(2800);

        if (step.humanWait) {
          console.log('  · ' + step.name + '：留 ' + (step.humanWait / 1000) + ' 秒给人操作…');
          await sleep(step.humanWait);
        }

        const text = await screenText(mp);
        if (AI_RE.test(text)) throw new Error('上屏出现 AI 字样');
        if (PROMISE_RE.test(text)) throw new Error('上屏出现时效承诺');

        if (step.expect) {
          const miss = step.expect.filter((k) => !text.includes(k));
          if (miss.length) throw new Error('缺少：' + miss.join('、'));
        }
        if (step.expectAny) {
          if (!step.expectAny.some((k) => text.includes(k))) {
            throw new Error('以下任意一个都没出现：' + step.expectAny.join(' / '));
          }
        }
        if (step.forbid) {
          const hit = step.forbid.filter((k) => text.includes(k));
          if (hit.length) throw new Error('D39 出现禁用字样：' + hit.join('、'));
        }

        const target = path.join(OUT, step.shot);
        await mp.screenshot({ path: target });
        const size = fs.statSync(target).size;
        if (size < 15000) throw new Error('截图疑似空图，仅 ' + size + ' 字节');

        row.pass = true;
        row.note = size + ' bytes';
        console.log('  ✓ ' + step.n + '. ' + step.name + ' → ' + step.shot + ' (' + size + ' bytes)');
      } catch (e) {
        row.note = e.message;
        failed += 1;
        console.log('  ✗ ' + step.n + '. ' + step.name + ' 失败：' + e.message);
      }
      log.push(row);
    }
  } finally {
    if (mp) { try { await mp.disconnect(); } catch (e) { /* 已断开 */ } }
  }

  // 写一份文字记录，作为录屏的配套证据
  const stamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
  const logFile = path.join(OUT, 'flow-' + stamp + '.md');
  const lines = [
    '# 真机全流程记录 ' + stamp,
    '',
    '| 步骤 | 名称 | 结果 | 说明 |',
    '| --- | --- | --- | --- |',
  ];
  log.forEach((r) => lines.push('| ' + r.step + ' | ' + r.name + ' | ' + (r.pass ? '✅' : '❌') + ' | ' + r.note + ' |'));
  lines.push('', '截图目录：' + OUT);
  fs.writeFileSync(logFile, lines.join('\n'), 'utf8');

  console.log('\n记录：' + logFile);
  console.log(failed ? '✗ 有 ' + failed + ' 步失败' : '✓ 5 步全部通过');
  return failed ? 1 : 0;
}

main()
  .then((code) => process.exit(code))
  .catch((e) => { console.error('失败：' + e.message); process.exit(1); });
