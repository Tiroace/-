const automator = require('miniprogram-automator');
const fs = require('fs');
const OUT = 'D:\\程序上线资料准备\\提审截图\\';
const RED = [
  '诚招操作工 待遇优厚',
  '月薪8000-30000元，上不封顶，轻松月入过万',
  '入职需交押金300元，服装费自理',
  '工作地点：缅甸，包机票包吃住，月入2万',
  '联系人：薇信 abc123',
].join('\n');
const GREEN = [
  '东风科技有限公司 招聘 前端开发工程师',
  '岗位职责：负责公司后台系统的开发、协助测试、整理技术文档',
  '薪资：15000-18000元/月',
  '试用期3个月，签订劳动合同，缴纳五险一金',
  '工作地点：深圳市南山区科技园某某大厦8楼',
].join('\n');

const sleep = (ms) => new Promise(r => setTimeout(r, ms));

async function tapExact(page, text) {
  const views = await page.$$('view');
  for (const v of views) {
    let t = '';
    try { t = (await v.text()) || ''; } catch (e) {}
    if (t.trim() === text) { await v.tap(); return true; }
  }
  // 兜底：xpath
  const el = await page.getElementByXpath(`//*[text()="${text}"]`);
  if (el) { await el.tap(); return true; }
  return false;
}

async function waitReport(mp, timeout = 20000) {
  const t0 = Date.now();
  while (Date.now() - t0 < timeout) {
    const p = await mp.currentPage();
    if (p && p.path === 'pages/report/index') return p;
    await sleep(500);
  }
  return null;
}

(async () => {
  const mp = await automator.connect({ wsEndpoint: 'ws://127.0.0.1:9421' });

  // ① 首页空态
  await mp.reLaunch('/pages/index/index');
  await sleep(2500);
  await mp.screenshot({ path: OUT + '01-首页空态.png' });
  console.log('shot 01');

  // ② 粘贴文字后
  let page = await mp.currentPage();
  const ta = await page.$('textarea');
  await ta.input(RED);
  await sleep(1200);
  await mp.screenshot({ path: OUT + '02-粘贴文字后.png' });
  console.log('shot 02');

  // ③ 红灯报告
  const tapped = await tapExact(page, '开始检查');
  console.log('tap 开始检查:', tapped);
  const rp = await waitReport(mp);
  console.log('report page:', rp && rp.path);
  await sleep(1500);
  await mp.screenshot({ path: OUT + '03-红灯报告.png' });
  console.log('shot 03');

  // ④ 绿灯报告
  await mp.reLaunch('/pages/index/index');
  await sleep(2000);
  page = await mp.currentPage();
  const ta2 = await page.$('textarea');
  await ta2.input(GREEN);
  await sleep(1000);
  const tapped2 = await tapExact(page, '开始检查');
  console.log('tap2:', tapped2);
  await waitReport(mp);
  await sleep(1500);
  await mp.screenshot({ path: OUT + '04-绿灯报告.png' });
  console.log('shot 04');

  // ⑤ 检查规则说明页
  await mp.navigateTo('/pages/doc/index');
  await sleep(2000);
  await mp.screenshot({ path: OUT + '05-检查规则说明页.png' });
  console.log('shot 05');

  process.exit(0);
})().catch(e => { console.error('ERR', e && e.message); process.exit(1); });
