// Mock 平台实现：H5 预览、或「我的 → 开发自测」里打开「强制 Mock 平台」时使用。
// 用途：开发者工具里没有真实广告位/支付权限时，也能把业务主流程走通。
// 注意：mock 的「看完广告」是本地模拟，不产生任何广告请求，绝不能进正式包。
import { STORAGE_KEYS } from '@/common/config.js';

export default {
  login() {
    const code = 'mock-code-' + Date.now();
    return Promise.resolve({ code, anonymousCode: code });
  },
  isRewardedAdSupported() {
    return true;
  },
  // 模拟一次激励视频：850ms 后按「看完」返回；可注入失败用于测试兜底分支
  createRewardedAd() {
    let fail = false;
    try {
      fail = uni.getStorageSync(STORAGE_KEYS.mockAdFail) === '1';
    } catch (e) {
      fail = false;
    }
    return new Promise((resolve) => {
      setTimeout(() => {
        if (fail) {
          resolve({ ok: false, fallback: true, reason: 'mock-fallback' });
        } else {
          resolve({ ok: true, watched: true, fallback: false });
        }
      }, 850);
    });
  },
  destroyRewardedAd() {},
  isPaymentSupported() {
    return true;
  },
  pay() {
    return Promise.resolve({ ok: true, mock: true });
  },
};
