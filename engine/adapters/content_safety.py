"""内容安全适配器（§4.2 第一步：违规图片直接拦截，不扣次数）。

本机没有云内容安全账号，原型期用本地桩：只做文件存在性/大小等粗检，
真实实现换成平台接口即可。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class SafetyResult:
    passed: bool
    code: str = "pass"                      # pass / blocked / not_configured
    reason: str = ""
    meta: dict = field(default_factory=dict)


@dataclass
class TextSafetyResult:
    """文本内容安全结论。suggest 取值 pass / review / risky / unknown。"""

    passed: bool = True
    suggest: str = "pass"
    code: str = "pass"                      # pass / blocked / degraded / not_configured / disabled
    reason: str = ""
    meta: dict = field(default_factory=dict)


class ContentSafetyAdapter:
    name = "base"

    def check(self, images: list[Path]) -> SafetyResult:
        raise NotImplementedError

    def check_text(self, content: str) -> TextSafetyResult:
        """文本检测。默认实现：未接真实接口，明确标注 not_configured 并放行。

        子类（微信适配器）覆盖为真实 msgSecCheck。所有实现**都不能抛异常**
        ——内容安全接口出问题不该让用户传不了截图。
        """
        return TextSafetyResult(
            passed=True,
            suggest="pass",
            code="not_configured",
            reason=self.name + "：未接入文本内容安全接口",
        )


class LocalContentSafetyStub(ContentSafetyAdapter):
    """本地桩：不做真实识别，只记录「未接真实内容安全」这一事实。"""

    name = "local-stub"

    def __init__(self, max_files: int = 3, max_mb: int = 10):
        self.max_files = max_files
        self.max_mb = max_mb

    def check(self, images: list[Path]) -> SafetyResult:
        if len(images) > self.max_files:
            return SafetyResult(False, "blocked", f"最多上传 {self.max_files} 张截图，当前 {len(images)} 张")
        for p in images:
            if p.is_file() and p.stat().st_size > self.max_mb * 1024 * 1024:
                return SafetyResult(False, "blocked", f"图片过大（>{self.max_mb}MB）：{p.name}")
        return SafetyResult(
            passed=True,
            code="not_configured",
            reason="本机无云内容安全账号，原型期跳过真实审核（见 docs/02 第 10 条）",
            meta={"engine": "local-stub", "images": len(images)},
        )


class CloudContentSafetyStub(ContentSafetyAdapter):
    name = "cloud-stub"

    def check(self, images: list[Path]) -> SafetyResult:
        return SafetyResult(
            passed=False,
            code="not_configured",
            reason="云内容安全未配置：拿到平台账号后在此接入",
        )
