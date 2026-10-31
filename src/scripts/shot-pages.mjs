// R1 改版截图：连自动化端口，逐页截图存到 reports/rebrand/。
// 用法：node miniprogram/scripts/shot-pages.mjs
// 依赖：cli.bat open --port 9420 + cli.bat auto --auto-port 9422 已启动；
//       automator 装在 D:\qiuzhibilei\tests\node_modules
import { createRequire } from 'node:module';
import fs from 'node:fs';
import path from 'node:path';

const require = createRequire('D:/qiuzhibilei/tests/');
const automator = require('miniprogram-automator');

const WS = process.env.QBL_WS || 'ws://127.0.0.1:9422';
const OUT = 'D:/qiuzhibilei/reports/rebrand';
fs.mkdirSync(OUT, { recursive: true });

const PAGES = [
  { name: '01-首页', route: '/pages/index/index' },
  { name: '05-我的', route: '/pages/mine/index' },
  { name: '04-会员页', route: '/pages/member/index' },
  { name: '06-广场', route: '/pages/square/index' },
  { name: '02-报告页', route: '/pages/report/index?sample=1' },
];

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

async function main() {
  console.log('连接', WS);
  const miniProgram = await automator.connect({ wsEndpoint: WS });
  console.log('已连接');

  for (const p of PAGES) {
    try {
      // evaluate 跑在页面注入上下文，没有 uni 全局；用小程序底层 API 导航
      await miniProgram.evaluate((route) => {
        const u = route;
        const isTab = u === '/pages/index/index' || u === '/pages/square/index' || u === '/pages/mine/index';
        if (isTab) {
          wx.switchTab({ url: u });
        } else {
          wx.navigateTo({ url: u });
        }
      }, p.route);
      // 等渲染稳定（tab 图标、灯动画都起来）
      await sleep(2500);
      const shot = path.join(OUT, p.name + '.png');
      await miniProgram.screenshot({ path: shot });
      const size = fs.statSync(shot).size;
      const info = await miniProgram.evaluate(() => {
        const pages = getCurrentPages();
        const cur = pages[pages.length - 1];
        return { route: cur.route };
      });
      console.log('✓', p.name, '→', shot, '(' + size + ' bytes)', JSON.stringify(info));
    } catch (e) {
      console.log('✗', p.name, '失败:', e.message);
    }
  }

  await miniProgram.disconnect();
  console.log('完成，截图目录：', OUT);
}

main().catch((e) => {
  console.error('截图失败：', e.message);
  process.exit(1);
});
