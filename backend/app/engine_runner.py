"""把识别引擎接进后端：引擎是纯函数库，这里只做「参数装配 + 错误翻译」。

真实 T4 会把这一步放进 Celery 任务；原型期同步调用（Mock 模型下 10–80ms，够联调）。
"""
from __future__ import annotations

import os
import threading
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
    """返回（报告, 轨迹）；失败抛 AnalysisError。

    `ocr_text` 只在「旁路/测试」时传入（预置文本或单测直接给文本）；
    正常情况下传 None，由 analyze() 走真实 OCR（RapidOCR）。
    """
    cfg = build_engine_config(settings, model_name)
    result = analyze(images, ocr_text, config=cfg)
    return result.report, result.trace


# 进程级 OCR 适配器缓存：模型一整套约 300MB，每任务重建会迅速把内存打爆
# （实测连续 21 个任务，单张耗时从 12s 涨到 136s —— 就是反复加载/不释放模型导致的换页）。
_ocr_cache: dict[str, object] = {}
_ocr_lock = threading.Lock()


def _get_ocr_adapter(settings: Settings):
    from engine.adapters.ocr import make_ocr_adapter

    backend = getattr(settings, "ocr_backend", None) or "rapidocr"
    with _ocr_lock:
        adapter = _ocr_cache.get(backend)
        if adapter is None:
            adapter = make_ocr_adapter(backend)
            _ocr_cache[backend] = adapter
        return adapter


def reset_ocr_adapter() -> None:
    """测试用：清掉缓存的 OCR 适配器。"""
    with _ocr_lock:
        _ocr_cache.clear()


def warmup_ocr(settings: Settings) -> bool:
    """启动时预加载模型：避免第一个请求额外背 15 秒的模型加载。失败不致命。"""
    try:
        _get_ocr_adapter(settings)
        return True
    except Exception:
        return False


def ocr_images(settings: Settings, images: list[Path]) -> tuple[str, dict]:
    """对一组图片跑真实 OCR，返回（合并后的文本, OCR 元信息）。

    第 2 关要求：API 链路必须真的识别图片，不能再读 uploads/<task_id>/ocr.txt 预置文本。
    多张图并行识别（每线程独立 RapidOCR 实例），串行 3 张 P95 已超 30 秒承诺。
    适配器按进程复用（见 _get_ocr_adapter），不能每个任务重建。
    """
    if not images:
        raise AnalysisError("OCR_UNAVAILABLE", "没有可识别的图片")
    try:
        adapter = _get_ocr_adapter(settings)
        result = adapter.extract(list(images))
    except Exception as exc:  # 依赖缺失/引擎异常统一翻成 OCR_UNAVAILABLE，由 worker 退次数
        raise AnalysisError("OCR_UNAVAILABLE", f"图片识别失败：{type(exc).__name__}") from exc
    if not (result.text or "").strip():
        raise AnalysisError("OCR_UNAVAILABLE", "图片里没有识别到文字")
    return result.text, dict(result.meta or {})


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
