"""微信内容安全适配器：文本 msgSecCheck + 图片 mediaCheckAsync。

官方文档：
- 文本：POST https://api.weixin.qq.com/wxa/msg_sec_check?access_token=ACCESS_TOKEN
        body {content, version:2, scene:1, openid}
        errcode 0 且 result.suggest 为 pass/review/risky
- 图片：POST https://api.weixin.qq.com/wxa/media_check_async?access_token=ACCESS_TOKEN
        body {media_url, media_type:2, version:2, scene:1, openid}
        **异步**：只回 trace_id，结果要等服务端回调（或之后查询）。

设计要点（对应第 2 关要求「带开关与失败降级：接口不可用时不阻塞主流程但记录」）：
- 开关：QBL_CONTENT_SAFETY=wechat 才启用真实接口；默认 auto（配置了 AppID/Secret 才用）
- 失败降级：网络错误 / 无 access_token / 接口 5xx / 未配置 → passed=True 但 code=degraded，
  **不阻塞**用户上传，同时把原因写进结果 meta，由调用方落日志
- 图片异步：默认只做「已提交检测」标记（pending），不假装同步拿到结果；
  本地已有的规则粗检仍然照跑（张数/大小/格式），两者叠加
"""
from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from .content_safety import ContentSafetyAdapter, SafetyResult, TextSafetyResult

logger = logging.getLogger("qbl.content_safety")

TOKEN_URL = "https://api.weixin.qq.com/cgi-bin/token"
MSG_SEC_URL = "https://api.weixin.qq.com/wxa/msg_sec_check"
MEDIA_SEC_URL = "https://api.weixin.qq.com/wxa/media_check_async"

# msgSecCheck 的 result.suggest 取值
SUGGEST_PASS = "pass"
SUGGEST_REVIEW = "review"
SUGGEST_RISKY = "risky"


class WechatApiError(RuntimeError):
    """调用微信接口失败（网络、返回错误码等）。"""


class AccessTokenCache:
    """access_token 缓存：微信给的有效期 7200 秒，这里提前 5 分钟过期重取。

    注意：access_token 是全局唯一的，多进程/多实例会互相顶掉。
    云托管单实例内用进程缓存够用；多实例部署要换成集中存储（Redis）。
    """

    def __init__(self, appid: str, secret: str, refresh_ahead: int = 300, timeout: float = 8.0):
        self.appid = appid
        self.secret = secret
        self.refresh_ahead = refresh_ahead
        self.timeout = timeout
        self._token = ""
        self._expires_at = 0.0

    def get(self) -> str:
        if self._token and time.time() < self._expires_at:
            return self._token
        if not self.appid or not self.secret:
            raise WechatApiError("未配置 QBL_WX_APPID / QBL_WX_SECRET")
        query = urllib.parse.urlencode(
            {"grant_type": "client_credential", "appid": self.appid, "secret": self.secret}
        )
        try:
            with urllib.request.urlopen(f"{TOKEN_URL}?{query}", timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise WechatApiError(f"获取 access_token 失败：{type(exc).__name__}") from exc
        if data.get("errcode"):
            raise WechatApiError(f"获取 access_token 被拒：{data.get('errcode')} {data.get('errmsg')}")
        self._token = str(data.get("access_token") or "")
        if not self._token:
            raise WechatApiError("获取 access_token 返回为空")
        ttl = int(data.get("expires_in") or 7200)
        self._expires_at = time.time() + max(60, ttl - self.refresh_ahead)
        return self._token


def _post_json(url: str, payload: dict, timeout: float = 8.0) -> dict:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise WechatApiError(f"请求 {url} 失败：{type(exc).__name__}") from exc


@dataclass
class TextCheck(TextSafetyResult):
    """微信 msgSecCheck 的文本结论。degraded 等字段继承基类，这里只补 label 与原始响应。"""

    label: int = 0
    raw: dict = field(default_factory=dict)


class WechatContentSafety(ContentSafetyAdapter):
    """接微信真实内容安全的适配器。"""

    name = "wechat"

    def __init__(
        self,
        appid: str,
        secret: str,
        openid: str = "",
        scene: int = 1,
        timeout: float = 8.0,
        token_cache: AccessTokenCache | None = None,
        media_url_builder=None,
    ):
        self.appid = appid
        self.secret = secret
        self.openid = openid
        self.scene = scene
        self.timeout = timeout
        self.tokens = token_cache or AccessTokenCache(appid, secret, timeout=timeout)
        self.media_url_builder = media_url_builder

    # ---------------- 文本 ----------------
    def check_text(self, content: str) -> TextCheck:
        """msgSecCheck 同步检测文本。

        调用失败（网络/未配置/限频）一律降级为 degraded=True + 放行，
        由调用方记录日志——宁可不拦，也不能因为接口抖动让用户传不了截图上。
        **本方法保证不抛异常**（覆盖 ContentSafetyAdapter.check_text 的契约）。
        """
        try:
            return self._check_text(content)
        except Exception as exc:  # noqa: BLE001
            logger.warning("内容安全调用异常，已降级放行：%s", exc)
            return TextCheck(
                suggest=SUGGEST_PASS, code="degraded", degraded=True, reason=f"调用异常：{type(exc).__name__}"
            )

    def _check_text(self, content: str) -> TextCheck:
        content = (content or "").strip()
        if not content:
            return TextCheck(suggest=SUGGEST_PASS, reason="空文本，跳过")
        try:
            token = self.tokens.get()
            url = f"{MSG_SEC_URL}?access_token={urllib.parse.quote(token)}"
            payload = {"content": content[:2500], "version": 2, "scene": self.scene}
            if self.openid:
                payload["openid"] = self.openid
            data = _post_json(url, payload, timeout=self.timeout)
        except WechatApiError as exc:
            return TextCheck(suggest=SUGGEST_PASS, code="degraded", degraded=True, reason=str(exc))
        errcode = int(data.get("errcode") or 0)
        if errcode != 0:
            return TextCheck(
                suggest=SUGGEST_PASS,
                code="degraded",
                degraded=True,
                reason=f"msgSecCheck 返回错误码 {errcode} {data.get('errmsg')}",
                raw=data,
            )
        result = data.get("result") or {}
        return TextCheck(
            suggest=str(result.get("suggest") or "").lower(),
            label=int(result.get("label") or 0),
            raw=data,
        )

    # ---------------- 图片 ----------------
    def check(self, images: list[Path]) -> SafetyResult:
        """图片走 mediaCheckAsync（异步）。

        这里只负责「提交检测 + 记录 trace_id」，不等回调——同步拿不到结果，
        假装拿到就是自欺欺人。真正判定由回调/后续查询完成。
        """
        if not images:
            return SafetyResult(True, "pass", "", {"engine": self.name, "images": 0})
        if not self.media_url_builder:
            return SafetyResult(
                True,
                "degraded",
                "图片内容安全需要可公网访问的 URL，未配置 media_url_builder，跳过图片检测",
                {"engine": self.name},
            )
        submitted, degraded_reason = [], ""
        try:
            token = self.tokens.get()
        except WechatApiError as exc:
            return SafetyResult(True, "degraded", f"无法获取 access_token：{exc}", {"engine": self.name})
        for p in images:
            url = self.media_url_builder(p)
            if not url:
                degraded_reason = f"图片 {p.name} 没有公网 URL，跳过"
                continue
            payload = {"media_url": url, "media_type": 2, "version": 2, "scene": self.scene}
            if self.openid:
                payload["openid"] = self.openid
            try:
                data = _post_json(f"{MEDIA_SEC_URL}?access_token={urllib.parse.quote(token)}", payload, self.timeout)
            except WechatApiError as exc:
                degraded_reason = str(exc)
                continue
            if int(data.get("errcode") or 0) != 0:
                degraded_reason = f"mediaCheckAsync 错误码 {data.get('errcode')} {data.get('errmsg')}"
                continue
            submitted.append({"file": p.name, "trace_id": data.get("trace_id")})
        if not submitted:
            return SafetyResult(
                True, "degraded", degraded_reason or "图片检测未提交", {"engine": self.name}
            )
        return SafetyResult(
            passed=True,
            code="pending",
            reason="图片已提交异步检测，结果见 trace_id",
            meta={"engine": self.name, "submitted": submitted},
        )
