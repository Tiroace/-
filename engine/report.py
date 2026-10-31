"""报告组装 v2：6 维度灯 + findings + overall 由规则算 + 灰灯自动补追问 + 文案红线。

overall 一律后端算，模型自报的 overall 不用（前端也不自己算）：
有红→red，否则有黄→amber，否则绿；非招聘/信息太少→unknown。
"""
from __future__ import annotations

from .prompts import DIMENSION_LABELS, GREY_QUESTIONS, SAFE_QUESTIONS, SAFE_VERIFY
from .schema import computed_overall
from .textnorm import DIMENSION_KEYS, LEVEL_RANK, mask_and_filter

DIM_SHORT = {"red": "有问题", "amber": "要问清", "green": "看着正常", "none": "没提到"}
OVERALL_SUMMARY = {
    "red": "有几处不对劲，先别急着去",
    "amber": "有几处要问清楚再决定",
    "green": "截图里没看到明显风险",
    "unknown": "信息不足，再补一张截图",
}
GREY_QUESTION_TEMPLATE = "截图里没提到「{label}」，可以问 HR：{question}"
EMPTY_QUESTIONS = ["请上传包含岗位名称、薪资、工作内容的招聘截图"]
EMPTY_VERIFY = ["把岗位详情和 HR 聊天记录一起截图上传，判断更准"]


def build_dimensions(findings: list[dict]) -> list[dict]:
    dimensions: list[dict] = []
    for key in DIMENSION_KEYS:
        related = [f.get("level") for f in findings if isinstance(f, dict) and f.get("dimension") == key]
        level = "none"
        if related:
            level = max(related, key=lambda lv: LEVEL_RANK.get(lv, 0))
        dimensions.append({"key": key, "level": level, "short": DIM_SHORT[level]})
    return dimensions


def _grey_questions(dimensions: list[dict]) -> list[dict]:
    grey = []
    for dim in dimensions:
        if dim["level"] == "none":
            question = GREY_QUESTION_TEMPLATE.format(
                label=DIMENSION_LABELS.get(dim["key"], dim["key"]),
                question=GREY_QUESTIONS[dim["key"]],
            )
            if len(question) > 60:
                question = question[:60]
            grey.append({"dimension": dim["key"], "question": question})
    return grey


def build_report(
    model_out: dict,
    findings: list[dict],
    is_job_posting: bool,
    rules_version: str,
    pattern_db_version: str,
) -> tuple[dict, list[dict]]:
    """返回（报告, 灰灯追问记录）。"""
    if not is_job_posting:
        dimensions = [{"key": key, "level": "none", "short": DIM_SHORT["none"]} for key in DIMENSION_KEYS]
        return (
            {
                "is_job_posting": False,
                "overall": "unknown",
                "summary": OVERALL_SUMMARY["unknown"],
                "dimensions": dimensions,
                "findings": [],
                "questions_to_ask": list(EMPTY_QUESTIONS),
                "how_to_verify": list(EMPTY_VERIFY),
                "rules_version": rules_version,
                "pattern_db_version": pattern_db_version,
            },
            [],
        )

    dimensions = build_dimensions(findings)
    overall = computed_overall(dimensions, findings, True)

    questions = [str(q) for q in (model_out.get("questions_to_ask") or [])]
    grey = _grey_questions(dimensions) if overall != "unknown" else []
    for item in grey:
        if item["question"] not in questions:
            questions.append(item["question"])
    questions = [q for q in questions if q][:6] or list(SAFE_QUESTIONS)

    verify = [str(v) for v in (model_out.get("how_to_verify") or []) if str(v).strip()][:4] or list(SAFE_VERIFY)

    report = {
        "is_job_posting": True,
        "overall": overall,
        "summary": OVERALL_SUMMARY[overall],
        "dimensions": dimensions,
        "findings": [
            {
                "level": f["level"],
                "dimension": f["dimension"],
                "title": f["title"],
                "evidence": f["evidence"],
                "context": f.get("context") or f["evidence"],
                "reason": f["reason"],
                "source": f["source"],
                "pattern_id": f.get("pattern_id"),
                "rule_id": f.get("rule_id"),
            }
            for f in findings
        ],
        "questions_to_ask": questions,
        "how_to_verify": verify,
        "rules_version": rules_version,
        "pattern_db_version": pattern_db_version,
    }
    return report, grey


def apply_text_policy(report: dict) -> tuple[dict, list[str]]:
    """文案红线：定性词替换 + 手机号/证件号脱敏（§8）。

    evidence 与 context 一起脱敏，保证「context 包含 evidence」在校验时仍成立；
    脱敏前原文留在 trace.evidence_raw，供评测与人工复核。
    """
    banned: list[str] = []
    report["summary"], hits = mask_and_filter(str(report.get("summary") or ""))
    report["summary"] = report["summary"][:30]
    banned.extend(hits)
    for finding in report.get("findings") or []:
        finding["evidence"], hits = mask_and_filter(str(finding.get("evidence") or ""))
        banned.extend(hits)
        finding["context"], hits = mask_and_filter(str(finding.get("context") or ""))
        banned.extend(hits)
        finding["reason"], hits = mask_and_filter(str(finding.get("reason") or ""))
        banned.extend(hits)
    report["questions_to_ask"] = [mask_and_filter(str(q))[0] for q in report.get("questions_to_ask") or []]
    report["how_to_verify"] = [mask_and_filter(str(v))[0] for v in report.get("how_to_verify") or []]
    return report, banned
