"""引擎契约测试 · 链路纵深防御（路线调整令后的确定性口径）

【历史】第一轮实测发现 MockModel 会照抄规则命中，导致「证据校验」「等级校准」
被整个关掉也全绿，于是用**故意作恶的假模型**去打这两道防线。

【现状（2026-10-31 路线调整令）】一期不接大模型，`source` 只有 `rule`/`pattern`，
`model` 参数即使传入也不会被调用。原「假模型攻击」场景不存在，
改为直接对**证据校验**与**等级校准**这两个函数做对抗测试——防线本身必须能工作。
"""
from __future__ import annotations

import pytest

from conftest import ROOT, run_engine, assert_report_v2

pytestmark = pytest.mark.smoke

DEPOSIT_TEXT = """招聘打包员
入职需缴纳押金 800 元，离职退还
月薪 6000，包吃住
"""

RANK = {"red": 3, "amber": 2, "green": 1, "none": 0}


class Test证据校验仍然在删:
    def test_编造证据被删除(self):
        """直接打验证函数：原文里找不到的证据必须被删掉。"""
        from engine.evidence import verify_findings

        findings = [
            {
                "level": "red",
                "dimension": "fee",
                "title": "编造安家费",
                "evidence": "入职当天发放 2000 元安家费，工资日结",  # 原文没有
                "context": "入职当天发放 2000 元安家费，工资日结",
                "reason": "编造",
                "source": "rule",
                "pattern_id": None,
                "rule_id": "R-DEPOSIT-01",
            }
        ]
        kept, dropped = verify_findings(findings, DEPOSIT_TEXT)
        assert not kept, f"编造的证据没有被删除：{kept}"
        assert dropped, "删除动作没有记录"

    def test_真实证据被保留(self):
        """反向保护：原文存在的证据不能被误删。"""
        from engine.evidence import verify_findings

        findings = [
            {
                "level": "red",
                "dimension": "fee",
                "title": "先交押金",
                "evidence": "入职需缴纳押金 800 元",
                "context": "入职需缴纳押金 800 元，离职退还",
                "reason": "入职前收押金",
                "source": "rule",
                "pattern_id": None,
                "rule_id": "R-DEPOSIT-01",
            }
        ]
        kept, _ = verify_findings(findings, DEPOSIT_TEXT)
        assert kept, "真实存在的证据被误删了"

    def test_端到端_报告不含编造证据(self, tmp_path):
        report, _ = run_engine(DEPOSIT_TEXT, tmp_path=tmp_path)
        assert_report_v2(report)
        for f in report["findings"]:
            assert "安家费" not in f["evidence"]


class Test等级校准真的在回拉:
    def test_规则等级是下限(self):
        """校准必须把被压低的 level 拉回规则等级。"""
        from engine.calibrate import calibrate
        from engine.lexicon import load_lexicon, scan
        from conftest import LEXICON_PATH

        lexicon = load_lexicon(LEXICON_PATH)
        text = "入职需缴纳押金 800 元"
        hits = scan(text, lexicon)
        if not hits:
            pytest.skip("词库未命中押金规则")

        floor_hit = max(hits, key=lambda h: RANK.get(getattr(h, "finding_level", h.level), 0))
        finding = {
            "level": "green",  # 人为压低
            "dimension": floor_hit.dimension,
            "title": "先交押金",
            "evidence": "入职需缴纳押金 800 元",
            "context": "入职需缴纳押金 800 元",
            "reason": "入职前收押金",
            "source": "rule",
            "pattern_id": None,
            "rule_id": floor_hit.rule_id,
        }
        result = calibrate([finding], hits, [])
        assert result.findings, "校准把发现项全删了"
        got = result.findings[0]["level"]
        floor_level = getattr(floor_hit, "finding_level", floor_hit.level)
        assert RANK[got] >= RANK[floor_level], (
            f"规则下限 {floor_level}，校准后 {got}；记录={result.adjustments}"
        )

    def test_端到端_押金文本必须红灯(self, tmp_path):
        report, _ = run_engine(DEPOSIT_TEXT, tmp_path=tmp_path)
        assert_report_v2(report)
        assert report["overall"] == "red", f"押金文本应为红灯，实际 {report['overall']}"


class Test真实链路:
    def test_来源只允许rule和pattern(self, tmp_path):
        report, _ = run_engine(DEPOSIT_TEXT, tmp_path=tmp_path)
        assert_report_v2(report)
        for f in report["findings"]:
            assert f["source"] in ("rule", "pattern"), f"非法来源：{f['source']}"

    def test_样例全部跑通不崩溃(self, tmp_path):
        """遍历样例，确认没有崩溃、结构合法（D-09 的常驻防线）。"""
        checked, failures = 0, []
        for sid in ("T001", "T002", "T003", "T004", "T005"):
            p = ROOT / "data" / "testset" / "ocr" / f"{sid}.txt"
            if not p.is_file():
                continue
            checked += 1
            try:
                report, _ = run_engine(p.read_text(encoding="utf-8"), tmp_path=tmp_path)
                assert_report_v2(report)
            except Exception as e:  # noqa: BLE001
                failures.append(f"{sid}: {type(e).__name__}: {e}")
        if checked == 0:
            pytest.skip("找不到样例")
        assert not failures, "样例跑不通：\n" + "\n".join(failures)
