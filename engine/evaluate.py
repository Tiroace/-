"""评测脚本 v2：跑 data/testset/index.jsonl，算改版后的指标。

指标口径（写死在这里，避免口径漂移）：
- 整体结论准确率 overall_exact：6 档整体结论（red/amber/green/unknown）判对比例
- 高危召回率 red_recall：标注 red 的样例中 overall 也是 red 的比例（门槛 ≥ 90%，沿用 A 关口）
- 正常岗位误判高危率 green_false_red：标注 green 的样例中 overall=red 的比例（门槛 ≤ 5%）
- 维度级准确率 dimension_accuracy：6 个维度的灯色（red/amber/green/none）判对比例（新指标）
- 套路库召回率 pattern_recall：标注的 pattern 在 findings.pattern_id 里出现的比例（新指标）
- 证据可追溯率 evidence_traceable：脱敏前 evidence 能在 OCR 原文找到的比例（门槛 100%）
- context 自洽率：最终报告里 context 包含 evidence 的比例（门槛 100%）
- 输出层 PII 泄漏：报告 JSON 全文扫描，必须 0 处
- 平均耗时：单条 内容安全→出报告 的墙钟时间（95% 在 30 秒内）
- 灰灯追问率：出现灰灯（none）时，questions_to_ask 里带了「没提到」追问的比例

用法：
    python -m engine.evaluate
    python -m engine.evaluate --compare data/eval/eval_report.json
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

from .config import EngineConfig, PROJECT_ROOT, default_config
from .lexicon import load_lexicon
from .patterns import PatternLibrary
from .pipeline import AnalysisError, analyze, make_model
from .schema import validate_report
from .textnorm import DIMENSION_KEYS, evidence_in_text, find_pii, normalize

THRESHOLDS = {
    "red_recall": 0.90,
    "green_false_red": 0.05,
    "evidence_traceable": 1.0,
    "context_consistent": 1.0,
    "pii_leaks": 0,
    "dimension_accuracy": 0.80,
    "pattern_recall": 0.60,
    "avg_ms": 30_000,
}
METRIC_DIRECTIONS = {
    "red_recall": "up",
    "green_false_red": "down",
    "overall_exact": "up",
    "dimension_accuracy": "up",
    "pattern_recall": "up",
    "evidence_traceable": "up",
    "pii_leaks": "down",
    "avg_ms": "down",
}


def load_index(path: Path) -> list[dict]:
    rows: list[dict] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"index.jsonl 第 {lineno} 行不是合法 JSON：{exc}") from exc
        if "id" not in row or "ocr_text" not in row:
            raise SystemExit(f"index.jsonl 第 {lineno} 行缺字段 id/ocr_text")
        # 双轨格式（S0001/RT0001）：标注在 label 下；老格式兼容：字段在顶层
        label = row.get("label") if isinstance(row.get("label"), dict) else {}
        row.setdefault("overall", label.get("overall", row.get("overall")))
        row.setdefault("dimensions", label.get("dimensions", row.get("dimensions")))
        row.setdefault("track", row.get("track") or (row.get("source") or {}).get("type") or "synthetic")
        if row.get("overall") is None:
            raise SystemExit(f"index.jsonl 第 {lineno} 行缺标注 overall")
        rows.append(row)
    return rows


def evaluate(
    index_path: Path | None = None,
    config: EngineConfig | None = None,
    model_name: str = "mock",
    defects: bool = True,
    limit: int | None = None,
) -> dict:
    cfg = config or default_config()
    cfg.use_dedupe = False
    cfg.report_dir = None
    index_path = index_path or (cfg.testset_dir / "index.jsonl")
    rows = load_index(index_path)
    if limit:
        rows = rows[:limit]

    lexicon = load_lexicon(cfg.lexicon_path, cfg.variants_path)
    patterns = PatternLibrary(cfg.patterns_path, threshold=cfg.pattern_threshold)
    model = make_model(model_name, defects=defects) if cfg.use_llm else None

    cases: list[dict] = []
    failures: list[dict] = []
    latencies: list[float] = []
    evidence_total = evidence_traceable = 0
    context_total = context_ok = 0
    pii_total = 0
    grey_checked = grey_ok = 0
    dropped_total = 0
    calibration_total = 0
    retry_total = 0
    schema_ok = 0

    for row in rows:
        cid = row["id"]
        ocr_file = PROJECT_ROOT / row["ocr_text"] if not Path(row["ocr_text"]).is_absolute() else Path(row["ocr_text"])
        text = ocr_file.read_text(encoding="utf-8") if ocr_file.is_file() else ""
        if not text:
            failures.append({"id": cid, "error": f"OCR 文本缺失：{ocr_file}"})
            continue

        started = time.perf_counter()
        try:
            result = analyze([], text, config=cfg, model=model, lexicon=lexicon, patterns=patterns)
        except AnalysisError as exc:
            failures.append({"id": cid, "error": f"{exc.code}: {exc.message}"})
            continue
        latency_ms = (time.perf_counter() - started) * 1000
        latencies.append(latency_ms)

        report = result.report
        trace = result.trace
        errors = validate_report(report, final=True)
        if not errors:
            schema_ok += 1
        dropped_total += len(trace.get("findings_dropped", []))
        calibration_total += len(trace.get("calibration", []))
        if len(trace.get("model_attempts", [])) > 1:
            retry_total += 1

        # 证据可追溯（脱敏前）
        raw_evidence = trace.get("evidence_raw") or []
        untraceable = []
        for item in raw_evidence:
            evidence_total += 1
            if evidence_in_text(str(item.get("evidence", "")), text):
                evidence_traceable += 1
            else:
                untraceable.append(item.get("evidence"))

        # context 自洽（最终报告层面）
        for finding in report["findings"]:
            context_total += 1
            if normalize(finding["evidence"]) in normalize(finding["context"]):
                context_ok += 1

        leaks = trace.get("pii_leaks")
        if leaks is None:
            leaks = find_pii(json.dumps(report, ensure_ascii=False))
        pii_total += len(leaks)

        # 灰灯追问
        grey_keys = [d["key"] for d in report["dimensions"] if d["level"] == "none"]
        if grey_keys:
            grey_checked += 1
            if any("没提到" in q for q in report["questions_to_ask"]):
                grey_ok += 1

        # 维度准确率
        gt_dims = row.get("dimensions") or {}
        pred_dims = {d["key"]: d["level"] for d in report["dimensions"]}
        dim_checked = 0
        dim_hit = 0
        dim_wrong: list[dict] = []
        for key in DIMENSION_KEYS:
            if key not in gt_dims:
                continue
            dim_checked += 1
            if pred_dims.get(key) == gt_dims[key]:
                dim_hit += 1
            else:
                dim_wrong.append({"dimension": key, "gt": gt_dims[key], "pred": pred_dims.get(key)})

        # 套路召回：检索命中（trace.pattern_hits）或最终 finding 里带 pattern_id 都算命中
        gt_patterns = set(row.get("patterns") or [])
        pred_patterns = {f["pattern_id"] for f in report["findings"] if f.get("pattern_id")}
        pred_patterns |= {m.get("pattern_id") for m in trace.get("pattern_hits", []) if m.get("pattern_id")}
        pattern_hit = len(gt_patterns & pred_patterns)

        cases.append(
            {
                "id": cid,
                "gt_overall": row["overall"],
                "pred_overall": report["overall"],
                "gt_dimensions": gt_dims,
                "pred_dimensions": pred_dims,
                "dimension_checked": dim_checked,
                "dimension_hit": dim_hit,
                "dimension_wrong": dim_wrong,
                "gt_patterns": sorted(gt_patterns),
                "pred_patterns": sorted(pred_patterns),
                "pattern_hit": pattern_hit,
                "patterns_extra": sorted(pred_patterns - gt_patterns),
                "findings": len(report["findings"]),
                "latency_ms": round(latency_ms, 2),
                "untraceable": untraceable,
                "grey_keys": grey_keys,
                "schema_ok": not errors,
                "schema_errors": errors,
                "dropped": len(trace.get("findings_dropped", [])),
                "calibration": len(trace.get("calibration", [])),
                "model_reported_overall": trace.get("model_reported_overall"),
            }
        )

    red_cases = [c for c in cases if c["gt_overall"] == "red"]
    green_cases = [c for c in cases if c["gt_overall"] == "green"]
    amber_cases = [c for c in cases if c["gt_overall"] == "amber"]

    def rate(num: int, den: int) -> float:
        return round(num / den, 4) if den else 0.0

    red_recall = rate(sum(1 for c in red_cases if c["pred_overall"] == "red"), len(red_cases))
    green_false_red = rate(sum(1 for c in green_cases if c["pred_overall"] == "red"), len(green_cases))
    overall_exact = rate(sum(1 for c in cases if c["pred_overall"] == c["gt_overall"]), len(cases))
    amber_alarm = rate(sum(1 for c in amber_cases if c["pred_overall"] in ("amber", "red")), len(amber_cases))
    dim_checked = sum(c["dimension_checked"] for c in cases)
    dim_hit = sum(c["dimension_hit"] for c in cases)
    dimension_accuracy = rate(dim_hit, dim_checked)
    gt_pattern_total = sum(len(c["gt_patterns"]) for c in cases)
    gt_pattern_hit = sum(c["pattern_hit"] for c in cases)
    pattern_recall = rate(gt_pattern_hit, gt_pattern_total)
    pred_pattern_total = sum(len(c["pred_patterns"]) for c in cases)
    pattern_precision = rate(gt_pattern_hit, pred_pattern_total)
    avg_ms = round(statistics.fmean(latencies), 2) if latencies else 0.0
    p95_ms = round(sorted(latencies)[max(0, int(len(latencies) * 0.95) - 1)], 2) if latencies else 0.0

    metrics = {
        "overall_exact": overall_exact,
        "red_recall": red_recall,
        "green_false_red": green_false_red,
        "amber_alarm": amber_alarm,
        "dimension_accuracy": dimension_accuracy,
        "dimension_checked": dim_checked,
        "dimension_hit": dim_hit,
        "pattern_recall": pattern_recall,
        "pattern_precision": pattern_precision,
        "pattern_hit": gt_pattern_hit,
        "pattern_total": gt_pattern_total,
        "evidence_traceable": rate(evidence_traceable, evidence_total),
        "context_consistent": rate(context_ok, context_total),
        "pii_leaks": pii_total,
        "grey_question_rate": rate(grey_ok, grey_checked),
        "avg_ms": avg_ms,
        "p95_ms": p95_ms,
        "schema_pass_rate": rate(schema_ok, len(cases)),
        "findings_dropped_total": dropped_total,
        "calibration_adjust_total": calibration_total,
        "model_retry_cases": retry_total,
        "level_dist": {
            level: sum(1 for c in cases if c["pred_overall"] == level)
            for level in ("red", "amber", "green", "unknown")
        },
    }

    gate = {
        "red_recall": "pass" if red_recall >= THRESHOLDS["red_recall"] else "fail",
        "green_false_red": "pass" if green_false_red <= THRESHOLDS["green_false_red"] else "fail",
        "evidence_traceable": "pass" if metrics["evidence_traceable"] >= THRESHOLDS["evidence_traceable"] else "fail",
        "context_consistent": "pass" if metrics["context_consistent"] >= THRESHOLDS["context_consistent"] else "fail",
        "pii_zero_leak": "pass" if pii_total == 0 else "fail",
        "dimension_accuracy": "pass" if dimension_accuracy >= THRESHOLDS["dimension_accuracy"] else "fail",
        "pattern_recall": (
            "skip"
            if gt_pattern_total == 0
            else ("pass" if pattern_recall >= THRESHOLDS["pattern_recall"] else "fail")
        ),
        "schema": "pass" if cases and schema_ok == len(cases) else "fail",
    }

    return {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "schema_version": "v2",
        "engine_mode": "llm" if cfg.use_llm else "rules",
        "model": model.name if model is not None else None,
        "lexicon_version": lexicon.version,
        "variants_version": getattr(lexicon, "variants_version", "v0"),
        "pattern_db_version": patterns.version,
        "pattern_count": patterns.count,
        "testset": str(index_path),
        "sample_count": len(cases),
        "failure_count": len(failures),
        "failures": failures,
        "metrics": metrics,
        "gate": gate,
        "thresholds": THRESHOLDS,
        "cases": cases,
    }


def compare(baseline: dict, current: dict) -> tuple[bool, list[str]]:
    ok = True
    lines: list[str] = []
    for key, direction in METRIC_DIRECTIONS.items():
        old = (baseline.get("metrics") or {}).get(key)
        new = (current.get("metrics") or {}).get(key)
        if old is None or new is None:
            continue
        delta = new - old
        worse = delta < -0.005 if direction == "up" else delta > 0.005
        if key == "avg_ms":
            worse = new > old * 1.2 and new > 50
        lines.append(f"{key}: {old} → {new}（{'下降' if worse else '无回归'}）")
        ok = ok and not worse
    return ok, lines


def format_summary(result: dict) -> str:
    m = result["metrics"]
    g = result["gate"]
    lines = [
        f"引擎：{result.get('engine_mode', 'rules')}（模型={result.get('model') or '无'}，大模型插件默认关闭）",
        f"测试集：{result['testset']}（v2 标注），样例 {result['sample_count']} 条，执行失败 {result['failure_count']} 条",
        f"词库：{result['lexicon_version']}；套路库：{result['pattern_db_version']}（{result['pattern_count']} 条）",
        "",
        f"整体结论准确率      {m['overall_exact']:.2%}",
        f"高危召回率(red)     {m['red_recall']:.2%}  (≥90%)   {g['red_recall']}",
        f"正常误判红(green→red){m['green_false_red']:.2%}  (≤5%)    {g['green_false_red']}",
        f"中风险报警率(amber) {m['amber_alarm']:.2%}",
        f"维度级准确率        {m['dimension_accuracy']:.2%}  ({m['dimension_hit']}/{m['dimension_checked']})  {g['dimension_accuracy']}",
        f"套路库召回率        {m['pattern_recall']:.2%}  ({m['pattern_hit']}/{m['pattern_total']})  {g['pattern_recall']}",
        f"套路库精确率        {m['pattern_precision']:.2%}",
        f"证据可追溯率(脱敏前){m['evidence_traceable']:.2%}          {g['evidence_traceable']}",
        f"context 自洽率      {m['context_consistent']:.2%}          {g['context_consistent']}",
        f"输出层 PII 泄漏      {m['pii_leaks']} 处（硬要求 0）    {g['pii_zero_leak']}",
        f"灰灯追问率          {m['grey_question_rate']:.2%}",
        f"平均耗时            {m['avg_ms']:.2f} ms（p95 {m['p95_ms']:.2f} ms）{g.get('schema')}",
        f"schema 通过率       {m['schema_pass_rate']:.2%}          {g['schema']}",
        "",
        f"证据校验删除条数    {m['findings_dropped_total']}",
        f"等级校准次数        {m['calibration_adjust_total']}",
        f"模型重试案例        {m['model_retry_cases']}",
        f"整体结论分布        {m['level_dist']}",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    parser = argparse.ArgumentParser(prog="python -m engine.evaluate", description="识别引擎评测 v2")
    parser.add_argument("--index", help="测试集 index.jsonl，默认 data/testset/index.jsonl")
    parser.add_argument("--out", help="评测结果 JSON 输出路径，默认 data/eval/eval_report.json")
    parser.add_argument("--model", default="mock", choices=["mock", "deepseek"])
    parser.add_argument("--no-mock-defects", action="store_true", help="Mock 不注入缺陷（对照实验）")
    parser.add_argument("--limit", type=int, help="只跑前 N 条")
    parser.add_argument("--compare", help="与上一版评测结果比对，指标下降则退出码 3")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    result = evaluate(
        Path(args.index) if args.index else None,
        model_name=args.model,
        defects=not args.no_mock_defects,
        limit=args.limit,
    )
    out = Path(args.out) if args.out else PROJECT_ROOT / "data" / "eval" / "eval_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    if not args.quiet:
        print(format_summary(result))
    print(f"\n评测结果已写入 {out}")

    exit_code = 0
    if any(v == "fail" for v in result["gate"].values()):
        exit_code = 2
        print("\n[不达标] 有指标未过门槛，见上方 fail 项", file=sys.stderr)

    if args.compare:
        baseline = json.loads(Path(args.compare).read_text(encoding="utf-8"))
        ok, lines = compare(baseline, result)
        print("\n[回归比对]")
        for line in lines:
            print("  " + line)
        if not ok:
            exit_code = 3
            print("  结论：指标下降，按回归规则不能上线", file=sys.stderr)
        else:
            print("  结论：无回归")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
