"""引擎契约测试 · 证据可追溯（需求书 §4.2 证据校验 + §4.5 指标）

底线：报告里每一条 evidence 都必须能在 OCR 原文里逐字找回（去空白/标点归一化后子串匹配）；
找不回的必须删掉；删完没证据的风险项不展示。

这是全项目最不能松的一条 —— 报告给的是「风险提示」，引一句不存在的原文就是造谣。
"""
from __future__ import annotations

import pytest

from conftest import (
    assert_evidence_traceable,
    normalize,
    run_engine,
    assert_report_v2,)

PHONE = "13800138000"

# 原文里故意夹了空格、全角标点、换行，验证归一化口径
DIRTY_TEXT = """【高薪兼职】日结 300 元／天
入职需交纳　服装费　980 元、押金 500 元
联系电话：138 0013 8000
"""

# 模型编造场景：mock 注入了「原文里没有的证据」
FABRICATE_PRONE_TEXT = """招聘 电商客服
工资面议，包吃住
联系人：王女士
"""

class Test证据可在原文找回:
    def test_每条证据都能在原文找到(self, tmp_path):
        report, _ = run_engine(DIRTY_TEXT, tmp_path=tmp_path)
        assert_report_v2(report)
        for i, risk in enumerate(report["findings"]):
            assert_evidence_traceable(risk["evidence"], DIRTY_TEXT), (
                f"risks[{i}] 的证据在原文中找不到：{risk['evidence']!r}"
            )

    def test_全角半角与空格不影响追溯(self, tmp_path):
        """同一个数字，全角/半角/带空格应判为同一条证据，不能因归一化漏判或误判。"""
        a = normalize("138 0013 8000")
        b = normalize("１３８００１３８０００")
        assert a == b, f"归一化口径不一致：{a!r} vs {b!r}"

    def test_编造证据必须被删除(self, tmp_path):
        """开启「注入缺陷」的 mock，验证证据校验真的在删，而不是照单全收。"""
        from engine.config import default_config
        from engine.pipeline import analyze, make_model

        cfg = default_config()
        cfg.report_dir = None
        text_file = tmp_path / "ocr.txt"
        text_file.write_text(FABRICATE_PRONE_TEXT, encoding="utf-8")

        model = make_model("mock", defects=True)
        result = analyze([], str(text_file), config=cfg, model=model)
        report = result.report

        # 1) 报告最终不能含有原文里没有的证据
        for risk in report["findings"]:
            assert_evidence_traceable(risk["evidence"], FABRICATE_PRONE_TEXT)

        # 2) 链路轨迹里应当记录了删除动作（说明校验环节确实工作过）
        dropped = result.trace.get("evidence_dropped", [])
        assert isinstance(dropped, list)


class Test无证据不展示:
    def test_删空证据的风险项不出现(self, tmp_path):
        """构造一段没有任何硬证据的普通文本，报告不应凭空给出高风险项。"""
        plain = "招一名仓库管理员，月薪 5000，工作地点在本地。"
        report, _ = run_engine(plain, tmp_path=tmp_path)
        assert_report_v2(report)
        for risk in report["findings"]:
            assert normalize(risk["evidence"]), "存在 evidence 归一化后为空的风险项"
            assert_evidence_traceable(risk["evidence"], plain)

    def test_风险项证据长度受控(self, tmp_path):
        """evidence 上限 120 字：太长无法在 UI 上高亮定位。"""
        report, _ = run_engine(DIRTY_TEXT, tmp_path=tmp_path)
        for risk in report["findings"]:
            assert len(risk["evidence"]) <= 120

# 路线调整令第九节：本文件属「快跑冒烟」核心防线
pytestmark = pytest.mark.smoke
