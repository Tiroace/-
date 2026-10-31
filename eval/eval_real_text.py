"""确定性引擎在真实话术用例上的准确率（real_text 轨道）。

用法：python eval/eval_real_text.py [--verbose]
指标：整体结论准确率（与标注一致）、六维灯色一致率、证据可追溯率。
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.config import default_config  # noqa: E402
from engine.pipeline import analyze  # noqa: E402
from engine.textnorm import DIMENSION_KEYS  # noqa: E402

CASES = ROOT / "data" / "testset" / "real_cases_v1.jsonl"


def main() -> int:
    verbose = "--verbose" in sys.argv
    cfg = default_config()
    cfg.use_dedupe = False
    cfg.report_dir = None
    rows = [json.loads(line) for line in CASES.read_text(encoding="utf-8").splitlines() if line.strip()]
    overall_ok = 0
    dim_hit = dim_total = 0
    evidence_ok = 0
    misses = []
    by_dim_miss = Counter()
    for row in rows:
        text = (ROOT / row["ocr_text"]).read_text(encoding="utf-8")
        res = analyze([], text, config=cfg)
        report = res.report
        label = row.get("label") or {}
        gt_overall = label.get("overall")
        if report["overall"] == gt_overall:
            overall_ok += 1
        else:
            misses.append((row["id"], gt_overall, report["overall"], text.strip().split("\n")[0][:40]))
        gt_dims = label.get("dimensions") or {}
        pred_dims = {d["key"]: d["level"] for d in report["dimensions"]}
        for key in DIMENSION_KEYS:
            if key in gt_dims:
                dim_total += 1
                if pred_dims.get(key) == gt_dims[key]:
                    dim_hit += 1
                else:
                    by_dim_miss[key] += 1
        trace_text = (ROOT / row["ocr_text"]).read_text(encoding="utf-8")
        ok = all(f["evidence"].replace(" ", "") in trace_text.replace(" ", "") for f in report["findings"])
        evidence_ok += 1 if ok else 0

    total = len(rows)
    print(f"引擎：确定性规则（rules_version={cfg.rules_version}）")
    print(f"用例：{total} 条（real_text）")
    print(f"整体结论准确率：{overall_ok}/{total} = {overall_ok / total:.1%}")
    print(f"维度灯色一致率：{dim_hit}/{dim_total} = {dim_hit / dim_total:.1%}")
    print(f"证据可追溯：{evidence_ok}/{total} = {evidence_ok / total:.1%}")
    if by_dim_miss:
        print("维度未命中分布：", dict(by_dim_miss))
    if verbose:
        print("\n未命中明细（前 20）：")
        for item in misses[:20]:
            print("  ", item)
    return 0 if overall_ok / total >= 0.7 else 1


if __name__ == "__main__":
    raise SystemExit(main())
