// B 关口联调点检：完全按前端 api.js 会发的请求形状打真后端，打印每一步的真实返回。
// 用法（在 miniprogram/ 下）：node tests/integration-probe.mjs
// 依赖：后端已起在 http://127.0.0.1:8000
const BASE = process.env.QBL_API_BASE || 'http://127.0.0.1:8000';

let token = '';
const rows = [];

function rid() {
  return 'r' + Date.now().toString(36) + Math.random().toString(36).slice(2, 10);
}

async function call(label, path, { method = 'GET', body, headers = {}, raw = false } = {}) {
  const url = BASE + path;
  const h = Object.assign({ 'X-Request-Id': rid() }, headers);
  if (token) h.Authorization = 'Bearer ' + token;
  if (body && !raw) h['content-type'] = 'application/json';

  let res;
  try {
    res = await fetch(url, { method, headers: h, body: raw ? body : body ? JSON.stringify(body) : undefined });
  } catch (e) {
    rows.push({ step: label, status: '网络失败', detail: e.message, pass: false });
    return null;
  }
  let json = null;
  try {
    json = await res.json();
  } catch (e) {
    json = null;
  }
  const ok = (json && json.ok) === true;
  const errCode = json && json.error ? json.error.code : '';
  rows.push({
    step: label,
    status: res.status + (ok ? ' ok' : ' ' + errCode),
    detail: ok ? summarize(json.data) : JSON.stringify(json && json.error ? json.error : json),
    pass: res.status < 400 && ok,
  });
  return { status: res.status, json, ok };
}

function summarize(d) {
  if (!d) return '';
  const bits = [];
  if (d.task_id) bits.push('task_id=' + d.task_id);
  if (d.status) bits.push('status=' + d.status);
  if (d.quota) bits.push('余额=' + d.quota.balance);
  if (d.report) bits.push('报告=' + d.report.risk_level + '/' + (d.report.summary || '').slice(0, 16));
  if (d.image_id) bits.push('image_id=' + d.image_id);
  if (d.granted !== undefined) bits.push('granted=' + d.granted + ' reason=' + d.reason);
  if (d.amount_fen) bits.push('金额=' + d.amount_fen + '分');
  if (d.plans) bits.push('套餐=' + d.plans.length + '档');
  if (d.items) bits.push('历史=' + d.items.length + '条');
  if (d.platform_mode) bits.push('platform_mode=' + d.platform_mode);
  return bits.join(', ');
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

// ---------- 主流程 ----------
async function main() {
  // 0. 健康检查
  await call('0. GET /health', '/health');

  // 1. 登录（前端把平台 login 的 code 原样传过来；无 AppID 时后端走 Mock 适配器）
  const login = await call('1. POST /auth/login', '/auth/login', {
    method: 'POST',
    body: { code: 'mock', platform: 'toutiao' },
  });
  if (login && login.json && login.json.ok) token = login.json.data.token;

  // 2. GET /me
  await call('2. GET /me', '/me');

  // 3. GET /plans
  await call('3. GET /plans', '/plans');

  // 4. D9 第一步：逐张上传（multipart 单图，字段名 image）
  const pngBytes = makeTinyPng();
  const ids = [];
  for (let i = 0; i < 2; i += 1) {
    const fd = new FormData();
    fd.append('image', new Blob([pngBytes], { type: 'image/png' }), 'shot' + i + '.png');
    const r = await call('4.' + (i + 1) + ' POST /analysis/upload（第 ' + (i + 1) + ' 张）', '/analysis/upload', {
      method: 'POST',
      body: fd,
      raw: true,
    });
    if (r && r.json && r.json.ok) ids.push(r.json.data.image_id);
  }

  // 5. D9 第二步：提交分析（JSON image_ids + 幂等键）
  //    注意：本机没有云 OCR，不带 ocr_text 时后端会在分析阶段返回 ANALYSIS_UNAVAILABLE（已退次数）。
  //    正式版接真 OCR 后这个旁路会删掉，所以这里分两次跑：一次纯上传（验证失败退次数），一次带 ocr_text（验证完整链路）。
  const idem = 'idem-' + Date.now();
  const created = await call('5. POST /analysis（提交 ' + ids.length + ' 个 image_id）', '/analysis', {
    method: 'POST',
    body: { image_ids: ids, idempotency_key: idem },
    headers: { 'Idempotency-Key': idem },
  });

  // 6. 轮询到终态
  let taskId = created && created.json && created.json.data ? created.json.data.task_id : '';
  if (taskId) {
    let last = null;
    for (let i = 0; i < 40; i += 1) {
      // eslint-disable-next-line no-await-in-loop
      await sleep(800);
      // eslint-disable-next-line no-await-in-loop
      const r = await call('6.' + (i + 1) + ' GET /analysis/{id}（轮询）', '/analysis/' + taskId);
      last = r && r.json && r.json.data;
      if (!last) break;
      if (last.status === 'done' || last.status === 'failed') break;
    }
    if (last && last.status === 'failed') {
      // 预期行为：本机无云 OCR，失败且次数已退回
      rows.push({
        step: '6.x 失败原因与退次数',
        status: last.error_code || 'failed',
        detail: (last.error_message || '').slice(0, 40) + '，余额已回到 ' + (last.quota ? last.quota.balance : '?'),
        pass: last.error_code === 'ANALYSIS_UNAVAILABLE' && last.report === null,
      });
    }
  }

  // 6b. 带 ocr_text 旁路再跑一次，验证能走到 done 并拿到完整报告
  const idem2 = 'idem2-' + Date.now();
  const created2 = await call('6b. POST /analysis（带 ocr_text 旁路）', '/analysis', {
    method: 'POST',
    body: {
      image_ids: ids,
      idempotency_key: idem2,
      ocr_text: '诚聘行政助理，大专以上学历，熟练使用办公软件，薪资8-12K，转正后缴纳五险一金。',
    },
    headers: { 'Idempotency-Key': idem2 },
  });
  let taskId2 = created2 && created2.json && created2.json.data ? created2.json.data.task_id : '';
  if (taskId2) {
    let last2 = null;
    for (let i = 0; i < 40; i += 1) {
      // eslint-disable-next-line no-await-in-loop
      await sleep(800);
      // eslint-disable-next-line no-await-in-loop
      const r = await call('6c.' + (i + 1) + ' 轮询（带 ocr_text）', '/analysis/' + taskId2);
      last2 = r && r.json && r.json.data;
      if (!last2) break;
      if (last2.status === 'done' || last2.status === 'failed') break;
    }
    if (last2 && last2.status === 'done' && last2.report) {
      const rep = last2.report;
      const risks = rep.risks || [];
      // 证据可追溯：只要列了风险，每条都必须带原文（§4.2 证据校验）；
      // 「较安全」的报告 risks 可能为空，这是正常的，不算失败。
      const evidenceOk = risks.every((x) => x.evidence && String(x.evidence).length > 0);
      rows.push({
        step: '6d 报告字段核对',
        status: 'done',
        detail:
          '等级=' + rep.risk_level +
          '，结论=' + rep.verdict +
          '，证据=' + risks.length + ' 条' + (risks.length ? '（全部带原文）' : '（无风险项）') +
          '，问题=' + (rep.questions_to_ask || []).length + ' 个' +
          '，model=' + (rep.model || rep.prompt_version || '?'),
        pass: evidenceOk && !!rep.risk_level && !!rep.verdict,
      });
    }
  }

  // 7. 幂等重放：同一个 Idempotency-Key 再提交一次
  await call('7. POST /analysis（幂等重放同一 key）', '/analysis', {
    method: 'POST',
    body: { image_ids: ids, idempotency_key: idem },
    headers: { 'Idempotency-Key': idem },
  });

  // 8. 历史报告
  await call('8. GET /reports', '/reports?limit=20');

  // 9. 广告领奖：result=no_fill（§6.2 兜底，必须发次数）
  await call('9. POST /ad/reward（result=no_fill 兜底）', '/ad/reward', {
    method: 'POST',
    body: { request_id: 'req-' + Date.now().toString(36) + '-a', ad_unit_id: '', result: 'no_fill' },
  });

  // 10. 广告领奖幂等：同一个 request_id 再提交
  const sameReq = 'req-' + Date.now().toString(36) + '-b';
  await call('10. POST /ad/reward（第一次）', '/ad/reward', {
    method: 'POST',
    body: { request_id: sameReq, ad_unit_id: '', result: 'completed' },
  });
  await call('10b. POST /ad/reward（同 request_id 重放）', '/ad/reward', {
    method: 'POST',
    body: { request_id: sameReq, ad_unit_id: '', result: 'completed' },
  });

  // 11. 会员下单（mock 支付，别真扣）
  const order = await call('11. POST /orders（月卡）', '/orders', {
    method: 'POST',
    body: { plan: 'month', channel: 'toutiao' },
  });
  if (order && order.json && order.json.ok) {
    const pp = order.json.data.pay_params;
    rows.push({
      step: '11b pay_params 必须是占位',
      status: pp && pp.mock === true ? 'ok' : '异常',
      detail: JSON.stringify(pp),
      pass: !!(pp && pp.mock === true),
    });
  }

  // 12. 反馈
  await call('12. POST /feedback（判断不准）', '/feedback', {
    method: 'POST',
    body: { type: 'inaccurate', report_id: '', content: '联调测试：等级判高了' },
  });

  // 输出
  console.log('');
  console.log('步骤'.padEnd(38) + '状态'.padEnd(20) + '返回摘要');
  console.log('-'.repeat(120));
  let failed = 0;
  for (const r of rows) {
    if (!r.pass) failed += 1;
    console.log(
      (r.pass ? '  ' : '✗ ') + String(r.step).padEnd(36) + String(r.status).padEnd(20) + String(r.detail || '')
    );
  }
  console.log('-'.repeat(120));
  console.log('共 ' + rows.length + ' 步，通过 ' + (rows.length - failed) + ' 步，失败 ' + failed + ' 步');
  process.exit(failed === 0 ? 0 : 1);
}

// 生成一个最小的合法 PNG（1x1），避免依赖外部图片文件
function makeTinyPng() {
  return Buffer.from(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==',
    'base64'
  );
}

main().catch((e) => {
  console.error('点检脚本异常：', e);
  process.exit(1);
});
