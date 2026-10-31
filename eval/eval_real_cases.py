"""用引擎跑真实话术用例，验证识别效果

这是这批素材的核心价值：不是「收了素材」，而是「验证规则能识别多少真实骗术」。

用法：python eval/eval_real_cases.py
"""
from __future__ import annotations

from _console import safe_console  # noqa: E402

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

CASES = ROOT / "data" / "testset" / "real_cases_v1.jsonl"


def main() -> int:
    safe_console()
    from engine.config import default_config
    from engine.pipeline import analyze, make_model

    cfg = default_config()
    cfg.report_dir = None
    cfg.cache_dir = ROOT / "var" / "cache" / "real_eval"
    cfg.use_dedupe = False
    model = make_model("mock", defects=False)

    rows = [json.loads(l) for l in CASES.read_text(encoding="utf-8").splitlines() if l.strip()]
    print(f"用例数：{len(rows)}\n")

    stats = Counter()
    misses = []
    by_dim = Counter()
    dim_hit = Counter()

    for r in rows:
        ocr_path = ROOT / r["ocr_text"]
        text = ocr_path.read_text(encoding="utf-8")
        expected = r["label"]["overall"]
        exp_dims = {k: v for k, v in r["label"]["dimensions"].items() if v != "none"}

        try:
            result = analyze([], str(ocr_path), config=cfg, model=model)
            report = result.report
        except Exception as e:  # noqa: BLE001
            stats["error"] += 1
            misses.append((r["id"], "执行失败：" + str(e)[:60]))
            continue

        got = report["overall"]
        got_dims = {d["key"]: d["level"] for d in report["dimensions"]}

        stats["total"] += 1
        if got == expected:
            stats["overall_exact"] += 1
        elif expected == "red" and got in ("red", "amber"):
            stats["overall_partial"] += 1
        else:
            stats["overall_miss"] += 1
            for f in report.get("findings", [])[:1]:
                pass
            misses.append((r["id"], f"期望 {expected} 实得 {got}｜{text.strip().splitlines()[0][:40]}"))

        for d, lv in exp_dims.items():
            by_dim[d] += 1
            if got_dims.get(d) == lv:
                dim_hit[d] += 1
            elif got_dims.get(d) in ("red", "amber") and lv in ("red", "amber"):
                dim_hit[d] += 0  # 等级不同但都报警，单独计
                stats["dim_level_off"] += 1

    total = stats["total"]
    print("=== 整体结论 ===")
    print(f"  完全一致：{stats['overall_exact']}/{total}  ({stats['overall_exact']/max(1,total)*100:.1f}%)")
    print(f"  方向正确（红判成红或黄）：{stats['overall_partial']}")
    print(f"  漏判/错判：{stats['overall_miss']}")
    if stats["error"]:
        print(f"  执行失败：{stats['error']}")

    print("\n=== 维度级命中 ===")
    for d in ["fee", "work", "title", "pay", "company", "contract"]:
        if by_dim[d]:
            print(f"  {d:9} {dim_hit[d]}/{by_dim[d]}")

    if misses:
        print(f"\n=== 未命中明细（前 15 条）===")
        for cid, why in misses[:15]:
            print(f"  {cid}: {why}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
