// 配置中心：环境、广告位 ID、支付开关。
// 后续真实广告位/商户参数出来后，只改这里，业务代码不动。
import { detectPlatform } from '@/platform/detect.js';

// 接口基地址（真后端）。由 vite.config.js 在构建时注入：
// - 开发构建（uni -p mp-weixin）：默认 http://127.0.0.1:8000，方便本机联调
// - 生产构建（uni build -p mp-weixin）：默认空串，产物里不会出现内网地址
// - 覆盖方式：$env:VITE_API_BASE_URL = "http://x.x.x.x:8000" 后再构建
// 运行时再用本地存储 qiuzhibilei_api_base 覆盖（「开发自测」页）。
/* global __QBL_API_BASE_URL__ */
export const DEV_API_BASE_URL =
  typeof __QBL_API_BASE_URL__ !== 'undefined' ? __QBL_API_BASE_URL__ : '';

// 接口基地址的默认值：mock 模式下为空（不走网络）
export const API_BASE_URL = '';

// ---- 运行时开关（不重新编译就能切），都落在本地存储里 ----
// 用法：开发者工具里打开「我的 → 开发自测」页面切换
export const STORAGE_KEYS = {
  // '1' = 用真后端；其它/空 = 用 mock
  useRealBackend: 'qiuzhibilei_use_real_backend',
  // 真后端的 baseURL，默认为 DEV_API_BASE_URL
  apiBase: 'qiuzhibilei_api_base',
  // 强制 mock 平台（广告/支付不真正调起）
  forceMock: 'qiuzhibilei_force_mock',
  // mock 广告返回「拉不出来」，用来测兜底分支
  mockAdFail: 'qiuzhibilei_mock_ad_fail',
  // mock 创建分析直接返回 running（测 D8）
  mockStartRunning: 'qiuzhibilei_mock_start_running',
  // mock 轮询强制返回 background_mode=true
  mockBackground: 'qiuzhibilei_mock_background',
  // mock 报告结论强制指定：red/amber/green/unknown，其余值一律忽略（提审截图用）
  mockForceOverall: 'qiuzhibilei_mock_force_overall',
};

function readStorage(key) {
  try {
    return uni.getStorageSync(key);
  } catch (e) {
    return '';
  }
}

// 是否使用 mock 数据层：默认 true，保留 mock 分支（测试依赖它）。
// 真后端联调时通过「开发自测」页或本地存储切过去。
//
// 安全（改动清单 1 · 约束 4）：mock 专用开关写在本地存储里，会跟着设备走。
// 正式模式（useRealBackend=1）下主动清掉「强制报告结论」开关，
// 保证设备上不残留一个能人为指定「这份报告没有风险」的键。
// 切回 mock 后重新布防，下次再进正式模式仍会清理。
let mockForceOverallCleared = false;
export function useMock() {
  if (readStorage(STORAGE_KEYS.useRealBackend) === '1') {
    if (!mockForceOverallCleared) {
      try {
        uni.removeStorageSync(STORAGE_KEYS.mockForceOverall);
      } catch (e) {
        // 存储不可用时忽略：正式模式本来就不读这个键
      }
      mockForceOverallCleared = true;
    }
    return false;
  }
  mockForceOverallCleared = false;
  return true;
}

// 当前生效的接口基地址
export function getApiBaseUrl() {
  const custom = readStorage(STORAGE_KEYS.apiBase);
  return String(custom || DEV_API_BASE_URL || '').replace(/\/+$/, '');
}

// 兼容旧写法：静态常量已废弃，请改用 useMock() / getApiBaseUrl()
export const USE_MOCK = true;

// 激励视频广告位 ID（待老板/平台后台开通后填）。
// 未配置时，业务层按「广告拉不出来」处理，直接给次数兜底 —— 这是平台强制要求。
export const AD_UNIT_IDS = {
  douyin: '',
  weixin: '',
};

export function getAdUnitId() {
  const { platform } = detectPlatform();
  if (platform === 'douyin') return AD_UNIT_IDS.douyin || '';
  if (platform === 'weixin') return AD_UNIT_IDS.weixin || '';
  return '';
}

// 会员是否在客户端展示可购买。
// 抖音 iOS 虚拟支付能力能否开通待核实（下派书 §6.3/T1），未开通前 iOS 隐藏价格与购买入口。
// 注意：微信侧规则还在核实，先别改这三处（会员 iOS 开关、隐私保护指引、服务说明入口）。
export const MEMBER_BUY_ENABLED = {
  douyin: { ios: false, android: true },
  weixin: { ios: false, android: false },
  h5: { ios: true, android: true },
};

// 额度规则展示用（真实规则以服务端为准，这里只用于文案）
export const QUOTA_RULES = {
  newUserFree: 3,
  adDailyLimit: 5,
  memberDailyLimit: 20,
};

// 报告保存期限（文案用）
export const REPORT_TTL = {
  normal: 7,
  member: 30,
};
