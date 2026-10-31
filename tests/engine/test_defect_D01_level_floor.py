"""缺陷回归测试 · D-01：词库规则等级是下限，模型下调必须被拦截（v2 口径）

【缺陷单号】D-01（软件测试者 2026-10-31 首轮实测发现，v2 改版后已修复）
【严重级】中高（等级偏低 → 用户以为「轻微」而放松警惕，是漏判的实际形态）

【v1 时期的现象】
    文本 T012「合同期一年，试用期六个月」，词库 R-PROBATION-01 等级 warn，
    模型给 notice，校准不拦下调 → 最终 notice（应为 warn）。
    T012/T013/T014 三条同一根因，导致「中低风险等级命中率」只有 57.14%。

【v2 现状（2026-10-31 04:xx 实测）】
    T012 → overall=amber，contract 维度 amber
    T013 → overall=amber，contract 维度 amber
    T014 → overall=amber，contract 维度 amber
    三条都不再被压到最低档，**缺陷已修复**。

本文件保留为回归保护：一旦有人把「下限回拉」改掉，这里会立刻变红。
"""
from __future__ import annotations

import pytest

from conftest import ROOT, run_engine, assert_report_v2
pytestmark = pytest.mark.usefixtures("engine")

# v2 等级：red(3) > amber(2) > green(1)
RANK = {"red": 3, "amber": 2, "green": 1, "none": 0}

# 三条实测被低判的样例：id -> (期望最低等级, 命中规则, 触发文本, 承载维度)
CASES = [
    ("T012", "amber", "R-PROBATION-01", "合同期一年，试用期六个月", "contract"),
    ("T013", "amber", "R-NOSOCIAL-01", "试用期三个月，期间不缴纳社保，转正后补缴", "contract"),
    ("T014", "amber", "R-IDHOLD-01", "入职需上交毕业证原件由公司保管", "contract"),
]


@pytest.mark.parametrize("sample_id, floor, rule_id, snippet, dimension", CASES, ids=[c[0] for c in CASES])

def test_模型不得把规则等级往下压(sample_id, floor, rule_id, snippet, dimension, tmp_path):
    """回归保护：这三条非法条款至少要是 amber（不能掉到 green）。"""
    text = (ROOT / "data" / "testset" / "ocr" / f"{sample_id}.txt").read_text(encoding="utf-8")
    assert snippet in text, f"样例 {sample_id} 内容与预期不符"

    report, _ = run_engine(text, tmp_path=tmp_path)
    assert_report_v2(report)

    # 1) 整体结论不得低于下限
    assert RANK[report["overall"]] >= RANK[floor], (
        f"[D-01 回归] {sample_id}：词库规则 {rule_id} 下限 {floor}，"
        f"实际 overall={report['overall']}"
    )

    # 2) 承载该规则的维度也不得低于下限
    dims = {d["key"]: d["level"] for d in report["dimensions"]}
    assert RANK[dims.get(dimension, "none")] >= RANK[floor], (
        f"[D-01 回归] {sample_id}：{dimension} 维度下限 {floor}，实际 {dims.get(dimension)}"
    )

    # 3) 必须存在对应发现项（不能「等级对但没说出来」）
    hit = [f for f in report["findings"] if f["dimension"] == dimension]
    assert hit, f"[D-01 回归] {sample_id}：{dimension} 维度没有任何发现项，等于漏报"


def test_规则来源的下限回拉生效():
    """D-01 本身：source=rule 的发现被压低时，校准必须拉回词库下限。

    注：source=llm 但带 rule_id 的情况是另一个缺陷（D-02），
    见 tests/engine/test_defect_D02_llm_floor.py。
    """
    from engine.calibrate import calibrate
    from engine.lexicon import load_lexicon, scan as lexicon_scan
    from conftest import LEXICON_PATH

    lexicon = load_lexicon(LEXICON_PATH)
    text = "合同期一年，试用期六个月"
    hits = lexicon_scan(text, lexicon)
    assert hits, "词库没命中 R-PROBATION-01，词库可能被改动"

    model_findings = [
        {
            "level": "green",
            "dimension": "contract",
            "title": "试用期太长",
            "evidence": "合同期一年，试用期六个月",
            "context": "合同期一年，试用期六个月",
            "reason": "试用期偏长",
            "source": "rule",
            "pattern_id": None,
            "rule_id": "R-PROBATION-01",
        }
    ]
    result = calibrate(model_findings, hits, [])

    assert result.findings, "校准把发现项全删了"
    got = result.findings[0]["level"]
    assert RANK[got] >= RANK["amber"], (
        f"[D-01 回归] 校准未把 green 拉回词库下限 amber，实际 {got}；"
        f"调整记录：{result.adjustments}"
    )


def test_规则硬证据仍然兜底红灯(tmp_path):
    """防回归：改 D-01 时不能把硬证据的红灯兜底弄丢。"""
    report, _ = run_engine("招聘打包员\n入职需缴纳押金 800 元，离职退还\n", tmp_path=tmp_path)
    assert report["overall"] == "red", f"押金硬证据应为红灯，实际 {report['overall']}"

# 路线调整令第九节：本文件属「快跑冒烟」核心防线
pytestmark = pytest.mark.smoke
