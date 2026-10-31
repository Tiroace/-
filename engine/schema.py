"""报告 schema v2 校验（替换旧 §4.3）。

顶层：is_job_posting / overall / summary / dimensions(6) / findings / questions_to_ask /
      how_to_verify / prompt_version / pattern_db_version
校验分两档：
- 模型原始输出（final=False）：类型/枚举/长度/字段完整性，用来决定是否重试；
- 校准后的最终报告（final=True）：额外校验维度与发现一致、overall 由维度算出、证据与整句自洽。
"""
from __future__ import annotations

import re

from .textnorm import (
    DIMENSION_KEYS,
    DIM_LEVELS,
    FINDING_LEVELS,
    LEVEL_RANK,
    OVERALL_LEVELS,
    SOURCE_KINDS,
    normalize,
)

TOP_KEYS = {
    "is_job_posting",
    "overall",
    "summary",
    "dimensions",
    "findings",
    "questions_to_ask",
    "how_to_verify",
    "rules_version",
    "pattern_db_version",
}
DIM_KEYS = {"key", "level", "short"}
FINDING_KEYS = {"level", "dimension", "title", "evidence", "context", "reason", "source", "pattern_id", "rule_id"}
RULES_VERSION_RE = re.compile(r"^v\d+\.\d+$")
PATTERN_DB_VERSION_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MAX_FINDINGS = 12


def _check_str(errors: list[str], obj: dict, key: str, label: str, max_len: int | None = None) -> None:
    value = obj.get(key)
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{label} 必须是非空字符串")
        return
    if max_len and len(value.strip()) > max_len:
        errors.append(f"{label} 超出长度上限 {max_len}（当前 {len(value.strip())}）")


def _check_str_list(errors: list[str], obj: dict, key: str, label: str, max_items: int = 6, max_len: int = 60) -> None:
    value = obj.get(key)
    if not isinstance(value, list) or not value:
        errors.append(f"{label} 必须是非空数组")
        return
    if len(value) > max_items:
        errors.append(f"{label} 最多 {max_items} 条（当前 {len(value)}）")
    for i, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            errors.append(f"{label}[{i}] 必须是非空字符串")
        elif len(item) > max_len:
            errors.append(f"{label}[{i}] 超出长度上限 {max_len}")


def computed_overall(dimensions: list[dict], findings: list[dict], is_job_posting: bool) -> str:
    """overall 由后端规则算：有红→red，否则有黄→amber，否则绿；非招聘/信息太少→unknown。"""
    if not is_job_posting:
        return "unknown"
    levels = [d.get("level") for d in dimensions if isinstance(d, dict)]
    if not findings or all(level == "none" for level in levels):
        return "unknown"
    if "red" in levels:
        return "red"
    if "amber" in levels:
        return "amber"
    return "green"


def validate_report(report: object, final: bool = True) -> list[str]:
    """返回错误列表，空列表表示通过。"""
    errors: list[str] = []
    if not isinstance(report, dict):
        return ["报告必须是一个 JSON 对象"]

    missing = TOP_KEYS - set(report)
    extra = set(report) - TOP_KEYS
    if missing:
        errors.append(f"缺少字段：{', '.join(sorted(missing))}")
    if extra:
        errors.append(f"出现未定义字段：{', '.join(sorted(extra))}")

    is_job = report.get("is_job_posting")
    if not isinstance(is_job, bool):
        errors.append("is_job_posting 必须是布尔值")
    if report.get("overall") not in OVERALL_LEVELS:
        errors.append(f"overall 必须是 {'/'.join(OVERALL_LEVELS)} 之一")
    _check_str(errors, report, "summary", "summary", max_len=30)

    rules_version = report.get("rules_version")
    if not isinstance(rules_version, str) or not RULES_VERSION_RE.match(rules_version):
        errors.append(f"rules_version 必须是 v主.次（当前 {rules_version!r}）")
    pattern_db_version = report.get("pattern_db_version")
    if not isinstance(pattern_db_version, str) or not PATTERN_DB_VERSION_RE.match(pattern_db_version):
        errors.append(f"pattern_db_version 必须是 YYYY-MM-DD（当前 {pattern_db_version!r}）")

    # ---- dimensions：固定 6 项且顺序固定 ----
    dimensions = report.get("dimensions")
    if not isinstance(dimensions, list):
        errors.append("dimensions 必须是数组")
        dimensions = []
    else:
        keys = [d.get("key") for d in dimensions if isinstance(d, dict)]
        if keys != list(DIMENSION_KEYS):
            errors.append(f"dimensions 必须是固定 6 项且顺序固定：{list(DIMENSION_KEYS)}（当前 {keys}）")
        for i, dim in enumerate(dimensions):
            prefix = f"dimensions[{i}]"
            if not isinstance(dim, dict):
                errors.append(f"{prefix} 必须是对象")
                continue
            if set(dim) - DIM_KEYS or DIM_KEYS - set(dim):
                errors.append(f"{prefix} 字段必须恰好是 key/level/short")
            if dim.get("level") not in DIM_LEVELS:
                errors.append(f"{prefix}.level 必须是 {'/'.join(DIM_LEVELS)}")
            _check_str(errors, dim, "short", f"{prefix}.short", max_len=6)

    # ---- findings ----
    findings = report.get("findings")
    if not isinstance(findings, list):
        errors.append("findings 必须是数组")
        findings = []
    if len(findings) > MAX_FINDINGS:
        errors.append(f"findings 最多 {MAX_FINDINGS} 条（当前 {len(findings)}）")
    for i, finding in enumerate(findings):
        prefix = f"findings[{i}]"
        if not isinstance(finding, dict):
            errors.append(f"{prefix} 必须是对象")
            continue
        missing_f = FINDING_KEYS - set(finding)
        extra_f = set(finding) - FINDING_KEYS
        if missing_f:
            errors.append(f"{prefix} 缺少字段：{', '.join(sorted(missing_f))}")
        if extra_f:
            errors.append(f"{prefix} 出现未定义字段：{', '.join(sorted(extra_f))}")
        if finding.get("level") not in FINDING_LEVELS:
            errors.append(f"{prefix}.level 必须是 {'/'.join(FINDING_LEVELS)}")
        if finding.get("dimension") not in DIMENSION_KEYS:
            errors.append(f"{prefix}.dimension 必须是 6 个维度之一")
        _check_str(errors, finding, "title", f"{prefix}.title")
        if isinstance(finding.get("title"), str) and not 4 <= len(finding["title"]) <= 8:
            errors.append(f"{prefix}.title 必须是 4–8 字（当前 {len(finding['title'])} 字）")
        _check_str(errors, finding, "evidence", f"{prefix}.evidence", max_len=120)
        _check_str(errors, finding, "context", f"{prefix}.context", max_len=160)
        _check_str(errors, finding, "reason", f"{prefix}.reason", max_len=80)
        if finding.get("source") not in SOURCE_KINDS:
            errors.append(f"{prefix}.source 必须是 rule/pattern 之一")
        if finding.get("source") == "pattern" and not finding.get("pattern_id"):
            errors.append(f"{prefix}.pattern_id 在 source=pattern 时必填")
        if finding.get("source") == "rule" and not finding.get("rule_id"):
            errors.append(f"{prefix}.rule_id 在 source=rule 时必填")
        if finding.get("source") != "pattern" and finding.get("pattern_id"):
            errors.append(f"{prefix}.pattern_id 只允许 source=pattern 时出现")
        if finding.get("source") != "rule" and finding.get("rule_id"):
            errors.append(f"{prefix}.rule_id 只允许 source=rule 时出现")
        evidence = finding.get("evidence")
        context = finding.get("context")
        if isinstance(evidence, str) and isinstance(context, str):
            if normalize(evidence) and normalize(evidence) not in normalize(context):
                errors.append(f"{prefix}.context 必须包含 evidence 原文")

    _check_str_list(errors, report, "questions_to_ask", "questions_to_ask")
    _check_str_list(errors, report, "how_to_verify", "how_to_verify")

    if not final:
        return errors

    # ---- 最终一致性（校准之后必须成立）----
    dim_levels = {d.get("key"): d.get("level") for d in dimensions if isinstance(d, dict)}
    for key, level in dim_levels.items():
        related = [f.get("level") for f in findings if isinstance(f, dict) and f.get("dimension") == key]
        expected = "none"
        if related:
            expected = max(related, key=lambda lv: LEVEL_RANK.get(lv, 0))
        if level != expected:
            errors.append(f"dimensions.{key} 与 findings 不一致：应为 {expected}（当前 {level}）")

    expected_overall = computed_overall(dimensions, findings, bool(is_job))
    if report.get("overall") != expected_overall:
        errors.append(f"overall 应为 {expected_overall}（按维度规则计算），当前 {report.get('overall')}")

    if report.get("overall") == "unknown" and findings:
        errors.append("overall=unknown 时不应有 findings")

    return errors
