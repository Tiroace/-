// 抖音小程序平台实现（tt.*）。
//
// 合规要点（下派书 §6.2，逐条对照）：
// - tt.createRewardedVideoAd 只在用户点按钮之后调用，模块加载时不预创建；
// - 广告实例按广告位 ID 缓存复用，页面切换时由调用方 destroy()，保证一个页面最多一个；
// - tt.createRewardedVideoAd 本身不会预加载失败抛错，真正的「无填充/版本低」
//   表现为 .show() 的 reject 或 onError 回调 —— 两种情况都 resolve 成 fallback，
//   让业务直接发奖励（平台要求：广告拉不出来必须给奖励）。
// - 实现里用 globalThis 取运行时对象，避免业务代码出现 tt. 前缀；
//   若运行时确实没有 tt，则直接走 fallback，不报错。

/* eslint-disable no-undef */
const TT = () => (typeof globalThis !== 'undefined' ? globalThis.tt : undefined);

// 按广告位缓存实例，同一广告位只创建一次，页面 onUnload 时销毁
const adCache = new Map();

function isRewardedAdSupported() {
  const tt = TT();
  return !!(tt && typeof tt.createRewardedVideoAd === 'function');
}

function createRewardedAd(adUnitId) {
  const tt = TT();
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
    ad = tt.createRewardedVideoAd({ adUnitId });
  } catch (e) {
    return Promise.resolve({ ok: false, fallback: true, reason: 'create-failed' });
  }
  adCache.set(adUnitId, ad);
  return awaitShow(ad);
}

// 调起广告并等待结果。四种结局：
// watched  -> 用户完整看完，业务发奖励
// skipped  -> 用户中途关闭，不发奖励，也不阻塞（提示一句即可）
// fallback -> 拉不出来（无填充/版本低/未配置），业务必须直接发奖励
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
      // 抖音端 isEnded 为 true 表示看完
      if (res && (res.isEnded === true || res.isEnded === undefined)) {
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
      // 首次 show 失败通常是没预加载好：再 load 一次重试；
      // 仍然失败就是拉不出来，走兜底给奖励。
      ad.load()
        .then(() => ad.show())
        .catch(() => {
          cleanup();
          finish({ ok: false, fallback: true, reason: 'load-failed' });
        });
    });

    // 用户点关闭按钮没触发 onClose 的兜底保护：5 分钟超时按 fallback 处理，避免卡死
    setTimeout(() => {
      if (!settled) {
        cleanup();
        finish({ ok: false, fallback: true, reason: 'timeout' });
      }
    }, 5 * 60 * 1000);
  });
}

// 销毁页面上的广告实例（页面 onUnload / onHide 时调用）
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

function isPaymentSupported() {
  const tt = TT();
  return !!(tt && (typeof tt.pay === 'function' || typeof tt.requestGamePayment === 'function'));
}

function pay(orderInfo) {
  const tt = TT();
  if (!isPaymentSupported()) {
    // 抖音 iOS 虚拟支付/钻石支付能否开通待核实（下派书 §6.3），未开通直接告知不可用
    return Promise.resolve({ ok: false, reason: 'unsupported' });
  }
  return new Promise((resolve) => {
    tt.pay({
      orderInfo,
      service: 5,
      success: () => resolve({ ok: true }),
      fail: (err) => resolve({ ok: false, reason: (err && err.errMsg) || 'fail' }),
    });
  });
}

function login() {
  const tt = TT();
  if (!tt || typeof tt.login !== 'function') {
    return Promise.reject(new Error('当前环境不支持抖音登录'));
  }
  return new Promise((resolve, reject) => {
    tt.login({
      force: false,
      success: (res) => resolve({ code: res.code, anonymousCode: res.anonymousCode }),
      fail: (err) => reject(new Error((err && err.errMsg) || '抖音登录失败')),
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
