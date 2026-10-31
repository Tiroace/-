"""引擎配置。默认值按本机目录约定来，命令行可覆盖。"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from .prompts import RULES_VERSION

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass
class EngineConfig:
    root: Path = PROJECT_ROOT
    lexicon_path: Path = field(default_factory=lambda: PROJECT_ROOT / "rules" / "lexicon_v3.json")
    patterns_path: Path = field(default_factory=lambda: PROJECT_ROOT / "rules" / "patterns_v1.json")
    testset_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "data" / "testset")
    cache_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "var" / "cache" / "dedupe")
    report_dir: Path | None = field(default_factory=lambda: PROJECT_ROOT / "var" / "reports")
    model_name: str = "mock"
    # OCR 后端：rapidocr（本地 CPU 离线，默认）/ sidecar（旁路文本）/ mock
    ocr_backend: str = field(default_factory=lambda: os.environ.get("QBL_OCR_BACKEND", "rapidocr"))
    ocr_limit_side_len: int = field(default_factory=lambda: int(os.environ.get("QBL_OCR_LIMIT_SIDE_LEN", "1000")))
    ocr_threads: int = field(default_factory=lambda: int(os.environ.get("QBL_OCR_THREADS", "8")))
    ocr_model_dir: str | None = field(default_factory=lambda: os.environ.get("QBL_OCR_MODEL_DIR") or None)
    # 变形写法表（V信→微信、扣扣→QQ、「押 金」→押金），运营可配
    variants_path: Path = field(default_factory=lambda: PROJECT_ROOT / "rules" / "variants_v1.json")
    # 报告里的规则版本号（路线调整令：原 prompt_version 改名 rules_version）
    rules_version: str = RULES_VERSION
    # 一期不接大模型：只有显式打开才调用模型插件（打开前必须先完成生成式 AI 登记）
    use_llm: bool = field(default_factory=lambda: os.environ.get("QBL_USE_LLM", "0") == "1")
    use_dedupe: bool = True
    dedupe_ttl_hours: int = 24
    mock_defects: bool = True
    pattern_top_k: int = 5
    # 只有当套路相似度达到这个分数才写成 finding（比召回阈值更严，避免干净岗位被误判）。
    pattern_report_threshold: float = field(
        default_factory=lambda: float(os.environ.get("QBL_PATTERN_REPORT_THRESHOLD", "0.5"))
    )
    # 空 = 用套路库文件里的 threshold；可被环境变量 QBL_PATTERN_THRESHOLD 覆盖
    pattern_threshold: float | None = field(
        default_factory=lambda: (
            float(os.environ["QBL_PATTERN_THRESHOLD"]) if os.environ.get("QBL_PATTERN_THRESHOLD") else None
        )
    )


def default_config() -> EngineConfig:
    return EngineConfig()


# 兼容旧代码/测试里的 cfg.prompt_version 读取；报告字段已经改用 rules_version。
def _prompt_version(self: EngineConfig) -> str:
    return self.rules_version


EngineConfig.prompt_version = property(_prompt_version)  # type: ignore[attr-defined]
