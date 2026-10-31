// mock 数据层：按 docs/04-后端接口契约.md 造数据。
//
// 对齐口径（2026-10-31 契约 v0.1）：
// - 响应封套 { ok, data, request_id } / { ok:false, error:{code,message,detail}, request_id }
// - 错误码用 1.4 那张表，前端按 code 分支，不按文案
// - POST /analysis 立即返回 { task_id, status:'pending', poll_after_ms }，不等结果
// - GET /analysis/{id} 轮询，状态 pending → running → done/failed
// - 报告 JSON 就是引擎 §4.3 的 schema，evidence 已是脱敏后的版本，前端不要再还原
//
// 后端联调：在「我的 → 开发自测」里打开「使用真后端」即可切走，页面代码不用动，mock 分支保留。
import { getExampleReport } from '@/common/exampleReports.js';
import { STORAGE_KEYS } from '@/common/config.js';

const MOCK_DELAY = 220;

function delay(value, ms = MOCK_DELAY) {
  return new Promise((resolve) => setTimeout(() => resolve(value), ms));
}

function rid() {
  return 'req-' + Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
}

// 成功封套
function ok(data) {
  return { ok: true, data, request_id: rid() };
}

// 失败封套（照着契约 1.4 的错误码表）
export const ERROR_CODES = {
  VALIDATION_ERROR: 400,
  UNAUTHORIZED: 401,
  FORBIDDEN: 403,
  NOT_FOUND: 404,
  QUOTA_EXHAUSTED: 402,
  IDEMPOTENCY_CONFLICT: 409,
  ORDER_NOT_FOUND: 404,
  AMOUNT_MISMATCH: 400,
  SIGNATURE_INVALID: 401,
  CONTENT_BLOCKED: 422,
  RATE_LIMITED: 429,
  PLATFORM_ERROR: 502,
  ANALYSIS_UNAVAILABLE: 503,
  ANALYSIS_FAILED: 502,
  INTERNAL_ERROR: 500,
};

function fail(code, message, detail) {
  return {
    ok: false,
    error: { code, message, detail: detail || {} },
    request_id: rid(),
  };
}

// ---------- 样例报告（复用 common/exampleReports.js —— 引擎真实输出的 v2 报告） ----------
// 之前用 sampleReports.js 的 v1 结构（risk_level/risks），已和引擎 v2（overall/dimensions/findings）不一致
const OVERALL_KEYS = ['red', 'amber', 'green', 'unknown'];

function buildReport(overallKey) {
  return getExampleReport(overallKey) || getExampleReport('red');
}

// 按图片哈希稳定分到不同 overall，演示「同样的图给同样的报告」
function pickReportId(hash) {
  const keys = OVERALL_KEYS;
  let sum = 0;
  const s = String(hash || '');
  for (let i = 0; i < s.length; i += 1) sum = (sum + s.charCodeAt(i) * (i + 1)) % 9973;
  return keys[sum % keys.length];
}

// ---------- 内存状态 ----------
const state = {
  user: null,
  tasks: {}, // task_id -> 任务
  idemKeys: {}, // Idempotency-Key -> task_id
  reports: [], // 历史报告
  adRequests: {}, // request_id -> 发放结果
  adToday: 0,
};

const AD_DAILY_CAP = 5;
const MEMBER_DAILY_LIMIT = 20;

function ensureUser() {
  if (!state.user) {
    state.user = {
      user_id: 'u_mock_0001',
      platform: 'toutiao',
      created_at: nowStr(),
      quota: { balance: 3 },
      membership: { active: false, plan: null, expires_at: null, daily_limit: null },
      platform_mode: 'mock',
    };
  }
  return state.user;
}

// 广告配置 + 今日计数（契约：/me 要补 today_count / remaining_today）
function adInfo() {
  return {
    mode: 'mock',
    enabled: true,
    unit_id: '',
    daily_cap: AD_DAILY_CAP,
    today_count: state.adToday,
    remaining_today: Math.max(0, AD_DAILY_CAP - state.adToday),
  };
}

// 契约里的时间格式：YYYY-MM-DD HH:MM:SS
function nowStr(offsetMs = 0) {
  return fmt(Date.now() + offsetMs);
}

function fmt(ms) {
  const d = new Date(ms);
  const p = (n) => (n < 10 ? '0' + n : '' + n);
  return (
    d.getFullYear() +
    '-' +
    p(d.getMonth() + 1) +
    '-' +
    p(d.getDate()) +
    ' ' +
    p(d.getHours()) +
    ':' +
    p(d.getMinutes()) +
    ':' +
    p(d.getSeconds())
  );
}

function balance() {
  return state.user ? state.user.quota.balance : 0;
}

function setBalance(v) {
  ensureUser();
  state.user.quota.balance = Math.max(0, v);
}

// ---------- 2.1 POST /auth/login ----------
export function postAuthLogin(payload) {
  const platform = (payload && payload.platform) || 'toutiao';
  const code = payload && payload.code;
  if (!code) return delay(fail('VALIDATION_ERROR', '缺少登录 code'));
  const u = ensureUser();
  u.platform = platform === 'weixin' ? 'weixin' : 'toutiao';
  const isNew = !state._loggedOnce;
  state._loggedOnce = true;
  return delay(
    ok({
      token: 'mock-token-' + Date.now().toString(36),
      user_id: u.user_id,
      platform: u.platform,
      created_at: u.created_at,
      is_new_user: isNew,
      quota: { balance: balance() },
      membership: u.membership,
      platform_mode: 'mock',
      ad: adInfo(),
    })
  );
}

// ---------- 2.2 GET /me ----------
export function getMe() {
  const u = ensureUser();
  return delay(
    ok({
      user_id: u.user_id,
      platform: u.platform,
      created_at: u.created_at,
      quota: { balance: balance() },
      membership: u.membership,
      platform_mode: 'mock',
      ad: adInfo(),
    })
  );
}

// ---------- 2.3a POST /analysis/upload（D9：multipart 单图 → image_id） ----------
// 真实环境逐张上传，拿到 image_id 列表后再提交 POST /analysis。
const uploadedImages = {};

export function postAnalysisUpload(payload) {
  ensureUser();
  const filePath = (payload && payload.filePath) || '';
  const ocrText = (payload && payload.ocr_text) || '';
  if (!filePath && !ocrText) {
    return delay(fail('VALIDATION_ERROR', '没有收到图片'));
  }
  const imageId = 'img_' + Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
  const hash = 'h-' + String(filePath || ocrText).length + '-' + Math.random().toString(36).slice(2, 8);
  uploadedImages[imageId] = { image_id: imageId, hash, ocr_text: ocrText, file_path: filePath };
  return delay(
    ok({
      image_id: imageId,
      hash,
      expire_at: nowStr(24 * 3600 * 1000),
    }),
    260
  );
}

// ---------- 2.3b POST /analysis ----------
// 创建即预扣 1 次，立即返回；状态由 getAnalysis 轮询推进。
// 契约 D8：创建响应的 status 允许 pending 或 running（真实环境后台线程可能已开跑），
// 绝不允许是 done/failed、绝不带报告。联调时可以用开关让 mock 返回 running。
export function postAnalysis(payload) {
  ensureUser();
  const files = (payload && payload.files) || [];
  const imageIds = (payload && payload.image_ids) || [];
  const ocrText = (payload && payload.ocr_text) || '';
  const idemKey = payload && payload.idem_key;

  // 两种入参都接受：image_ids（D9 正式流程）或 files（联调用）
  if (!files.length && !imageIds.length && !ocrText) {
    return delay(fail('VALIDATION_ERROR', '请至少上传 1 张截图'));
  }
  if (files.length > 3 || imageIds.length > 3) {
    return delay(fail('VALIDATION_ERROR', '一次最多上传 3 张截图'));
  }
  // image_id 不存在 → 参数错误，不扣次数
  for (const id of imageIds) {
    if (!uploadedImages[id]) {
      return delay(fail('VALIDATION_ERROR', '图片已过期或不存在，请重新上传'));
    }
  }
  // 幂等重放
  if (idemKey && state.idemKeys[idemKey]) {
    const prev = state.tasks[state.idemKeys[idemKey]];
    return delay(
      ok({
        task_id: prev.task_id,
        // 重放时按 D8 同样只给 pending/running，不把终态暴露给创建接口
        status: prev.status === 'done' || prev.status === 'failed' ? 'running' : prev.status,
        poll_after_ms: 1500,
        quota: { balance: balance() },
        dedupe_hit: false,
        idempotent_replay: true,
        report: null,
      })
    );
  }
  // 次数不足：402，不扣
  if (balance() <= 0) {
    return delay(fail('QUOTA_EXHAUSTED', '次数不足，看广告或开会员可继续', { balance: 0 }));
  }

  // 预扣
  setBalance(balance() - 1);

  // 联调用：打开后创建响应直接返回 running（模拟后台线程已经开跑）
  let startRunning = false;
  try {
    startRunning = uni.getStorageSync(STORAGE_KEYS.mockStartRunning) === '1';
  } catch (e) {
    startRunning = false;
  }

  const hash =
    imageIds.map((id) => (uploadedImages[id] ? uploadedImages[id].hash : id)).join('|') ||
    files.map((f) => f.hash || f).join('|') ||
    ocrText.slice(0, 32) ||
    'h' + Date.now();
  const reportId = pickReportId(hash);
  const taskId = 'TASK-MOCK-' + Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
  state.tasks[taskId] = {
    task_id: taskId,
    report_id: reportId,
    status: startRunning ? 'running' : 'pending',
    created_ms: Date.now(),
    started_ms: null,
    finished_ms: null,
    // 前 2 次轮询走 pending/running，第 3 次起 done（模拟真实耗时）
    polls: 0,
    duration_ms: 2600,
  };
  if (idemKey) state.idemKeys[idemKey] = taskId;

  return delay(
    ok({
      task_id: taskId,
      // D8：只允许 pending 或 running，绝不返回 done/failed，也不带报告
      status: startRunning ? 'running' : 'pending',
      poll_after_ms: 1500,
      quota: { balance: balance() },
      dedupe_hit: false,
      idempotent_replay: false,
      report: null,
    }),
    420
  );
}

// ---------- 2.4 GET /analysis/{id} ----------
export function getAnalysis(taskId) {
  const t = state.tasks[taskId];
  if (!t) return delay(fail('NOT_FOUND', '任务不存在'), 100);

  t.polls += 1;
  const elapsed = Date.now() - t.created_ms;

  if (t.status !== 'done' && t.status !== 'failed') {
    // 状态单向：pending → running → done。
    // 有的任务是创建时就已在 running（D8），那就跳过 pending 这一步。
    if (t.status === 'running') {
      if (t.polls >= 2) {
        t.status = 'done';
        t.finished_ms = Date.now();
      }
    } else if (t.polls === 1) {
      t.status = 'pending';
    } else if (t.polls === 2) {
      t.status = 'running';
      if (!t.started_ms) t.started_ms = Date.now();
    } else {
      t.status = 'done';
      t.finished_ms = Date.now();
    }
    if (t.status === 'running' && !t.started_ms) t.started_ms = Date.now();
  }

  const base = {
    task_id: taskId,
    status: t.status,
    report: null,
    error_code: null,
    error_message: null,
    duration_ms: null,
    // 一期不用大模型：model 恒为 null，版本号统一叫 rules_version
    model: null,
    rules_version: null,
    created_at: fmt(t.created_ms),
    started_at: t.started_ms ? nowStr(0) : null,
    finished_at: t.finished_ms ? nowStr(0) : null,
    elapsed_ms: elapsed,
    poll_after_ms: null,
    background_mode: false,
    quota: { balance: balance() },
  };

  if (t.status === 'done') {
    const report = buildReport(t.report_id);
    base.report = report;
    base.duration_ms = t.duration_ms;
    base.rules_version = report.rules_version || null;
    // 去重历史：同一份报告只记一次
    // v2 报告用 overall（red/amber/green/unknown）+ findings；历史列表项仍沿用 docs/04 的
    // risk_level 字段名（列表摘要），值取 overall，保持一致
    if (!state.reports.find((r) => r.report_id === report.report_id)) {
      state.reports.unshift({
        report_id: report.report_id,
        task_id: taskId,
        risk_level: report.overall,
        verdict: report.overall,
        summary: report.summary,
        risk_count: (report.findings || []).length,
        created_at: base.created_at,
        expires_at: expiresAtStr(7),
      });
    }
    return delay(ok(base), 120);
  }

  if (t.status === 'failed') {
    base.error_code = 'ANALYSIS_FAILED';
    base.error_message = '这次分析没成功，次数已经退回';
    return delay(ok(base), 120);
  }

  base.poll_after_ms = 1500;
  // 契约 3.1 第 5 条：超过 30 秒仍在跑 → background_mode=true，服务端不取消任务。
  // 这里始终给显式布尔值（不省略字段），前端据此判断是否转「后台处理中」。
  base.background_mode = elapsed > 30000;
  // 联调用：打开后让服务端判定的转后台立刻生效
  try {
    if (uni.getStorageSync(STORAGE_KEYS.mockBackground) === '1') base.background_mode = true;
  } catch (e) {
    // 忽略
  }
  return delay(ok(base), 120);
}

function expiresAtStr(days) {
  return nowStr(days * 24 * 3600 * 1000);
}

// ---------- 2.5 GET /reports ----------
export function getReports(params) {
  ensureUser();
  const limit = (params && params.limit) || 20;
  const items = state.reports.slice(0, limit);
  return delay(
    ok({
      items,
      next_cursor: null,
      quota: { balance: balance() },
    })
  );
}

// ---------- 2.6 POST /ad/reward ----------
// §6.2：completed / no_fill / error 三种结果都必须发次数，靠每日上限防滥用
export function postAdReward(payload) {
  ensureUser();
  const requestId = payload && payload.request_id;
  const result = (payload && payload.result) || 'completed';
  if (!requestId || String(requestId).length < 8) {
    return delay(fail('VALIDATION_ERROR', 'request_id 不合法'));
  }
  if (!['completed', 'no_fill', 'error'].includes(result)) {
    return delay(fail('VALIDATION_ERROR', 'result 取值不合法'));
  }
  // 幂等：同一 request_id 返回第一次结果
  if (state.adRequests[requestId]) {
    const prev = state.adRequests[requestId];
    return delay(
      ok({
        granted: prev.granted,
        replayed: true,
        reason: 'duplicate_request_id',
        quota: { balance: balance() },
        today_count: state.adToday,
        daily_cap: AD_DAILY_CAP,
        remaining_today: Math.max(0, AD_DAILY_CAP - state.adToday),
      })
    );
  }

  if (state.adToday >= AD_DAILY_CAP) {
    const res = {
      granted: false,
      replayed: false,
      reason: 'daily_cap_reached',
      quota: { balance: balance() },
      today_count: state.adToday,
      daily_cap: AD_DAILY_CAP,
      remaining_today: 0,
    };
    state.adRequests[requestId] = res;
    return delay(ok(res));
  }

  // 兜底：不管看完还是拉不出来，都 +1
  setBalance(balance() + 1);
  state.adToday += 1;
  const res = {
    granted: true,
    replayed: false,
    reason: 'reward',
    quota: { balance: balance() },
    today_count: state.adToday,
    daily_cap: AD_DAILY_CAP,
    remaining_today: Math.max(0, AD_DAILY_CAP - state.adToday),
  };
  state.adRequests[requestId] = res;
  return delay(ok(res), 320);
}

// ---------- GET /plans（只读定价，Chief 已批） ----------
// 价格由服务端定价，前端不再写死；权益与 iOS 可用性也由服务端下发。
const PLAN_RIGHTS = ['每日最多 20 次检测', '历史报告保存 30 天', '优先体验新功能'];

export const MEMBER_PLANS = [
  { plan: 'week', name: '周卡', amount_fen: 690, days: 7, recommended: false },
  { plan: 'month', name: '月卡', amount_fen: 1990, days: 30, recommended: true },
  { plan: 'quarter', name: '季卡', amount_fen: 3990, days: 90, recommended: false },
];

export function getPlans() {
  return delay(
    ok({
      plans: MEMBER_PLANS.map((p) =>
        Object.assign({}, p, {
          rights: PLAN_RIGHTS,
          // iOS 端能否购买：真实环境由服务端按平台政策下发（§6.3）
          available_on_ios: false,
          available_on_android: true,
        })
      ),
    }),
    160
  );
}

// ---------- 2.7 POST /orders ----------
export function postOrders(payload) {
  ensureUser();
  const plan = MEMBER_PLANS.find((p) => p.plan === (payload && payload.plan));
  if (!plan) return delay(fail('VALIDATION_ERROR', '套餐不存在'));
  return delay(
    ok({
      order_id: 'ORDER-MOCK-' + Date.now().toString(36),
      plan: plan.plan,
      amount_fen: plan.amount_fen,
      channel: (payload && payload.channel) || 'toutiao',
      status: 'pending',
      // 契约 2.7：原型期占位，绝对不可用于真实扣款
      pay_params: { mock: true, plan: plan.plan },
      notice: '当前为演示环境，不会产生真实扣款',
    }),
    380
  );
}

// ---------- 2.9 POST /feedback ----------
const FEEDBACK_TYPE_NAME = {
  inaccurate: '判断不准',
  appeal: '申诉',
  suggestion: '建议',
};

export function postFeedback(payload) {
  const type = (payload && payload.type) || 'suggestion';
  if (!FEEDBACK_TYPE_NAME[type]) {
    return delay(fail('VALIDATION_ERROR', '反馈类型不合法'));
  }
  const content = (payload && payload.content) || '';
  if (content.length > 1000) {
    return delay(fail('VALIDATION_ERROR', '反馈内容不能超过 1000 字'));
  }
  return delay(
    ok({
      feedback_id: 'FB-MOCK-' + Date.now().toString(36),
      type,
      type_name: FEEDBACK_TYPE_NAME[type],
      status: 'open',
      expect_reply_within_days: 7,
      created_at: nowStr(),
    }),
    320
  );
}

// 自测专用：把 mock 状态重置到新用户（额度 3、历史清空）。
// 只有 tests/ 会调用，页面代码不要用。
export function __resetForTest() {
  state.user = null;
  state.tasks = {};
  state.idemKeys = {};
  state.reports = [];
  state.adRequests = {};
  state.adToday = 0;
  state._loggedOnce = false;
  ensureUser();
}

export default {
  postAuthLogin,
  getMe,
  postAnalysisUpload,
  postAnalysis,
  getAnalysis,
  getReports,
  postAdReward,
  getPlans,
  postOrders,
  postFeedback,
  MEMBER_PLANS,
  ERROR_CODES,
};
