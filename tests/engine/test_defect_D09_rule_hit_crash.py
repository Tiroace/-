"""缺陷回归测试 · D-09：规则命中的截图必须能跑通（引擎不能崩）

【缺陷单号】D-09（软件测试者 2026-10-31 17:30 发现，P0）
【现象】`engine/lexicon.py` 构造 `RuleHit` 时漏传 `why/law/questions/verify`，
       而 `to_dict()` 引用 `self.why` → 任何**规则命中**的截图都会
       `AttributeError: 'RuleHit' object has no attribute 'why'`。
【影响】主流程直接不可用；越是骗局命中越多，越容易崩。

本文件是冒烟级防线：**任何版本，只要有规则命中就必须能出报告**。
"""
from __future__ import annotations

import pytest

from conftest import ROOT, run_engine, assert_report_v2

pytestmark = pytest.mark.smoke

# 明确带硬规则命中的文本（刷单 + 垫付 + 押金）
HIT_TEXT = """【兼职招聘】日结高薪
工作内容：在家用手机给商家刷单，完成任务立返佣金
流程：加客服微信领取任务单，垫付货款后截图返款
首次垫付 100 元，返 130 元，当天到账
入职需缴纳押金 500 元
"""


def test_规则命中时能正常出报告(tmp_path):
    """D-09 核心：命中规则的截图不能崩。"""
    report, trace = run_engine(HIT_TEXT, tmp_path=tmp_path)
    assert report is not None, "命中规则的图片没有产出报告"
    assert_report_v2(report)
    # 必须真的有命中，否则这条用例没测到东西
    assert trace.get("rule_hit_count", 0) >= 1, (
        f"样例没有产生规则命中（rule_hit_count={trace.get('rule_hit_count')}），用例失效"
    )


def test_规则命中详情可序列化(tmp_path):
    """命中详情要能转成 dict（trace 里会序列化，这里正是崩溃点）。"""
    report, trace = run_engine(HIT_TEXT, tmp_path=tmp_path)
    hits = trace.get("rule_hits") or []
    assert hits, "trace 里没有 rule_hits"
    for h in hits:
        assert isinstance(h, dict), f"rule_hits 元素不是 dict：{type(h)}"
        for key in ("rule_id", "dimension", "level", "evidence"):
            assert key in h, f"rule_hits 缺字段 {key}"


def test_测试集里有命中的样例全部能跑通(tmp_path):
    """遍历测试集中已知会命中的样例，全部必须出报告。"""
    checked = 0
    failures = []
    for sid in ("T001", "T002", "T003", "T004", "T005", "T006", "T007"):
        p = ROOT / "data" / "testset" / "ocr" / f"{sid}.txt"
        if not p.is_file():
            continue
        checked += 1
        text = p.read_text(encoding="utf-8")
        try:
            report, _ = run_engine(text, tmp_path=tmp_path)
            assert_report_v2(report)
        except Exception as e:  # noqa: BLE001
            failures.append(f"{sid}: {type(e).__name__}: {e}")
    if checked == 0:
        pytest.skip("找不到可测样例")
    assert not failures, "以下样例跑不通：\n" + "\n".join(failures)
