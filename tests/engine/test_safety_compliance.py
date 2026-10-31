"""引擎契约测试 · 安全与合规红线（需求书 §7 / §8）

这组测试守住「上线会被下架 / 会被投诉」的几件事：
1. 报告**不得残留完整手机号、身份证号**等个人信息（输出层必须脱敏）。
2. 报告**不得下「这家公司是骗子」的定论**（只说「这条信息存在 xx 风险」）。
3. 非招聘文本不能被强行输出风险结论。
"""
from __future__ import annotations

import json
import re

import pytest

from conftest import run_engine, assert_report_v2
PHONE = "13800138000"
ID_CARD = "110101199003074415"

PII_TEXT = f"""高薪招聘 兼职刷单 日结300元
联系人电话：{PHONE}
身份证号：{ID_CARD}
入职需缴纳押金 500 元
"""

# 需求书 §7：不下第三方主体定性结论
FORBIDDEN_VERDICTS = [
    "骗子",
    "诈骗公司",
    "黑中介",
    "这家公司是",
    "该公司是骗子",
    "违法公司",
]

class Test个人信息脱敏:
    def test_报告不含完整手机号(self, tmp_path):
        report, _ = run_engine(PII_TEXT, tmp_path=tmp_path)
        raw = json.dumps(report, ensure_ascii=False)
        assert PHONE not in raw, "报告 JSON 里残留完整手机号，属隐私泄露"

    def test_报告不含完整身份证号(self, tmp_path):
        report, _ = run_engine(PII_TEXT, tmp_path=tmp_path)
        raw = json.dumps(report, ensure_ascii=False)
        assert ID_CARD not in raw, "报告 JSON 里残留完整身份证号，属隐私泄露"

    def test_脱敏后仍能定位到证据(self, tmp_path):
        """脱敏不能把证据整条删掉，用户仍要能看懂「哪里有问题」。"""
        report, _ = run_engine(PII_TEXT, tmp_path=tmp_path)
        assert_report_v2(report)
        assert report["findings"], "含押金/刷单的文本应至少有一条发现项"
        assert report["overall"] in {"red", "amber"}


class Test不得下第三方定性结论:
    @pytest.mark.parametrize("word", FORBIDDEN_VERDICTS)
    def test_报告不含定性用词(self, word, tmp_path):
        report, _ = run_engine(PII_TEXT, tmp_path=tmp_path)
        raw = json.dumps(report, ensure_ascii=False)
        assert word not in raw, f"报告出现定性用词「{word}」，违反 §7 合规红线"

    def test_summary只说信息有风险(self, tmp_path):
        report, _ = run_engine(PII_TEXT, tmp_path=tmp_path)
        summary = report["summary"]
        assert summary.strip(), "summary 不能为空"
        assert len(summary) <= 30


class Test非招聘文本处理:
    def test_非招聘不硬编风险(self, tmp_path):
        text = "明天几点开会？记得把发票带过来，下午三点在三楼会议室。"
        report, _ = run_engine(text, tmp_path=tmp_path)
        assert_report_v2(report)
        if report["is_job_posting"] is False:
            assert report["overall"] == "unknown"
            assert report["findings"] == []

# 路线调整令第九节：本文件属「快跑冒烟」核心防线
pytestmark = pytest.mark.smoke
