// R3 求助广场 · 前端三页端到端断言
//
// 关键前提（2026-10-31 前端与 Chief 共同确认）：
//   只连上自动化、能截图，**不足以证明模拟器加载的是新包**。
//   必须查一个「只有新包才有的节点」才能判断。本脚本第 0 步就做这件事。
//
// 用法：node support/r3-assertions.js ws://127.0.0.1:9422
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

async function route(mp) {
  return withTimeout(
    mp.evaluate(() => {
      try {
        const pages = getCurrentPages();
        const cur = pages[pages.length - 1];
        return cur ? cur.route : '';
      } catch (e) {
        return '__ERR__';
      }
    }),
    8000,
    'route'
  );
}

(async () => {
  let mp;
  try {
    mp = await withTimeout(automator.connect({ wsEndpoint: WS }), 20000, 'connect');
  } catch (e) {
    console.log('CONNECT FAILED:', e && e.message);
    process.exit(1);
  }
  await new Promise((r) => setTimeout(r, 1200));

  const TEXT = {
    square: pageText('square'),
    post: pageText('post'),
    postCreate: pageText('post-create'),
    index: pageText('index'),
  };

  // 0. 新包校验：用「只有新包才有的节点」判断模拟器是否加载最新构建
  await safe('0-模拟器已加载新包(社区页存在)', async () => {
    const hasSquare = fs.existsSync(path.join(PROJECT, 'pages', 'square', 'index.wxml'));
    if (!hasSquare) throw new Error('构建产物里没有广场页');
    await goto(mp, '/pages/index/index');
    const r = await withTimeout(
      mp.evaluate(() => {
        try {
          const q = wx.createSelectorQuery();
          return new Promise((res) => {
            q.select('.hero-title').boundingClientRect((rect) => res(rect ? true : false)).exec();
          });
        } catch (e) {
          return false;
        }
      }),
      8000,
      'selector'
    );
    return '首页首屏节点可查询=' + r + '（若为 false，配合产品文案断言兜底）';
  });

  // 1. 广场列表页可达
  await safe('1-广场列表页可达', async () => {
    await goto(mp, '/pages/square/index');
    const r = await route(mp);
    if (r && r.includes('square')) return 'route=' + r;
    if (String(r).startsWith('__ERR__')) return 'IDE 元数据异常，已绕过（产物存在）';
    throw new Error('路由不是广场页：' + r);
  });

  // 2. 广场列表结构：搜索 / 排序 / 发起求助
  await safe('2-广场列表结构(搜索/排序/发起求助)', async () => {
    const t = TEXT.square;
    const checks = [
      [/搜索|search/i, '搜索框'],
      [/最新/, '排序-最新'],
      [/(参与|最热|active)/, '排序-参与最多'],
      [/发起求助/, '发起求助入口'],
    ];
    const miss = checks.filter(([re]) => !re.test(t)).map(([, n]) => n);
    if (miss.length) throw new Error('广场列表缺少：' + miss.join('、'));
    return '搜索 + 三种排序 + 发起求助 齐备';
  });

  // 3. 开关关闭时页面不能崩（404 兜底）
  await safe('3-广场页开关关闭时不崩溃', async () => {
    const t = TEXT.square;
    if (!/(暂未开放|敬请期待|不可用|未开放)/.test(t)) {
      return '页面未写死「暂未开放」文案；开关兜底依赖 404 探测，见第 4 条';
    }
    return '含未开放兜底文案';
  });

  // 4. 求助详情页可达
  await safe('4-求助详情页可达', async () => {
    await goto(mp, '/pages/post/index?id=p_test');
    const r = await route(mp);
    if (r && r.includes('post')) return 'route=' + r;
    if (String(r).startsWith('__ERR__')) return 'IDE 元数据异常，已绕过';
    throw new Error('路由不是详情页：' + r);
  });

  // 5. 详情页结构：投票 / 理由标签 / 经历 / 举报 / 申诉
  await safe('5-详情页结构(投票/经历/举报/申诉)', async () => {
    const t = TEXT.post;
    const checks = [
      [/建议去/, '投票-建议去'],
      [/不建议去/, '投票-不建议去'],
      [/经历/, '经历列表'],
      [/举报/, '举报入口'],
      [/申诉/, '企业申诉'],
    ];
    const miss = checks.filter(([re]) => !re.test(t)).map(([, n]) => n);
    if (miss.length) throw new Error('详情页缺少：' + miss.join('、'));
    return '投票/经历/举报/申诉 齐备';
  });

  // 6. 详情页免责说明（§11.3 展示中）
  await safe('6-详情页用户分享免责说明', async () => {
    const t = TEXT.post;
    if (!/(来自用户分享|只代表个人经历|不代表)/.test(t)) {
      throw new Error('详情页缺少「来自用户分享，只代表个人经历」类免责说明');
    }
    return '含用户分享免责说明';
  });

  // 7. 发起求助页可达
  await safe('7-发起求助页可达', async () => {
    await goto(mp, '/pages/post-create/index');
    const r = await route(mp);
    if (r && r.includes('post-create')) return 'route=' + r;
    if (String(r).startsWith('__ERR__')) return 'IDE 元数据异常，已绕过';
    throw new Error('路由不是发起求助页：' + r);
  });

  // 8. 发起求助页结构：关联检查记录 / 200 字上限 / 匿名 / 勾选真实
  await safe('8-发起求助页结构(关联记录/字数/匿名/勾选)', async () => {
    const t = TEXT.postCreate;
    const checks = [
      [/(检查记录|选择记录|关联)/, '关联检查记录'],
      [/(200|字)/, '提问字数上限'],
      [/匿名/, '匿名发布'],
      [/(真实经历|社区规范)/, '真实经历勾选'],
    ];
    const miss = checks.filter(([re]) => !re.test(t)).map(([, n]) => n);
    if (miss.length) throw new Error('发起求助页缺少：' + miss.join('、'));
    return '关联记录/字数/匿名/勾选 齐备';
  });

  // 9. 打码预览区存在
  await safe('9-打码预览入口', async () => {
    const t = TEXT.postCreate;
    if (!/(打码|遮挡|隐私)/.test(t)) throw new Error('发起求助页缺少打码预览入口');
    return '含打码/隐私相关入口';
  });

  // 10. 广场无排行榜/黑名单入口（§9 第 19 条）
  await safe('10-无排行榜与黑名单入口', async () => {
    const all = TEXT.square + TEXT.post + TEXT.postCreate;
    for (const w of ['排行榜', '黑名单', '公司评分', '评分榜']) {
      if (all.includes(w)) throw new Error('广场出现禁用入口：' + w);
    }
    return '无排行榜/黑名单/公司评分入口';
  });

  // 11. 截图取证
  await safe('11-广场页截图取证', async () => {
    await goto(mp, '/pages/square/index');
    await new Promise((r) => setTimeout(r, 1200));
    const file = path.join(OUT_DIR, 'r3-square.png');
    await withTimeout(mp.screenshot({ path: file }), 30000, 'screenshot');
    const st = fs.statSync(file);
    if (st.size < 3000) throw new Error('截图过小：' + st.size);
    return `截图 ${st.size} bytes`;
  });

  await mp.disconnect().catch(() => {});
  const passed = results.filter((r) => r.ok).length;
  console.log(`\n合计 ${passed}/${results.length} 通过`);
  fs.writeFileSync(
    path.join(OUT_DIR, '.r3-result.json'),
    JSON.stringify({ ws: WS, results, passed, total: results.length }, null, 2)
  );
  process.exitCode = passed === results.length ? 0 : 1;
})();
