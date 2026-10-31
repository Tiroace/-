"""平台适配器接口。真实实现和 Mock 实现同一个形状，业务代码不关心背后是谁。"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass


class PlatformError(Exception):
    """平台接口调用失败（凭据错、网络错、平台返回错误码）。"""


@dataclass
class SessionInfo:
    openid: str
    unionid: str | None = None
    mode: str = "mock"          # mock / live
    raw: dict | None = None


class PlatformAdapter:
    name = "base"
    login_mode = "mock"
    pay_mode = "mock"

    def __init__(self, settings):
        self.settings = settings

    # -- 登录 ----------------------------------------------------
    def code2session(self, code: str) -> SessionInfo:
        raise NotImplementedError

    # -- 支付 ----------------------------------------------------
    def build_pay_params(self, order: dict) -> dict:
        raise NotImplementedError

    def verify_notify(self, fields: dict, headers: dict | None = None) -> bool:
        raise NotImplementedError

    # -- 激励视频 ------------------------------------------------
    def ad_config(self) -> dict:
        raise NotImplementedError

    # -- 工具 ----------------------------------------------------
    @staticmethod
    def _mock_openid(platform: str, code: str) -> str:
        return hashlib.sha256(f"{platform}:{code}".encode("utf-8")).hexdigest()[:32]
