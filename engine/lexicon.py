"""风险词库加载与规则初筛（v2：规则按 6 个维度归类）。

词库是运营配置：改 JSON 加词/加规则，不发版。本模块只负责读词库、扫文本、
把命中项交给后续环节。规则自带：
- `dimension`：6 个固定维度之一（fee/work/title/pay/company/contract）；
- `title`：finding 标题（4–8 字）；
- `level`：high / warn / notice / green（green 是正面证据，出绿灯 finding）。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from .textnorm import DIMENSION_KEYS, LEVEL_RANK, RULE_LEVEL_TO_FINDING, extract_evidence, to_simplified
from .variants import VariantTable, load_variants

CN_DIGITS = {"零": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
RULE_LEVELS = ("high", "warn", "notice", "green")
RULE_TYPES = ("scam", "train_loan", "bait_switch", "exaggerate", "illegal_clause", "normal")
DEFAULT_NEGATIONS = ("无需", "不必", "不需要", "不收", "不收取", "不交", "不缴", "免收", "没有", "不存在", "禁止收取")


class LexiconError(Exception):
    """词库文件不合法。"""


@dataclass
class Rule:
    rule_id: str
    type: str
    dimension: str
    level: str
    title: str
    hard: bool
    note: str
    pattern: re.Pattern
    negations: tuple[str, ...] = DEFAULT_NEGATIONS
    check: str | None = None
    raw: dict = field(default_factory=dict)
    why: str = ""
    law: str | None = None
    questions: str = ""
    verify: str = ""
    escalate: "re.Pattern | None" = None

    def to_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "type": self.type,
            "dimension": self.dimension,
            "level": self.level,
            "title": self.title,
            "hard": self.hard,
            "why": self.why,
            "law": self.law,
            "questions": self.questions,
            "verify": self.verify,
        }


@dataclass
class RuleHit:
    rule_id: str
    type: str
    dimension: str
    level: str
    title: str
    hard: bool
    evidence: str
    matched: str
    start: int
    end: int
    note: str = ""
    why: str = ""
    law: str | None = None
    questions: str = ""
    verify: str = ""

    @property
    def finding_level(self) -> str:
        return RULE_LEVEL_TO_FINDING.get(self.level, "amber")

    def to_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "type": self.type,
            "dimension": self.dimension,
            "level": self.level,
            "title": self.title,
            "hard": self.hard,
            "evidence": self.evidence,
            "matched": self.matched,
        }


@dataclass
class Lexicon:
    version: str
    rules: list[Rule]
    dimensions: list[dict]
    type_names: dict[str, str]
    level_names: dict[str, str]
    path: str = ""
    variants_version: str = "v0"

    def by_id(self, rule_id: str) -> Rule | None:
        for rule in self.rules:
            if rule.rule_id == rule_id:
                return rule
        return None


def _cn_to_int(text: str) -> int | None:
    text = text.strip()
    if not text:
        return None
    if text.isdigit():
        return int(text)
    if text == "十":
        return 10
    if len(text) == 2 and text[0] == "十" and text[1] in CN_DIGITS:
        return 10 + CN_DIGITS[text[1]]
    if len(text) == 2 and text[0] in CN_DIGITS and text[1] == "十":
        return CN_DIGITS[text[0]] * 10
    if len(text) == 3 and text[1] == "十":
        return CN_DIGITS.get(text[0], 0) * 10 + CN_DIGITS.get(text[2], 0)
    if len(text) == 1 and text in CN_DIGITS:
        return CN_DIGITS[text]
    return None


def _check_salary_span(text: str, m: re.Match) -> bool:
    """薪资区间倍数 ≥ 3 才算夸大（5k-30k 命中，8k-12k 不命中）。"""
    digits = re.findall(r"[0-9]{1,2}", m.group(0))
    if len(digits) < 2:
        return False
    low, high = float(digits[0]), float(digits[1])
    units = re.findall(r"[kK千万]", m.group(0))
    if units and units[0] != units[-1]:
        return False
    if low <= 0 or high <= low:
        return False
    return high / low >= 3


def _check_probation_over(text: str, m: re.Match) -> bool:
    """试用期超过法定上限才算违规；合同期没写时按最宽松（3 年以上）判定。"""
    months = _cn_to_int(m.group(1))
    if months is None:
        return False
    contract_lens = re.findall(r"合同期\s*[为]?\s*([0-9一二三四五六七八九十]{1,2})\s*年", text)
    limit = 6
    if contract_lens:
        years = _cn_to_int(contract_lens[0])
        if years is None:
            limit = 6
        elif years < 1:
            limit = 1
        elif years < 3:
            limit = 2
        else:
            limit = 6
    return months > limit


_CHECKS = {
    "salary_span": _check_salary_span,
    "probation_over": _check_probation_over,
}


def load_lexicon(path: str | Path, variants_path: str | Path | None = None) -> Lexicon:
    p = Path(path)
    if not p.is_file():
        raise LexiconError(f"词库文件不存在：{p}")
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise LexiconError(f"词库不是合法 JSON：{p}（{exc}）") from exc
    if not isinstance(data, dict) or not isinstance(data.get("rules"), list):
        raise LexiconError(f"词库缺 rules 数组：{p}")
    variants = load_variants(variants_path)

    rules: list[Rule] = []
    seen: set[str] = set()
    for idx, item in enumerate(data["rules"]):
        if not isinstance(item, dict):
            raise LexiconError(f"第 {idx} 条规则不是对象")
        rule_id = str(item.get("rule_id", "")).strip()
        rtype = str(item.get("type", "")).strip()
        level = str(item.get("level", "")).strip()
        dimension = str(item.get("dimension", "")).strip()
        title = str(item.get("title", "")).strip()
        if not rule_id or rule_id in seen:
            raise LexiconError(f"第 {idx} 条规则 rule_id 缺失或重复：{rule_id!r}")
        seen.add(rule_id)
        if rtype not in RULE_TYPES:
            raise LexiconError(f"{rule_id}: type 非法：{rtype!r}")
        if level not in RULE_LEVELS:
            raise LexiconError(f"{rule_id}: level 非法：{level!r}")
        if dimension not in DIMENSION_KEYS:
            raise LexiconError(f"{rule_id}: dimension 非法：{dimension!r}（应为 {DIMENSION_KEYS}）")
        if not 2 <= len(title) <= 10:
            raise LexiconError(f"{rule_id}: title 应为 2–10 字（finding 标题 4–8 字）：{title!r}")

        regex = str(item.get("regex") or "").strip()
        keywords = [str(k).strip() for k in (item.get("keywords") or []) if str(k).strip()]
        match_mode = str(item.get("match") or ("regex" if regex and not keywords else "any")).strip()
        if match_mode not in ("regex", "keyword", "any"):
            raise LexiconError(f"{rule_id}: match 非法：{match_mode!r}")

        parts = []
        if match_mode in ("regex", "any") and regex:
            parts.append(f"(?:{regex})")
        if match_mode in ("keyword", "any") and keywords:
            alts: list[str] = []
            for kw in sorted(keywords, key=len, reverse=True):
                # 变形写法：能展开就展开（V信→微信、押 金），否则至少容忍字间空格
                alts.append(variants.expand(kw) or variants.spaced(kw))
            parts.append("|".join(alts))
        if not parts:
            raise LexiconError(f"{rule_id}: 既没有 regex 也没有 keywords")
        try:
            pattern = re.compile("|".join(parts))
        except re.error as exc:
            raise LexiconError(f"{rule_id}: 正则无法编译（{exc}）") from exc

        escalate_raw = item.get("escalate_regex")
        escalate_pat = None
        if escalate_raw:
            try:
                escalate_pat = re.compile(str(escalate_raw))
            except re.error as exc:
                raise LexiconError(f"{rule_id}: escalate_regex 无法编译（{exc}）") from exc

        check = item.get("check")
        if check and check not in _CHECKS:
            raise LexiconError(f"{rule_id}: check 未实现：{check!r}")

        why = str(item.get("why") or "").strip()
        law_raw = item.get("law")
        law = None if law_raw in (None, "", "null", "—", "-") else str(law_raw).strip()
        questions = str(item.get("questions") or "").strip()
        verify = str(item.get("verify") or "").strip()
        rules.append(
            Rule(
                rule_id=rule_id,
                type=rtype,
                dimension=dimension,
                level=level,
                title=title,
                hard=bool(item.get("hard", False)),
                note=str(item.get("说明") or "").strip(),
                why=why,
                law=law,
                questions=questions,
                verify=verify,
                pattern=pattern,
                escalate=escalate_pat,
                negations=tuple(item.get("negations") or DEFAULT_NEGATIONS),
                check=check,
                raw=item,
            )
        )

    return Lexicon(
        version=str(data.get("version", "unknown")),
        rules=rules,
        dimensions=list(data.get("dimensions") or []),
        type_names=dict(data.get("type_names") or {}),
        level_names=dict(data.get("level_names") or {}),
        path=str(p),
        variants_version=variants.version,
    )


def _negated(text: str, start: int, negations: tuple[str, ...]) -> bool:
    window = text[max(0, start - 10) : start]
    return any(n in window for n in negations)


def scan(text: str, lexicon: Lexicon) -> list[RuleHit]:
    """按词库扫全文：逐行扫描 + 繁简两路 + 变形写法容错；证据一律取 OCR 原文。

    逐行为的是让「繁简转换后的匹配」也能映射回原始行做证据，避免出现
    “证据在 OCR 原文里找不到”的假阳性。
    """
    hits: list[RuleHit] = []
    seen: set[tuple[str, str]] = set()
    if not text:
        return hits

    lines = [line.strip() for line in text.split("\n") if line.strip()]
    candidates_by_line: list[list[str]] = []
    for line in lines:
        cands = [line]
        simplified = to_simplified(line)
        if simplified != line:
            cands.append(simplified)
        candidates_by_line.append(cands)

    for rule in lexicon.rules:
        for line, candidates in zip(lines, candidates_by_line):
            for cand in candidates:
                for m in rule.pattern.finditer(cand):
                    if _negated(cand, m.start(), rule.negations):
                        continue
                    if rule.check:
                        if not _CHECKS[rule.check](cand, m):
                            continue
                    hit_level = rule.level
                    if rule.escalate is not None and rule.escalate.search(cand):
                        # 明确欺骗句式（如「以某为由」「签声明规避引导贷款」）升红
                        hit_level = "high"
                    if cand == line:
                        evidence = extract_evidence(line, m.start(), m.end())
                    else:
                        # 繁简路径命中的，证据用整行原文（保证能在 OCR 原文里找到）
                        evidence = extract_evidence(line, 0, len(line)) or line[:90]
                    evidence = (evidence or "").strip()
                    if not evidence:
                        continue
                    key = (rule.rule_id, evidence)
                    if key in seen:
                        continue
                    seen.add(key)
                    hits.append(
                        RuleHit(
                            rule_id=rule.rule_id,
                            type=rule.type,
                            dimension=rule.dimension,
                            level=hit_level,
                            title=rule.title,
                            hard=rule.hard,
                            evidence=evidence,
                            matched=m.group(0),
                            start=m.start(),
                            end=m.end(),
                            note=rule.note,
                            why=rule.why,
                            law=rule.law,
                            questions=rule.questions,
                            verify=rule.verify,
                        )
                    )

    hits.sort(key=lambda h: (-LEVEL_RANK.get(h.finding_level, 0), -int(h.hard), h.start))
    return hits
