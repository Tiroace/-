"""命令行入口。

用法：
    python -m engine.cli analyze --images data/testset/images/T001.png --ocr-text data/testset/ocr/T001.txt --out report.json
    python -m engine.cli analyze --ocr-text data/testset/ocr/T001.txt --out report.json
    python -m engine.cli scan --ocr-text data/testset/ocr/T001.txt
    python -m engine.cli info
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import default_config
from .lexicon import load_lexicon, scan
from .pipeline import (
    ERR_CONTENT_BLOCKED,
    ERR_MODEL_FAILED,
    ERR_OCR_UNAVAILABLE,
    ERR_SCHEMA_FAILED,
    AnalysisError,
    analyze,
    make_model,
)
from .schema import validate_report

EXIT_CODES = {
    ERR_OCR_UNAVAILABLE: 3,
    ERR_CONTENT_BLOCKED: 4,
    ERR_MODEL_FAILED: 5,
    ERR_SCHEMA_FAILED: 6,
}


def _setup_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def _print_json(obj: object) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def cmd_analyze(args: argparse.Namespace) -> int:
    cfg = default_config()
    if args.lexicon:
        cfg.lexicon_path = Path(args.lexicon)
    if args.no_dedupe:
        cfg.use_dedupe = False
    if args.no_report_dir:
        cfg.report_dir = None

    images = [Path(p) for p in (args.images or [])]
    missing = [p for p in images if not p.is_file()]
    if missing and not args.ocr_text:
        print(f"[错误] 图片不存在：{', '.join(str(p) for p in missing)}", file=sys.stderr)
        return 2
    if missing:
        print(f"[提示] 图片不存在，按 OCR 旁路文本继续：{', '.join(str(p) for p in missing)}", file=sys.stderr)
        images = []

    try:
        model = make_model(args.model, defects=not args.no_mock_defects)
        result = analyze(images, args.ocr_text, config=cfg, model=model)
    except AnalysisError as exc:
        print(f"[失败] {exc.code}：{exc.message}", file=sys.stderr)
        if exc.detail:
            print(json.dumps(exc.detail, ensure_ascii=False, indent=2), file=sys.stderr)
        return EXIT_CODES.get(exc.code, 1)

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result.report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[完成] 报告已写入 {out}", file=sys.stderr)
    else:
        _print_json(result.report)

    if args.trace_out:
        path = Path(args.trace_out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result.trace, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.print_trace:
        _print_json(result.trace)

    trace = result.trace
    print(
        "[摘要] 结论={overall} 发现={n} 规则命中={hits} 发现删除={drop} 校准={cal} 耗时={ms}ms".format(
            overall=result.report["overall"],
            n=len(result.report["findings"]),
            hits=trace.get("rule_hit_count", 0),
            drop=len(trace.get("findings_dropped", [])),
            cal=len(trace.get("calibration", [])),
            ms=trace.get("total_ms", 0),
        ),
        file=sys.stderr,
    )
    return 0


def cmd_scan(args: argparse.Namespace) -> int:
    cfg = default_config()
    if args.lexicon:
        cfg.lexicon_path = Path(args.lexicon)
    lexicon = load_lexicon(cfg.lexicon_path)
    text = Path(args.ocr_text).read_text(encoding="utf-8") if args.ocr_text else sys.stdin.read()
    hits = scan(text, lexicon)
    print(f"[词库] {lexicon.version}，共 {len(lexicon.rules)} 条规则；命中 {len(hits)} 条")
    for hit in hits:
        flag = "硬证据" if hit.hard else "软信号"
        print(f"  - {hit.rule_id} [{hit.type}/{hit.level}/{flag}] 原文：{hit.evidence}")
    return 0


def cmd_info(args: argparse.Namespace) -> int:
    cfg = default_config()
    lexicon = load_lexicon(cfg.lexicon_path)
    by_type: dict[str, int] = {}
    for rule in lexicon.rules:
        by_type[rule.type] = by_type.get(rule.type, 0) + 1
    info = {
        "engine_version": __import__("engine").__version__,
        "project_root": str(cfg.root),
        "rules": {
            "path": str(cfg.lexicon_path),
            "version": lexicon.version,
            "rules": len(lexicon.rules),
            "by_type": by_type,
            "hard_rules": sum(1 for r in lexicon.rules if r.hard),
        },
        "model": cfg.model_name,
        "prompt_version": cfg.prompt_version,
        "dedupe": {"enabled": cfg.use_dedupe, "ttl_hours": cfg.dedupe_ttl_hours, "dir": str(cfg.cache_dir)},
    }
    _print_json(info)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m engine.cli", description="面试请等等 · 识别引擎原型")
    sub = parser.add_subparsers(dest="command", required=True)

    p_analyze = sub.add_parser("analyze", help="分析一组截图，输出 §4.3 结构的报告 JSON")
    p_analyze.add_argument("--images", nargs="+", help="截图路径，1–3 张")
    p_analyze.add_argument("--ocr-text", help="OCR 旁路文本文件（原型期没有云 OCR 时用）")
    p_analyze.add_argument("--out", help="报告 JSON 输出路径；不写则打印到 stdout")
    p_analyze.add_argument("--trace-out", help="链路轨迹 JSON 输出路径（耗时/命中/删除/校准）")
    p_analyze.add_argument("--model", default="mock", choices=["mock", "deepseek"], help="模型适配器")
    p_analyze.add_argument("--lexicon", help="词库路径，默认 lexicon/lexicon_v1.json")
    p_analyze.add_argument("--no-dedupe", action="store_true", help="关闭 24 小时去重")
    p_analyze.add_argument("--no-report-dir", action="store_true", help="不写 var/reports")
    p_analyze.add_argument("--no-mock-defects", action="store_true", help="Mock 不注入缺陷（用于对照）")
    p_analyze.add_argument("--print-trace", action="store_true", help="把链路轨迹打印到 stdout")
    p_analyze.set_defaults(func=cmd_analyze)

    p_scan = sub.add_parser("scan", help="只跑规则初筛，看词库命中")
    p_scan.add_argument("--ocr-text", help="OCR 文本文件；不传则从 stdin 读")
    p_scan.add_argument("--lexicon", help="词库路径")
    p_scan.set_defaults(func=cmd_scan)

    p_info = sub.add_parser("info", help="打印引擎/词库/模型配置")
    p_info.set_defaults(func=cmd_info)
    return parser


def main(argv: list[str] | None = None) -> int:
    _setup_console()
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
