// 设备标识：给服务端做「同一设备短时间大量投票」的风控用。
//
// 规则（Chief D18）：
// - 前端首次生成一个 uuid，持久化到本地存储，之后社区请求都带上 X-Device-Id
// - 生成失败 / 取不到时**不要报错**，直接返回空串，后端会退回用 openid+IP 判断
// - 前端不做任何拦截或提示，用户完全无感
const DEVICE_ID_KEY = 'qiuzhibilei_device_id';

// 生成 uuid v4（不依赖 crypto，小程序端兼容性最稳）
function makeUuid() {
  const hex = '0123456789abcdef';
  let s = '';
  for (let i = 0; i < 36; i += 1) {
    if (i === 8 || i === 13 || i === 18 || i === 23) {
      s += '-';
    } else if (i === 14) {
      s += '4';
    } else if (i === 19) {
      // variant 位：8/9/a/b
      s += hex[(Math.floor(Math.random() * 4) + 8) % 16];
    } else {
      s += hex[Math.floor(Math.random() * 16)];
    }
  }
  return s;
}

let cached = '';

/**
 * 取设备 ID。任何异常都静默返回空串，调用方不需要 try/catch。
 * @returns {string} uuid，取不到时为空串
 */
export function getDeviceId() {
  if (cached) return cached;
  try {
    const saved = uni.getStorageSync(DEVICE_ID_KEY);
    if (saved && typeof saved === 'string' && saved.length >= 8) {
      cached = saved;
      return cached;
    }
    const id = makeUuid();
    uni.setStorageSync(DEVICE_ID_KEY, id);
    cached = id;
    return cached;
  } catch (e) {
    // 存储不可用等情况：返回空串，后端退回 openid+IP
    return '';
  }
}

// 自测用：清掉缓存
export function __resetDeviceIdForTest() {
  cached = '';
}
