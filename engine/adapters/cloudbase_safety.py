"""微信云托管「开放接口服务 / 云调用」令牌适配器：免 AppSecret 调内容安全。

官方依据（已核对原文，2026-11-03）：
https://developers.weixin.qq.com/miniprogram/dev/wxcloudservice/wxcloudrun/src/guide/weixin/token.html

关键事实（原文摘录）：
1. 云调用是「免鉴权调用微信开放服务接口」的能力，「免鉴权，也就是免密钥，全程不暴漏任何信息，
   开发者无需维护 access_token」。
2. 云托管不限定语言、没有各语言 SDK，**云开发的 wx-server-sdk 云调用在云托管走不通**，
   云托管走的是自己的「开放接口服务」+ 微信令牌。
3. 微信后台周期性把 access_token **推送到容器实例**，挂载路径
   `/.tencentcloudbase/wx/cloudbase_access_token`；推送间隔 10 分钟，有效期 30 分钟，
   同环境所有实例的令牌相同。
4. 调用时把令牌放在 **`cloudbase_access_token`** 查询参数上（不是 access_token）：
   `https://api.weixin.qq.com/wxa/msg_sec_check?cloudbase_access_token=TOKEN`
5. **必须先配置接口白名单**：控制台 → 微信云托管 → 云调用 / 微信令牌配置，
   填接口路径（`api.weixin.qq.com` 之后、`?` 之前的部分，例如 `/wxa/msg_sec_check`）。
   「不在白名单中的接口不允许使用微信令牌」——不配就报 `API unauthorized`。
6. 配置是**环境维度**的，不同环境各配各的。
7. 资源复用/服务商场景要拼 `appid@token`（本项目单主体，不需要）。

结论：**内容安全可以免 AppSecret**，前提是：
  a) 部署在微信云托管（令牌由平台推送，本地/别的云没有这个文件）；
  b) 在控制台把 `/wxa/msg_sec_check`（和图片用的接口路径）加进白名单。
本地开发没有令牌文件，自动回落到 AppSecret 或降级放行。
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from .content_safety import ContentSafetyAdapter, SafetyResult, TextSafetyResult

logger = logging.getLogger("qbl.content_safety")

# 官方文档给的挂载路径
CLOUDBASE_TOKEN_PATH = Path("/.tencentcloudbase/wx/cloudbase_access_token")
MSG_SEC_URL = "https://api.weixin.qq.com/wxa/msg_sec_check"
MEDIA_SEC_URL = "https://api.weixin.qq.com/wxa/media_check_async"

SUGGEST_PASS = "pass"


def read_cloudbase_token(path: Path | None = None) -> str:
    """读云托管推送的令牌；读不到返回空串（本地开发/非云托管环境）。"""
    token_path = path or CLOUDBASE_TOKEN_PATH
    try:
        if token_path.is_file():
            return token_path.read_text(encoding="utf-8").strip()
    except OSError as exc:  # 权限/IO 问题不该影响主流程
        logger.warning("读取云托管令牌失败（%s）：%s", token_path, exc)
    return ""


def _post_json(url: str, payload: dict, timeout: float = 8.0) -> dict:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"请求 {url} 失败：{type(exc).__name__}") from exc


@dataclass
class CloudCallResult:
    ok: bool
    data: dict
    degraded: bool = False
    reason: str = ""


class CloudbaseTokenSafety(ContentSafetyAdapter):
    """用云托管令牌（cloudbase_access_token）调内容安全，免 AppSecret。"""

    name = "cloudbase-token"

    def __init__(self, timeout: float = 8.0, token_reader=None, openid: str = "", scene: int = 1):
        self.timeout = timeout
        self.token_reader = token_reader or read_cloudbase_token
        self.openid = openid
        self.scene = scene

    def _call(self, api_path: str, payload: dict) -> CloudCallResult:
        token = (self.token_reader() or "").strip()
        if not token:
            return CloudCallResult(
                ok=False,
                data={},
                degraded=True,
                reason="未找到云托管令牌 /" + str(CLOUDBASE_TOKEN_PATH) + "（非云托管环境或未挂载）",
            )
        url = f"https://api.weixin.qq.com{api_path}?cloudbase_access_token={urllib.parse.quote(token)}"
        try:
            data = _post_json(url, payload, self.timeout)
        except Exception as exc:  # noqa: BLE001
            return CloudCallResult(ok=False, data={}, degraded=True, reason=f"调用异常：{type(exc).__name__}")
        errcode = int(data.get("errcode") or 0)
        if errcode == 0:
            return CloudCallResult(ok=True, data=data)
        # 40001/48001/API unauthorized 基本都是「没配白名单」或令牌失效
        hint = ""
        if errcode in (40001, 40014, 42001):
            hint = "（令牌无效/过期，检查云托管令牌推送）"
        elif errcode in (48001, 61007):
            hint = "（无权限：确认控制台已把 " + api_path + " 加进云调用白名单，且是环境维度配置）"
        return CloudCallResult(
            ok=False,
            data=data,
            degraded=True,
            reason=f"errcode={errcode} {data.get('errmsg')}{hint}",
        )

    # ---------------- 文本 ----------------
    def check_text(self, content: str) -> TextSafetyResult:
        content = (content or "").strip()
        if not content:
            return TextSafetyResult(passed=True, suggest=SUGGEST_PASS, reason="空文本，跳过")
        payload = {"content": content[:2500], "version": 2, "scene": self.scene}
        if self.openid:
            payload["openid"] = self.openid
        result = self._call("/wxa/msg_sec_check", payload)
        if not result.ok:
            return TextSafetyResult(
                passed=True, suggest=SUGGEST_PASS, code="degraded", reason=result.reason
            )
        body = result.data.get("result") or {}
        return TextSafetyResult(
            passed=str(body.get("suggest") or "").lower() != "risky",
            suggest=str(body.get("suggest") or "").lower(),
            code="pass",
            reason="",
            meta={"engine": self.name, "label": body.get("label")},
        )

    # ---------------- 图片（异步） ----------------
    def check(self, images: list[Path]) -> SafetyResult:
        if not images:
            return SafetyResult(True, "pass", "", {"engine": self.name, "images": 0})
        return SafetyResult(
            True,
            "degraded",
            "图片检测走 mediaCheckAsync（异步），需要在控制台把 /wxa/media_check_async 加进白名单"
            "并提供公网可访问的图片 URL；当前未启用，不假装已检",
            {"engine": self.name, "images": len(images)},
        )
