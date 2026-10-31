"""平台适配层：抖音 / 微信。

后端不直接散落调用平台接口，全部收敛到这里：
- 登录 code2session；
- 支付下单参数；
- 支付回调验签；
- 激励视频广告位配置。

配置驱动：没凭据一律走 MockAdapter，并在响应里标 `mode: "mock"` / `mock: true`，
前端和测试能一眼看出「这是假数据」，不会被当成真实支付/登录。
"""
from .base import PlatformAdapter, PlatformError, SessionInfo
from .mock import MockAdapter
from .weixin import WeixinAdapter
from .toutiao import ToutiaoAdapter

__all__ = ["PlatformAdapter", "PlatformError", "SessionInfo", "MockAdapter", "ToutiaoAdapter", "WeixinAdapter"]


def get_adapter(platform: str, settings) -> PlatformAdapter:
    """按平台 + 配置决定用真实适配器还是 Mock。"""
    if platform == "toutiao" and getattr(settings, "tt_appid", "") and getattr(settings, "tt_secret", ""):
        return ToutiaoAdapter(settings)
    if platform == "weixin" and getattr(settings, "wx_appid", "") and getattr(settings, "wx_secret", ""):
        return WeixinAdapter(settings)
    return MockAdapter(platform, settings)
