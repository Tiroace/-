// 功能开关（前端侧）
//
// 社区按 D14 默认关闭：后端 `QBL_FEATURE_COMMUNITY=0` 时所有 /community/* 返回 404。
// 前端策略是「入口整个隐藏」，不是显示「开发中」——所以这里不写死开关，
// 而是以「探测后端是否开放」为准，避免两边开关不一致导致露出入口却点进去 404。
import { fetchPosts, isCommunityClosed } from '@/services/api.js';

// 运行内缓存：探测一次就复用，避免每个页面都打一次接口
let cached = null;

export function getCommunityEnabledCache() {
  return cached;
}

// 探测社区是否开放
// 返回 true=开放 / false=关闭 / null=未知（网络异常等，按关闭处理更安全）
export function probeCommunity() {
  if (cached !== null) return Promise.resolve(cached);
  return fetchPosts({ sort: 'latest', limit: 1 })
    .then(() => {
      cached = true;
      return true;
    })
    .catch((err) => {
      if (isCommunityClosed(err)) {
        cached = false;
        return false;
      }
      // 其它错误（网络/未登录）先按关闭处理，不让用户看到坏页面
      return false;
    });
}

// 页面 onShow 时允许重新探测（比如后端刚打开开关）
export function resetCommunityProbe() {
  cached = null;
}
