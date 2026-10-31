"""Mock 平台适配器：没有 AppID/Secret 时的唯一可用实现。

所有对外响应都会带 `mode: "mock"` / `mock: true`，避免被误当成真实登录/支付。
"""
from __future__ import annotations

from ..security import sign_pay_payload, verify_pay_payload
from .base import PlatformAdapter, SessionInfo

PAY_FIELDS = ("order_id", "platform_order_id", "amount_fen", "status")


class MockAdapter(PlatformAdapter):
    name = "mock"

    def __init__(self, platform: str, settings):
        super().__init__(settings)
        self.platform = platform
        self.name = f"mock-{platform}"
        self.login_mode = "mock"
        self.pay_mode = "mock"

    def code2session(self, code: str) -> SessionInfo:
        return SessionInfo(openid=self._mock_openid(self.platform, code), mode="mock", raw={"mock": True})

    def build_pay_params(self, order: dict) -> dict:
        return {
            "provider": self.platform,
            "mode": "mock",
            "mock": True,
            "order_id": order["order_id"],
            "amount_fen": order["amount_fen"],
            "prepay_id": "mock-prepay-" + order["order_id"],
            "notice": "未接入真实支付，此参数不可用于发起真实扣款",
        }

    def verify_notify(self, fields: dict, headers: dict | None = None) -> bool:
        signature = fields.get("signature") or ""
        canonical = {k: fields.get(k) for k in PAY_FIELDS}
        return verify_pay_payload(canonical, signature, self.settings.pay_secret)

    def ad_config(self) -> dict:
        return {
            "mode": "mock",
            "enabled": True,
            "unit_id": f"mock-ad-unit-{self.platform}",
            "daily_cap": self.settings.ad_daily_cap,
            "notice": "mock 广告位：前端不得据此发起真实广告请求",
        }

    def sign(self, fields: dict) -> str:
        """自测用：按 Mock 规则签一份回调。"""
        canonical = {k: fields.get(k) for k in PAY_FIELDS}
        return sign_pay_payload(canonical, self.settings.pay_secret)
