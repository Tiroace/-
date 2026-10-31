"""适配器入口：OCR（RapidOCR 默认）/ 内容安全 / 模型插件（默认关闭）。"""
from .content_safety import CloudContentSafetyStub, ContentSafetyAdapter, LocalContentSafetyStub, SafetyResult
from .models import DeepSeekModel, ModelAdapter, ModelNotConfigured, ModelRequest, MockModel
from .ocr import (
    CloudOcrStub,
    LocalSidecarOcr,
    OcrAdapter,
    OcrLine,
    OcrNotAvailable,
    OcrResult,
    RapidOCREngine,
    make_ocr_adapter,
)

__all__ = [
    "ContentSafetyAdapter",
    "LocalContentSafetyStub",
    "CloudContentSafetyStub",
    "SafetyResult",
    "ModelAdapter",
    "ModelRequest",
    "MockModel",
    "DeepSeekModel",
    "ModelNotConfigured",
    "OcrAdapter",
    "OcrResult",
    "OcrLine",
    "LocalSidecarOcr",
    "RapidOCREngine",
    "CloudOcrStub",
    "OcrNotAvailable",
    "make_ocr_adapter",
]
