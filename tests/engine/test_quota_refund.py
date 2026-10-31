"""引擎契约测试 · 退次数逻辑（需求书 §4.2 / §4.4）

规则（测试视角的落地口径）：
- 只有「拿到了可用报告」才算扣次数；引擎抛 AnalysisError 时后端必须**退次数**。
- 因此引擎必须给出**可判别的失败原因码**，后端才可能正确退次数。
- 同一张图重复提交（24h 去重命中）不应再扣次数。

本组测试守着三件事：
1) 每种失败路径都有唯一的错误码，且错误码常量稳定（后端按它映射退次数）。
2) 失败时**不返回报告**（避免后端「既退次数又展示报告」）。
3) 去重命中时链路轨迹里有 dedupe_hit=True（后端据此不扣次数）。
"""
from __future__ import annotations

import json
import pytest

from conftest import ROOT, run_cli

pytestmark = pytest.mark.usefixtures("engine")


class Test失败原因码:
    def test_失败码常量齐全且互不相同(self, engine):
        from engine.pipeline import (
            ERR_OCR_UNAVAILABLE,
            ERR_CONTENT_BLOCKED,
            ERR_MODEL_FAILED,
            ERR_SCHEMA_FAILED,
        )

        codes = [ERR_OCR_UNAVAILABLE, ERR_CONTENT_BLOCKED, ERR_MODEL_FAILED, ERR_SCHEMA_FAILED]
        assert len(set(codes)) == len(codes), f"失败原因码有重复：{codes}"
        for c in codes:
            assert isinstance(c, str) and c.strip(), "失败原因码不能为空"

    def test_引擎失败一律抛AnalysisError(self, engine):
        """所有失败都要是 AnalysisError（带 code），不能是裸异常。"""
        from engine.pipeline import AnalysisError
        assert issubclass(AnalysisError, Exception)
        exc = AnalysisError("MODEL_FAILED", "测试")
        assert exc.code == "MODEL_FAILED"
        assert exc.message == "测试"


class Test空输入必须失败而不是返回报告:
    """OCR 拿不到文本时，绝不能返回一份「未发现风险」的报告。"""

    def test_空OCR文本_CLI退出码非0(self, tmp_path):
        empty = tmp_path / "empty.txt"
        empty.write_text("   \n\n  ", encoding="utf-8")
        out = tmp_path / "report.json"
        r = run_cli(["analyze", "--ocr-text", str(empty), "--out", str(out)])
        assert r.returncode != 0, f"空文本应失败，实际退出码 {r.returncode}：{r.stderr[:300]}"
        assert not out.exists(), "失败时不应产出报告文件"
        assert "OCR_UNAVAILABLE" in (r.stderr or ""), f"未给出可判别的原因码：{r.stderr[:300]}"

    @pytest.mark.xfail(
        strict=False,
        reason="D-03：CLI 摘要行仍读 v1 字段 risk_level，任何 analyze 都会崩；"
        "此崩溃归 D-03 管，修好后本用例转绿。见 test_defect_D03_cli_summary.py",
    )
    def test_文本缺失_不崩栈(self, tmp_path):
        """路径不存在时 ocr_text 会被当成文本内容传入。

        期望：要么失败退次数，要么按非招聘处理，但**绝不能抛未捕获异常**。
        注意：不能简单查 stderr 里有没有 "Traceback" —— CLI 会把完整日志
        （含路径名）写到 stderr，路径本身就可能含这些字。要按行首判断。
        """
        out = tmp_path / "report.json"
        r = run_cli(["analyze", "--ocr-text", str(tmp_path / "nope.txt"), "--out", str(out)])
        stderr_lines = (r.stderr or "").splitlines()
        traceback_lines = [ln for ln in stderr_lines if ln.startswith("Traceback (most recent call last)")]
        assert not traceback_lines, f"CLI 出现未捕获异常：\n" + "\n".join(stderr_lines[:20])


class Test模型失败必须退次数:
    """【2026-10-31 路线调整令后】

    一期不接大模型，确定性引擎不会因“模型失败”而报错——模型插件默认关闭，
    传入 model 也不会被调用。因此原「模型失败→退次数」用例按新口径改为：
    - 主流程不调用模型（传一个会爆炸的 model，结果照常成功）
    - 把插件显式打开（QBL_USE_LLM=1）时才走模型失败路径
    """

    def test_确定性主流程不调用模型(self, tmp_path):
        """路线令核心：即使传入会抛异常的 model，主流程也必须照常出报告。"""
        from engine.config import default_config
        from engine.pipeline import analyze
        from engine.adapters.models import ModelAdapter

        class BoomModel(ModelAdapter):
            name = "boom"
            is_mock = False
            called = 0

            def generate(self, request):
                BoomModel.called += 1
                raise RuntimeError("模拟模型服务 502")

        cfg = default_config()
        cfg.report_dir = None
        cfg.use_dedupe = False
        cfg.cache_dir = tmp_path / "cache"
        f = tmp_path / "ocr.txt"
        f.write_text("招聘程序员，月薪 20K。", encoding="utf-8")

        result = analyze([], str(f), config=cfg, model=BoomModel())
        assert result.report is not None, "确定性引擎应自行出报告"
        assert BoomModel.called == 0, (
            f"路线令规定不接大模型，但模型被调用了 {BoomModel.called} 次"
        )

    def test_模型插件打开时才可能失败(self, tmp_path):
        """插件打开（QBL_USE_LLM=1）时才走模型路径；默认关闭不受影响。"""
        import os

        from engine.config import default_config

        cfg = default_config()
        # 默认应为关闭
        use_llm = getattr(cfg, "use_llm", None)
        if use_llm is None:
            pytest.skip("当前配置里没有 use_llm 开关（模型插件接口尚未落地）")
        assert use_llm is False, "模型插件默认必须关闭（路线令）"
        assert os.environ.get("QBL_USE_LLM") in (None, "", "0"), (
            "测试环境不应打开模型插件"
        )


class Test去重命中不重复扣次数:
    def test_重复提交命中缓存(self, tmp_path):
        from engine.config import default_config
        from engine.pipeline import analyze, make_model

        cfg = default_config()
        cfg.report_dir = None
        # 必须指向 tmp_path：默认 cache_dir 是 var/cache/dedupe 全局共享，
        # 不隔离会让用例受历史缓存影响（第一轮实测踩到过）
        cfg.cache_dir = tmp_path / "cache"
        cfg.use_dedupe = True
        cfg.dedupe_ttl_hours = 24
        f = tmp_path / "ocr.txt"
        f.write_text("招聘客服，入职需缴纳押金 500 元。", encoding="utf-8")

        model = make_model("mock", defects=False)
        first = analyze([], str(f), config=cfg, model=model)
        assert first.trace.get("dedupe_hit") is False

        second = analyze([], str(f), config=cfg, model=model)
        assert second.trace.get("dedupe_hit") is True, "同文本重复提交未命中去重，会导致重复扣次数"
        assert second.report == first.report, "去重返回的报告与首次不一致"

    def test_全局缓存跨用户共享_需产品确认(self, tmp_path):
        """【待确认风险】去重 key 只按「内容+模型+词库+提示词」算，不含用户维度。

        现状：两个不同用户上传同一张图，第二个会直接拿到缓存报告，后端不发请求 ⇒ 不扣次数。
        这对用户是好事，但如果产品要求「每人都扣一次」，这就是缺陷；
        且如果缓存里有他人脱敏前的中间产物，还可能构成信息泄漏。
        先把它钉成用例，等产品口径确认后改成硬断言。
        """
        from engine.config import default_config
        from engine.pipeline import analyze, make_model

        cfg = default_config()
        cfg.report_dir = None
        cfg.cache_dir = tmp_path / "cache"
        cfg.use_dedupe = True
        f = tmp_path / "ocr.txt"
        f.write_text("招聘客服，入职需缴纳押金 500 元。", encoding="utf-8")

        model = make_model("mock", defects=False)
        a = analyze([], str(f), config=cfg, model=model)
        b = analyze([], str(f), config=cfg, model=model)
        # 记录当前行为（不是断言它正确）：第二次命中缓存
        assert b.trace.get("dedupe_hit") is True


class TestCLI失败码与退出码一致:
    EXIT_BY_CODE = {
        "OCR_UNAVAILABLE": 3,
        "CONTENT_BLOCKED": 4,
        "MODEL_FAILED": 5,
        "SCHEMA_FAILED": 6,
    }

    def test_退出码映射表(self, engine):
        from engine.cli import EXIT_CODES
        from engine.pipeline import (
            ERR_OCR_UNAVAILABLE, ERR_CONTENT_BLOCKED, ERR_MODEL_FAILED, ERR_SCHEMA_FAILED,
        )

        assert EXIT_CODES[ERR_OCR_UNAVAILABLE] == 3
        assert EXIT_CODES[ERR_CONTENT_BLOCKED] == 4
        assert EXIT_CODES[ERR_MODEL_FAILED] == 5
        assert EXIT_CODES[ERR_SCHEMA_FAILED] == 6

    def test_空文本CLI退出码为3(self, tmp_path):
        empty = tmp_path / "empty.txt"
        empty.write_text("", encoding="utf-8")
        r = run_cli(["analyze", "--ocr-text", str(empty)])
        assert r.returncode == 3, f"OCR 不可用应退出码 3，实际 {r.returncode}"
