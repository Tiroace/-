"""证据校验 v2：每条 finding（红/黄/绿都算）的 evidence 必须在 OCR 原文里能找到。

找不到就删掉（防模型编造）；`context` 由 pipeline 用 OCR 切句重算，保证「包含 evidence 的整句」。
"""
from __future__ import annotations

from dataclasses import dataclass

from .textnorm import evidence_in_text, normalize


@dataclass
class DroppedFinding:
    finding: dict
    reason: str

    def to_dict(self) -> dict:
        return {
            "dimension": self.finding.get("dimension"),
            "level": self.finding.get("level"),
            "source": self.finding.get("source"),
            "pattern_id": self.finding.get("pattern_id"),
            "rule_id": self.finding.get("rule_id"),
            "evidence": self.finding.get("evidence"),
            "reason": self.reason,
        }


def verify_findings(findings: list[dict], ocr_text: str) -> tuple[list[dict], list[DroppedFinding]]:
    kept: list[dict] = []
    dropped: list[DroppedFinding] = []
    seen: set[tuple[str, str]] = set()

    for finding in findings:
        if not isinstance(finding, dict):
            dropped.append(DroppedFinding({}, "finding 不是对象"))
            continue
        evidence = str(finding.get("evidence") or "").strip()
        if not evidence:
            dropped.append(DroppedFinding(finding, "证据为空，没有原文支撑"))
            continue
        if not evidence_in_text(evidence, ocr_text):
            dropped.append(DroppedFinding(finding, "证据在 OCR 原文里找不到（疑似模型编造）"))
            continue
        key = (str(finding.get("dimension")), normalize(evidence))
        if key in seen:
            continue
        seen.add(key)
        kept.append(finding)

    return kept, dropped
