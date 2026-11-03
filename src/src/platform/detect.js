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
  // 再接一层真实运行时判断：uni 的 uniPlatform 在个别基础库/构建组合下可能为空，
  // 这时用 wx / tt 全局对象兜底，避免误判成 unknown（「我的」页会显示成「用户」）
  const g = typeof globalThis !== 'undefined' ? globalThis : {};
  if (g.wx) {
    // 微信小程序有 wx，抖音有 tt；两者不会同时存在
    return { platform: 'weixin', runtime: 'miniProgram' };
  }
  if (g.tt) {
    return { platform: 'douyin', runtime: 'miniProgram' };
  }
  return { platform: 'unknown', runtime: 'unknown' };
}

// 平台兜底文案（拿不到昵称时用），各页面共用。
// 原来「我的」页把兜底写死成「抖音用户」，微信版里也显示抖音，是明确 bug。
export const PLATFORM_LABELS = {
  weixin: '微信用户',
  douyin: '抖音用户',
  h5: '用户',
  unknown: '用户',
};
