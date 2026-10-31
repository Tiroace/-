"""确定性报告引擎（一期无大模型）：规则命中 + 套路库命中 → 报告 schema 所需字段。

路线调整令第二节：不再调用大模型，报告文字全部由模板拼出来，不临时生成新文字。
这里负责把命中项拼成 `findings` / `is_job_posting` / `questions_to_ask` / `how_to_verify`，
再由 `report.build_report` 统一算灯、整体结论与灰灯追问。
"""
from __future__ import annotations

from .prompts import (
    DIMENSION_FALLBACK_REASON,
    REASON_BY_RULE,
)
from .textnorm import LEVEL_RANK, context_containing, normalize

# 招聘截图判定（路线调整令 §2.3）：少于 20 字，或一个招聘关键词都没有 → unknown
MIN_TEXT_CHARS = 20
JOB_KEYWORDS = (
    "招聘", "岗位", "职位", "薪资", "工资", "底薪", "月薪", "年薪", "日结",
    "面试", "入职", "上班", "工作", "兼职", "全职", "待遇", "福利", "招人",
    "急聘", "诚聘", "hr", "HR", "应聘", "简历",
)
MAX_FINDINGS = 12
MAX_PER_DIMENSION = 3

# 标题兜底（finding.title 必须 4–8 字）
DIM_TITLE = {
    "fee": "入职前收费",
    "work": "工作内容可疑",
    "title": "岗位名不符",
    "pay": "薪资写法可疑",
    "company": "公司信息不全",
    "contract": "合同社保存疑",
}

# D31「一事一灯」优先级：冲突时取序号小的（收费直接掏空钱包，法条最硬）
DIM_PRIORITY = {"fee": 0, "work": 1, "contract": 2, "pay": 3, "title": 4, "company": 5}

PATTERN_LEVEL_TO_FINDING = {
    "high": "red",
    "red": "red",
    "warn": "amber",
    "amber": "amber",
    "notice": "amber",
}


def is_job_posting(text: str) -> bool:
    plain = normalize(text)
    if len(plain) < MIN_TEXT_CHARS:
        return False
    lowered = text.lower()
    return any(keyword.lower() in lowered for keyword in JOB_KEYWORDS)


def _title(raw: str, dimension: str) -> str:
    title = (raw or "").strip()
    if 4 <= len(title) <= 8:
        return title
    return DIM_TITLE.get(dimension, "这条有风险")


def _clamp(text: str, limit: int = 80) -> str:
    text = (text or "").strip()
    return text[:limit] if len(text) > limit else text


def _split_copy(text: str) -> list[str]:
    """把产品审定的一句话话术切成可直接使用的条目（不生成新文字）。"""
    text = (text or "").strip()
    if not text:
        return []
    parts = [p.strip() for p in text.replace("；", "。").split("。") if p.strip()]
    return parts[:2]


def _reason(rule_id: str | None, dimension: str, pattern_why: str | None = None, rule_why: str | None = None) -> str:
    if pattern_why and pattern_why.strip():
        return _clamp(pattern_why)
    if rule_why and rule_why.strip():
        return _clamp(rule_why)
    if rule_id:
        reason = REASON_BY_RULE.get(rule_id)
        if reason:
            return _clamp(reason)
    return _clamp(DIMENSION_FALLBACK_REASON.get(dimension, "这一项有风险，建议先核实。"))


def _pick_by_priority(a: dict, b: dict) -> tuple[dict, dict]:
    """D31 优先级：fee > work > contract > pay > title > company；同维取等级高的。"""
    rank = DIM_PRIORITY
    ra = (rank.get(a["dimension"], 99), -LEVEL_RANK[a["level"]])
    rb = (rank.get(b["dimension"], 99), -LEVEL_RANK[b["level"]])
    return (a, b) if ra <= rb else (b, a)


def compose(text: str, hits, pattern_hits, *, min_pattern_score: float = 0.5) -> dict:
    """把规则/套路命中拼成模型输出形状（不生成任何新文字）。

    `min_pattern_score`：套路相似度低于这个分数不写 finding。
    召回阈值（0.35）是为了不漏，写报告要更严，否则干净岗位会被低分套路误判成黄灯。
    """
    job = is_job_posting(text)
    findings: list[dict] = []
    green_dims: set[str] = set()
    questions: list[str] = []
    verifies: list[str] = []
    if job:
        for hit in hits:
            evidence = (hit.evidence or "").strip()
            if not evidence:
                continue
            if hit.finding_level == "green":
                green_dims.add(hit.dimension)
            findings.append(
                {
                    "level": hit.finding_level,
                    "dimension": hit.dimension,
                    "title": _title(hit.title, hit.dimension),
                    "evidence": evidence,
                    "context": context_containing(text, evidence),
                    "reason": _reason(hit.rule_id, hit.dimension, rule_why=getattr(hit, "why", "")),
                    "source": "rule",
                    "pattern_id": None,
                    "rule_id": hit.rule_id,
                }
            )
            for question in _split_copy(getattr(hit, "questions", "")):
                if question not in questions:
                    questions.append(question)
            for verify in _split_copy(getattr(hit, "verify", "")):
                if verify not in verifies:
                    verifies.append(verify)
        for match in pattern_hits:
            if float(getattr(match, "score", 1.0)) < min_pattern_score:
                continue
            pattern = match.pattern
            dimension = pattern.dimension if pattern.dimension in DIM_TITLE else "work"
            if dimension in green_dims:
                # 同一维度已经有「写得清楚」的绿色规则证据，低置信套路不再盖过去
                continue
            evidence = (match.sentence or "").strip()
            if not evidence:
                continue
            findings.append(
                {
                    "level": PATTERN_LEVEL_TO_FINDING.get(str(pattern.level).lower(), "amber"),
                    "dimension": dimension,
                    "title": _title(pattern.name, dimension),
                    "evidence": evidence,
                    "context": context_containing(text, evidence),
                    "reason": _reason(None, dimension, pattern.why),
                    "source": "pattern",
                    "pattern_id": pattern.pattern_id,
                    "rule_id": None,
                }
            )
            for verify in _split_copy(getattr(pattern, "how", "")):
                if verify not in verifies:
                    verifies.append(verify)

    # 同一条规则/套路只保留一条 finding（取命中的第一处原文），避免同一标题刷屏；
    # 再按（维度, 证据）去重，保留等级最高的一条。
    best: dict[tuple[str, str], dict] = {}
    seen_rule: set[str] = set()
    for finding in findings:
        source_id = str(finding.get("rule_id") or finding.get("pattern_id") or "")
        if source_id and source_id in seen_rule:
            continue
        seen_rule.add(source_id)
        key = (finding["dimension"], normalize(finding["evidence"]))
        current = best.get(key)
        if current is None or LEVEL_RANK[finding["level"]] > LEVEL_RANK[current["level"]]:
            best[key] = finding

    ordered = sorted(
        best.values(),
        key=lambda f: (-LEVEL_RANK[f["level"]], f["dimension"], f["title"]),
    )

    # D34：同一句话被多条规则各报一次（例如培训贷同时命中 R-TRAIN-02 与 R-CLAUSE-02、
    # 「视频号发央国企招聘」同时命中 R-INSIDER-02 与 R-IMPERSON-01），会出现两盏灯都亮。
    # 按 D31 优先级「一事一灯」只保留优先级最高的那条，被丢弃的记进 dropped_by_priority 便于排查
    # ——不记日志就分不清「真多判被压掉」还是「规则漏了」（D34 明确要求）。
    groups: dict[str, list[dict]] = {}
    for finding in ordered:
        groups.setdefault(normalize(finding["evidence"]), []).append(finding)

    dropped: list[dict] = []
    survivors: list[dict] = []
    for evidence_key, group in groups.items():
        # 组内按 D31 优先级排序，第一名留下
        group.sort(key=lambda f: (DIM_PRIORITY.get(f["dimension"], 99), -LEVEL_RANK[f["level"]]))
        winner = group[0]
        survivors.append(winner)
        winner_id = winner.get("rule_id") or winner.get("pattern_id")
        for loser in group[1:]:
            dropped.append(
                {
                    "rule_id": loser.get("rule_id") or loser.get("pattern_id"),
                    "dimension": loser["dimension"],
                    "reason": f"same_evidence_as:{winner_id}",
                    "evidence": loser["evidence"][:60],
                }
            )
    ordered = sorted(
        survivors,
        key=lambda f: (-LEVEL_RANK[f["level"]], f["dimension"], f["title"]),
    )

    # 每个维度最多 3 条，总数 12
    counts: dict[str, int] = {}
    kept: list[dict] = []
    for finding in ordered:
        dimension = finding["dimension"]
        if counts.get(dimension, 0) >= MAX_PER_DIMENSION:
            continue
        counts[dimension] = counts.get(dimension, 0) + 1
        kept.append(finding)
        if len(kept) >= MAX_FINDINGS:
            break

    return {
        "is_job_posting": job,
        "findings": kept,
        "questions_to_ask": questions[:5],
        "how_to_verify": verifies[:5],
        "dropped_by_priority": dropped,
    }
