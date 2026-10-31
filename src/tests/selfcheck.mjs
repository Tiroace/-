// 单元自测：平台适配层 + 激励视频守卫 + 合规工具 + 接口契约对齐
// 运行方式（在 miniprogram/ 目录下任选一种）：
//   pnpm test                      ← 推荐（已配好 --import，别直接 node tests/selfcheck.mjs）
//   npm test                       本机没有独立 npm，用上面那条
//   node --import ./tests/register-alias.mjs tests/selfcheck.mjs
// 为什么要 --import：源码用 `@/` 别名（构建期由 uni-app 解析），Node 直接跑要装别名钩子，
// 否则会报 ERR_MODULE_NOT_FOUND: @/platform。
// 目的：在没有真实广告位和真机的情况下，验证 §6.2 的每条硬规范、§7/§8 合规、docs/04 契约在代码里成立。
import assert from 'node:assert';

// ---- 极简运行时替身：只提供业务代码用到的 uni.* 接口 ----
const storage = new Map();
globalThis.uni = {
  getStorageSync: (k) => (storage.has(k) ? storage.get(k) : ''),
  setStorageSync: (k, v) => storage.set(k, v),
  removeStorageSync: (k) => storage.delete(k),
  getSystemInfoSync: () => ({ uniPlatform: 'mp-toutiao', platform: 'android' }),
};

const results = [];

// 用例之间要干净：A 组会在 globalThis 上装假的 tt 对象，
// 不清掉会串到后面的守卫用例里。所以每个用例开始前统一重置运行时。
function resetRuntime() {
  delete globalThis.tt;
  delete globalThis.wx;
  storage.delete('qiuzhibilei_force_mock');
  storage.delete('qiuzhibilei_mock_ad_fail');
}

function test(name, fn) {
  resetRuntime();
  return Promise.resolve()
    .then(fn)
    .then(() => results.push({ name, pass: true }))
    .catch((e) => results.push({ name, pass: false, err: e.message }));
}

// ============ A. 平台适配层 ============
await test('A1 抖音端：未配置广告位 ID 时直接返回兜底，不发广告请求', async () => {
  const { default: tt } = await import('../src/platform/toutiao.js');
  const r = await tt.createRewardedAd('');
  assert.equal(r.fallback, true);
  assert.equal(r.reason, 'no-ad-unit');
});

await test('A2 抖音端：运行时没有 tt 对象时也走兜底，不抛错', async () => {
  const { default: tt } = await import('../src/platform/toutiao.js');
  const r = await tt.createRewardedAd('adunit-xxx');
  assert.equal(r.fallback, true);
});

let createdCount = 0;
let showCount = 0;
let loadCount = 0;
function installFakeTT(mode) {
  const handlers = { close: [], error: [] };
  const ad = {
    onClose: (f) => handlers.close.push(f),
    offClose: (f) => (handlers.close = handlers.close.filter((x) => x !== f)),
    onError: (f) => handlers.error.push(f),
    offError: (f) => (handlers.error = handlers.error.filter((x) => x !== f)),
    load: () => {
      loadCount += 1;
      return Promise.resolve();
    },
    show: () => {
      showCount += 1;
      if (mode === 'show-fail') return Promise.reject(new Error('no fill'));
      setTimeout(() => {
        if (mode === 'watched') handlers.close.forEach((f) => f({ isEnded: true }));
        if (mode === 'skipped') handlers.close.forEach((f) => f({ isEnded: false }));
        if (mode === 'error') handlers.error.forEach((f) => f({ errMsg: 'ad error' }));
      }, 10);
      return Promise.resolve();
    },
    destroy: () => {},
  };
  globalThis.tt = {
    createRewardedVideoAd: () => {
      createdCount += 1;
      return ad;
    },
    pay: () => {},
    login: ({ success }) => success({ code: 'tt-code' }),
  };
  createdCount = 0;
  showCount = 0;
  loadCount = 0;
}

await test('A3 抖音端：用户看完 → watched=true，且只创建 1 个广告实例、只 show 1 次', async () => {
  installFakeTT('watched');
  const { default: tt } = await import('../src/platform/toutiao.js');
  const r = await tt.createRewardedAd('adunit-1');
  assert.equal(r.watched, true);
  assert.equal(r.fallback, false);
  assert.equal(createdCount, 1);
  assert.equal(showCount, 1);
});

await test('A4 抖音端：用户中途关闭 → 不发奖励，且不算兜底', async () => {
  installFakeTT('skipped');
  const { default: tt } = await import('../src/platform/toutiao.js');
  const r = await tt.createRewardedAd('adunit-2');
  assert.equal(r.watched, false);
  assert.equal(r.fallback, false);
  assert.equal(r.reason, 'skipped');
});

await test('A5 抖音端：show 失败（无填充）→ 先 load 重试一次，仍失败则兜底', async () => {
  installFakeTT('show-fail');
  const { default: tt } = await import('../src/platform/toutiao.js');
  const r = await tt.createRewardedAd('adunit-3');
  assert.equal(r.fallback, true);
  assert.equal(r.reason, 'load-failed');
  assert.equal(loadCount, 1);
});

await test('A6 抖音端：onError（版本低/异常）→ 兜底', async () => {
  installFakeTT('error');
  const { default: tt } = await import('../src/platform/toutiao.js');
  const r = await tt.createRewardedAd('adunit-4');
  assert.equal(r.fallback, true);
});

await test('A7 微信端：未配置广告位 → 兜底；支付恒不可用（无资质）', async () => {
  const { default: wx } = await import('../src/platform/weixin.js');
  const r = await wx.createRewardedAd('');
  assert.equal(r.fallback, true);
  assert.equal(wx.isPaymentSupported(), false);
});

await test('A8 mock 平台：可模拟「广告拉不出来」用于联调兜底分支', async () => {
  storage.set('qiuzhibilei_mock_ad_fail', '1');
  const { default: m } = await import('../src/platform/mock.js');
  const r = await m.createRewardedAd();
  assert.equal(r.fallback, true);
  storage.delete('qiuzhibilei_mock_ad_fail');
});

// ============ B. 激励视频守卫（§6.2） ============
// 守卫约束与具体平台无关。这里用一个「确实能拉出广告」的假平台驱动守卫，
// 验证并发、频率、单次调起这几条约束本身；平台实现的兜底已在 A 组覆盖。
let createCallCount = 0;
let createFail = false;
const fakePlatform = {
  login: () => Promise.resolve({ code: 'x' }),
  isRewardedAdSupported: () => true,
  createRewardedAd: () => {
    createCallCount += 1;
    if (createFail) return Promise.resolve({ ok: false, fallback: true, reason: 'load-failed' });
    return new Promise((r) => setTimeout(() => r({ ok: true, watched: true, fallback: false }), 30));
  },
  isPaymentSupported: () => true,
  pay: () => Promise.resolve({ ok: true }),
};
// 切换当前生效的平台实现（自测专用，见下方统一实现）

// 守卫会先检查「有没有配广告位 ID」，没配就直接兜底（这是真实行为）。
// B 组要测守卫本身的约束，所以先补一个假的广告位 ID。
const configMod = await import('../src/common/config.js');
configMod.AD_UNIT_IDS.douyin = 'adunit-selftest';
configMod.AD_UNIT_IDS.weixin = 'adunit-selftest';

// 平台模块只加载一次并缓存引用，注入实现用同步接口，避免 await 期间的竞态。
const platformMod = await import('../src/platform/index.js');
function installFakePlatform(p) {
  platformMod.__setImplForTest(p);
}

await test('B1 账号有广告位、用户看完 → 发奖励（正常路径）', async () => {
  const guard = await import('../src/common/adGuard.js');
  installFakePlatform(fakePlatform);
  const r1 = await guard.runRewardedFlow('b1a-' + Date.now());
  assert.equal(r1.granted, true);
  assert.equal(r1.watched, true);
});

await test('B2 一个页面同时只允许一个流程，重复点击被拦', async () => {
  const guard = await import('../src/common/adGuard.js');
  installFakePlatform(fakePlatform);
  const p1 = guard.runRewardedFlow('b2');
  const p2 = await guard.runRewardedFlow('b2');
  assert.equal(p2.reason, 'running');
  assert.equal(p2.granted, false);
  const r1 = await p1;
  assert.equal(r1.watched, true);
});

await test('B3 60 秒内第 6 次调起被拒绝（频率上限 5 次）', async () => {
  const guard = await import('../src/common/adGuard.js');
  const key = 'b3-' + Date.now();
  for (let i = 0; i < 5; i += 1) {
    // eslint-disable-next-line no-await-in-loop
    await guard.runRewardedFlow(key);
  }
  const sixth = await guard.runRewardedFlow(key);
  assert.equal(sixth.reason, 'rate-limited');
  assert.equal(sixth.granted, false);
});

await test('B4 一次流程只创建、只调起 1 条广告（不循环、不连看）', async () => {
  const guard = await import('../src/common/adGuard.js');
  const before = createCallCount;
  const r = await guard.runRewardedFlow('b4');
  assert.equal(r.watched, true);
  assert.equal(r.granted, true);
  assert.equal(r.fallback, false);
  assert.equal(createCallCount - before, 1);
});

await test('B5 广告拉不出来 → 守卫返回 granted+fallback，业务照发奖励', async () => {
  createFail = true;
  const guard = await import('../src/common/adGuard.js');
  const r = await guard.runRewardedFlow('b5');
  createFail = false;
  assert.equal(r.granted, true);
  assert.equal(r.fallback, true);
});

// ============ C. 合规工具 ============
await test('C1 免责声明 = D20 定稿（带后半句，无 AI 字样）', async () => {
  const { DISCLAIMER_TEXT } = await import('../src/common/constants.js');
  assert.equal(
    DISCLAIMER_TEXT,
    '本报告由系统根据截图文字和规则库自动生成，仅供参考，不构成法律意见，也不代表对任何企业的评价；截图不完整或内容不实都会影响判断，重要事项请自行核实。'
  );
  // 路线令：产品文案不得出现 AI
  assert.equal(/(?<![A-Za-z])AI(?![A-Za-z])/.test(DISCLAIMER_TEXT), false, '免责声明仍含 AI 字样');
});

await test('C2 禁用词在前端二次过滤生效', async () => {
  const { safeText, FORBIDDEN_WORDS } = await import('../src/common/constants.js');
  for (const w of FORBIDDEN_WORDS) {
    assert.equal(safeText('这是' + w + '的文本').includes(w), false, '未过滤：' + w);
  }
});

await test('C3 分享脱敏：手机号 / 公司名 / 姓名都被打码', async () => {
  const { maskAll, maskCompanyName, maskPersonName } = await import('../src/common/format.js');
  assert.equal(maskAll('联系 13812345678').includes('13812345678'), false);
  assert.notEqual(maskCompanyName('某某网络科技有限公司'), '某某网络科技有限公司');
  assert.notEqual(maskPersonName('张伟'), '张伟');
});

await test('C4 报告文案不含定性/夸大词（禁用词表逐条扫描页面源码）', async () => {
  const { FORBIDDEN_WORDS } = await import('../src/common/constants.js');
  const fs = await import('node:fs');
  const dirs = ['../src/pages', '../src/common'];
  const files = [];
  const walk = (d) => {
    for (const f of fs.readdirSync(new URL(d, import.meta.url))) {
      const u = new URL(d + '/' + f, import.meta.url);
      if (fs.statSync(u).isDirectory()) walk(d + '/' + f);
      else if (/\.(vue|js)$/.test(f)) files.push(u);
    }
  };
  dirs.forEach(walk);
  const hits = [];
  for (const u of files) {
    const text = fs.readFileSync(u, 'utf8');
    // constants.js 里的禁用词表本身要放行
    if (u.pathname.endsWith('constants.js')) continue;
    for (const w of FORBIDDEN_WORDS) {
      if (text.includes(w)) hits.push(u.pathname.split('/').pop() + ' 含「' + w + '」');
    }
  }
  assert.deepEqual(hits, [], hits.join('；'));
});

await test('C5 业务代码不直接调用 tt./wx.（平台差异只在 platform/ 内）', async () => {
  const fs = await import('node:fs');
  const roots = ['../src/pages', '../src/services', '../src/common'];
  const files = [];
  const walk = (d) => {
    for (const f of fs.readdirSync(new URL(d, import.meta.url))) {
      const u = new URL(d + '/' + f, import.meta.url);
      if (fs.statSync(u).isDirectory()) walk(d + '/' + f);
      else if (/\.(vue|js)$/.test(f)) files.push(u);
    }
  };
  roots.forEach(walk);
  const hits = [];
  for (const u of files) {
    const lines = fs.readFileSync(u, 'utf8').split(/\r?\n/);
    lines.forEach((l, i) => {
      if (/^\s*\/\//.test(l)) return;
      if (/\b(tt|wx)\.[a-zA-Z]/.test(l)) hits.push(u.pathname.split('/').pop() + ':' + (i + 1));
    });
  }
  assert.deepEqual(hits, [], hits.join('、'));
});

// ============ D. 与 docs/04 接口契约对齐 ============
// 后端契约（2026-10-31 v0.1）是前后端唯一口径，这里逐条验证前端 mock 与接口层守住了它。

await test('D1 响应封套：成功是 {ok:true,data,request_id}，失败是 {ok:false,error:{code,message}}', async () => {
  const mock = await import('../src/services/mock.js');
  const okRes = await mock.postAuthLogin({ code: 'c', platform: 'toutiao' });
  assert.equal(okRes.ok, true);
  assert.ok(okRes.data && okRes.data.user_id);
  assert.ok(typeof okRes.request_id === 'string' && okRes.request_id.length > 0);

  const badRes = await mock.postAnalysis({ files: [] });
  assert.equal(badRes.ok, false);
  assert.equal(badRes.error.code, 'VALIDATION_ERROR');
  assert.ok(typeof badRes.error.message === 'string');
  assert.ok(typeof badRes.error.detail === 'object');
});

await test('D2 创建分析立即返回 pending + task_id + poll_after_ms（不等结果）', async () => {
  const mock = await import('../src/services/mock.js');
  const res = await mock.postAnalysis({ files: [{ hash: 'h-d2' }] });
  assert.equal(res.ok, true);
  assert.equal(res.data.status, 'pending');
  assert.ok(res.data.task_id);
  assert.equal(res.data.poll_after_ms, 1500);
  assert.equal(res.data.report, null);
});

await test('D3 轮询状态机 pending → running → done，done 时带 §4.3 报告', async () => {
  const mock = await import('../src/services/mock.js');
  const created = await mock.postAnalysis({ files: [{ hash: 'h-d3' }] });
  const taskId = created.data.task_id;

  const seen = [];
  let last = null;
  for (let i = 0; i < 5; i += 1) {
    // eslint-disable-next-line no-await-in-loop
    const r = await mock.getAnalysis(taskId);
    seen.push(r.data.status);
    last = r.data;
    if (r.data.status === 'done') break;
  }
  assert.deepEqual(seen, ['pending', 'running', 'done']);
  assert.ok(last.report, 'done 时应带报告');
  // 报告字段必须符合 v2 schema（一期不用大模型：rules_version，不是 prompt_version）
  for (const f of ['overall', 'summary', 'dimensions', 'findings', 'questions_to_ask', 'how_to_verify', 'rules_version']) {
    assert.ok(f in last.report, '报告缺字段：' + f);
  }
  assert.equal('prompt_version' in last.report, false, 'v2 报告不应再有 prompt_version');
  assert.equal(last.report.dimensions.length, 6, '维度必须 6 项');
  assert.ok(last.report.findings.every((x) => x.evidence && x.reason && x.level && x.dimension));
  assert.ok(
    last.report.findings.every((x) => ['rule', 'pattern'].includes(x.source)),
    'source 只允许 rule / pattern'
  );
  assert.equal(last.poll_after_ms, null, 'done 时 poll_after_ms 必须为 null');
});

await test('D4 次数不足返回 QUOTA_EXHAUSTED，且不扣次数', async () => {
  const mock = await import('../src/services/mock.js');
  // 把余额打到 0：连续提交 3 次（新用户 3 次）
  for (let i = 0; i < 3; i += 1) {
    // eslint-disable-next-line no-await-in-loop
    await mock.postAnalysis({ files: [{ hash: 'h-d4-' + i }] });
  }
  const res = await mock.postAnalysis({ files: [{ hash: 'h-d4-over' }] });
  assert.equal(res.ok, false);
  assert.equal(res.error.code, 'QUOTA_EXHAUSTED');
  assert.equal(res.error.detail.balance, 0);
});

await test('D5 广告奖励：no_fill / error 也必须发次数（§6.2 强制兜底）', async () => {
  const mock = await import('../src/services/mock.js');
  const ids = ['req-d5-nofill-1', 'req-d5-error-2', 'req-d5-completed-3'];
  const results = [];
  for (let i = 0; i < ids.length; i += 1) {
    // eslint-disable-next-line no-await-in-loop
    const r = await mock.postAdReward({ request_id: ids[i], result: ['no_fill', 'error', 'completed'][i] });
    results.push(r.data);
  }
  assert.ok(results.every((r) => r.granted === true), '三种结果都必须发次数');
  assert.equal(results[2].today_count, 3);
  assert.equal(results[2].daily_cap, 5);
});

await test('D6 广告奖励 request_id 幂等：重复提交不重复发放', async () => {
  const mock = await import('../src/services/mock.js');
  const first = await mock.postAdReward({ request_id: 'req-d6-abcdefgh', result: 'completed' });
  const second = await mock.postAdReward({ request_id: 'req-d6-abcdefgh', result: 'completed' });
  assert.equal(second.data.replayed, true);
  assert.equal(second.data.reason, 'duplicate_request_id');
  assert.equal(second.data.quota.balance, first.data.quota.balance, '重复提交不能加次数');
});

await test('D7 广告每日上限 5 次：第 6 次返回 daily_cap_reached 且不发', async () => {
  const mock = await import('../src/services/mock.js');
  let last = null;
  for (let i = 0; i < 6; i += 1) {
    // eslint-disable-next-line no-await-in-loop
    const r = await mock.postAdReward({ request_id: 'req-d7-cap-' + i + '-xxxx', result: 'completed' });
    last = r.data;
  }
  assert.equal(last.granted, false);
  assert.equal(last.reason, 'daily_cap_reached');
  assert.equal(last.remaining_today, 0);
});

await test('D8 分析幂等：同一 Idempotency-Key 返回同一 task_id，不重复预扣', async () => {
  const mock = await import('../src/services/mock.js');
  const key = 'idem-' + Date.now();
  const a = await mock.postAnalysis({ files: [{ hash: 'h-d8' }], idem_key: key });
  const b = await mock.postAnalysis({ files: [{ hash: 'h-d8' }], idem_key: key });
  assert.equal(a.data.task_id, b.data.task_id);
  assert.equal(b.data.idempotent_replay, true);
  assert.equal(a.data.quota.balance, b.data.quota.balance, '重放不能再扣');
});

await test('D9 历史报告：items[] 带 report_id/task_id/risk_level/summary/created_at/expires_at', async () => {
  const mock = await import('../src/services/mock.js');
  // 先跑出一个完成的任务，让历史里有数据
  const created = await mock.postAnalysis({ files: [{ hash: 'h-d9' }] });
  for (let i = 0; i < 4; i += 1) {
    // eslint-disable-next-line no-await-in-loop
    await mock.getAnalysis(created.data.task_id);
  }
  const res = await mock.getReports({ limit: 20 });
  assert.equal(res.ok, true);
  assert.ok(Array.isArray(res.data.items));
  assert.ok(res.data.items.length >= 1);
  // 历史列表项沿用 docs/04 的字段（risk_level 是列表摘要字段，不是报告体）
  for (const f of ['report_id', 'task_id', 'risk_level', 'summary', 'created_at', 'expires_at']) {
    assert.ok(f in res.data.items[0], '历史项缺字段：' + f);
  }
  assert.ok('next_cursor' in res.data);
});

await test('D10 错误码表与 docs/04 的 1.4 一致（前端不按文案分支）', async () => {
  const mock = await import('../src/services/mock.js');
  const need = [
    'VALIDATION_ERROR',
    'UNAUTHORIZED',
    'FORBIDDEN',
    'NOT_FOUND',
    'QUOTA_EXHAUSTED',
    'IDEMPOTENCY_CONFLICT',
    'ORDER_NOT_FOUND',
    'AMOUNT_MISMATCH',
    'SIGNATURE_INVALID',
    'CONTENT_BLOCKED',
    'RATE_LIMITED',
    'PLATFORM_ERROR',
    'ANALYSIS_UNAVAILABLE',
    'ANALYSIS_FAILED',
    'INTERNAL_ERROR',
  ];
  for (const c of need) assert.ok(mock.ERROR_CODES[c], '错误码缺失：' + c);
  assert.equal(mock.ERROR_CODES.QUOTA_EXHAUSTED, 402);
  assert.equal(mock.ERROR_CODES.CONTENT_BLOCKED, 422);
  assert.equal(mock.ERROR_CODES.RATE_LIMITED, 429);
});

await test('D11 订单：pay_params 必须标 mock:true（不可用于真实扣款）', async () => {
  const mock = await import('../src/services/mock.js');
  const res = await mock.postOrders({ plan: 'month', channel: 'toutiao' });
  assert.equal(res.ok, true);
  assert.equal(res.data.plan, 'month');
  assert.equal(res.data.amount_fen, 1990);
  assert.equal(res.data.pay_params.mock, true);
  assert.equal(res.data.status, 'pending');
});

await test('D12 反馈：type 取值与契约 2.9 一致，答复期限 7 天', async () => {
  const mock = await import('../src/services/mock.js');
  const r = await mock.postFeedback({ type: 'inaccurate', report_id: 'RPT-MOCK-0001', content: '等级判高了' });
  assert.equal(r.data.type, 'inaccurate');
  assert.equal(r.data.status, 'open');
  assert.equal(r.data.expect_reply_within_days, 7);
  const bad = await mock.postFeedback({ type: 'not-a-type' });
  assert.equal(bad.error.code, 'VALIDATION_ERROR');
});

await test('D13 报告 evidence 展示用脱敏版（示例数据里不能出现完整手机号）', async () => {
  const { EXAMPLE_REPORTS } = await import('../src/common/exampleReports.js');
  const text = JSON.stringify(EXAMPLE_REPORTS);
  const fullPhones = text.match(/1[3-9]\d{9}/g) || [];
  assert.deepEqual(fullPhones, [], '示例报告里出现了完整手机号：' + fullPhones.join(','));
  // 顺手校验 v2 结构：4 种 overall 齐全、每份 6 维、版本字段是 rules_version
  for (const o of ['red', 'amber', 'green', 'unknown']) {
    assert.ok(EXAMPLE_REPORTS[o], '缺示例：' + o);
    assert.equal(EXAMPLE_REPORTS[o].dimensions.length, 6, o + ' 维度不是 6 项');
    assert.ok(EXAMPLE_REPORTS[o].rules_version, o + ' 缺 rules_version');
    assert.equal('prompt_version' in EXAMPLE_REPORTS[o], false, o + ' 不应有 prompt_version');
  }
});

await test('D14 创建响应 status 只允许 pending/running，绝不返回 done/failed、绝不带报告（D8）', async () => {
  const mock = await import('../src/services/mock.js');
  // 默认路径：pending
  const a = await mock.postAnalysis({ files: [{ hash: 'h-d14-a' }] });
  assert.equal(a.data.status, 'pending');
  assert.equal(a.data.report, null);

  // 模拟后台线程已开跑：running
  storage.set('qiuzhibilei_mock_start_running', '1');
  const b = await mock.postAnalysis({ files: [{ hash: 'h-d14-b' }] });
  storage.delete('qiuzhibilei_mock_start_running');
  assert.equal(b.data.status, 'running');
  assert.equal(b.data.report, null);

  for (const r of [a, b]) {
    assert.notEqual(r.data.status, 'done');
    assert.notEqual(r.data.status, 'failed');
    assert.ok(!r.data.report, '创建响应不允许带报告');
  }
});

await test('D15 幂等重放也不暴露终态（D8 口径同样适用）', async () => {
  const mock = await import('../src/services/mock.js');
  const key = 'idem-d15-' + Date.now();
  const created = await mock.postAnalysis({ files: [{ hash: 'h-d15' }], idem_key: key });
  // 把任务推到 done
  for (let i = 0; i < 4; i += 1) {
    // eslint-disable-next-line no-await-in-loop
    await mock.getAnalysis(created.data.task_id);
  }
  const replay = await mock.postAnalysis({ files: [{ hash: 'h-d15' }], idem_key: key });
  assert.equal(replay.data.idempotent_replay, true);
  assert.notEqual(replay.data.status, 'done', '重放不能把终态暴露给创建接口');
  assert.notEqual(replay.data.status, 'failed');
  assert.equal(replay.data.report, null);
});

await test('D16 轮询响应总是带显式 background_mode 布尔值（前端不靠猜）', async () => {
  const mock = await import('../src/services/mock.js');
  // 前面用例可能把额度用光了，重置到新用户再测
  mock.__resetForTest();
  const created = await mock.postAnalysis({ files: [{ hash: 'h-d16-' + Date.now() }] });
  assert.equal(created.ok, true, '重置后应能创建任务：' + (created.error && created.error.code));
  const r = await mock.getAnalysis(created.data.task_id);
  assert.equal(typeof r.data.background_mode, 'boolean');
});

await test('D17 服务端说在跑就不能跳后台；服务端说转后台才跳（不取「或」）', async () => {
  // 这是前端页面的判定逻辑，抽成纯函数验证：服务端字段在就严格只认它
  const decide = (serverField, elapsedMs, localMs) => {
    if (typeof serverField === 'boolean') return serverField;
    return elapsedMs >= localMs;
  };
  // 服务端明确说还在前台分析，即使本地已经过了 40 秒，也不能跳后台
  assert.equal(decide(false, 40000, 30000), false, '服务端字段在时必须只认服务端');
  // 服务端说转后台
  assert.equal(decide(true, 1000, 30000), true);
  // 服务端字段缺失时，本地 30 秒兜底生效
  assert.equal(decide(undefined, 31000, 30000), true);
  assert.equal(decide(undefined, 29000, 30000), false);
});

await test('D18 GET /plans：价格由服务端下发，带权益和 iOS 可用性', async () => {
  const mock = await import('../src/services/mock.js');
  const r = await mock.getPlans();
  assert.equal(r.ok, true);
  assert.ok(Array.isArray(r.data.plans));
  assert.equal(r.data.plans.length, 3);
  for (const p of r.data.plans) {
    assert.ok(p.plan && p.name, '套餐缺 plan/name');
    assert.equal(typeof p.amount_fen, 'number');
    assert.ok(Array.isArray(p.rights) && p.rights.length > 0, '缺权益列表');
    assert.equal(typeof p.available_on_ios, 'boolean');
  }
});

await test('D19 /me 带广告计数：today_count / remaining_today', async () => {
  const mock = await import('../src/services/mock.js');
  mock.__resetForTest();
  const before = await mock.getMe();
  assert.equal(typeof before.data.ad.today_count, 'number');
  assert.equal(typeof before.data.ad.remaining_today, 'number');
  assert.equal(before.data.ad.today_count, 0);
  assert.equal(before.data.ad.remaining_today, 5);

  await mock.postAdReward({ request_id: 'req-d19-xxxxxxxx', result: 'no_fill' });
  const after = await mock.getMe();
  assert.equal(after.data.ad.today_count, 1, '领奖后计数要跟着变');
  assert.equal(after.data.ad.remaining_today, 4);
});

await test('D20 多图上传（D9）：upload 拿 image_id → analysis 提交 image_ids', async () => {
  const mock = await import('../src/services/mock.js');
  mock.__resetForTest();
  const up1 = await mock.postAnalysisUpload({ filePath: '/tmp/a.png' });
  const up2 = await mock.postAnalysisUpload({ filePath: '/tmp/b.png' });
  assert.equal(up1.ok, true);
  assert.ok(up1.data.image_id && up1.data.hash && up1.data.expire_at);

  const created = await mock.postAnalysis({ image_ids: [up1.data.image_id, up2.data.image_id] });
  assert.equal(created.ok, true);
  assert.equal(created.data.status, 'pending');
  assert.equal(created.data.report, null);
});

await test('D21 多图上传：image_id 不存在或超过 3 张 → VALIDATION_ERROR，不扣次数', async () => {
  const mock = await import('../src/services/mock.js');
  mock.__resetForTest();
  const bad = await mock.postAnalysis({ image_ids: ['img_not_exist'] });
  assert.equal(bad.ok, false);
  assert.equal(bad.error.code, 'VALIDATION_ERROR');
  const me = await mock.getMe();
  assert.equal(me.data.quota.balance, 3, '参数错误不能扣次数');

  const ids = [];
  for (let i = 0; i < 4; i += 1) {
    // eslint-disable-next-line no-await-in-loop
    const up = await mock.postAnalysisUpload({ filePath: '/tmp/' + i + '.png' });
    ids.push(up.data.image_id);
  }
  const tooMany = await mock.postAnalysis({ image_ids: ids });
  assert.equal(tooMany.error.code, 'VALIDATION_ERROR');
  assert.ok(tooMany.error.message.includes('3'));
});

await test('D22 开关默认是 mock，mock 分支必须保留（测试依赖它）', async () => {
  const cfg = await import('../src/common/config.js');
  assert.equal(cfg.useMock(), true, '默认必须走 mock');
  assert.ok(typeof cfg.getApiBaseUrl() === 'string');
  // 真后端地址由 vite 构建期注入；Node 直接跑时没这个常量，走空串兜底
  assert.ok(typeof cfg.DEV_API_BASE_URL === 'string');
});

await test('D23 打开「使用真后端」开关后 useMock() 变 false，关掉又变回 true', async () => {
  const cfg = await import('../src/common/config.js');
  uni.setStorageSync(cfg.STORAGE_KEYS.useRealBackend, '1');
  assert.equal(cfg.useMock(), false, '开关打开后应走真后端');
  uni.setStorageSync(cfg.STORAGE_KEYS.useRealBackend, '0');
  assert.equal(cfg.useMock(), true, '开关关掉后应回到 mock');
});

await test('D24 baseURL 可覆盖，且自动去掉结尾斜杠', async () => {
  const cfg = await import('../src/common/config.js');
  uni.setStorageSync(cfg.STORAGE_KEYS.apiBase, 'http://192.168.1.5:8000/');
  assert.equal(cfg.getApiBaseUrl(), 'http://192.168.1.5:8000');
  uni.removeStorageSync(cfg.STORAGE_KEYS.apiBase);
  assert.equal(cfg.getApiBaseUrl(), cfg.DEV_API_BASE_URL, '去掉覆盖后应回到构建期注入的值');
});

await test('D25 存储键集中管理：页面代码里不再有散落的字符串键', async () => {
  const fs = await import('node:fs');
  const roots = ['../src/pages', '../src/services', '../src/platform'];
  const files = [];
  const walk = (d) => {
    for (const f of fs.readdirSync(new URL(d, import.meta.url))) {
      const u = new URL(d + '/' + f, import.meta.url);
      if (fs.statSync(u).isDirectory()) walk(d + '/' + f);
      else if (/\.(vue|js)$/.test(f)) files.push(u);
    }
  };
  roots.forEach(walk);
  const hits = [];
  const pattern = /['"]qiuzhibilei_(force_mock|mock_ad_fail|mock_start_running|mock_background|use_real_backend|api_base)['"]/;
  for (const u of files) {
    const lines = fs.readFileSync(u, 'utf8').split(/\r?\n/);
    lines.forEach((l, i) => {
      if (/^\s*\/\//.test(l)) return;
      if (pattern.test(l)) hits.push(u.pathname.split('/').pop() + ':' + (i + 1));
    });
  }
  assert.deepEqual(hits, [], '这些地方还在写死存储键，应改用 STORAGE_KEYS：' + hits.join('、'));
});

await test('E1 设备 ID：首次生成 uuid 并持久化，二次读取一致', async () => {
  const dev = await import('../src/common/deviceId.js');
  dev.__resetDeviceIdForTest();
  storage.delete('qiuzhibilei_device_id');
  const a = dev.getDeviceId();
  assert.ok(a && a.length === 36, '应是 36 位 uuid，实际：' + a);
  assert.ok(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(a), 'uuid v4 格式不对：' + a);
  assert.equal(storage.get('qiuzhibilei_device_id'), a, '应写入本地存储');
  const b = dev.getDeviceId();
  assert.equal(b, a, '二次读取应一致');
});

await test('E2 设备 ID：存储已有值就直接用，不重新生成', async () => {
  const dev = await import('../src/common/deviceId.js');
  dev.__resetDeviceIdForTest();
  storage.set('qiuzhibilei_device_id', 'saved-device-id-123');
  assert.equal(dev.getDeviceId(), 'saved-device-id-123');
});

await test('E3 设备 ID：存储不可用时不报错，返回空串（后端退回 openid+IP）', async () => {
  const dev = await import('../src/common/deviceId.js');
  dev.__resetDeviceIdForTest();
  const realGet = uni.getStorageSync;
  const realSet = uni.setStorageSync;
  // 模拟存储全部抛异常
  uni.getStorageSync = () => {
    throw new Error('storage broken');
  };
  uni.setStorageSync = () => {
    throw new Error('storage broken');
  };
  let threw = false;
  let id = '';
  try {
    id = dev.getDeviceId();
  } catch (e) {
    threw = true;
  }
  uni.getStorageSync = realGet;
  uni.setStorageSync = realSet;
  dev.__resetDeviceIdForTest();
  assert.equal(threw, false, '取不到设备 ID 时不能抛错');
  assert.equal(id, '', '取不到时应返回空串');
});

await test('E4 社区请求带 X-Device-Id，非社区请求不带', async () => {
  const fs = await import('node:fs');
  const src = fs.readFileSync(new URL('../src/services/api.js', import.meta.url), 'utf8');
  // 必须是按 /community/ 前缀判断后才加头
  assert.ok(/path\.indexOf\('\/community\/'\) === 0/.test(src), '缺少 /community/ 前缀判断');
  assert.ok(/headers\['X-Device-Id'\] = deviceId/.test(src), '没有设置 X-Device-Id 头');
  assert.ok(/if \(deviceId\)/.test(src), '设备 ID 为空时不应设置该头');
  // 不能因为缺设备 ID 就抛错
  assert.ok(!/throw new Error\(.*device/i.test(src), '不应因设备 ID 抛错');
});

// ============ 输出 ============
let pass = 0;
for (const r of results) {
  if (r.pass) pass += 1;
  console.log((r.pass ? '  ✓ ' : '  ✗ ') + r.name + (r.pass ? '' : '  → ' + r.err));
}
console.log('\n共 ' + results.length + ' 项，通过 ' + pass + ' 项，失败 ' + (results.length - pass) + ' 项');
process.exit(pass === results.length ? 0 : 1);
