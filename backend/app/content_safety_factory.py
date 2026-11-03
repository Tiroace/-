"""内容安全适配器工厂：按配置选实现，统一带上「失败降级不阻塞」的语义。

第 2 关要求：接微信真实接口（msgSecCheck / mediaCheckAsync），
接口不可用时**不阻塞主流程，但要记录**。
"""
from __future__ import annotations

import logging

from engine.adapters.content_safety import ContentSafetyAdapter, LocalContentSafetyStub, SafetyResult
from engine.adapters.wechat_safety import WechatContentSafety

from .config import Settings

logger = logging.getLogger("qbl.content_safety")


class DisabledContentSafety(ContentSafetyAdapter):
    """完全关闭内容安全（QBL_CONTENT_SAFETY=off）：显式声明「没检」，不做假通过。"""

    name = "off"

    def check(self, images):
        return SafetyResult(True, "disabled", "内容安全已关闭（QBL_CONTENT_SAFETY=off）", {"engine": self.name})

    def check_text(self, content: str):
        from engine.adapters.content_safety import TextSafetyResult

        return TextSafetyResult(
            passed=True,
            suggest="pass",
            code="disabled",
            reason="内容安全已关闭（QBL_CONTENT_SAFETY=off），未做文本检测",
        )


def _media_url_builder(settings: Settings):
    """图片异步检测要公网可访问的 URL：用配置的对外域名拼。

    拿不到域名就返回 None，让适配器降级并记录——不能编一个假 URL 提交上去。
    """
    base = (settings.content_safety_media_base or "").rstrip("/")
    if not base:
        return None

    def build(path) -> str:
        try:
            rel = path.relative_to(settings.upload_dir)
        except ValueError:
            return ""
        return f"{base}/{rel.as_posix()}"

    return build


def build_content_safety(settings: Settings, openid: str = "") -> ContentSafetyAdapter:
    mode = (settings.content_safety or "local").lower()
    if mode == "off":
        return DisabledContentSafety()
    if mode == "wechat":
        return WechatContentSafety(
            appid=settings.wx_appid,
            secret=settings.wx_secret,
            openid=openid,
            timeout=settings.content_safety_timeout,
            media_url_builder=_media_url_builder(settings),
        )
    # 默认：本地桩（粗检 + 明确标注 not_configured）
    return LocalContentSafetyStub(max_files=settings.max_images, max_mb=settings.max_image_mb)


def log_safety(result: SafetyResult, where: str, task_hint: str = "") -> None:
    """统一记录内容安全结论，降级/未配置必须留下痕迹。"""
    if result.passed and result.code == "pass":
        return
    level = logging.INFO
    if result.code in ("degraded", "not_configured", "disabled"):
        level = logging.WARNING
    logger.log(
        level,
        "内容安全 %s：code=%s passed=%s reason=%s %s",
        where,
        result.code,
        result.passed,
        result.reason or "-",
        task_hint,
    )
