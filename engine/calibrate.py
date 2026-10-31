"""等级校准 v2：规则命中/套路命中给的等级是下限，模型不得判轻。

- 规则命中（hard 与否都算，D-01 口径）：finding.level 至少为规则等级；
- 套路匹配：finding.level 至少为该套路等级（高相似红灯套路不得下调）；
- 模型漏掉硬证据规则：按规则兜底补一条 finding（规则打底，不让漏报）。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .lexicon import RuleHit
from .patterns import PatternMatch
from .prompts import DIMENSION_FALLBACK_REASON, GREEN_REASON_DEFAULT, REASON_BY_RULE
from .textnorm import LEVEL_RANK, normalize

FLOOR_KIND = {"rule": "规则命中", "pattern": "套路库命中"}


@dataclass
class CalibrationResult:
    findings: list[dict]
    adjustments: list[dict] = field(default_factory=list)


def _same_evidence(a: str, b: str) -> bool:
    na, nb = normalize(a), normalize(b)
    return bool(na) and (na == nb or na in nb or nb in na)


def _floor_for(finding: dict, hits: list[RuleHit], patterns: list[PatternMatch]) -> tuple[str, dict] | None:
    """返回（下限等级, 来源信息），没有可对照的来源返回 None。

    注意（D-02）：判断依据是「有没有引用规则/套路」，**不是 source 标签**。
    模型可能把来源写成 llm，却引用了真规则、证据也是原文，等级同样不得低于词库下限。
    """
    evidence = str(finding.get("evidence") or "")
    rule_id = str(finding.get("rule_id") or "")
    if rule_id:
        for hit in hits:
            if hit.rule_id == rule_id:
                return hit.finding_level, {"kind": "rule", "id": hit.rule_id}
    # 没写 rule_id 或写错，但证据能对上某条命中规则 → 同样按下限保护
    if evidence:
        for hit in hits:
            if _same_evidence(hit.evidence, evidence):
                return hit.finding_level, {"kind": "rule", "id": hit.rule_id}
    pattern_id = str(finding.get("pattern_id") or "")
    if pattern_id:
        for match in patterns:
            if match.pattern.pattern_id == pattern_id:
                return match.pattern.level, {"kind": "pattern", "id": pattern_id}
    return None


def calibrate(findings: list[dict], hits: list[RuleHit], patterns: list[PatternMatch]) -> CalibrationResult:
    findings = [dict(f) for f in findings]
    adjustments: list[dict] = []

    # 1) 回拉：规则/套路等级是下限
    for finding in findings:
        floor = _floor_for(finding, hits, patterns)
        if floor is None:
            continue
        level, source = floor
        current = str(finding.get("level"))
        if LEVEL_RANK.get(level, 0) > LEVEL_RANK.get(current, 0):
            adjustments.append(
                {
                    "kind": "raise",
                    "source": source["kind"],
                    "pattern_id": source["id"] if source["kind"] == "pattern" else None,
                    "rule_id": source["id"] if source["kind"] == "rule" else None,
                    "from": current,
                    "to": level,
                    "evidence": finding.get("evidence"),
                    "why": f"{FLOOR_KIND[source['kind']]}等级是下限，模型不得判轻（D-01）",
                }
            )
            finding["level"] = level

    # 2) 兜底：硬证据规则命中但模型没写，补一条
    covered_rule_ids = {str(f.get("rule_id")) for f in findings}
    covered_evidence = [str(f.get("evidence") or "") for f in findings]
    for hit in hits:
        if not hit.hard or hit.rule_id in covered_rule_ids:
            continue
        if any(_same_evidence(hit.evidence, ev) for ev in covered_evidence):
            continue
        findings.append(
            {
                "level": hit.finding_level,
                "dimension": hit.dimension,
                "title": hit.title,
                "evidence": hit.evidence,
                "context": hit.evidence,
                "reason": REASON_BY_RULE.get(hit.rule_id)
                or (GREEN_REASON_DEFAULT if hit.finding_level == "green" else DIMENSION_FALLBACK_REASON.get(hit.dimension, "截图原文存在需要警惕的信号，建议核实。")),
                "source": "rule",
                "pattern_id": None,
                "rule_id": hit.rule_id,
            }
        )
        covered_rule_ids.add(hit.rule_id)
        covered_evidence.append(hit.evidence)
        adjustments.append(
            {
                "kind": "add",
                "source": "rule",
                "pattern_id": None,
                "rule_id": hit.rule_id,
                "from": None,
                "to": hit.finding_level,
                "evidence": hit.evidence,
                "why": "模型漏报硬证据，按规则打底补一条",
            }
        )

    # 3) 去重 + 排序
    seen: set[tuple[str, str]] = set()
    unique: list[dict] = []
    for finding in findings:
        key = (str(finding.get("dimension")), normalize(str(finding.get("evidence") or "")))
        if key in seen:
            continue
        seen.add(key)
        unique.append(finding)
    unique.sort(key=lambda f: (-LEVEL_RANK.get(str(f.get("level")), 0), str(f.get("dimension"))))
    return CalibrationResult(findings=unique[:12], adjustments=adjustments)
