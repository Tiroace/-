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


class ContentSafetyAdapter:
    name = "base"

    def check(self, images: list[Path]) -> SafetyResult:
        raise NotImplementedError


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
