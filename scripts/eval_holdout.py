"""第 4 关留出集评测：真实截图上的四项指标。

指标（规范 docs/24 §四）：
  1. 高危召回   ：overall=red 的样本里，引擎也判 red        ≥ 90%
  2. 正常误判   ：is_normal=true 的样本里，引擎判 red/amber ≤ 5%
  3. 证据可追溯 ：findings 的 evidence 能在 OCR 原文里找到  = 100%
  4. 结果一致   ：同一张图跑两次结论完全相同                 = 100%

用法：python scripts/eval_holdout.py [--repeat 2] [--verbose]

为什么误判要把 amber 也算进去：第 4 关的承诺是「正常岗位不该被吓到」。
判黄同样会让用户紧张，所以口径从严；但会分别报 red / amber，便于定位是
规则过严还是等级抖动。

前置：跑 `python scripts/annotate_screenshot.py check` 确认留出集达标。
留出集为空时本脚本**直接失败**，不会返回一个「0 条、100%」的假结果。
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.config import default_config  # noqa: E402
from engine.pipeline import analyze  # noqa: E402

DATA = ROOT / "data" / "testset" / "real_screenshots_v1.jsonl"

MIN_RECALL = 0.90
MAX_WRONG_RED = 0.05


def _norm(t: str) -> str:
    import unicodedata

    t = unicodedata.normalize("NFKC", t or "")
    return "".join(c for c in t if unicodedata.category(c)[0] in ("L", "N"))


def main() -> int:
    verbose = "--verbose" in sys.argv
    repeat = 2
    if "--repeat" in sys.argv:
        try:
            repeat = int(sys.argv[sys.argv.index("--repeat") + 1])
        except (IndexError, ValueError):
            pass

    if not DATA.is_file():
        print(f"✗ 留出集不存在：{DATA}")
        print("  第 4 关评测条件不成立，不能报数。规范见 docs/24-真实截图留出集标注规范.md")
        return 1
    rows = [json.loads(x) for x in DATA.read_text(encoding="utf-8").splitlines() if x.strip()]
    if not rows:
        print("✗ 留出集为空——不能报数（空集的『100%』没有意义）")
        return 1

    cfg = default_config()
    cfg.use_dedupe = False
    cfg.report_dir = None

    red_total = red_hit = 0
    normal_total = normal_red = normal_amber = 0
    evidence_ok = 0
    consistent_ok = 0
    misses: list[tuple] = []
    wrong_normals: list[tuple] = []

    for r in rows:
        rid = r["id"]
        text_file = ROOT / r["ocr_text"]
        if not text_file.is_file():
            print(f"✗ {rid}: OCR 文本不存在 {r['ocr_text']}（先跑 annotate_screenshot）")
            return 1
        text = text_file.read_text(encoding="utf-8")

        report = analyze([], text, config=cfg).report
        got = report["overall"]
        want = (r.get("label") or {}).get("overall")

        # 2. 结果一致：再跑一次（含 repeat>2 时多跑几轮）
        consistent = True
        for _ in range(max(1, repeat - 1)):
            again = analyze([], text, config=cfg).report
            if again["overall"] != got or [d["level"] for d in again["dimensions"]] != [
                d["level"] for d in report["dimensions"]
            ]:
                consistent = False
                break
        consistent_ok += 1 if consistent else 0

        # 3. 证据可追溯
        src = _norm(text)
        ev_ok = all(_norm(f.get("evidence", "")) in src for f in report["findings"])
        evidence_ok += 1 if ev_ok else 0

        # 1. 高危召回
        if want == "red":
            red_total += 1
            if got == "red":
                red_hit += 1
            else:
                misses.append((rid, want, got, (report.get("summary") or "")[:40]))

        # 2. 正常误判
        if r.get("is_normal") is True:
            normal_total += 1
            if got == "red":
                normal_red += 1
                wrong_normals.append((rid, "red", (report.get("summary") or "")[:40]))
            elif got == "amber":
                normal_amber += 1
                wrong_normals.append((rid, "amber", (report.get("summary") or "")[:40]))

    n = len(rows)

    # 【样本量闸门】样本太少时四项指标都可能是 100%——1 条 red 判对就是 100% 召回，
    # 0 条正常就是 0% 误判。这种数字挂出去会误导人，所以先卡样本量：
    # 低于门槛直接判「条件不成立」，不给达标结论（但照样打印指标供参考）。
    MIN_ITEMS = 60
    MIN_NORMAL = 30
    thin: list[str] = []
    if n < MIN_ITEMS:
        thin.append(f"留出集只有 {n} 条 < {MIN_ITEMS} 条")
    if normal_total < MIN_NORMAL:
        thin.append(f"正常样本只有 {normal_total} 条 < {MIN_NORMAL} 条")

    recall = red_hit / red_total if red_total else None
    wrong = (normal_red + normal_amber) / normal_total if normal_total else None
    ev_rate = evidence_ok / n
    con_rate = consistent_ok / n

    print(f"引擎：确定性规则（rules_version={cfg.rules_version}）")
    print(f"留出集：{n} 条真实截图")
    print()
    print(f"高危召回      ：{red_hit}/{red_total}"
          + (f" = {recall:.1%}（要求 ≥{MIN_RECALL:.0%}）" if recall is not None else "（无 red 样本，无法计算）"))
    print(f"正常误判      ：{(normal_red + normal_amber)}/{normal_total}"
          + (f" = {wrong:.1%}（要求 ≤{MAX_WRONG_RED:.0%}）" if wrong is not None else "（无正常样本，无法计算）"))
    print(f"  其中判红 {normal_red} 条、判黄 {normal_amber} 条")
    print(f"证据可追溯    ：{evidence_ok}/{n} = {ev_rate:.1%}（要求 100%）")
    print(f"同一图一致性  ：{consistent_ok}/{n} = {con_rate:.1%}（要求 100%，每图跑 {repeat} 次）")

    if verbose:
        if misses:
            print("\n漏判明细：")
            for m in misses:
                print("  ", m)
        if wrong_normals:
            print("\n正常岗被误判明细：")
            for m in wrong_normals:
                print("  ", m)

    ok = True
    if thin:
        ok = False
        print("\n✗ 样本量不足，评测条件不成立，以上指标仅供参考、不得对外报数：")
        for t in thin:
            print("   ", t)
    if recall is None or recall < MIN_RECALL:
        ok = False
        print("✗ 高危召回未达标")
    if wrong is None or wrong > MAX_WRONG_RED:
        ok = False
        print("✗ 正常误判未达标")
    if ev_rate < 1.0:
        ok = False
        print("✗ 证据可追溯未达标")
    if con_rate < 1.0:
        ok = False
        print("✗ 同一图一致性未达标")

    if ok:
        print("\n✓ 第 4 关四项指标全部达标")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
