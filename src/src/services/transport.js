// 网络传输层（唯一出口）：决定一次请求走「微信云托管内网调用」还是普通 uni.request。
//
// 为什么不直接用 uni.request：
// - 云托管正确姿势是小程序端 wx.cloud.callContainer —— 走微信内网，不需要合法域名；
// - 云托管建议关闭公网访问，此时普通 https 请求打不到服务；
// - 平台差异（wx.*）只在 platform/ 内出现，所以这里借 platform.callContainer 转发。
//
// 配置来源（构建时注入，见 vite.config.js）：
//   VITE_CLOUD_ENV      云托管环境 ID
//   VITE_CLOUD_SERVICE  云托管服务名（如 qbl-api）
// 两者为空时回落到 uni.request + getApiBaseUrl()，行为与旧版完全一致。
import { CLOUD_ENV, CLOUD_SERVICE, getApiBaseUrl, hasCloudBackend } from '@/common/config.js';
import { callContainer } from '@/platform/index.js';
import { compressToBase64 } from '@/platform/image.js';

// 响应头统一小写，避免上层依赖平台大小写
function pickHeaders(header) {
  const out = {};
  if (!header) return out;
  Object.keys(header).forEach((k) => {
    out[k.toLowerCase()] = header[k];
  });
  return out;
}

function safeJson(s) {
  try {
    return JSON.parse(s);
  } catch (e) {
    return {};
  }
}

function normalizeBody(data) {
  if (data === '' || data === undefined || data === null) return {};
  return typeof data === 'string' ? safeJson(data) : data;
}

// POST/GET 普通 JSON 请求 → { statusCode, data, header }
// 网络层失败 reject；业务错误由调用方按 data.ok 判断。
export function httpRequest({ path, method = 'GET', data = null, header = {} }) {
  const merged = Object.assign({ 'content-type': 'application/json' }, header);

  if (hasCloudBackend()) {
    return callContainer({
      path,
      method: method || 'GET',
      data: data === null ? undefined : data,
      header: merged,
      env: CLOUD_ENV,
      service: CLOUD_SERVICE,
    }).then((res) => ({
      statusCode: res.statusCode || 200,
      data: normalizeBody(res.data),
      header: pickHeaders(res.header),
    }));
  }

  return new Promise((resolve, reject) => {
    uni.request({
      url: getApiBaseUrl() + path,
      method: method || 'GET',
      data: data === null ? undefined : data,
      header: merged,
      success: (res) =>
        resolve({ statusCode: res.statusCode, data: normalizeBody(res.data), header: pickHeaders(res.header) }),
      fail: (err) => reject(new Error((err && err.errMsg) || '网络异常')),
    });
  });
}

// 文件上传（multipart，字段名 image）——本地/公网链路用这个。
// 云托管链路不能用它（callContainer 不支持 multipart），见 httpUploadAny。
export function httpUpload({ path, filePath, name = 'image', formData = {}, header = {} }) {
  return new Promise((resolve, reject) => {
    uni.uploadFile({
      url: getApiBaseUrl() + path,
      filePath,
      name,
      formData,
      header: Object.assign({}, header),
      success: (res) => resolve({ statusCode: res.statusCode, data: normalizeBody(res.data) }),
      fail: (err) => reject(new Error((err && err.errMsg) || '上传失败')),
    });
  });
}

/**
 * 上传截图：按当前链路自动选通道，调用方只拿 { statusCode, data }。
 * - 云托管（callContainer 内网）→ 前端压缩后 POST /analysis/upload-base64（JSON）
 * - 其它（本地联调 / 未来开公网）→ 原 multipart POST /analysis/upload
 * 两条通道返回同一个 { image_id, hash, size, expires_at, safety } 封套。
 */
export async function httpUploadAny({ path, base64Path, filePath, name = 'image', formData = {}, header = {} }) {
  if (!hasCloudBackend()) {
    return httpUpload({ path, filePath, name, formData, header });
  }
  const img = await compressToBase64(filePath);
  return httpRequest({
    path: base64Path,
    method: 'POST',
    data: { image_b64: img.base64, mime: img.mime },
    header,
  });
}
