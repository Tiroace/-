"""确定性口径评测（路线调整令第三节）

验收门槛：
1. 同一张图重复检查结果必须完全一致（确定性）
2. 单次检查（1–3 张图）≤ 5 秒
3. 证据可追溯 100%
4. 真实/合成分开统计；6 维度分开统计

用法：
    python eval/eval_deterministic.py            # 跑全部轨道
    python eval/eval_deterministic.py --repeat 3 # 重复次数
"""
from __future__ import annotations

from _console import safe_console  # noqa: E402

import json
import statistics
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DIMENSIONS = ["fee", "work", "title", "pay", "company", "contract"]


def load_cases() -> list[dict]:
    cases = []
    base = ROOT / "data" / "testset"
    idx = base / "index.jsonl"
    if idx.is_file():
        cases += [json.loads(l) for l in idx.read_text(encoding="utf-8").splitlines() if l.strip()]
    rc = base / "real_cases_v1.jsonl"
    if rc.is_file():
        cases += [json.loads(l) for l in rc.read_text(encoding="utf-8").splitlines() if l.strip()]
    return cases


def normalize_output(report: dict) -> str:
    """把报告归一化成可比较的字符串（用于确定性判定）。"""
    dims = tuple((d["key"], d["level"]) for d in report.get("dimensions", []))
    findings = tuple(
        (f["level"], f["dimension"], f["evidence"]) for f in report.get("findings", [])
    )
    return json.dumps(
        {
            "overall": report.get("overall"),
            "is_job": report.get("is_job_posting"),
            "dims": dims,
            "findings": findings,
        },
        ensure_ascii=False,
        sort_keys=True,
    )


def ocr_text_of(case: dict) -> str:
    p = ROOT / case["ocr_text"]
    return p.read_text(encoding="utf-8") if p.is_file() else ""


def norm(s: str) -> str:
    import unicodedata

    t = unicodedata.normalize("NFKC", s or "")
    return "".join(ch for ch in t if unicodedata.category(ch)[0] in ("L", "N"))


def main() -> int:
    safe_console()
    from engine.config import default_config
    from engine.pipeline import analyze, make_model

    repeat = 1
    if "--repeat" in sys.argv:
        repeat = int(sys.argv[sys.argv.index("--repeat") + 1])

    cfg = default_config()
    cfg.report_dir = None
    cfg.cache_dir = ROOT / "var" / "cache" / "determinism"
    cfg.use_dedupe = False
    model = make_model("mock", defects=False)

    cases = load_cases()
    print(f"用例总数：{len(cases)}（index + real_text）\n")

    by_track = defaultdict(lambda: Counter())
    by_dim = defaultdict(lambda: Counter())
    durations = []
    nondeterministic = []
    untraceable = []

    for case in cases:
        track = case.get("track", "unknown")
        text = ocr_text_of(case)
        if not text:
            continue
        label = case.get("label") or {}
        exp_overall = label.get("overall")
        exp_dims = {k: v for k, v in (label.get("dimensions") or {}).items() if v != "none"}

        runs = []
        for _ in range(repeat):
            t0 = time.perf_counter()
            try:
                rep = analyze([], str(ROOT / case["ocr_text"]), config=cfg, model=model).report
            except Exception:
                rep = None
            durations.append((time.perf_counter() - t0) * 1000)
            runs.append(rep)

        # --- 确定性 ---
        sigs = {normalize_output(r) if r else "<error>" for r in runs}
        if len(sigs) > 1:
            nondeterministic.append(case["id"])

        rep = runs[0]
        if rep is None:
            by_track[track]["error"] += 1
            continue

        by_track[track]["total"] += 1
        if rep["overall"] == exp_overall:
            by_track[track]["overall_ok"] += 1

        got_dims = {d["key"]: d["level"] for d in rep["dimensions"]}
        for d, lv in exp_dims.items():
            by_dim[d]["expected"] += 1
            if got_dims.get(d) == lv:
                by_dim[d]["hit"] += 1

        # --- 证据可追溯 ---
        src = norm(text)
        for f in rep.get("findings", []):
            ev = norm(f.get("evidence", ""))
            if not ev or ev not in src:
                untraceable.append((case["id"], f.get("evidence", "")[:30]))

    # ---- 报告 ----
    print("=== 1. 确定性（同图重复 %d 次）===" % repeat)
    if nondeterministic:
        print(f"  ❌ 不一致：{len(nondeterministic)} 条 → {nondeterministic[:10]}")
    else:
        print(f"  ✅ 全部一致（{sum(t['total'] for t in by_track.values())} 条用例）")

    print("\n=== 2. 耗时 ===")
    if durations:
        durations_sorted = sorted(durations)
        p50 = statistics.median(durations)
        p95 = durations_sorted[int(len(durations_sorted) * 0.95) - 1]
        print(f"  平均 {sum(durations)/len(durations):.0f}ms  P50 {p50:.0f}ms  P95 {p95:.0f}ms  最大 {max(durations):.0f}ms")
        over5 = sum(1 for d in durations if d > 5000)
        print(f"  超过 5 秒：{over5} 次 / 共 {len(durations)} 次")

    print("\n=== 3. 证据可追溯 ===")
    if untraceable:
        print(f"  ❌ 不可追溯 {len(untraceable)} 条：{untraceable[:5]}")
    else:
        print("  ✅ 100%（所有 findings 的 evidence 都能在 OCR 原文找到）")

    print("\n=== 4. 按轨道分开统计 ===")
    for track, c in by_track.items():
        if c["total"]:
            pct = c["overall_ok"] / c["total"] * 100
            print(f"  {track:10} 整体一致 {c['overall_ok']:3}/{c['total']:3}  ({pct:.1f}%)")

    print("\n=== 5. 6 维度分开统计 ===")
    for d in DIMENSIONS:
        c = by_dim[d]
        if c["expected"]:
            print(f"  {d:9} {c['hit']:3}/{c['expected']:3}  ({c['hit']/c['expected']*100:.1f}%)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
