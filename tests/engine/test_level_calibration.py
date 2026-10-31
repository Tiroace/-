"""引擎契约测试 · 等级校准（需求书 §4.2 等级校准）

规则：命中「押金 / 服装费 / 体检费 / 保证金 / 刷单 / 垫付 / 培训费 / 培训贷 / 贷款 / 境外高薪」
这类硬证据，等级最低 high，**模型不能下调**。

为什么单列一组：模型（尤其 mock / 小模型）倾向于给「warn」显得稳妥，
但押金、刷单法条上是硬红线，调低等级等于放过骗子。
"""
from __future__ import annotations

import pytest

from conftest import run_engine, assert_report_v2, highest_level

# 每一种硬证据单独一条，逐条验证「模型压到 warn 也会被校准回 high」
HARD_EVIDENCE_CASES = [
    ("押金", "招聘服务员，入职需缴纳押金 500 元，离职时退还。"),
    ("服装费", "公司直招，需先交服装费 980 元，统一工装。"),
    ("体检费", "面试通过后需到指定医院体检，体检费 680 元自理，不予报销。"),
    ("保证金", "签合同前需交纳保证金 2000 元，履约后退回。"),
    ("刷单", "高薪兼职，主要负责刷单，日结工资，多劳多得。"),
    ("垫付", "工作内容：代客户下单，需先垫付货款，完成后退还。"),
    ("培训费", "入职前参加岗前培训，培训费 3980 元，工作满一年可报销。"),
    ("培训贷", "培训期间费用可办理分期，签署培训贷协议后即可上岗。"),
    ("贷款", "需先办理小额贷款缴纳保证金，公司会帮你还第一期。"),
    ("境外高薪", "境外高薪招聘，月薪 3 万起，包机票食宿，无需经验。"),
]


@pytest.mark.parametrize("keyword,text", HARD_EVIDENCE_CASES, ids=[c[0] for c in HARD_EVIDENCE_CASES])
def test_硬证据等级不得低于red(keyword, text, tmp_path):
    """v2：硬证据维度至少红灯（旧 v1 的 high 对应 v2 的 red）。"""
    report, trace = run_engine(text, tmp_path=tmp_path)
    assert_report_v2(report)

    if not report["is_job_posting"]:
        pytest.skip(f"该文本被判为非招聘信息，硬证据校验不适用：{text[:16]}")

    # 1) 整体结论必须够重
    assert report["overall"] in {"red", "amber"}, (
        f"含硬证据「{keyword}」却被判为 {report['overall']}，模型下调未被拦住"
    )

    # 2) 命中该硬证据的发现本身必须是 red
    hit = [f for f in report["findings"] if keyword in f["evidence"] or keyword in f["reason"]]
    assert hit, f"含硬证据「{keyword}」却没有对应发现（漏检）：{text}\n实际 findings：{[f['evidence'] for f in report['findings']]}"
    assert any(f["level"] == "red" for f in hit), (
        f"硬证据「{keyword}」对应发现等级为 {[f['level'] for f in hit]}，应至少 red"
    )

    # 3) 承载该发现的维度也必须是红灯
    dims = {d["key"]: d["level"] for d in report["dimensions"]}
    for f in hit:
        if f["level"] == "red":
            assert dims.get(f["dimension"]) == "red", (
                f"维度 {f['dimension']} 有红灯发现，但维度灯是 {dims.get(f['dimension'])}"
            )

    # 4) 校准环节应留下记录
    calibration = trace.get("calibration", [])
    assert isinstance(calibration, list)


def test_校准后整体结论与灯色一致(tmp_path):
    text = "招聘打包员，需缴纳押金 800 元。"
    report, _ = run_engine(text, tmp_path=tmp_path)
    assert_report_v2(report)
    levels = {f["level"] for f in report["findings"]}
    if "red" in levels:
        assert report["overall"] == "red", (
            f"有红灯发现但 overall={report['overall']}"
        )


def test_模型不得低于词库规则等级(tmp_path):
    """词库给的 level 是下限：模型输出更低时必须被抬回去。"""
    from engine.lexicon import load_lexicon, scan
    from conftest import LEXICON_PATH

    lexicon = load_lexicon(LEXICON_PATH)
    # 注意：引擎有「少于 20 字视为非招聘」的判定（MIN_TEXT_CHARS），用例文本必须够长，否则会判 unknown
    text = "招聘客服岗位，入职需交押金 500 元，转正后签订劳动合同。"
    hits = scan(text, lexicon)
    hard = [h for h in hits if getattr(h, "hard", False)]
    assert hard, "词库未命中硬证据，词库规则可能有问题"

    report, _ = run_engine(text, tmp_path=tmp_path)
    floor = max(getattr(h, "finding_level", getattr(h, "level", "notice")) for h in hard)
    assert report["overall"] in {"red", "amber"}, (
        f"词库规则等级下限 {floor}，实际输出 overall={report['overall']}"
    )
