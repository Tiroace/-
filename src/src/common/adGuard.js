// 激励视频守卫：把下派书 §6.2 的五条硬规范做成代码约束，业务页面绕不过去。
//
// 硬规范 → 代码落点：
// 1. 用户主动点按钮才创建广告请求，不预创建、不自动播放
//    → createRewardedAd 只能由 runRewardedFlow() 在点击事件里调用；模块加载时不创建任何实例。
// 2. 一个页面最多一个激励视频
//    → 每个 pageKey 同时只允许一个进行中的流程，重复点击直接拒绝。
// 3. 同一奖励不能要求连看多条广告
//    → 一次 runRewardedFlow() 只调起 1 条，结果只对应 1 次奖励，绝不循环。
// 4. 60 秒内最多调起 5 次
//    → 本地滑动窗口计数，超限直接拒绝（服务端还有一层，见 /ad/reward）。
// 5. 广告拉不出来（无填充/版本低/未配置广告位）必须直接给奖励
//    → 任何失败都返回 { grant: true, fallback: true }，业务层必须照发奖励。
//    防滥用靠服务端每日上限，不靠前端拦。
import { createRewardedAd, isRewardedAdSupported } from '@/platform/index.js';
import { getAdUnitId } from '@/common/config.js';

const PAGE_WINDOW_MS = 60 * 1000;
const MAX_IN_WINDOW = 5;

// 每个页面的调起时间戳窗口
const windowMap = new Map();
// 每个页面正在进行的流程
const runningMap = new Map();

function getWindow(pageKey) {
  const now = Date.now();
  const list = (windowMap.get(pageKey) || []).filter((t) => now - t < PAGE_WINDOW_MS);
  windowMap.set(pageKey, list);
  return list;
}

// 查询当前页面还能不能调起广告（用于按钮文案/置灰提示）
export function canTriggerAd(pageKey = 'default') {
  const list = getWindow(pageKey);
  return list.length < MAX_IN_WINDOW;
}

export function getRemainingTriggers(pageKey = 'default') {
  return Math.max(0, MAX_IN_WINDOW - getWindow(pageKey).length);
}

/**
 * 跑一次完整的激励视频流程。必须在用户点击事件里调用。
 * @param {string} pageKey 页面标识，用于「一个页面最多一个」和 60 秒频率限制
 * @returns {Promise<{
 *   granted: boolean,     // 是否应该发奖励
 *   watched: boolean,     // 是否完整看完
 *   fallback: boolean,    // 是否走了「广告拉不出来直接给」的兜底
 *   skipped: boolean,     // 用户中途关闭
 *   reason: string,       // 服务端/前端的判断依据
 *   message: string       // 给用户看的提示
 * }>}
 */
export async function runRewardedFlow(pageKey = 'default') {
  if (runningMap.get(pageKey)) {
    return {
      granted: false,
      watched: false,
      fallback: false,
      skipped: true,
      reason: 'running',
      message: '广告正在加载中，请稍等',
    };
  }

  const win = getWindow(pageKey);
  if (win.length >= MAX_IN_WINDOW) {
    // 60 秒内调起次数已达上限：不给奖励、不重复弹广告，提示稍后再试
    return {
      granted: false,
      watched: false,
      fallback: false,
      skipped: true,
      reason: 'rate-limited',
      message: '操作太频繁了，请等一会儿再试',
    };
  }

  win.push(Date.now());
  runningMap.set(pageKey, true);

  let result;
  try {
    // 没有广告位 ID / 平台不支持，都视为「拉不出来」，直接兜底给奖励
    const adUnitId = getAdUnitId();
    if (!adUnitId || !isRewardedAdSupported()) {
      result = { ok: false, watched: false, fallback: true, reason: 'no-ad' };
    } else {
      result = await createRewardedAd(adUnitId);
    }
  } catch (e) {
    result = { ok: false, watched: false, fallback: true, reason: 'exception' };
  } finally {
    runningMap.delete(pageKey);
  }

  if (result && result.watched) {
    return {
      granted: true,
      watched: true,
      fallback: false,
      skipped: false,
      reason: 'watched',
      message: '已增加 1 次',
    };
  }

  if (result && result.fallback) {
    // 平台强制要求：广告拉不出来必须发奖励，靠服务端每日上限防滥用
    return {
      granted: true,
      watched: false,
      fallback: true,
      skipped: false,
      reason: result.reason || 'fallback',
      message: '广告这次没加载出来，已直接送你 1 次',
    };
  }

  return {
    granted: false,
    watched: false,
    fallback: false,
    skipped: true,
    reason: (result && result.reason) || 'skipped',
    message: '广告没看完，没有拿到次数',
  };
}
