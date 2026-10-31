// 登录态与用户信息：轻量单例，页面通过 ensureLogin() / getUser() 取用。
// 字段按契约 2.1/2.2：{ user_id, platform, created_at, quota:{balance}, membership, platform_mode, ad }
import { loginByCode, fetchMe, setToken, clearToken, getToken, ApiError } from './api.js';
import { login as platformLogin, currentPlatform } from '@/platform/index.js';

let userCache = null;
let loginPromise = null;

export function getUser() {
  return userCache;
}

export function setUser(user) {
  userCache = user;
}

// 便捷取余额（契约里余额只有 quota.balance 一个口径）
export function getBalance() {
  return userCache && userCache.quota ? Number(userCache.quota.balance || 0) : 0;
}

export function isMember() {
  return !!(userCache && userCache.membership && userCache.membership.active);
}

// 确保已登录：已登录直接返回缓存，未登录则走平台登录 + 换 token
// 失败时抛错，由调用方决定是提示还是静默
export function ensureLogin() {
  if (userCache && getToken()) return Promise.resolve(userCache);
  if (loginPromise) return loginPromise;

  loginPromise = platformLogin()
    .then((res) =>
      // 契约 2.1：platform 取 toutiao / weixin
      loginByCode(res.code, currentPlatform.platform === 'weixin' ? 'weixin' : 'toutiao').then(
        (data) => {
          setToken(data.token);
          userCache = {
            user_id: data.user_id,
            platform: data.platform,
            created_at: data.created_at,
            quota: data.quota,
            membership: data.membership,
            platform_mode: data.platform_mode,
            ad: data.ad,
          };
          return userCache;
        }
      )
    )
    .then((user) => {
      loginPromise = null;
      return user;
    })
    .catch((err) => {
      loginPromise = null;
      throw err;
    });

  return loginPromise;
}

// 刷新用户信息（次数、会员状态）
export function refreshUser() {
  return fetchMe().then((u) => {
    userCache = u;
    return u;
  });
}

export function logoutLocal() {
  userCache = null;
  clearToken();
}

export function isLoggedIn() {
  return !!(userCache && getToken());
}

export { ApiError };
