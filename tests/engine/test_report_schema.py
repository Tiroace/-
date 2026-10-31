"""引擎契约测试 · 报告 schema v2（docs/09-改版实施计划.md §二）

不依赖引擎内部实现，只按「报告 JSON 应该长什么样」独立断言。
任何一条失败 = 前端渲染或后端入库会出问题，属阻断级。

> v2 改版（2026-10-31）：旧 §4.3 的 risk_level/risks/verdict 作废，
> 新版为 overall + 6 维度 + findings。详见 tests/engine/test_report_v2.py。
"""
from __future__ import annotations

import pytest

from conftest import run_engine, assert_report_v2
HIGH_RISK_TEXT = """高薪招聘 兼职刷单 日结300元
入职需缴纳服装费980元、押金500元，离职退还
联系方式：13800138000
"""

SAFE_TEXT = """招聘岗位：前端开发工程师
公司：某科技有限公司
薪资：15-25K，五险一金，双休
要求：本科及以上，3 年经验
面试地点：公司总部
"""

NON_JOB_TEXT = """今天天气不错，和朋友去公园散步，晚上吃了火锅。
"""

def _analyze(text, tmp_path):
    report, trace = run_engine(text, tmp_path=tmp_path)
    return report, trace


class Test报告结构:
    """v2 结构契约。"""

    def test_高危样例报告结构合法(self, tmp_path):
        report, _ = _analyze(HIGH_RISK_TEXT, tmp_path)
        assert_report_v2(report)

    def test_正常样例报告结构合法(self, tmp_path):
        report, _ = _analyze(SAFE_TEXT, tmp_path)
        assert_report_v2(report)

    def test_非招聘文本报告结构合法(self, tmp_path):
        report, _ = _analyze(NON_JOB_TEXT, tmp_path)
        assert_report_v2(report)

    def test_没有未定义字段泄漏到前端(self, tmp_path):
        report, _ = _analyze(HIGH_RISK_TEXT, tmp_path)
        allowed = {
            "is_job_posting", "overall", "summary", "dimensions", "findings",
            "questions_to_ask", "how_to_verify", "rules_version", "pattern_db_version",
        }
        extra = set(report) - allowed
        assert not extra, f"报告出现 v2 未定义字段：{sorted(extra)}"

    def test_questions与how_to_verify非空(self, tmp_path):
        """报告必须给用户「去问什么 / 怎么核实」，空数组等于没给建议。"""
        report, _ = _analyze(HIGH_RISK_TEXT, tmp_path)
        assert isinstance(report["questions_to_ask"], list) and report["questions_to_ask"]
        assert isinstance(report["how_to_verify"], list) and report["how_to_verify"]

    def test_rules_version格式(self, tmp_path):
        report, _ = _analyze(SAFE_TEXT, tmp_path)
        # 路线令：prompt_version → rules_version，版本号随规则迭代上升，只校验格式
        import re

        assert re.match(r"^v\d+\.\d+$", report["rules_version"]), (
            f"rules_version 格式应为 vX.Y：{report['rules_version']}"
        )


class Test整体结论:
    """「红灯绝不能被文案稀释」这类红线。"""

    def test_高危文本不得判为绿(self, tmp_path):
        report, _ = _analyze(HIGH_RISK_TEXT, tmp_path)
        if report["is_job_posting"]:
            assert report["overall"] in {"red", "amber"}, (
                f"含押金/刷单的文本被判为 {report['overall']}"
            )
            assert report["overall"] != "green", "识别出风险却给绿灯，会误导用户"

    def test_正常文本不应被判红(self, tmp_path):
        report, _ = _analyze(SAFE_TEXT, tmp_path)
        assert report["overall"] != "red", "正常岗位被判红灯＝误判，会吓跑用户"

    def test_非招聘文本为unknown且无红灯发现(self, tmp_path):
        report, _ = _analyze(NON_JOB_TEXT, tmp_path)
        if report["is_job_posting"] is False:
            assert report["overall"] == "unknown"
            reds = [f for f in report["findings"] if f["level"] == "red"]
            assert reds == [], f"非招聘文本不应有红灯发现：{reds}"

# 路线调整令第九节：本文件属「快跑冒烟」核心防线
pytestmark = pytest.mark.smoke
