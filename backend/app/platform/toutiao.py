"""抖音（头条）平台适配器壳。

- 登录：真实 code2session（配了 TT_APPID / TT_SECRET 才用）
- 支付：**未接**抖音虚拟支付/钻石支付，仍返回 mock 参数并标 `mock: true`
- 激励视频：广告位 ID 从 TT_AD_UNIT_ID 读，没配就是 mock 广告位

凭据走环境变量（生产走安全卡片），不要写进代码或仓库。
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

from .base import PlatformAdapter, PlatformError, SessionInfo

CODE2SESSION_URL = "https://developer.toutiao.com/api/apps/v2/jscode2session"


class ToutiaoAdapter(PlatformAdapter):
    name = "toutiao"

    def __init__(self, settings):
        super().__init__(settings)
        self.appid = settings.tt_appid
        self.secret = settings.tt_secret
        self.login_mode = "live"
        self.pay_mode = "mock"   # 虚拟支付未接入，见 docs/02

    def code2session(self, code: str) -> SessionInfo:
        payload = {"appid": self.appid, "secret": self.secret, "code": code}
        request = urllib.request.Request(
            CODE2SESSION_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=8) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise PlatformError(f"抖音 code2session 调用失败：{exc}") from exc
        # 抖音返回 {"err_no":0,"data":{"openid":...,"session_key":...}}；session_key 不落库
        if body.get("err_no") not in (0, None) or not (body.get("data") or {}).get("openid"):
            raise PlatformError(f"抖音 code2session 返回错误：{body}")
        data = body["data"]
        return SessionInfo(openid=data["openid"], unionid=data.get("unionid"), mode="live")

    def build_pay_params(self, order: dict) -> dict:
        return {
            "provider": "toutiao",
            "mode": "mock",
            "mock": True,
            "order_id": order["order_id"],
            "amount_fen": order["amount_fen"],
            "prepay_id": "mock-prepay-" + order["order_id"],
            "notice": "抖音虚拟支付未接入，此参数不可用于真实扣款",
        }

    def verify_notify(self, fields: dict, headers: dict | None = None) -> bool:
        # 真实实现要按抖音开放平台回调签名算法验；接入前一律拒绝真实回调，只认 Mock 签名
        from .mock import MockAdapter

        return MockAdapter("toutiao", self.settings).verify_notify(fields, headers)

    def ad_config(self) -> dict:
        unit_id = getattr(self.settings, "tt_ad_unit_id", "")
        if not unit_id:
            return {
                "mode": "mock",
                "enabled": True,
                "unit_id": "mock-ad-unit-toutiao",
                "daily_cap": self.settings.ad_daily_cap,
                "notice": "未配置 TT_AD_UNIT_ID，使用 mock 广告位",
            }
        return {"mode": "live", "enabled": True, "unit_id": unit_id, "daily_cap": self.settings.ad_daily_cap}
