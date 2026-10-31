"""报告 JSON v2 契约测试（依据 docs/09-改版实施计划.md §二 + 任务书 §9）

设计原则：
- **先写测试、后落实现**。引擎 v2 尚未落地时，这组用例会失败——这正确反映「v2 未完成」，
  是开发者的验收标尺，不是测试噪音。
- 只认报告 JSON 的表面结构，不 import 引擎内部实现（除读取 OCR 原文做追溯校验）。
- 每条用例的文档串写明它对应任务书 §9 的哪一条验收项。

覆盖 §9 条目：7（4 种 overall）、8（6 维度灰灯补追问）、9（来源标签 + evidence 可追溯，含绿灯）、10（套路命中）
"""
from __future__ import annotations

import json
import re

import pytest

from conftest import ROOT, normalize, run_engine, assert_evidence_traceable

pytestmark = pytest.mark.usefixtures("engine")

# v2 契约常量（来自 docs/09 §二）
DIMENSION_KEYS = ["fee", "work", "title", "pay", "company", "contract"]
DIMENSION_NAMES = {
    "fee": "收费与借贷",
    "work": "工作内容",
    "title": "岗位名称",
    "pay": "薪资待遇",
    "company": "公司信息",
    "contract": "合同社保",
}
OVERALL_LEVELS = {"red", "amber", "green", "unknown"}
DIM_LEVELS = {"red", "amber", "green", "none"}
FINDING_LEVELS = {"red", "amber", "green"}
SOURCES = {"rule", "pattern"}  # 路线令：llm 已移除
LEVEL_RANK = {"red": 3, "amber": 2, "green": 1}
TOP_KEYS = {
    "is_job_posting", "overall", "summary", "dimensions", "findings",
    "questions_to_ask", "how_to_verify", "rules_version", "pattern_db_version",
}

# 高危文本：押金/刷单/垫付，必然有红
RED_TEXT = """高薪招聘 兼职刷单 日结300元
入职需缴纳服装费980元、押金500元，离职退还
流程：加客服微信领取任务单，垫付货款后截图返款
"""

# 正常文本：信息完整，大概率绿
GREEN_TEXT = """招聘岗位：前端开发工程师
公司：某科技有限公司
薪资：15-25K，五险一金，双休
要求：本科及以上，3 年经验
面试地点：公司总部
"""

# 只有薪资含糊，其他维度没提：用于验证灰灯 + 补追问
PARTIAL_TEXT = """招聘运营助理
月薪 3000-30000，上不封顶
"""

NON_JOB_TEXT = """今天天气不错，和朋友去公园散步，晚上吃了火锅。
"""


def _analyze(text, tmp_path, name="ocr.txt"):
    d = tmp_path / name
    d.parent.mkdir(parents=True, exist_ok=True)
    report, trace = run_engine(text, tmp_path=d.parent)
    return report, trace


def _ocr_text_for(sample_id: str) -> str:
    p = ROOT / "data" / "testset" / "ocr" / f"{sample_id}.txt"
    return p.read_text(encoding="utf-8")


# ================================================================ 结构契约

class Test报告v2结构:
    def test_顶层字段齐全且无多余字段(self, tmp_path):
        report, _ = _analyze(RED_TEXT, tmp_path)
        missing = TOP_KEYS - set(report)
        extra = set(report) - TOP_KEYS
        assert not missing, f"报告 v2 缺字段：{sorted(missing)}"
        assert not extra, f"报告 v2 出现未定义字段：{sorted(extra)}"

    def test_旧v1字段必须消失(self, tmp_path):
        """v1 的 risk_level / risks / verdict / risk_score 一律作废，不得残留。"""
        report, _ = _analyze(RED_TEXT, tmp_path)
        v1_keys = {"risk_level", "risks", "verdict", "risk_score"}
        leftover = v1_keys & set(report)
        assert not leftover, f"报告里仍有 v1 字段：{sorted(leftover)}"

    def test_overall取值合法(self, tmp_path):
        report, _ = _analyze(RED_TEXT, tmp_path)
        assert report["overall"] in OVERALL_LEVELS, f"overall 非法：{report['overall']}"

    def test_rules_version格式合法(self, tmp_path):
        report, _ = _analyze(RED_TEXT, tmp_path)
        # 路线令：prompt_version → rules_version，版本随规则迭代上升，只校验格式
        assert re.match(r"^v\d+\.\d+$", str(report["rules_version"])), (
            f"rules_version 格式应为 vX.Y，实际 {report['rules_version']!r}"
        )

    def test_pattern_db_version存在且非空(self, tmp_path):
        report, _ = _analyze(RED_TEXT, tmp_path)
        assert "pattern_db_version" in report, "缺少 pattern_db_version"
        assert isinstance(report["pattern_db_version"], str) and report["pattern_db_version"].strip(), (
            "pattern_db_version 不能为空（报告要能追溯用的是哪一版套路库）"
        )

    def test_summary不超过30字(self, tmp_path):
        report, _ = _analyze(RED_TEXT, tmp_path)
        assert len(report["summary"]) <= 30, f"summary 超 30 字：{len(report['summary'])}"


# ================================================================ 6 维度（§9 第 8 条）

class Test六维度:
    def test_维度必须恰好6项且齐全(self, tmp_path):
        report, _ = _analyze(RED_TEXT, tmp_path)
        dims = report["dimensions"]
        assert isinstance(dims, list), "dimensions 必须是数组"
        keys = [d["key"] for d in dims]
        assert len(dims) == 6, f"dimensions 必须固定 6 项，实际 {len(dims)}"
        assert set(keys) == set(DIMENSION_KEYS), f"维度不符：缺 {set(DIMENSION_KEYS)-set(keys)}，多 {set(keys)-set(DIMENSION_KEYS)}"
        assert len(set(keys)) == 6, f"维度 key 有重复：{keys}"

    def test_维度顺序固定(self, tmp_path):
        report, _ = _analyze(RED_TEXT, tmp_path)
        keys = [d["key"] for d in report["dimensions"]]
        assert keys == DIMENSION_KEYS, f"维度顺序应为 {DIMENSION_KEYS}，实际 {keys}"

    def test_每个维度level合法(self, tmp_path):
        report, _ = _analyze(RED_TEXT, tmp_path)
        for d in report["dimensions"]:
            assert d.get("level") in DIM_LEVELS, f"{d.get('key')} 的 level 非法：{d.get('level')}"

    def test_每个维度short不超过6字且非空(self, tmp_path):
        report, _ = _analyze(RED_TEXT, tmp_path)
        for d in report["dimensions"]:
            short = d.get("short", "")
            assert isinstance(short, str) and short.strip(), f"{d['key']} 的 short 为空"
            assert len(short) <= 6, f"{d['key']} 的 short 超 6 字：{short!r}（{len(short)}）"

    def test_未提到的维度应为灰灯none(self, tmp_path):
        """§9 第 8 条：6 个维度都能出现灰灯「截图里没提到」。"""
        report, _ = _analyze(PARTIAL_TEXT, tmp_path)
        dims = {d["key"]: d["level"] for d in report["dimensions"]}
        # 这段文本只提了薪资，其余维度都有理由为 none
        assert dims["pay"] != "none", "文本明确提了薪资，pay 不该是灰灯"
        grey = [k for k, v in dims.items() if v == "none"]
        assert grey, f"部分信息的文本应至少出现一个灰灯维度，实际 {dims}"

    def test_灰灯维度自动补进追问清单(self, tmp_path):
        """§9 第 8 条：灰灯维度要自动补进 questions_to_ask。"""
        report, _ = _analyze(PARTIAL_TEXT, tmp_path)
        dims = {d["key"]: d["level"] for d in report["dimensions"]}
        grey = [k for k, v in dims.items() if v == "none"]
        if not grey:
            pytest.skip("本样例没有灰灯维度，跳过")

        questions = " ".join(report["questions_to_ask"])
        # 灰灯维度应体现在追问里：用维度中文名或关键词匹配
        dim_keywords = {
            "fee": ["费用", "交钱", "收费", "押金", "交费"],
            "work": ["做什么", "工作内容", "职责", "具体做"],
            "title": ["岗位", "职位", "名称"],
            "pay": ["薪资", "工资", "底薪", "多少"],
            "company": ["公司", "主体", "全称", "企业"],
            "contract": ["合同", "社保", "五险", "试用期"],
        }
        missing = []
        for k in grey:
            kws = dim_keywords.get(k, [])
            if not any(kw in questions for kw in kws):
                missing.append(f"{k}（{DIMENSION_NAMES[k]}，关键词 {kws} 均未出现在追问里）")
        assert not missing, "灰灯维度未补进追问清单：\n" + "\n".join(missing)


# ================================================================ findings（§9 第 9 条）

class Test发现项:
    def test_findings字段齐全(self, tmp_path):
        report, _ = _analyze(RED_TEXT, tmp_path)
        assert isinstance(report["findings"], list)
        for i, f in enumerate(report["findings"]):
            for key in ("level", "dimension", "title", "evidence", "context", "reason", "source", "pattern_id", "rule_id"):
                assert key in f, f"findings[{i}] 缺字段 {key}"

    def test_source只能三选一(self, tmp_path):
        """§9 第 9 条：每条发现都标了来源。"""
        report, _ = _analyze(RED_TEXT, tmp_path)
        for i, f in enumerate(report["findings"]):
            assert f["source"] in SOURCES, f"findings[{i}].source 非法：{f['source']}"

    def test_source与id字段自洽(self, tmp_path):
        report, _ = _analyze(RED_TEXT, tmp_path)
        for i, f in enumerate(report["findings"]):
            if f["source"] == "rule":
                assert f.get("rule_id"), f"findings[{i}] source=rule 但 rule_id 为空"
            if f["source"] == "pattern":
                assert f.get("pattern_id"), f"findings[{i}] source=pattern 但 pattern_id 为空"
            if f["source"] == "llm":
                assert not f.get("rule_id") and not f.get("pattern_id"), (
                    f"findings[{i}] source=llm 却带了 rule_id/pattern_id"
                )

    def test_finding维度必须在6项之内(self, tmp_path):
        report, _ = _analyze(RED_TEXT, tmp_path)
        for i, f in enumerate(report["findings"]):
            assert f["dimension"] in DIMENSION_KEYS, f"findings[{i}].dimension 非法：{f['dimension']}"

    def test_finding_level只能红黄绿(self, tmp_path):
        report, _ = _analyze(RED_TEXT, tmp_path)
        for i, f in enumerate(report["findings"]):
            assert f["level"] in FINDING_LEVELS, f"findings[{i}].level 非法：{f['level']}"

    def test_title长度4到8字(self, tmp_path):
        report, _ = _analyze(RED_TEXT, tmp_path)
        for i, f in enumerate(report["findings"]):
            t = f.get("title", "")
            assert 4 <= len(t) <= 8, f"findings[{i}].title 应为 4–8 字，实际 {t!r}（{len(t)}）"

    def test_findings按红黄绿排序(self, tmp_path):
        report, _ = _analyze(RED_TEXT, tmp_path)
        levels = [f["level"] for f in report["findings"]]
        ranks = [LEVEL_RANK[lv] for lv in levels]
        assert ranks == sorted(ranks, reverse=True), f"findings 未按红黄绿排序：{levels}"


class Test证据可追溯:
    def test_每条evidence都能在OCR原文找到(self, tmp_path):
        """§9 第 9 条：每条 evidence 都能在 OCR 原文里找到。"""
        report, _ = _analyze(RED_TEXT, tmp_path)
        for i, f in enumerate(report["findings"]):
            assert_evidence_traceable(f["evidence"], RED_TEXT)

    def test_绿灯也要证据(self, tmp_path):
        """§2 流程明确：证据校验覆盖绿灯。绿灯也不能凭空说「这项没问题」。"""
        report, _ = _analyze(GREEN_TEXT, tmp_path)
        for i, f in enumerate(report["findings"]):
            if f["level"] == "green":
                assert f.get("evidence", "").strip(), (
                    f"findings[{i}] 是绿灯但没有 evidence（绿也要指出原文依据）"
                )
                assert_evidence_traceable(f["evidence"], GREEN_TEXT)

    def test_context包含evidence(self, tmp_path):
        report, _ = _analyze(RED_TEXT, tmp_path)
        for i, f in enumerate(report["findings"]):
            ev = normalize(f.get("evidence", ""))
            ctx = normalize(f.get("context", ""))
            if not ev:
                continue
            assert ev in ctx, (
                f"findings[{i}].context 未包含 evidence：evidence={f['evidence']!r}"
            )

    def test_context也能在原文找到(self, tmp_path):
        report, _ = _analyze(RED_TEXT, tmp_path)
        for i, f in enumerate(report["findings"]):
            ctx = f.get("context", "").strip()
            if ctx:
                assert_evidence_traceable(ctx, RED_TEXT)

    def test_全部测试集样例都过证据校验(self, tmp_path):
        """回归：20 条样例逐条跑，证据都必须可追溯（红黄绿都算）。"""
        problems = []
        for sid in [f"T{i:03d}" for i in range(1, 21)]:
            try:
                text = _ocr_text_for(sid)
            except FileNotFoundError:
                continue
            report, _ = _analyze(text, tmp_path, name=f"{sid}.txt")
            for f in report.get("findings", []):
                ev = normalize(f.get("evidence", ""))
                if not ev:
                    problems.append(f"{sid}: {f.get('title')} 没有 evidence")
                elif ev not in normalize(text):
                    problems.append(f"{sid}: 证据找不到 {f.get('evidence')!r}")
        assert not problems, "证据不可追溯：\n" + "\n".join(problems[:10])


# ================================================================ overall 规则

class Test整体结论规则:
    def test_有红则overall为red(self, tmp_path):
        report, _ = _analyze(RED_TEXT, tmp_path)
        has_red = any(f["level"] == "red" for f in report["findings"])
        if has_red:
            assert report["overall"] == "red", (
                f"存在红灯但 overall={report['overall']}，应按规则算 red"
            )

    def test_overall与灯色一致(self, tmp_path):
        """后端按规则算：有红→red，否则有黄→amber，否则绿，非招聘→unknown。"""
        for text, name in [(RED_TEXT, "red.txt"), (GREEN_TEXT, "green.txt"), (NON_JOB_TEXT, "nonjob.txt")]:
            report, _ = _analyze(text, tmp_path, name=name)
            overall = report["overall"]
            findings = report.get("findings", [])
            levels = {f["level"] for f in findings}

            if not report["is_job_posting"]:
                assert overall == "unknown", f"{name}: 非招聘文本应为 unknown，实际 {overall}"
                continue

            if "red" in levels:
                assert overall == "red", f"{name}: 有红灯应为 red，实际 {overall}"
            elif "amber" in levels:
                assert overall == "amber", f"{name}: 有黄无红应为 amber，实际 {overall}"
            elif levels == {"green"} or not levels:
                assert overall in ("green",), f"{name}: 无红无黄应为 green，实际 {overall}"

    def test_非招聘文本为unknown(self, tmp_path):
        report, _ = _analyze(NON_JOB_TEXT, tmp_path, name="nonjob.txt")
        if report["is_job_posting"] is False:
            assert report["overall"] == "unknown"

    def test_维度灯与发现不矛盾(self, tmp_path):
        """某维度有红灯，该维度自己的灯也必须是红（不能出现「维度绿但里面有红灯」）。"""
        report, _ = _analyze(RED_TEXT, tmp_path)
        dim_of = {d["key"]: d["level"] for d in report["dimensions"]}
        for f in report["findings"]:
            dim_level = dim_of.get(f["dimension"])
            if dim_level is None:
                continue
            if f["level"] == "red":
                assert dim_level == "red", (
                    f"维度 {f['dimension']} 有红灯发现，但维度灯是 {dim_level}"
                )

    def test_绿灯维度不得有红灯发现(self, tmp_path):
        report, _ = _analyze(GREEN_TEXT, tmp_path, name="green.txt")
        dim_of = {d["key"]: d["level"] for d in report["dimensions"]}
        for f in report["findings"]:
            if f["level"] == "red":
                assert dim_of.get(f["dimension"]) != "green", (
                    f"维度 {f['dimension']} 是绿灯却出现红灯发现，前后矛盾"
                )


# ================================================================ 追问与核实

class Test追问与核实:
    def test_追问与核实非空且是字符串数组(self, tmp_path):
        report, _ = _analyze(RED_TEXT, tmp_path)
        for key in ("questions_to_ask", "how_to_verify"):
            v = report[key]
            assert isinstance(v, list) and v, f"{key} 不能为空数组"
            assert all(isinstance(x, str) and x.strip() for x in v), f"{key} 含空字符串"

    def test_追问条数合理(self, tmp_path):
        """最多 6 条，太多用户不看。"""
        report, _ = _analyze(PARTIAL_TEXT, tmp_path)
        assert len(report["questions_to_ask"]) <= 6, (
            f"追问 {len(report['questions_to_ask'])} 条，超过 6 条上限"
        )
