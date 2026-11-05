// 手机认字：微信 VisionKit 静态图 OCR。
//
// ⚠️ 当前状态：**不启用**（2026-11-05 双版本令修订）。
// 双版本令第二节第 1 条：「手机认字（ocr.js）这一版不做，以后作为更新再加」。
// 规则版已改为「用户粘贴文字」，首页没有任何地方 import 这个文件，产物里搜不到
// visionKit / createVKSession（见 scripts/check-rules-build.mjs 的联网自检）。
// 文件按令保留，供以后作为更新启用；**在真机验证通过之前，不要把它当成可用能力**。
//
// 实现严格照《识别架构改造令》第三节第 2 条给出的代码写。
//
// 关键点（不要自己「优化」掉）：
// - 能力探测看 wx.createVKSession 且基础库 ≥ 2.27.0，不支持时 resolve(null)；
// - 用 createVKSession({ track: { OCR: { mode: 2 } } })，runOCR 喂 RGBA 像素；
// - 结果从 'updateAnchors' 事件拿，anchor.text 按行用 \n 拼；
// - 字段名/事件名以官方文档为准：
//   https://developers.weixin.qq.com/miniprogram/dev/framework/open-ability/visionkit/ocr.html
//   第一次真机必须把 anchors 原样打印出来确认字段；
// - updateAnchors 没触发或返回空，就当不支持处理。
//
// 启用前必须先做：真机上把 anchors 原样打印出来，确认能认出文字；
// **未验证就启用等于靠猜**。若接口不存在，按当时文档换实现，不要硬套。
//
// 用户可见文案里不出现「AI」（路线调整令 §6），统一叫「认字」。

const OCR_MIN_SDK = '2.27.0';
const DEFAULT_MAX_SIDE = 1600;
const DEFAULT_TIMEOUT = 8000;

export function isPhoneOcrSupported() {
  const wx = globalThis.wx;
  if (!wx || typeof wx.createVKSession !== 'function') return false;
  try {
    const v = wx.getAppBaseInfo ? wx.getAppBaseInfo().SDKVersion : wx.getSystemInfoSync().SDKVersion;
    return compareVersion(v, OCR_MIN_SDK) >= 0;
  } catch (e) {
    return false;
  }
}

// 别名：首页统一用这个名字判断
export const isOcrSupported = isPhoneOcrSupported;

// 返回 { text, ms } 或 null
export function phoneOcr(filePath, { maxSide = DEFAULT_MAX_SIDE, timeout = DEFAULT_TIMEOUT } = {}) {
  const wx = globalThis.wx;
  if (!wx) return Promise.resolve(null);
  const t0 = Date.now();
  return new Promise((resolve) => {
    let done = false;
    let session = null;
    const finish = (val) => {
      if (done) return;
      done = true;
      try {
        if (session) session.destroy();
      } catch (e) {
        /* destroy 失败不影响结果 */
      }
      resolve(val);
    };
    const timer = setTimeout(() => finish(null), timeout);

    wx.getImageInfo({
      src: filePath,
      success: (info) => {
        try {
          const scale = Math.min(1, maxSide / Math.max(info.width, info.height));
          const w = Math.round(info.width * scale);
          const h = Math.round(info.height * scale);
          const canvas = wx.createOffscreenCanvas({ type: '2d', width: w, height: h });
          const ctx = canvas.getContext('2d');
          const img = canvas.createImage();
          img.onload = () => {
            try {
              ctx.drawImage(img, 0, 0, w, h);
              const pixels = ctx.getImageData(0, 0, w, h).data.buffer; // RGBA

              session = wx.createVKSession({ track: { OCR: { mode: 2 } } });
              session.on('updateAnchors', (anchors) => {
                // 第一次接入时把 anchors 原样打印，确认字段名（文档写 anchor.text / anchor.box）
                const lines = (anchors || []).map((a) => a.text || '').filter(Boolean);
                clearTimeout(timer);
                finish({ text: lines.join('\n'), ms: Date.now() - t0 });
              });
              session.start((err) => {
                if (err) {
                  clearTimeout(timer);
                  return finish(null);
                }
                session.runOCR({ frameBuffer: pixels, width: w, height: h });
              });
            } catch (e) {
              clearTimeout(timer);
              finish(null);
            }
          };
          img.onerror = () => {
            clearTimeout(timer);
            finish(null);
          };
          img.src = filePath;
        } catch (e) {
          clearTimeout(timer);
          finish(null);
        }
      },
      fail: () => {
        clearTimeout(timer);
        finish(null);
      },
    });
  });
}

// 多张图：逐张识别，文字用 \n---\n 拼起来（改造令第三节第 2 条原文要求）
// 返回 { ok, text, ms, failedCount }
export async function recognizeImages(paths) {
  if (!isPhoneOcrSupported()) return { ok: false, text: '', ms: 0, failedCount: 0, reason: 'unsupported' };
  const t0 = Date.now();
  const parts = [];
  let failedCount = 0;
  const list = (paths || []).slice(0, 3);
  for (let i = 0; i < list.length; i += 1) {
    // eslint-disable-next-line no-await-in-loop
    const r = await phoneOcr(list[i]);
    if (r && r.text) parts.push(r.text);
    else failedCount += 1;
  }
  const text = parts.join('\n---\n').trim();
  return {
    ok: !!text,
    text,
    ms: Date.now() - t0,
    failedCount,
    reason: text ? '' : failedCount === list.length ? 'unsupported' : 'empty',
  };
}

function compareVersion(a, b) {
  const x = String(a).split('.');
  const y = String(b).split('.');
  for (let i = 0; i < 3; i += 1) {
    const d = parseInt(x[i] || 0, 10) - parseInt(y[i] || 0, 10);
    if (d) return d;
  }
  return 0;
}
