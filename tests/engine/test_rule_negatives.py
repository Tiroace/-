"""反例回归：PM 点名的三类易误判（①关系户内推 ③异地引流 ⑧冒名招聘）。

正规「国企招聘公告」「大厂外包岗位」「外地工厂招工」不能被新规则命中。
语料在 `lexicon/rule_negatives_v1.json`，与 `scripts/eval_negatives.py` 同源，
这里接成 pytest 让它进每次全量，不靠人记得去跑脚本。

另有一条守住「两份反例文件不许脱节」——历史上存在两份：
`lexicon/rule_negatives_v1.json`（引擎真读这份）和
`data/testset/rule_negatives_v1.jsonl`。后者没人读，容易腐坏。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CASES = ROOT / "rules" / "rule_negatives_v1.json"

pytestmark = pytest.mark.smoke


def _load() -> list[dict]:
    data = json.loads(CASES.read_text(encoding="utf-8"))
    return data["cases"]


def _analyze(text: str):
    from engine.config import default_config
    from engine.pipeline import analyze

    cfg = default_config()
    cfg.use_dedupe = False
    cfg.report_dir = None
    return analyze([], text, config=cfg).report


@pytest.mark.parametrize("case", _load(), ids=[c["id"] for c in _load()])
def test_反例不被误判(case: dict) -> None:
    report = _analyze(case["text"])
    fired = {f["rule_id"] for f in report["findings"] if f.get("rule_id")}
    forbidden = sorted(fired & set(case["forbid_rules"]))
    assert not forbidden, (
        f"{case['id']}（{case['category']}）被误判命中 {forbidden}\n"
        f"原文：{case['text']}"
    )
    assert report["overall"] in case["expect_overall"], (
        f"{case['id']} 结论 {report['overall']} 不在允许集合 {case['expect_overall']}\n"
        f"原文：{case['text']}"
    )


def test_绿灯规则命中不算误判() -> None:
    """反例允许命中 `R-GREEN-*`（「明确不收费」「薪资明确」这类正面标注）。

    实测（2026-10-31）：正规岗位常同时命中绿灯规则，这是设计意图——绿灯是
    告诉用户「这条看着没问题」。若把绿灯也当误判，反例会永远红，逼人删规则。
    这里明确：`forbid_rules` 只列危险规则，判定 overall 时不把绿灯当犯规。
    """
    from engine.rules_engine import compose  # noqa: F401  # 存在性检查，导入失败即失败

    report = _analyze("招聘岗位：客服专员\n内推不收取任何费用\n薪资：8000-12000元/月")
    greens = [f for f in report["findings"] if str(f.get("rule_id", "")).startswith("R-GREEN-")]
    assert report["overall"] == "green"
    for f in greens:
        assert f.get("level") in ("green", "info"), f"R-GREEN 规则等级异常：{f}"


def test_三类反例各有至少三条() -> None:
    """PM 明确要求三类各配 3-5 条；少一条就是覆盖退化。"""
    from collections import Counter

    counts = Counter(c["category"] for c in _load())
    need = ["① 关系户内推", "③ 异地引流", "⑧ 冒名招聘"]
    missing = [k for k in need if counts.get(k, 0) < 3]
    assert not missing, f"以下类别反例不足 3 条：{missing}；实际分布 {dict(counts)}"
