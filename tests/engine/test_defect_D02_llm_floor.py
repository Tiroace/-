"""回归测试 · D-02 的去模型化收口（路线调整令后）

【历史】D-02 原为：`source=llm` 但带 rule_id 的发现绕过了词库等级下限，
属真缺陷，已修复。

【现状（2026-10-31 路线调整令）】一期不接大模型，`source` 只允许 `rule` / `pattern`，
**`llm` 来源已彻底移除**。原 D-02 的缺陷场景不复存在。

本文件改为守住两件事：
1. 报告里不允许再出现 `source=llm`（防止有人把模型插件重新打开后漏标）
2. 等级下限回拉对 `rule` 来源生效（D-01/D-02 的防线不回归）
"""
from __future__ import annotations

import pytest

from conftest import ROOT, run_engine, assert_report_v2

pytestmark = pytest.mark.smoke

RANK = {"red": 3, "amber": 2, "green": 1, "none": 0}
ALLOWED_SOURCES = {"rule", "pattern"}


def test_报告里不允许出现llm来源(tmp_path):
    """路线令：一期不接大模型，source 只有 rule/pattern。"""
    text = """高薪招聘 兼职刷单 日结300元
入职需缴纳服装费980元、押金500元
"""
    report, _ = run_engine(text, tmp_path=tmp_path)
    assert_report_v2(report)
    bad = [f["source"] for f in report["findings"] if f["source"] not in ALLOWED_SOURCES]
    assert not bad, f"报告出现非 rule/pattern 的来源：{bad}"


def test_全部样例报告都不含llm(tmp_path):
    """遍历测试集样例，确保没有任何一条报告残留 llm 来源。"""
    ocr_dir = ROOT / "data" / "testset" / "ocr"
    files = sorted(ocr_dir.glob("*.txt"))[:10]
    assert files, "测试集 ocr 目录为空"
    bad = []
    for p in files:
        text = p.read_text(encoding="utf-8")
        report, _ = run_engine(text, tmp_path=tmp_path)
        for f in report.get("findings", []):
            if f.get("source") not in ALLOWED_SOURCES:
                bad.append((p.name, f.get("source")))
    assert not bad, f"以下样例出现非法来源：{bad[:5]}"


def test_规则来源的下限回拉生效():
    """D-01/D-02 的真相：校准必须把被压低的 level 拉回词库下限。"""
    from engine.calibrate import calibrate
    from engine.lexicon import load_lexicon, scan
    from conftest import LEXICON_PATH

    lexicon = load_lexicon(LEXICON_PATH)
    text = "合同期一年，试用期六个月"
    hits = scan(text, lexicon)
    if not hits:
        pytest.skip("词库未命中该规则，词库可能已调整")

    finding = {
        "level": "green",           # 人为压低
        "dimension": "contract",
        "title": "试用期太长",
        "evidence": "合同期一年，试用期六个月",
        "context": "合同期一年，试用期六个月",
        "reason": "试用期偏长",
        "source": "rule",
        "pattern_id": None,
        "rule_id": hits[0].rule_id,
    }
    result = calibrate([finding], hits, [])
    assert result.findings, "校准把发现项全删了"
    got = result.findings[0]["level"]
    assert RANK[got] >= RANK["amber"], (
        f"校准未把 green 拉回下限，实际 {got}；调整记录={result.adjustments}"
    )


def test_端到端_非法条款保持amber(tmp_path):
    """端到端：试用期超期等非法条款不得判绿。"""
    checked = 0
    for sid in ("S0012", "S0013", "S0014", "T012", "T013", "T014"):
        p = ROOT / "data" / "testset" / "ocr" / f"{sid}.txt"
        if not p.is_file():
            continue
        checked += 1
        text = p.read_text(encoding="utf-8")
        report, _ = run_engine(text, tmp_path=tmp_path)
        assert_report_v2(report)
        assert RANK[report["overall"]] >= RANK["amber"], (
            f"{sid} overall={report['overall']}，非法条款不该判绿"
        )
    if checked == 0:
        pytest.skip("找不到对应样例")
