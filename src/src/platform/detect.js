// 平台探测：只用 uni.getSystemInfoSync 拿到的 uniPlatform / platform，不碰小程序全局对象。
// 返回值示例：{ platform: 'douyin' | 'weixin' | 'h5' | 'unknown', runtime: 'miniProgram' }
export function detectPlatform() {
  let info = {};
  try {
    info = uni.getSystemInfoSync() || {};
  } catch (e) {
    info = {};
  }
  const uniPlatform = String(info.uniPlatform || '').toLowerCase();
  const platform = String(info.platform || '').toLowerCase();

  if (uniPlatform === 'mp-toutiao') {
    return { platform: 'douyin', runtime: 'miniProgram' };
  }
  if (uniPlatform === 'mp-weixin') {
    return { platform: 'weixin', runtime: 'miniProgram' };
  }
  if (uniPlatform === 'web') {
    return { platform: 'h5', runtime: 'web' };
  }
  if (platform === 'devtools') {
    // 兜底：编译期没注入时，开发者工具里按微信处理
    return { platform: 'weixin', runtime: 'miniProgram' };
  }
  return { platform: 'unknown', runtime: 'unknown' };
}
