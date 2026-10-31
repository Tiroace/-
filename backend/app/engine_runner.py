"""把识别引擎接进后端：引擎是纯函数库，这里只做「参数装配 + 错误翻译」。

真实 T4 会把这一步放进 Celery 任务；原型期同步调用（Mock 模型下 10–80ms，够联调）。
"""
from __future__ import annotations

import os
from pathlib import Path

from engine.calibrate import CalibrationResult  # noqa: F401  # 便于排查时 import
from engine.config import EngineConfig
from engine.pipeline import AnalysisError, analyze

from .config import Settings


def build_engine_config(settings: Settings, model_name: str) -> EngineConfig:
    cfg = EngineConfig()
    cfg.model_name = model_name
    # 一期默认走确定性规则引擎；大模型只是插件，由 QBL_USE_LLM=1 显式打开（EngineConfig 统一读环境变量）。
    # 之前这里写死 False，导致插件根本打不开（smoke 的失败路径用例因此永远等不到 failed）。
    cfg.use_llm = os.environ.get("QBL_USE_LLM", "0") == "1"
    cfg.report_dir = settings.report_dir
    cfg.cache_dir = settings.cache_dir
    cfg.use_dedupe = False   # 去重按「同一用户」在后端做（引擎缓存是全局的，跨用户会串报告）
    cfg.dedupe_ttl_hours = 24
    return cfg


def run_engine(settings: Settings, model_name: str, images: list[Path], ocr_text: str | None) -> tuple[dict, dict]:
    """返回（报告, 轨迹）；失败抛 AnalysisError。"""
    cfg = build_engine_config(settings, model_name)
    result = analyze(images, ocr_text, config=cfg)
    return result.report, result.trace


def translate_engine_error(exc: AnalysisError) -> tuple[str, int]:
    """引擎错误码 → (后端错误码, HTTP 状态码)。

    规则：内容安全拦截不扣次数；OCR 不可用/模型失败/schema 两次不合格都退次数。
    """
    mapping = {
        "OCR_UNAVAILABLE": ("ANALYSIS_UNAVAILABLE", 503),
        "CONTENT_BLOCKED": ("CONTENT_BLOCKED", 422),
        "MODEL_FAILED": ("ANALYSIS_FAILED", 502),
        "SCHEMA_FAILED": ("ANALYSIS_FAILED", 502),
        "PII_LEAK": ("ANALYSIS_FAILED", 502),
        "BAD_CONFIG": ("INTERNAL_ERROR", 500),
    }
    return mapping.get(exc.code, ("ANALYSIS_FAILED", 502))
