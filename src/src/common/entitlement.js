// 额度与会员相关的展示判断
import { MEMBER_BUY_ENABLED } from '@/common/config.js';
import { detectPlatform } from '@/platform/detect.js';

// 从系统信息里取操作系统（iOS / android / devtools）
export function getOsName() {
  try {
    const info = uni.getSystemInfoSync() || {};
    const platform = String(info.platform || '').toLowerCase();
    if (platform === 'ios') return 'ios';
    if (platform === 'android') return 'android';
    // 开发者工具下按 android 处理（便于本地验证购买流程）
    return 'android';
  } catch (e) {
    return 'android';
  }
}

// 当前端是否展示会员价格与购买按钮
// 抖音 iOS：虚拟支付能力是否开通待核实（§6.3 / T1），未开通则隐藏，iOS 用户只能看广告换次数
// 微信：二期再做，暂不开放购买
export function canBuyMember() {
  const { platform } = detectPlatform();
  const os = getOsName();
  const cfg = MEMBER_BUY_ENABLED[platform];
  if (!cfg) return false;
  return !!cfg[os];
}

// iOS 端隐藏购买入口时给出的说明
export const MEMBER_IOS_HINT =
  '当前版本暂不支持在苹果手机上购买会员，你可以继续通过看广告获取检测次数。';

// 额度是否用完（契约 2.2：余额只有 quota.balance 一个口径）
export function isQuotaEmpty(user) {
  if (!user || !user.quota) return false;
  return Number(user.quota.balance || 0) <= 0;
}
