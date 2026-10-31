"""缺陷回归测试 · D-03：CLI 摘要行仍读 v1 字段，导致每次 analyze 都以 KeyError 崩溃

【缺陷单号】D-03（软件测试者 2026-10-31 v2 验收时发现）
【严重级】中（不影响报告内容，但 CLI 退出码非 0，脚本化与 CI 全部会误判失败）

【现象】
`engine/cli.py` 第 93–103 行的「[摘要]」打印语句仍在读 v1 字段：
    level=result.report["risk_level"]     ← v2 已无此字段
    n=len(result.report["risks"])         ← v2 改名为 findings
v2 改版后每跑一次 `python -m engine.cli analyze ...` 都会走到这行并抛：
    KeyError: 'risk_level'

【影响范围（已实测）】
- `--out` 导出：**报告文件已经正常写出**，随后才崩在摘要行 → 文件对、退出码错
- 不带 `--out`：JSON 已打印到 stdout，随后崩 → 输出对、退出码错
两种情况下调用方拿到的都是非 0 退出码，`scripts/run_engine.ps1`、CI、以及
后端 `engine_runner` 若以退出码判成功，会全部判失败。

【当前状态】未修复（红）。修复后本条自动转绿。
【建议修复】摘要行改用 v2 字段：
    level=result.report["overall"]
    n=len(result.report["findings"])
    并把 trace 的 evidence_dropped 兼容成 findings_dropped。
"""
from __future__ import annotations

import json

import pytest

from conftest import run_cli, ROOT
OCR_SAMPLE = """招聘打包员
入职需缴纳押金 800 元，离职退还
"""

def _write_ocr(tmp_path) -> str:
    p = tmp_path / "ocr.txt"
    p.write_text(OCR_SAMPLE, encoding="utf-8")
    return str(p)


def test_analyze带out导出退出码为0(tmp_path):
    """核心复现：报告正常导出后，CLI 不应崩溃。"""
    ocr = _write_ocr(tmp_path)
    out = tmp_path / "report.json"
    r = run_cli(["analyze", "--ocr-text", ocr, "--out", str(out), "--no-report-dir", "--no-dedupe"])

    # 报告本身应该写出来
    assert out.exists(), f"报告没导出；stderr={r.stderr[:300]}"

    # 关键断言：不能有未捕获异常
    tb = [ln for ln in (r.stderr or "").splitlines() if ln.startswith("Traceback (most recent call last)")]
    assert not tb, (
        "[D-03] CLI 抛未捕获异常（摘要行读 v1 字段 risk_level/risks）：\n"
        + "\n".join((r.stderr or "").splitlines()[-12:])
    )
    assert r.returncode == 0, f"[D-03] analyze 退出码应为 0，实际 {r.returncode}"


def test_analyze不带out退出码为0(tmp_path):
    ocr = _write_ocr(tmp_path)
    r = run_cli(["analyze", "--ocr-text", ocr, "--no-report-dir", "--no-dedupe"])
    tb = [ln for ln in (r.stderr or "").splitlines() if ln.startswith("Traceback (most recent call last)")]
    assert not tb, "[D-03] 不带 --out 时同样崩溃"
    assert r.returncode == 0, f"[D-03] 退出码应为 0，实际 {r.returncode}"


def test_导出的报告是合法v2结构(tmp_path):
    """即使摘要行崩了，导出文件本身必须是合法 v2（确认缺陷不影响数据正确性）。"""
    ocr = _write_ocr(tmp_path)
    out = tmp_path / "report.json"
    run_cli(["analyze", "--ocr-text", ocr, "--out", str(out), "--no-report-dir", "--no-dedupe"])

    if not out.exists():
        pytest.skip("报告文件未导出，另有缺陷")
    report = json.loads(out.read_text(encoding="utf-8"))
    assert "overall" in report, "导出文件应为 v2 结构"
    assert "risk_level" not in report, "导出文件不应含 v1 字段"

# 路线调整令第九节：本文件属「快跑冒烟」核心防线
pytestmark = pytest.mark.smoke
