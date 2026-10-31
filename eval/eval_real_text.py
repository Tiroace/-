"""确定性引擎在真实话术用例上的准确率（real_text 轨道），练习集/留出集分开报。

用法：
    python eval/eval_real_text.py [--verbose] [--split practice|holdout|all] [--threshold 0.95]

为什么分开报：practice 集上的数字会被后续调规则「刷高」，它不代表真实上线表现；
真正能说明泛化能力的是**冻结的留出集**（eval/splits.json，冻结后不得改动）。
上线验收看留出集，不到线必须红着退出，不能静默通过。
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
SPLITS = ROOT / "eval" / "splits.json"

# 上线验收线：整体结论准确率（docs/11 上线清单 B 组）。练习集只作参考，不设门槛。
ACCEPTANCE = 0.95


def _argv(name: str, default: str | None = None) -> str | None:
    if name in sys.argv:
        idx = sys.argv.index(name)
        if idx + 1 < len(sys.argv):
            return sys.argv[idx + 1]
    return default


def _load_splits() -> dict[str, set[str]]:
    data = json.loads(SPLITS.read_text(encoding="utf-8"))
    return {"practice": set(data.get("practice") or []), "holdout": set(data.get("holdout") or [])}


def _evaluate(rows: list[dict], cfg) -> dict:
    overall_ok = 0
    dim_hit = dim_total = 0
    evidence_ok = 0
    misses = []
    by_dim_miss: Counter = Counter()
    dim_stat: dict[str, list[int]] = {}
    for row in rows:
        text = (ROOT / row["ocr_text"]).read_text(encoding="utf-8")
        report = analyze([], text, config=cfg).report
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
                stat = dim_stat.setdefault(key, [0, 0])
                stat[1] += 1
                if pred_dims.get(key) == gt_dims[key]:
                    dim_hit += 1
                    stat[0] += 1
                else:
                    by_dim_miss[key] += 1
        ok = all(f["evidence"].replace(" ", "") in text.replace(" ", "") for f in report["findings"])
        evidence_ok += 1 if ok else 0
    total = len(rows)
    return {
        "total": total,
        "overall_ok": overall_ok,
        "overall": overall_ok / total if total else 0.0,
        "dim_hit": dim_hit,
        "dim_total": dim_total,
        "dim": dim_hit / dim_total if dim_total else 0.0,
        "evidence": evidence_ok / total if total else 0.0,
        "by_dim_miss": by_dim_miss,
        "dim_stat": dim_stat,
        "misses": misses,
    }


def _report(name: str, res: dict, threshold: float | None) -> bool:
    """打印一组结果；返回是否达到验收线（threshold=None 表示不设门槛）。"""
    total = res["total"]
    print(f"\n【{name}】{total} 条")
    if total == 0:
        print("  （无用例）")
        return False
    print(f"  整体结论准确率：{res['overall_ok']}/{total} = {res['overall']:.1%}")
    print(f"  六维灯色一致率：{res['dim_hit']}/{res['dim_total']} = {res['dim']:.1%}")
    dims = "  ".join(
        f"{k} {v[0]}/{v[1]}" for k, v in sorted(res["dim_stat"].items())
    )
    print(f"  分维度：{dims}")
    print(f"  证据可追溯：{res['evidence']:.1%}")
    if res["by_dim_miss"]:
        print(f"  维度未命中：{dict(res['by_dim_miss'])}")
    if threshold is None:
        print("  验收线：不设门槛（练习集只作参考，不能用来代表泛化能力）")
        return True
    ok = res["overall"] >= threshold
    state = "达标" if ok else "**未达验收线**"
    print(f"  验收线：{threshold:.0%} → {state}（差 {(threshold - res['overall']) * 100:+.1f} 个百分点）")
    return ok


def main() -> int:
    verbose = "--verbose" in sys.argv
    only = _argv("--split", "all")
    threshold = float(_argv("--threshold", str(ACCEPTANCE)) or ACCEPTANCE)
    cfg = default_config()
    cfg.use_dedupe = False
    cfg.report_dir = None
    splits = _load_splits()
    rows = [json.loads(line) for line in CASES.read_text(encoding="utf-8").splitlines() if line.strip()]
    tagged = {row["id"]: ("holdout" if row["id"] in splits["holdout"] else "practice") for row in rows}

    print(f"引擎：确定性规则（rules_version={cfg.rules_version}）")
    print(f"用例：{len(rows)} 条（real_text，划分 {SPLITS.name} 冻结）")

    groups: dict[str, list[dict]] = {"practice": [], "holdout": []}
    unassigned = []
    for row in rows:
        tag = tagged.get(row["id"])
        if tag is None:
            unassigned.append(row["id"])
        else:
            groups[tag].append(row)
    without_split = [row for row in rows if row["id"] not in splits["practice"] and row["id"] not in splits["holdout"]]

    results = {name: _evaluate(group, cfg) for name, group in groups.items()}
    if without_split:
        results["未划分（不计入验收）"] = _evaluate(without_split, cfg)

    ok = True
    for name, res in results.items():
        # 只有留出集代表泛化能力，练习集不设门槛
        show_threshold = threshold if (name == "holdout" and only in ("all", "holdout")) else None
        passed = _report(name, res, show_threshold)
        if show_threshold is not None:
            ok = ok and passed
        if verbose:
            print(f"  未命中明细（{len(res['misses'])} 条）：")
            for item in res["misses"][:20]:
                print("    ", item)

    print()
    print("口径说明：练习集用于调规则，数字会偏高；留出集冻结、只用来看泛化，上线验收以留出集为准。")
    if unassigned:
        print(f"注意：{len(unassigned)} 条用例不在 splits.json 里：{unassigned[:10]}")
    if not ok:
        print("结果：留出集未达上线验收线，不能据此发布新的 rules_version。")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
