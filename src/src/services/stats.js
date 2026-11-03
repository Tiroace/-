// 匿名统计上报（老板 2026-11-04 定）：只报「命中了哪些套路 + 整体套路 + 红黄绿」。
//
// 隐私底线（写进隐私政策）：
// - **不带文字、不带截图、不带用户身份**（不带 token、不带设备号、不带 openid）；
// - 只是计数，用于首页「最近常见的」Top 5；
// - 失败一律静默，绝不影响用户看报告。
//
// 走独立的 uni.request（不用 services/api.js 的 request，因为那个会带 Authorization 头）。

import { API_BASE_URL, hasCloudBackend } from '@/common/config.js';

const PATH = '/stats/pattern';

function endpoint() {
  // 云托管环境没有公网域名，统计用普通 HTTP 也不通；直接跳过，不阻塞
  const base = String(API_BASE_URL || '').replace(/\/$/, '');
  if (!base) return '';
  return base + PATH;
}

export function reportStats(overall, { patternIds = [], schemeId = '' } = {}) {
  const url = endpoint();
  if (!url) return Promise.resolve(false);
  // 只要结论是红/黄/绿才报；unknown 没有信息量
  if (!['red', 'amber', 'green'].includes(overall)) return Promise.resolve(false);
  const payload = {
    overall,
    pattern_ids: (patternIds || []).slice(0, 12),
    scheme_id: schemeId || '',
  };
  return new Promise((resolve) => {
    try {
      uni.request({
        url,
        method: 'POST',
        timeout: 5000,
        header: { 'Content-Type': 'application/json' },
        data: payload,
        success: () => resolve(true),
        fail: () => resolve(false),
      });
    } catch (e) {
      resolve(false);
    }
  });
}

export function statsEnabled() {
  return !!endpoint();
}
