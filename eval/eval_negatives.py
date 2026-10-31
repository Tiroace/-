"""反例语料回归：正规场景不能被六维规则误判（PM 点名的三类易误判）。

用法：python eval/eval_negatives.py
"""
from __future__ import annotations

from _console import safe_console  # noqa: E402

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.config import default_config  # noqa: E402
from engine.pipeline import analyze  # noqa: E402

CASES = ROOT / "rules" / "rule_negatives_v1.json"


def main() -> int:
    safe_console()
    cfg = default_config()
    cfg.use_dedupe = False
    cfg.report_dir = None
    data = json.loads(CASES.read_text(encoding="utf-8"))
    ok = 0
    fails = []
    for case in data["cases"]:
        report = analyze([], case["text"], config=cfg).report
        fired = {f["rule_id"] for f in report["findings"] if f.get("rule_id")}
        forbidden = sorted(fired & set(case["forbid_rules"]))
        overall_ok = report["overall"] in case["expect_overall"]
        if not forbidden and overall_ok:
            ok += 1
        else:
            fails.append((case["id"], report["overall"], forbidden))
    total = len(data["cases"])
    print(f"反例语料：{total} 条")
    print(f"通过：{ok}/{total} = {ok / total:.1%}")
    for item in fails:
        print("  [FAIL]", item)
    return 0 if ok == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
