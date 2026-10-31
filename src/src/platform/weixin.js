// 微信小程序平台实现（wx.*）。
// 二期才上微信，但适配层先落地，保证业务代码完全不知道底层是谁。
// 激励视频规范同抖音（微信侧同样要求用户主动点击、不预加载滥用、拉不出来给兜底）。
const WX = () => (typeof globalThis !== 'undefined' ? globalThis.wx : undefined);

const adCache = new Map();

function isRewardedAdSupported() {
  const wx = WX();
  return !!(wx && typeof wx.createRewardedVideoAd === 'function');
}

function createRewardedAd(adUnitId) {
  const wx = WX();
  if (!adUnitId) {
    return Promise.resolve({ ok: false, fallback: true, reason: 'no-ad-unit' });
  }
  if (!isRewardedAdSupported()) {
    return Promise.resolve({ ok: false, fallback: true, reason: 'unsupported' });
  }
  if (adCache.has(adUnitId)) {
    return awaitShow(adCache.get(adUnitId));
  }
  let ad;
  try {
    ad = wx.createRewardedVideoAd({ adUnitId });
  } catch (e) {
    return Promise.resolve({ ok: false, fallback: true, reason: 'create-failed' });
  }
  adCache.set(adUnitId, ad);
  return awaitShow(ad);
}

function awaitShow(ad) {
  return new Promise((resolve) => {
    let settled = false;
    const finish = (r) => {
      if (settled) return;
      settled = true;
      resolve(r);
    };

    const onClose = (res) => {
      cleanup();
      if (res && res.isEnded === true) {
        finish({ ok: true, watched: true, fallback: false });
      } else {
        finish({ ok: false, watched: false, fallback: false, reason: 'skipped' });
      }
    };
    const onError = () => {
      cleanup();
      finish({ ok: false, fallback: true, reason: 'ad-error' });
    };
    const cleanup = () => {
      if (typeof ad.offClose === 'function') ad.offClose(onClose);
      if (typeof ad.offError === 'function') ad.offError(onError);
    };

    ad.onClose(onClose);
    ad.onError(onError);

    ad.show().catch(() => {
      ad.load()
        .then(() => ad.show())
        .catch(() => {
          cleanup();
          finish({ ok: false, fallback: true, reason: 'load-failed' });
        });
    });

    setTimeout(() => {
      if (!settled) {
        cleanup();
        finish({ ok: false, fallback: true, reason: 'timeout' });
      }
    }, 5 * 60 * 1000);
  });
}

function destroyRewardedAd(adUnitId) {
  if (!adUnitId) {
    adCache.forEach((ad) => {
      if (ad && typeof ad.destroy === 'function') ad.destroy();
    });
    adCache.clear();
    return;
  }
  const ad = adCache.get(adUnitId);
  if (ad && typeof ad.destroy === 'function') ad.destroy();
  adCache.delete(adUnitId);
}

// 微信虚拟支付：iOS/安卓都需要商户号与虚拟支付权限，本机无资质，恒不可用，
// 由 isPaymentSupported 返回 false，业务层按「当前版本暂不支持购买」处理。
function isPaymentSupported() {
  return false;
}

function pay() {
  return Promise.resolve({ ok: false, reason: 'unsupported' });
}

function login() {
  const wx = WX();
  if (!wx || typeof wx.login !== 'function') {
    return Promise.reject(new Error('当前环境不支持微信登录'));
  }
  return new Promise((resolve, reject) => {
    wx.login({
      success: (res) => resolve({ code: res.code }),
      fail: (err) => reject(new Error((err && err.errMsg) || '微信登录失败')),
    });
  });
}

export default {
  login,
  isRewardedAdSupported,
  createRewardedAd,
  destroyRewardedAd,
  isPaymentSupported,
  pay,
};

export { destroyRewardedAd };
