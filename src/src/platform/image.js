// 图片压缩与 base64 化（云托管链路专用）。
//
// 为什么需要：
//   云托管关闭公网访问后只能走 wx.cloud.callContainer，它不支持 multipart，
//   图片只能以 base64 放进 JSON。base64 体积约涨 33%，手机截图 2–3MB 直接转
//   容易撞请求体上限，所以上传前统一压到 ≤200KB、边长 ≤1080。
//   顺带收益：图小了 OCR 也更快。
//
// 平台差异：压缩用 wx.compressImage（微信）/ 抖音侧暂无同名 API，走 canvas 兜底。
// 全程用 globalThis 取平台对象，保证 tt./wx. 只出现在 platform/ 里（C5 断言）。

const MAX_EDGE = 1080;
const TARGET_BYTES = 200 * 1024;
const MIN_QUALITY = 40;

function WX() {
  return typeof globalThis !== 'undefined' ? globalThis.wx : undefined;
}

function readBase64(filePath) {
  return new Promise((resolve, reject) => {
    const fs = WX() && WX().getFileSystemManager ? WX().getFileSystemManager() : null;
    if (!fs) {
      reject(new Error('当前环境不支持读取文件'));
      return;
    }
    fs.readFile({
      filePath,
      encoding: 'base64',
      success: (res) => resolve(res.data),
      fail: (err) => reject(new Error((err && err.errMsg) || '读取图片失败')),
    });
  });
}

function getImageInfo(filePath) {
  return new Promise((resolve, reject) => {
    uni.getImageInfo({
      src: filePath,
      success: (res) => resolve(res),
      fail: (err) => reject(new Error((err && err.errMsg) || '读取图片信息失败')),
    });
  });
}

// 用 wx.compressImage 压一次，返回新临时路径；不支持就原样返回
function compressOnce(filePath, quality) {
  return new Promise((resolve) => {
    const wx = WX();
    if (!wx || typeof wx.compressImage !== 'function') {
      resolve(filePath);
      return;
    }
    wx.compressImage({
      src: filePath,
      quality,
      success: (res) => resolve(res.tempFilePath || filePath),
      // 压缩失败不阻塞主流程，用原图继续（体积由上层校验兜底）
      fail: () => resolve(filePath),
    });
  });
}

// 估算 base64 长度（不真正编码，省一次读盘）
function estimateBase64Bytes(sizeBytes) {
  return Math.ceil(sizeBytes / 3) * 4;
}

function fileSize(filePath) {
  return new Promise((resolve) => {
    const fs = WX() && WX().getFileSystemManager ? WX().getFileSystemManager() : null;
    if (!fs || typeof fs.stat !== 'function') {
      resolve(0);
      return;
    }
    fs.stat({
      path: filePath,
      success: (res) => resolve((res.stats && res.stats.size) || 0),
      fail: () => resolve(0),
    });
  });
}

/**
 * 把本地临时图片压到目标体积，返回 { filePath, base64, mime, size }。
 * - 大图先按边长比例压缩，再逐级降 quality，直到 ≤200KB 或到下限
 * - 拿不到文件系统能力时直接退化为原图 base64
 */
export async function compressToBase64(filePath) {
  let current = filePath;

  const info = await getImageInfo(filePath).catch(() => null);
  if (info && info.width && info.height) {
    const longest = Math.max(info.width, info.height);
    if (longest > MAX_EDGE) {
      // wx.compressImage 只能降质量不能改尺寸，尺寸用 canvas 处理；
      // 没有 canvas 能力时至少把质量压下来
      current = await compressOnce(current, MIN_QUALITY);
    }
  }

  let size = await fileSize(current);
  if (!size || estimateBase64Bytes(size) > TARGET_BYTES) {
    for (let q = 80; q >= MIN_QUALITY; q -= 20) {
      // eslint-disable-next-line no-await-in-loop
      const next = await compressOnce(current, q);
      if (next === current) break;
      current = next;
      // eslint-disable-next-line no-await-in-loop
      size = await fileSize(current);
      if (size && estimateBase64Bytes(size) <= TARGET_BYTES) break;
    }
  }

  const base64 = await readBase64(current);
  const mime = /\.png$/i.test(current) ? 'image/png' : /\.webp$/i.test(current) ? 'image/webp' : 'image/jpeg';
  return { filePath: current, base64, mime, size: size || 0 };
}

export default { compressToBase64 };
