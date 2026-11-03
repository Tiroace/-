// 运行环境判断：开发版 / 体验版 / 正式版。
//
// 用途（老板 2026-11-04 定）：develop（开发版）和 trial（体验版）下**不限次数、不弹
// 「次数用完」、不看广告**，方便内测同学放心测；release（正式版）照常扣次数。
//
// 取值来自 wx.getAccountInfoSync().miniProgram.envVersion，官方定义：
//   develop 开发版 / trial 体验版 / release 正式版
// 拿不到（H5、旧基础库、异常）时一律按 release 处理——**宁可多扣次数，也不能让正式版用户白嫖**。

const ENV_DEV = 'develop';
const ENV_TRIAL = 'trial';
const ENV_RELEASE = 'release';

let cached = null;

export function getEnvVersion() {
  if (cached) return cached;
  let v = ENV_RELEASE;
  try {
    const wx = globalThis.wx;
    if (wx && typeof wx.getAccountInfoSync === 'function') {
      const info = wx.getAccountInfoSync() || {};
      const mp = info.miniProgram || {};
      const raw = String(mp.envVersion || '').trim();
      if (raw === ENV_DEV || raw === ENV_TRIAL || raw === ENV_RELEASE) v = raw;
    }
  } catch (e) {
    v = ENV_RELEASE;
  }
  cached = v;
  return v;
}

// 开发版或体验版：内测环境，免次数限制
export function isUnlimitedEnv() {
  const v = getEnvVersion();
  return v === ENV_DEV || v === ENV_TRIAL;
}

// 测试用：清缓存（正式包不会用到）
export function resetEnvCache() {
  cached = null;
}
