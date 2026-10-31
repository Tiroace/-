"""识别链路编排 v2。

内容安全 → OCR 提取 → 去重 → 规则初筛 → 套路库召回 → 模型（6 维度）→ 补整句 →
证据校验（红黄绿都算）→ 等级校准 → 组装（灯/整体结论/灰灯追问）→ PII 硬断言 → schema 校验 → 出报告
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from .adapters.content_safety import ContentSafetyAdapter, LocalContentSafetyStub
from .adapters.models import ModelAdapter, ModelRequest, MockModel
from .adapters.ocr import LocalSidecarOcr, OcrAdapter, OcrNotAvailable
from .calibrate import calibrate
from .config import EngineConfig, default_config
from .dedupe import DedupeCache, build_key
from .evidence import verify_findings
from .lexicon import Lexicon, load_lexicon, scan
from .patterns import PatternLibrary
from .prompts import RULES_VERSION
from .report import apply_text_policy, build_report
from .rules_engine import compose
from .schema import validate_report
from .textnorm import context_containing, find_pii

ENGINE_VERSION = "3.0.0"

# 失败原因码：T4 后端按这个回退次数/提示文案
ERR_OCR_UNAVAILABLE = "OCR_UNAVAILABLE"
ERR_CONTENT_BLOCKED = "CONTENT_BLOCKED"
ERR_MODEL_FAILED = "MODEL_FAILED"
ERR_SCHEMA_FAILED = "SCHEMA_FAILED"
ERR_SCHEMA_FIXED = "SCHEMA_FIXED_AFTER_RETRY"
ERR_PII_LEAK = "PII_LEAK"


class AnalysisError(Exception):
    def __init__(self, code: str, message: str, detail: dict | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.detail = detail or {}


@dataclass
class AnalysisResult:
    report: dict
    trace: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"report": self.report, "trace": self.trace}


class _Timer:
    def __init__(self) -> None:
        self.stages: dict[str, float] = {}
        self._start = time.perf_counter()

    def stage(self, name: str, t0: float) -> None:
        self.stages[name] = round((time.perf_counter() - t0) * 1000, 2)

    @property
    def total_ms(self) -> float:
        return round((time.perf_counter() - self._start) * 1000, 2)


def make_model(name: str, defects: bool = True) -> ModelAdapter:
    if name == "mock":
        return MockModel(defects=defects)
    if name == "deepseek":
        from .adapters.models import DeepSeekModel

        return DeepSeekModel()
    raise AnalysisError("BAD_CONFIG", f"未知模型：{name}（可选 mock / deepseek）")


def _context_for(text: str, evidence: str, max_len: int = 160) -> str:
    """context = 包含 evidence 的原文片段（整句优先，过长时取窗口）。"""
    return context_containing(text, evidence, max_len=max_len)


def analyze(
    images: list[str | Path] | None = None,
    ocr_text: str | None = None,
    *,
    config: EngineConfig | None = None,
    model: ModelAdapter | None = None,
    ocr_adapter: OcrAdapter | None = None,
    safety_adapter: ContentSafetyAdapter | None = None,
    lexicon: Lexicon | None = None,
    patterns: PatternLibrary | None = None,
    use_dedupe: bool | None = None,
) -> AnalysisResult:
    cfg = config or default_config()
    timer = _Timer()
    task_id = f"{time.strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}"
    image_paths = [Path(p) for p in (images or [])]

    # ---- 0. 词库 + 套路库 ----
    lexicon = lexicon or load_lexicon(cfg.lexicon_path, cfg.variants_path)
    patterns = patterns or PatternLibrary(cfg.patterns_path, threshold=cfg.pattern_threshold)
    engine_mode = "llm" if cfg.use_llm else "rules"
    model = (model or make_model(cfg.model_name, cfg.mock_defects)) if cfg.use_llm else None
    ocr_adapter = ocr_adapter or LocalSidecarOcr(search_dirs=[cfg.testset_dir / "ocr"])
    safety_adapter = safety_adapter or LocalContentSafetyStub()
    rules_version = cfg.rules_version or RULES_VERSION

    trace: dict = {
        "task_id": task_id,
        "engine_version": ENGINE_VERSION,
        "engine_mode": engine_mode,
        "model": model.name if model is not None else None,
        "rules_version": rules_version,
        "lexicon_version": lexicon.version,
        "lexicon_rule_count": len(lexicon.rules),
        "variants_version": getattr(lexicon, "variants_version", "v0"),
        "pattern_db_version": patterns.version,
        "pattern_count": patterns.count,
        "images": [str(p) for p in image_paths],
        "stages_ms": {},
        "warnings": [],
    }

    # ---- 1. 内容安全 ----
    t0 = time.perf_counter()
    safety = safety_adapter.check(image_paths)
    timer.stage("content_safety", t0)
    trace["content_safety"] = {"passed": safety.passed, "code": safety.code, "reason": safety.reason}
    if not safety.passed:
        raise AnalysisError(ERR_CONTENT_BLOCKED, safety.reason, {"content_safety": trace["content_safety"]})

    # ---- 2. OCR ----
    t0 = time.perf_counter()
    ocr_spec = ocr_text
    if ocr_spec:
        candidate = Path(ocr_spec)
        if candidate.is_file():
            ocr_spec = candidate.read_text(encoding="utf-8")
    try:
        ocr = ocr_adapter.extract(image_paths, sidecar_text=ocr_spec)
    except OcrNotAvailable as exc:
        raise AnalysisError(ERR_OCR_UNAVAILABLE, str(exc)) from exc
    timer.stage("ocr", t0)
    text = ocr.text
    trace["ocr"] = {"source": ocr.source, "chars": len(text), "meta": ocr.meta}
    if not text.strip():
        raise AnalysisError(ERR_OCR_UNAVAILABLE, "OCR 文本为空，无法分析")

    # ---- 3. 去重 ----
    use_dedupe = cfg.use_dedupe if use_dedupe is None else use_dedupe
    cache = DedupeCache(cfg.cache_dir, cfg.dedupe_ttl_hours)
    key = build_key(image_paths, text, lexicon.version, engine_mode, rules_version, patterns.version)
    trace["cache_key"] = key[:16]
    if use_dedupe:
        t0 = time.perf_counter()
        cached = cache.get(key)
        timer.stage("dedupe", t0)
        if cached is not None:
            trace["dedupe_hit"] = True
            trace["total_ms"] = timer.total_ms
            trace["stages_ms"] = timer.stages
            return AnalysisResult(report=cached, trace=trace)
    trace["dedupe_hit"] = False

    # ---- 4. 规则初筛 ----
    t0 = time.perf_counter()
    hits = scan(text, lexicon)
    timer.stage("rule_scan", t0)
    trace["rule_hits"] = [h.to_dict() for h in hits]
    trace["rule_hit_count"] = len(hits)
    trace["hard_hit_count"] = sum(1 for h in hits if h.hard)

    # ---- 5. 套路库召回 ----
    t0 = time.perf_counter()
    pattern_hits = patterns.match(text, top_k=cfg.pattern_top_k)
    timer.stage("pattern_match", t0)
    trace["pattern_hits"] = [m.to_dict() for m in pattern_hits]

    # ---- 6. 判断：一期用确定性规则引擎；大模型只在插件开关打开时启用 ----
    if engine_mode == "llm":
        t0 = time.perf_counter()
        attempts: list[dict] = []
        model_out: dict | None = None
        retry_errors: list[str] = []
        for attempt in (1, 2):
            try:
                candidate = model.generate(  # type: ignore[union-attr]
                    ModelRequest(
                        ocr_text=text,
                        rule_hits=hits,
                        pattern_hits=pattern_hits,
                        type_names={},
                        prompt_version=rules_version,
                        pattern_db_version=patterns.version,
                        retry_errors=retry_errors,
                        images=image_paths,
                    )
                )
            except Exception as exc:  # 模型异常：不重试，按失败处理（退次数）
                attempts.append({"attempt": attempt, "ok": False, "error": f"{type(exc).__name__}: {exc}"})
                raise AnalysisError(ERR_MODEL_FAILED, f"模型调用失败：{exc}", {"attempts": attempts}) from exc

            errors = validate_report(candidate, final=False)
            attempts.append({"attempt": attempt, "ok": not errors, "errors": errors[:6]})
            if not errors:
                model_out = candidate
                break
            retry_errors = errors
        timer.stage("llm", t0)
        trace["model_attempts"] = attempts
        if model_out is None:
            raise AnalysisError(ERR_SCHEMA_FAILED, "模型输出连续两次不符合 schema，按失败处理并退次数", {"attempts": attempts})
        if len(attempts) > 1:
            trace["warnings"].append(ERR_SCHEMA_FIXED)
    else:
        t0 = time.perf_counter()
        model_out = compose(text, hits, pattern_hits, min_pattern_score=cfg.pattern_report_threshold)
        timer.stage("rules_compose", t0)
        trace["model_attempts"] = []
        trace["compose_findings"] = len(model_out.get("findings") or [])
        # D34：同一证据被多条规则各报一次时，按优先级只留一条；被丢弃的记进来，
        # 否则分不清「真多判被压掉」和「规则漏了」。
        trace["dropped_by_priority"] = model_out.get("dropped_by_priority") or []

    is_job = bool(model_out.get("is_job_posting", True))

    # ---- 7. 补齐 context（整句必须是包含 evidence 的原文）----
    raw_findings: list[dict] = []
    for item in model_out.get("findings") or []:
        if not isinstance(item, dict):
            continue
        evidence = str(item.get("evidence") or "").strip()
        item = dict(item)
        item["context"] = _context_for(text, evidence)
        raw_findings.append(item)

    # ---- 8. 证据校验（绿也要）----
    t0 = time.perf_counter()
    kept, dropped = verify_findings(raw_findings, text) if is_job else ([], [])
    timer.stage("evidence", t0)
    trace["findings_dropped"] = [d.to_dict() for d in dropped]
    trace["findings_kept"] = len(kept)

    # ---- 9. 等级校准（规则/套路下限 + 硬证据兜底）----
    t0 = time.perf_counter()
    calib = calibrate(kept, hits, pattern_hits) if is_job else None
    timer.stage("calibrate", t0)
    calibrated = calib.findings if calib else []
    trace["calibration"] = calib.adjustments if calib else []
    for finding in calibrated:   # 兜底补的 finding 也要补整句
        finding["context"] = _context_for(text, str(finding.get("evidence") or ""))

    # ---- 10. 组装报告（灯 / overall / 灰灯追问）----
    t0 = time.perf_counter()
    report, grey = build_report(
        model_out,
        calibrated,
        is_job,
        rules_version,
        patterns.version,
    )
    trace["evidence_raw"] = [{"dimension": f["dimension"], "level": f["level"], "evidence": f["evidence"]} for f in report["findings"]]
    trace["grey_dimensions"] = [{"dimension": g["dimension"], "question": g["question"]} for g in grey]
    timer.stage("compose", t0)

    # ---- 11. 文案红线 + 输出层 PII 硬断言 ----
    report, banned = apply_text_policy(report)
    trace["banned_words"] = banned
    leaks = find_pii(json.dumps(report, ensure_ascii=False))
    trace["pii_leaks"] = leaks
    if leaks:
        raise AnalysisError(
            ERR_PII_LEAK,
            f"输出层仍有 {len(leaks)} 处个人信息未脱敏，按失败处理并退次数",
            {"leaks": leaks},
        )

    # ---- 12. 最终 schema 校验 ----
    t0 = time.perf_counter()
    final_errors = validate_report(report, final=True)
    timer.stage("schema_check", t0)
    if final_errors:
        raise AnalysisError(
            ERR_SCHEMA_FAILED,
            "校准后的报告仍不符合 v2 schema，按失败处理并退次数",
            {"errors": final_errors, "report": report},
        )

    trace["overall"] = report["overall"]
    trace["dimensions"] = {d["key"]: d["level"] for d in report["dimensions"]}
    trace["finding_count"] = len(report["findings"])
    trace["stages_ms"] = timer.stages
    trace["total_ms"] = timer.total_ms

    # ---- 13. 落库/缓存 ----
    if cfg.report_dir is not None:
        cfg.report_dir.mkdir(parents=True, exist_ok=True)
        (cfg.report_dir / f"{task_id}.json").write_text(
            json.dumps(AnalysisResult(report=report, trace=trace).to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    if use_dedupe:
        cache.put(key, report)

    return AnalysisResult(report=report, trace=trace)
