// 手机本地认字（微信 VisionKit）：截图不上传，认字在手机上完成。
//
// 老板 2026-11-05 双版本令第二节：规则版全部在手机上跑。
// VisionKit 是微信提供的能力，接口是 wx.visionKit（基础库 3.x+，需在后台开通「VisionKit 通用识别」）。
// 这里不猜接口：先用 capability 探测，探不到就返回 unsupported，
// 由上层提示「没认出文字，换一张清楚的截图，或把微信升级到最新版」，不扣次数、不退回服务器。
//
// 用户可见文案里不能出现「AI」（路线调整令 §6），所以这里统一叫「认字」。

const MAX_SIDE = 1600;

function getWx() {
  return typeof globalThis !== 'undefined' ? globalThis.wx : undefined;
}

// 是否支持手机认字：有 VisionKit 就说支持
export function isOcrSupported() {
  const wx = getWx();
  if (!wx) return false;
  return typeof wx.visionKit !== 'undefined' && !!wx.visionKit && typeof wx.visionKit.ocr === 'function';
}

// 把 VisionKit 返回的结构压成纯文本。
// 不同基础库返回结构可能不一样（woris / words / lines），这里做兼容，
// 认不出任何结构就返回空串，让上层按「没认出字」处理，绝不猜。
export function extractText(result) {
  if (!result) return '';
  if (typeof result === 'string') return result;
  const out = [];

  // 结构一：{ woris: [{ text }] }
  if (Array.isArray(result.woris)) {
    result.woris.forEach((w) => {
      if (w && w.text) out.push(String(w.text));
    });
  }
  // 结构二：{ words: [{ text }] }
  if (!out.length && Array.isArray(result.words)) {
    result.words.forEach((w) => {
      if (w && w.text) out.push(String(w.text));
    });
  }
  // 结构三：{ lines: [{ text }] }
  if (!out.length && Array.isArray(result.lines)) {
    result.lines.forEach((l) => {
      if (l && l.text) out.push(String(l.text));
    });
  }
  // 结构四：{ result: '整段文字' }
  if (!out.length && typeof result.result === 'string') return result.result;
  // 结构五：{ text }
  if (!out.length && typeof result.text === 'string') return result.text;

  return out.join('\n');
}

// 压缩到长边 ≤1600，和改造令第二节一致（太大 VisionKit 也慢）
function compress(filePath) {
  const wx = getWx();
  return new Promise((resolve) => {
    if (!wx || typeof wx.getImageInfo !== 'function') return resolve(filePath);
    wx.getImageInfo({
      src: filePath,
      success: (info) => {
        const w = Number(info.width) || 0;
        const h = Number(info.height) || 0;
        if (!w || !h || Math.max(w, h) <= MAX_SIDE) return resolve(filePath);
        const scale = MAX_SIDE / Math.max(w, h);
        const nw = Math.round(w * scale);
        const nh = Math.round(h * scale);
        if (typeof wx.compressImage !== 'function') return resolve(filePath);
        wx.compressImage({
          src: filePath,
          quality: 85,
          compressedWidth: nw,
          compressedHeight: nh,
          success: (res) => resolve(res.tempFilePath || filePath),
          fail: () => resolve(filePath),
        });
      },
      fail: () => resolve(filePath),
    });
  });
}

// 认一张图。resolve { ok, text, reason }
// ok=false 时 reason 只有这几种：'unsupported' / 'fail' / 'empty'
function recognizeOne(filePath) {
  const wx = getWx();
  return new Promise((resolve) => {
    if (!isOcrSupported()) return resolve({ ok: false, reason: 'unsupported' });
    try {
      wx.visionKit.ocr({
        type: 'general',
        src: filePath,
        success: (res) => {
          const text = extractText(res);
          if (!String(text || '').trim()) return resolve({ ok: false, reason: 'empty' });
          resolve({ ok: true, text });
        },
        fail: () => resolve({ ok: false, reason: 'fail' }),
      });
    } catch (e) {
      resolve({ ok: false, reason: 'fail' });
    }
  });
}

// 认多张图（最多 3 张）。按顺序拼起来，保留换行，便于证据按行定位。
// 返回 { ok, text, failedCount }：
//   ok=true 表示至少认出一张有字的图；text 是拼好的全文。
export async function recognizeImages(paths) {
  if (!isOcrSupported()) return { ok: false, text: '', failedCount: 0, reason: 'unsupported' };
  const parts = [];
  let failedCount = 0;
  const list = (paths || []).slice(0, 3);
  for (let i = 0; i < list.length; i += 1) {
    // eslint-disable-next-line no-await-in-loop
    const src = await compress(list[i]);
    // eslint-disable-next-line no-await-in-loop
    const r = await recognizeOne(src);
    if (r.ok) parts.push(r.text);
    else failedCount += 1;
  }
  const text = parts.join('\n').trim();
  return { ok: !!text, text, failedCount, reason: text ? '' : 'empty' };
}
