"""OCR 适配器：本地 RapidOCR（默认）/ 旁路文本（mock）/ 云 OCR（stub）。

RapidOCR 是本机离线 CPU 推理（rapidocr + onnxruntime，模型随包），
输出「行文本 + 坐标 + 置信度」，供六维规则与证据校验使用。

性能参数全部可配（路线令：性能单独一轮调，别写死）：
- limit_side_len：检测长边缩放，默认 1000（800–1000 是 CER/耗时平衡区）
- intra_op_num_threads：onnxruntime 线程数，默认 8（4 核机实测最优）
- 模型目录：model_root_dir / det_model_dir / rec_model_dir，null 用随包模型
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from pathlib import Path


class OcrNotAvailable(Exception):
    """拿不到 OCR 文本（既没有旁路文本，也没有可用 OCR 引擎）。"""


@dataclass
class OcrLine:
    """一行识别结果：文本 + 四点坐标 + 置信度。"""

    text: str
    box: list[list[float]] = field(default_factory=list)   # [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]
    score: float = 0.0

    @property
    def center_y(self) -> float:
        if not self.box:
            return 0.0
        return sum(p[1] for p in self.box) / len(self.box)

    @property
    def left_x(self) -> float:
        if not self.box:
            return 0.0
        return min(p[0] for p in self.box)

    def to_dict(self) -> dict:
        return {"text": self.text, "box": self.box, "score": round(self.score, 4)}


@dataclass
class OcrResult:
    text: str
    source: str                       # rapidocr / local-sidecar / cloud
    lines: list[OcrLine] = field(default_factory=list)
    meta: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "source": self.source,
            "meta": self.meta,
            "lines": [ln.to_dict() for ln in self.lines],
        }


class OcrAdapter:
    """OCR 接口。"""

    name = "base"

    def extract(self, images: list[Path], sidecar_text: str | None = None) -> OcrResult:
        raise NotImplementedError


class RapidOCREngine(OcrAdapter):
    """本地 CPU 离线 OCR（rapidocr + onnxruntime）。

    同一张图同一参数 → 同一结果（确定性），满足路线令「同图同结果」。
    """

    name = "rapidocr"

    def __init__(
        self,
        limit_side_len: int = 1000,
        intra_op_num_threads: int = 8,
        model_root_dir: str | None = None,
        det_model_dir: str | None = None,
        rec_model_dir: str | None = None,
        text_score: float = 0.5,
        use_cls: bool = True,
        log_level: str = "warning",
    ):
        self.limit_side_len = int(limit_side_len)
        self.intra_op_num_threads = int(intra_op_num_threads)
        self.model_root_dir = model_root_dir
        self.det_model_dir = det_model_dir
        self.rec_model_dir = rec_model_dir
        self.text_score = float(text_score)
        self.use_cls = bool(use_cls)
        self.log_level = log_level
        self._engine = None

    # -- 延迟初始化：只有真的要跑图片时才加载模型（避免 import 就吃内存）--
    def _ensure_engine(self):
        if self._engine is not None:
            return self._engine
        try:
            from rapidocr import RapidOCR
        except ImportError as exc:  # pragma: no cover - 依赖缺失时明确报错
            raise OcrNotAvailable(
                "本机未安装 rapidocr/onnxruntime，请先 pip install rapidocr onnxruntime"
            ) from exc

        params: dict = {
            "Global.log_level": self.log_level,
            "Global.text_score": self.text_score,
            "Global.use_cls": self.use_cls,
            "Det.limit_side_len": self.limit_side_len,
            "EngineConfig.onnxruntime.intra_op_num_threads": self.intra_op_num_threads,
        }
        if self.model_root_dir:
            params["Global.model_root_dir"] = self.model_root_dir
        if self.det_model_dir:
            params["Det.model_dir"] = self.det_model_dir
        if self.rec_model_dir:
            params["Rec.model_dir"] = self.rec_model_dir
        self._engine = RapidOCR(params=params)
        return self._engine

    # -- 结果解析 -------------------------------------------------
    @staticmethod
    def _parse(result) -> list[OcrLine]:
        """把 RapidOCR 输出解析成 OcrLine 列表（兼容不同版本字段名）。"""
        lines: list[OcrLine] = []
        boxes = getattr(result, "boxes", None)
        txts = getattr(result, "txts", None)
        scores = getattr(result, "scores", None)
        if boxes is None or txts is None:
            return lines
        for idx, txt in enumerate(txts):
            if txt is None or not str(txt).strip():
                continue
            box = boxes[idx]
            try:
                box_list = [[float(p[0]), float(p[1])] for p in box]
            except (TypeError, IndexError):
                box_list = []
            score = float(scores[idx]) if scores is not None and idx < len(scores) else 0.0
            lines.append(OcrLine(text=str(txt).strip(), box=box_list, score=score))
        return lines

    @staticmethod
    def _merge_lines(lines: list[OcrLine]) -> list[OcrLine]:
        """同一行（纵坐标接近）的碎块按 x 合并，避免一句话被切碎。"""
        if not lines:
            return []
        ordered = sorted(lines, key=lambda ln: (round(ln.center_y / 12), ln.left_x))
        merged: list[OcrLine] = []
        for line in ordered:
            if merged and abs(merged[-1].center_y - line.center_y) <= 8:
                prev = merged[-1]
                prev.text = prev.text + line.text
                prev.box = prev.box + line.box if prev.box and line.box else prev.box
                prev.score = min(prev.score, line.score) if prev.score else line.score
            else:
                merged.append(OcrLine(line.text, list(line.box), line.score))
        return merged

    # -- 主接口 ---------------------------------------------------
    def extract(self, images: list[Path], sidecar_text: str | None = None) -> OcrResult:
        if sidecar_text and sidecar_text.strip():
            return OcrResult(text=sidecar_text, source="local-sidecar", meta={"file": "<inline>"})
        if not images:
            raise OcrNotAvailable("没有图片可识别")
        engine = self._ensure_engine()
        all_lines: list[OcrLine] = []
        started = time.perf_counter()
        per_image: list[dict] = []
        for path in images:
            t0 = time.perf_counter()
            result = engine(str(path))
            lines = self._merge_lines(self._parse(result))
            elapsed = round(time.perf_counter() - t0, 3)
            per_image.append({"file": str(path), "lines": len(lines), "seconds": elapsed})
            all_lines.extend(lines)
        text = "\n".join(ln.text for ln in all_lines)
        return OcrResult(
            text=text,
            source=self.name,
            lines=all_lines,
            meta={
                "engine": "rapidocr",
                "limit_side_len": self.limit_side_len,
                "intra_op_num_threads": self.intra_op_num_threads,
                "images": per_image,
                "seconds": round(time.perf_counter() - started, 3),
            },
        )


class LocalSidecarOcr(OcrAdapter):
    """旁路：直接读 OCR 文本文件（无 OCR 环境时跑通链路）。"""

    name = "local-sidecar"

    def __init__(self, text_path: str | Path | None = None, search_dirs: list[str | Path] | None = None):
        self.text_path = Path(text_path) if text_path else None
        self.search_dirs = [Path(d) for d in (search_dirs or [])]

    def extract(self, images: list[Path], sidecar_text: str | None = None) -> OcrResult:
        if sidecar_text and sidecar_text.strip():
            return OcrResult(text=sidecar_text, source=self.name, meta={"file": "<inline>"})

        if self.text_path:
            path = self.text_path
            if path.is_dir():
                path = self._resolve_in_dir(path, images)
            text = path.read_text(encoding="utf-8").strip()
            if not text:
                raise OcrNotAvailable(f"OCR 旁路文本是空的：{path}")
            return OcrResult(text=text, source=self.name, meta={"file": str(path)})

        for directory in self.search_dirs:
            if not directory.is_dir():
                continue
            try:
                path = self._resolve_in_dir(directory, images)
            except OcrNotAvailable:
                continue
            text = path.read_text(encoding="utf-8").strip()
            if text:
                return OcrResult(text=text, source=self.name, meta={"file": str(path)})
        raise OcrNotAvailable("没有 OCR 文本可用，请用 --ocr-text 指定旁路文本")

    @staticmethod
    def _resolve_in_dir(directory: Path, images: list[Path]) -> Path:
        if images:
            for img in images:
                candidate = directory / f"{img.stem}.txt"
                if candidate.is_file():
                    return candidate
        txts = sorted(directory.glob("*.txt"))
        if len(txts) == 1:
            return txts[0]
        if not txts:
            raise OcrNotAvailable(f"目录里没有 OCR 文本：{directory}")
        raise OcrNotAvailable(f"目录里有多份 OCR 文本，请用 --ocr-text 指定：{directory}")


class CloudOcrStub(OcrAdapter):
    """云 OCR 占位（路线令后一期不用，保留接口）。"""

    name = "cloud-stub"

    def __init__(self, provider: str = "aliyun", **config):
        self.provider = provider
        self.config = config

    def extract(self, images: list[Path], sidecar_text: str | None = None) -> OcrResult:
        raise OcrNotAvailable(f"云 OCR（{self.provider}）未配置：路线令一期不接云 OCR")


def make_ocr_adapter(backend: str = "rapidocr", **kwargs) -> OcrAdapter:
    """按 OCR_BACKEND 造适配器：rapidocr / sidecar / mock。"""
    backend = (backend or "rapidocr").lower()
    if backend in ("rapidocr", "local", "rapid"):
        return RapidOCREngine(
            limit_side_len=int(kwargs.get("limit_side_len", 1000)),
            intra_op_num_threads=int(kwargs.get("intra_op_num_threads", 8)),
            model_root_dir=kwargs.get("model_root_dir") or os.environ.get("QBL_OCR_MODEL_DIR") or None,
        )
    if backend in ("sidecar", "mock", "text"):
        return LocalSidecarOcr()
    raise OcrNotAvailable(f"未知 OCR 后端：{backend}（可选 rapidocr / sidecar / mock）")
