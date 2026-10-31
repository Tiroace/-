"""鉴权、签名与脱敏。原型期用 HMAC 自签 token；生产换平台登录态 + HTTPS。"""
from __future__ import annotations

import base64
import hashlib
import hmac
import time

from engine.textnorm import mask_pii


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _sign(secret: str, payload: str) -> str:
    return _b64(hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).digest())


def issue_token(user_id: str, secret: str, ttl_seconds: int) -> str:
    exp = int(time.time()) + ttl_seconds
    payload = f"u1.{user_id}.{exp}"
    return f"{payload}.{_sign(secret, payload)}"


def verify_token(token: str, secret: str) -> str | None:
    """校验通过返回 user_id，否则返回 None。"""
    parts = (token or "").split(".")
    if len(parts) != 4:
        return None
    version, user_id, exp_raw, sig = parts
    if version != "u1" or not user_id or not all(c.isalnum() or c in "_-" for c in user_id) or not exp_raw.isdigit():
        return None
    payload = f"{version}.{user_id}.{exp_raw}"
    if not hmac.compare_digest(sig, _sign(secret, payload)):
        return None
    if int(exp_raw) < int(time.time()):
        return None
    return user_id


def sign_pay_payload(fields: dict, secret: str) -> str:
    """支付回调签名：按 key 字典序拼 k=v&... 后 HMAC-SHA256。

    真实平台用各自的签名算法（微信 v3 / 抖音开放平台），这里只固化「要验签 + 幂等」的形状。
    """
    parts = [f"{k}={fields[k]}" for k in sorted(fields) if fields[k] is not None]
    return _sign(secret, "&".join(parts))


def verify_pay_payload(fields: dict, signature: str, secret: str) -> bool:
    expected = sign_pay_payload(fields, secret)
    return hmac.compare_digest(expected, signature or "")


def constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a or "", b or "")


def safe_log_text(text: str) -> str:
    """日志一律过一遍脱敏（§8：日志里手机号/证件号不得明文）。"""
    return mask_pii(text or "")
