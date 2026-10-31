"""微信平台适配器壳（二期用）。

- 登录：真实 jscode2session（配了 WX_APPID / WX_SECRET 才用）
- 支付：微信支付未接入，返回 mock 参数并标 `mock: true`
- 激励视频：广告位 ID 从 WX_AD_UNIT_ID 读
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

from .base import PlatformAdapter, PlatformError, SessionInfo

CODE2SESSION_URL = "https://api.weixin.qq.com/sns/jscode2session"


class WeixinAdapter(PlatformAdapter):
    name = "weixin"

    def __init__(self, settings):
        super().__init__(settings)
        self.appid = settings.wx_appid
        self.secret = settings.wx_secret
        self.login_mode = "live"
        self.pay_mode = "mock"

    def code2session(self, code: str) -> SessionInfo:
        query = urllib.parse.urlencode(
            {"appid": self.appid, "secret": self.secret, "js_code": code, "grant_type": "authorization_code"}
        )
        try:
            with urllib.request.urlopen(f"{CODE2SESSION_URL}?{query}", timeout=8) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise PlatformError(f"微信 code2session 调用失败：{exc}") from exc
        if body.get("errcode") or not body.get("openid"):
            raise PlatformError(f"微信 code2session 返回错误：{body.get('errcode')} {body.get('errmsg')}")
        return SessionInfo(openid=body["openid"], unionid=body.get("unionid"), mode="live")

    def build_pay_params(self, order: dict) -> dict:
        return {
            "provider": "weixin",
            "mode": "mock",
            "mock": True,
            "order_id": order["order_id"],
            "amount_fen": order["amount_fen"],
            "prepay_id": "mock-prepay-" + order["order_id"],
            "notice": "微信支付未接入，此参数不可用于真实扣款",
        }

    def verify_notify(self, fields: dict, headers: dict | None = None) -> bool:
        from .mock import MockAdapter

        return MockAdapter("weixin", self.settings).verify_notify(fields, headers)

    def ad_config(self) -> dict:
        unit_id = getattr(self.settings, "wx_ad_unit_id", "")
        if not unit_id:
            return {
                "mode": "mock",
                "enabled": True,
                "unit_id": "mock-ad-unit-weixin",
                "daily_cap": self.settings.ad_daily_cap,
                "notice": "未配置 WX_AD_UNIT_ID，使用 mock 广告位",
            }
        return {"mode": "live", "enabled": True, "unit_id": unit_id, "daily_cap": self.settings.ad_daily_cap}
