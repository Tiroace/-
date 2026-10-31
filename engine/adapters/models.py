"""模型适配器 v2：默认 MockModel（无 key 也能跑通全链路），DeepSeek 适配器写好但不启用。

模型输出 v2 报告骨架（6 维度 + findings + overall + 两版版本号），
证据校验 / 等级校准 / overall 规则计算在 pipeline 里做，模型说了不算。
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from ..lexicon import RuleHit
from ..patterns import PatternMatch
from ..prompts import (
    DIMENSION_FALLBACK_REASON,
    DIMENSION_LABELS,
    DIMENSION_ORDER,
    GREEN_REASON_DEFAULT,
    GREY_QUESTIONS,
    PROMPT_VERSION,
    REASON_BY_RULE,
    SAFE_QUESTIONS,
    SAFE_VERIFY,
    SYSTEM_PROMPT,
    VERIFY_BY_DIMENSION,
)
from ..schema import computed_overall
from ..textnorm import DIMENSION_KEYS, LEVEL_RANK, context_containing


class ModelNotConfigured(Exception):
    """模型没有配置（缺 API key / 账号）。"""


class ModelOutputInvalid(Exception):
    """模型输出不是合法 JSON 或不符合 schema。"""


@dataclass
class ModelRequest:
    ocr_text: str
    rule_hits: list[RuleHit]
    pattern_hits: list[PatternMatch] = field(default_factory=list)
    type_names: dict[str, str] = field(default_factory=dict)
    prompt_version: str = PROMPT_VERSION
    pattern_db_version: str = ""
    retry_errors: list[str] = field(default_factory=list)
    images: list[Path] = field(default_factory=list)


class ModelAdapter:
    name = "base"
    is_mock = False

    def generate(self, req: ModelRequest) -> dict:
        raise NotImplementedError


# ---------------------------------------------------------------- Mock v2
JOB_HINTS = (
    "招聘", "岗位", "职位", "薪资", "月薪", "工资", "面试", "入职", "任职",
    "工作", "职责", "待遇", "底薪", "提成", "试用期", "五险一金",
    "兼职", "日结", "时薪", "佣金", "客服", "临时工", "钟点工", "简历",
)

# Mock 用来模拟「模型编造」的证据：故意不在任何 OCR 原文里出现。
HALLUCINATED_EVIDENCE = "入职当天发放 2000 元安家费，工资日结"

DIM_SHORT = {"red": "有问题", "amber": "要问清", "green": "看着正常", "none": "没提到"}
DIM_TITLE_FALLBACK = {
    "fee": "收费问题",
    "work": "内容不清",
    "title": "名头不符",
    "pay": "薪资可疑",
    "company": "公司不明",
    "contract": "合同问题",
}
LEVEL_DOWNGRADE = {"red": "amber", "amber": "green", "green": "green"}
OVERALL_SUMMARY = {
    "red": "有几处不对劲，先别急着去",
    "amber": "有几处要问清楚再决定",
    "green": "目前看没大问题，可以去",
    "unknown": "信息不足，再补一张截图",
}


def _stable_hash(text: str) -> int:
    return int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:12], 16)


def _fit_title(title: str, dimension: str) -> str:
    title = (title or "").strip()
    if 4 <= len(title) <= 8:
        return title
    return DIM_TITLE_FALLBACK.get(dimension, "值得问问")


class MockModel(ModelAdapter):
    """确定性 Mock v2：从规则命中 + 套路命中生成 6 维度报告。

    故意注入两类「模型缺陷」用于自测：
    1. 把一部分 finding 等级下调 → 由等级校准拉回（规则/套路下限）；
    2. 凭空编一条证据 → 由证据校验删掉。
    重试（retry_errors 非空）时不再注入缺陷。
    """

    name = "mock-v2"
    is_mock = True

    def __init__(self, defects: bool = True, seed: int = 20261031):
        self.defects = defects
        self.seed = seed

    def _is_job_posting(self, text: str, req: ModelRequest) -> bool:
        hints = sum(1 for k in JOB_HINTS if k in text)
        return hints >= 2 or len(req.rule_hits) >= 2 or bool(req.pattern_hits)

    @staticmethod
    def _dimensions_from(findings: list[dict]) -> list[dict]:
        dims = []
        for key in DIMENSION_KEYS:
            related = [f["level"] for f in findings if f.get("dimension") == key]
            level = "none"
            if related:
                level = max(related, key=lambda lv: LEVEL_RANK.get(lv, 0))
            dims.append({"key": key, "level": level, "short": DIM_SHORT[level]})
        return dims

    def _empty_report(self, req: ModelRequest) -> dict:
        return {
            "is_job_posting": False,
            "overall": "unknown",
            "summary": "没识别到招聘内容，再补一张截图",
            "dimensions": [{"key": key, "level": "none", "short": "没提到"} for key in DIMENSION_KEYS],
            "findings": [],
            "questions_to_ask": ["请上传包含岗位名称、薪资、工作内容的招聘截图"],
            "how_to_verify": ["把岗位详情和 HR 聊天记录一起截图上传，判断更准"],
            "prompt_version": req.prompt_version,
            "pattern_db_version": req.pattern_db_version,
        }

    def generate(self, req: ModelRequest) -> dict:
        text = req.ocr_text or ""
        if not self._is_job_posting(text, req):
            return self._empty_report(req)

        findings: list[dict] = []
        seen: set[tuple[str, str]] = set()

        # 1) 规则命中（优先，source=rule）
        for hit in req.rule_hits:
            key = (hit.dimension, hit.evidence)
            if key in seen:
                continue
            seen.add(key)
            findings.append(
                {
                    "level": hit.finding_level,
                    "dimension": hit.dimension,
                    "title": _fit_title(hit.title, hit.dimension),
                    "evidence": hit.evidence,
                    "context": context_containing(text, hit.evidence),
                    "reason": REASON_BY_RULE.get(hit.rule_id)
                    or (GREEN_REASON_DEFAULT if hit.finding_level == "green" else DIMENSION_FALLBACK_REASON.get(hit.dimension, "这条信息存在需要警惕的信号。")),
                    "source": "rule",
                    "pattern_id": None,
                    "rule_id": hit.rule_id,
                }
            )

        # 2) 套路库命中（source=pattern，不覆盖同维度同原文的规则 finding）
        for match in req.pattern_hits:
            key = (match.pattern.dimension, match.sentence)
            if key in seen:
                continue
            seen.add(key)
            findings.append(
                {
                    "level": match.pattern.level,
                    "dimension": match.pattern.dimension,
                    "title": _fit_title(match.pattern.name, match.pattern.dimension),
                    "evidence": match.sentence,
                    "context": match.sentence,
                    "reason": match.pattern.why or DIMENSION_FALLBACK_REASON.get(match.pattern.dimension, ""),
                    "source": "pattern",
                    "pattern_id": match.pattern.pattern_id,
                    "rule_id": None,
                }
            )

        if self.defects and not req.retry_errors:
            # 缺陷 1：部分 finding 被下调一级（校准会按规则/套路下限拉回）
            for finding in findings:
                if _stable_hash(finding["rule_id"] or finding["pattern_id"] or "" + str(self.seed)) % 2 == 0:
                    finding["level"] = LEVEL_DOWNGRADE[finding["level"]]
            # 缺陷 2：偶发编造一条证据（证据校验会删掉）
            if _stable_hash(text + str(self.seed)) % 3 == 0:
                findings.append(
                    {
                        "level": "green",
                        "dimension": "company",
                        "title": "编造的绿灯",
                        "evidence": HALLUCINATED_EVIDENCE,
                        "context": HALLUCINATED_EVIDENCE,
                        "reason": "这条信息写着入职发安家费，公司福利不错。",
                        "source": "llm",
                        "pattern_id": None,
                        "rule_id": None,
                    }
                )

        findings = findings[:12]
        dimensions = self._dimensions_from(findings)
        overall = computed_overall(dimensions, findings, True)

        # 3) 追问与核实方法：只针对有问题的维度（灰灯追问由 pipeline 统一补）
        questions: list[str] = []
        verify: list[str] = []
        for dim in dimensions:
            if dim["level"] in ("red", "amber"):
                q = GREY_QUESTIONS[dim["key"]]
                if q not in questions:
                    questions.append(q)
                v = VERIFY_BY_DIMENSION[dim["key"]]
                if v not in verify:
                    verify.append(v)
        if not questions:
            questions = list(SAFE_QUESTIONS)
            verify = list(SAFE_VERIFY)

        return {
            "is_job_posting": True,
            "overall": overall,
            "summary": OVERALL_SUMMARY[overall],
            "dimensions": dimensions,
            "findings": findings,
            "questions_to_ask": questions[:4],
            "how_to_verify": verify[:4],
            "prompt_version": req.prompt_version,
            "pattern_db_version": req.pattern_db_version,
        }


# ---------------------------------------------------------------- DeepSeek
class DeepSeekModel(ModelAdapter):
    """DeepSeek 适配器（真实模型）。没有 key 时直接抛 ModelNotConfigured，不偷偷降级。

    环境变量：DEEPSEEK_API_KEY（走安全卡片注入，不要写进代码）。
    """

    name = "deepseek-flash"
    is_mock = False
    endpoint = "https://api.deepseek.com/chat/completions"

    def __init__(self, api_key: str | None = None, model: str | None = None, timeout: int = 60):
        self.api_key = api_key or os.environ.get("DEEPSEEK_API_KEY", "")
        self.model = model or self.name
        self.timeout = timeout

    def _build_messages(self, req: ModelRequest) -> list[dict]:
        rule_lines = "\n".join(
            f"- {h.rule_id}（{DIMENSION_LABELS.get(h.dimension, h.dimension)}/{h.finding_level}）：命中「{h.matched}」，原文：{h.evidence}"
            for h in req.rule_hits
        ) or "（无）"
        pattern_lines = "\n".join(
            f"- {m.pattern.pattern_id}（{m.pattern.name}/{m.pattern.level}，相似度 {m.score:.2f}）：{m.sentence}"
            for m in req.pattern_hits
        ) or "（无）"
        user_text = (
            f"【6 个维度】\n" + "\n".join(f"- {key} {DIMENSION_LABELS[key]}" for key in DIMENSION_ORDER) + "\n\n"
            f"【规则初筛命中（硬证据，等级不得下调）】\n{rule_lines}\n\n"
            f"【套路库相似命中（参考，必须有原文才写）】\n{pattern_lines}\n\n"
            f"【OCR 文字】\n{req.ocr_text}\n\n"
            f"提示词版本：{req.prompt_version}；套路库版本：{req.pattern_db_version}。只输出 JSON。"
        )
        if req.retry_errors:
            user_text += "\n\n上一次输出未通过校验，问题如下，请严格修正后重新输出：\n" + "\n".join(req.retry_errors)
        content: list[dict] | str = user_text
        if req.images:
            parts: list[dict] = [{"type": "text", "text": user_text}]
            for img in req.images[:3]:
                try:
                    data = base64.b64encode(Path(img).read_bytes()).decode("ascii")
                except OSError:
                    continue
                parts.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{data}"}})
            content = parts
        return [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": content},
        ]

    def generate(self, req: ModelRequest) -> dict:
        if not self.api_key:
            raise ModelNotConfigured(
                "没有 DEEPSEEK_API_KEY：请老板通过安全卡片提供，见 docs/02 待老板确认清单第 9 条"
            )
        payload = {
            "model": self.model,
            "messages": self._build_messages(req),
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
            "max_tokens": 1600,
        }
        request = urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
            raise ModelOutputInvalid(f"模型接口返回 HTTP {exc.code}：{detail}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise ModelOutputInvalid(f"模型接口连不上：{exc}") from exc

        try:
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ModelOutputInvalid(f"模型返回结构异常：{str(body)[:300]}") from exc
        content = content.strip()
        if content.startswith("```"):
            content = content.strip("`")
            if content.startswith("json"):
                content = content[4:]
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ModelOutputInvalid(f"模型输出不是合法 JSON：{content[:300]}") from exc
        if not isinstance(parsed, dict):
            raise ModelOutputInvalid("模型输出不是 JSON 对象")
        return parsed
