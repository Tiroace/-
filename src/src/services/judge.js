// 截图直发 DeepSeek 识图：一次调用完成「认出文字 + 判断套路」。
//
// 关键约束（改造令 §〇）：
// - 截图压缩后以 base64 放进 image_url，最多 3 张；
// - 不走 callContainer，直接 uni.request 到 api.deepseek.com（后台已加 request 合法域名）；
// - 要求模型把截图文字完整抄进 text，前端用 text 校验 evidence，找不到就丢；
// - 失败一律抛出，由上层静默退回服务器流程。
import { DEEPSEEK_KEY, DEEPSEEK_URL, DEEPSEEK_MODEL, DEEPSEEK_TIMEOUT } from '@/common/config.js';
import { PATTERNS, PATTERN_IDS } from '@/common/patterns.js';

// 模型只能从这里选编号；实测模型会自己编不存在的编号（如 P-BAIT-01），所以：
// 1) prompt 里给精确清单 + 明说「不许编」；2) 返回后用 PATTERN_IDS 白名单过滤。
function buildSystemPrompt() {
  const list = PATTERNS.map((p) => `${p.pattern_id}｜${p.name}｜${p.why || ''}`).join('\n');
  return [
    '你是招聘信息风险筛查器。用户给你 1-3 张招聘截图。',
    '第一步：把截图里的全部文字完整、原样抄进 text 字段，保留换行，不要概括、不要删减。',
    '第二步：判断这段文字是不是招聘信息或和 HR 的聊天；不是就 is_job_posting=false，hits 为空。',
    '第三步：从下面的套路清单里找出命中的编号。',
    '',
    '套路清单（只能从这里选，不在清单里的编号一律不许用，不许自己编造）：',
    list,
    '',
    '规则：',
    '1. 每条命中必须给 evidence：从 text 里原样复制一句（不超过 60 字），一个字都不能改。',
    '2. 没把握的不要选；没有命中就返回空数组。',
    '3. 正常薪资范围（例如「7000-8000元」「月薪 6000 元」）不是套路，不要因为出现薪资区间就命中。',
    '4. 正常公司信息（公司名称、地址、五险一金）不是套路。',
    '5. 只输出 JSON，不要任何解释：',
    '{"is_job_posting": true, "text": "截图里的全部文字", "hits": [{"pattern_id": "P-XXX", "evidence": "原文"}]}',
  ].join('\n');
}

// 图片压缩：长边 ≤ 1600、JPEG 质量 80，控制 base64 体积（≤500KB 量级）
function compressImage(filePath, maxSide = 1600, quality = 80) {
  const wx = globalThis.wx;
  if (!wx) return Promise.resolve({ ok: false, reason: 'no-wx' });
  return new Promise((resolve) => {
    wx.getImageInfo({
      src: filePath,
      success: (info) => {
        const scale = Math.min(1, maxSide / Math.max(info.width, info.height));
        const w = Math.round(info.width * scale);
        const h = Math.round(info.height * scale);
        try {
          const canvas = wx.createOffscreenCanvas({ type: '2d', width: w, height: h });
          const ctx = canvas.getContext('2d');
          const img = canvas.createImage();
          img.onload = () => {
            try {
              ctx.drawImage(img, 0, 0, w, h);
              const compressed = wx.canvasToTempFilePath
                ? null
                : null;
              // 小程序里用 canvas 取 base64 更稳的是 canvas.toDataURL；不支持时退回原图
              if (typeof canvas.toDataURL === 'function') {
                const dataUrl = canvas.toDataURL('image/jpeg', quality / 100);
                resolve({ ok: true, base64: String(dataUrl).split(',')[1] || '', width: w, height: h });
                return;
              }
              resolve({ ok: false, reason: 'no-toDataURL' });
            } catch (e) {
              resolve({ ok: false, reason: 'draw-failed' });
            }
          };
          img.onerror = () => resolve({ ok: false, reason: 'img-error' });
          img.src = filePath;
        } catch (e) {
          resolve({ ok: false, reason: 'canvas-failed' });
        }
      },
      fail: () => resolve({ ok: false, reason: 'info-failed' }),
    });
  });
}

// 读原图 base64（压缩失败时的兜底：优先保证能跑通，体积由调用方限制）
function readAsBase64(filePath) {
  const wx = globalThis.wx;
  return new Promise((resolve) => {
    if (!wx || typeof wx.getFileSystemManager !== 'function') return resolve(null);
    try {
      wx.getFileSystemManager().readFile({
        filePath,
        encoding: 'base64',
        success: (res) => resolve(res.data || null),
        fail: () => resolve(null),
      });
    } catch (e) {
      resolve(null);
    }
  });
}

export async function toBase64(filePath) {
  const c = await compressImage(filePath);
  if (c.ok && c.base64) return c.base64;
  return readAsBase64(filePath);
}

export function isVisionJudgeAvailable() {
  return !!DEEPSEEK_KEY;
}

// 调 DeepSeek：images 是 base64 数组（1-3 张）
export function judgeImages(images, { timeout = DEEPSEEK_TIMEOUT } = {}) {
  return new Promise((resolve, reject) => {
    if (!DEEPSEEK_KEY) return reject(new Error('NO_KEY'));
    if (!images || !images.length) return reject(new Error('NO_IMAGE'));

    const content = [{ type: 'text', text: '请识别并判断这些招聘截图。' }];
    images.slice(0, 3).forEach((b64) => {
      content.push({ type: 'image_url', image_url: { url: 'data:image/jpeg;base64,' + b64 } });
    });

    uni.request({
      url: DEEPSEEK_URL,
      method: 'POST',
      timeout,
      header: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + DEEPSEEK_KEY },
      data: {
        model: DEEPSEEK_MODEL,
        temperature: 0,
        max_tokens: 2000,
        response_format: { type: 'json_object' },
        // 关掉思考模式：实测 8-11 秒降到 2.4-2.7 秒，抄录与判断结果一致
        thinking: { type: 'disabled' },
        messages: [
          { role: 'system', content: buildSystemPrompt() },
          { role: 'user', content },
        ],
      },
      success: (res) => {
        if (res.statusCode !== 200) {
          // 402 余额不足、401 密钥失效等：都交给上层退回旧流程
          return reject(new Error('HTTP_' + res.statusCode));
        }
        try {
          const body = res.data || {};
          const choice = (body.choices || [])[0] || {};
          const msg = choice.message || {};
          const out = JSON.parse(msg.content || '{}');
          resolve({ raw: out, usage: body.usage || null });
        } catch (e) {
          reject(new Error('BAD_JSON'));
        }
      },
      fail: (err) => reject(new Error((err && err.errMsg) || 'NETWORK')),
    });
  });
}

// 前端校验：编号必须在白名单里；证据必须在模型抄录的 text 里（去空白后）逐字找到
export function validateHits(raw, text) {
  const norm = (s) => String(s || '').replace(/\s+/g, '');
  const body = norm(text);
  const seen = new Set();
  const hits = raw && Array.isArray(raw.hits) ? raw.hits : [];
  return hits
    .filter((h) => h && PATTERN_IDS.has(h.pattern_id) && h.evidence && body && body.includes(norm(h.evidence)))
    .filter((h) => (seen.has(h.pattern_id) ? false : (seen.add(h.pattern_id), true)));
}
