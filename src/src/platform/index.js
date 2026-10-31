// 平台适配层统一出口
// 约定：业务代码只从这里 import，绝不出现 tt. / wx. 直接调用。
// 三个能力：登录(login)、激励视频(rewardedAd)、支付(payment)。
import { detectPlatform } from './detect.js';
import weixin from './weixin.js';
import toutiao from './toutiao.js';
import mock from './mock.js';
import { STORAGE_KEYS } from '@/common/config.js';

const platform = detectPlatform();

// 强制 mock 的开关：开发者工具里没有真实广告位/支付权限时用。
// 打开方式：本地存储 qiuzhibilei_force_mock = '1'（「我的 → 开发自测」里有开关）
function forceMock() {
  try {
    return uni.getStorageSync(STORAGE_KEYS.forceMock) === '1';
  } catch (e) {
    return false;
  }
}

function pick() {
  // 自测注入点：只有 tests/ 下的单测会设置 __qiuzhibilei_fake_platform，
  // 小程序运行时不存在这个全局变量，走不到这一支。
  const injected =
    typeof globalThis !== 'undefined' ? globalThis.__qiuzhibilei_fake_platform : undefined;
  if (injected) return injected;
  if (forceMock()) return mock;
  if (platform.platform === 'douyin') return toutiao;
  if (platform.platform === 'weixin') return weixin;
  return mock;
}

// 当前生效的实现，放在一个转发对象里：
// 具名导出都是「函数」，内部每次调用时再取 impl.current，
// 这样即使中途切换实现，已经 import 过的模块也能拿到最新的那个。
const impl = { current: pick() };

// 供 tests/ 切换实现用（业务代码不要调用）
export function __setImplForTest(next) {
  impl.current = next || pick();
}

export const currentPlatform = platform;

// ---- 登录 ----
export const login = () => impl.current.login();

// ---- 激励视频 ----
// 设计要点（对应下派书 §6.2）：
// 1. 只在用户主动点按钮后调用 createRewardedAd()，模块加载时不预创建；
// 2. 一个页面同一时间只有一个广告流程，由 common/adGuard.js 保证；
// 3. 广告拉取失败（无填充/版本低/未配置广告位）一律 resolve 成 { fallback: true }，
//    业务层必须直接给奖励，绝不能让用户卡住。
export const isRewardedAdSupported = () => impl.current.isRewardedAdSupported();
export const createRewardedAd = (adUnitId) => impl.current.createRewardedAd(adUnitId);

// ---- 支付 ----
export const isPaymentSupported = () => impl.current.isPaymentSupported();
export const pay = (orderInfo) => impl.current.pay(orderInfo);

export default {
  currentPlatform,
  login,
  isRewardedAdSupported,
  createRewardedAd,
  isPaymentSupported,
  pay,
};
