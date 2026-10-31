"""文本归一化、脱敏与文案红线过滤。

本模块是证据校验的基础：OCR 原文与模型给的证据都要先归一化，再比对不对齐。
"""
from __future__ import annotations

import re
import unicodedata

# 需要从比对文本里剔除的字符：空白、各类标点、零宽字符
_STRIP_CATEGORIES = {"Zs", "Zl", "Zp", "Po", "Pd", "Ps", "Pe", "Pi", "Pf", "Pc"}
_EXTRA_STRIP = set("·、—－~～…•‧⁄／／")
_ZERO_WIDTH = set("\u200b\u200c\u200d\ufeff\u00a0")


def to_halfwidth(text: str) -> str:
    """全角转半角（NFKC 会顺带把全角数字、字母、部分标点转成半角）。"""
    return unicodedata.normalize("NFKC", text)


# ---------------------------------------------------------------- 繁简转换（路线调整令 §2）
_OPENCC = None


def to_simplified(text: str) -> str:
    """繁体转简体（OpenCC t2s）。只在“匹配”时使用，报告证据仍取 OCR 原文。

    未安装 OpenCC 时原样返回，不抛错。
    """
    global _OPENCC
    if not text:
        return ""
    if _OPENCC is None:
        try:
            from opencc import OpenCC  # type: ignore

            _OPENCC = OpenCC("t2s")
        except Exception:  # noqa: BLE001
            _OPENCC = False
    if not _OPENCC:
        return text
    try:
        return _OPENCC.convert(text)
    except Exception:  # noqa: BLE001
        return text


def normalize(text: str) -> str:
    """归一化：半角化 → 小写 → 去空白/标点/零宽字符。

    用于证据校验和词库命中，不用于展示。
    """
    if not text:
        return ""
    text = to_halfwidth(text).lower()
    out = []
    for ch in text:
        if ch in _ZERO_WIDTH:
            continue
        cat = unicodedata.category(ch)
        if cat in _STRIP_CATEGORIES or cat.startswith("Z"):
            continue
        if ch in _EXTRA_STRIP or ch.isspace():
            continue
        out.append(ch)
    return "".join(out)


def evidence_in_text(evidence: str, ocr_text: str) -> bool:
    """证据是否能在 OCR 原文里找到（归一化后子串匹配）。"""
    ev = normalize(evidence)
    if not ev:
        return False
    return ev in normalize(ocr_text)


# ---------------------------------------------------------------- 脱敏
_MOBILE_RE = re.compile(r"(?<!\d)(1[3-9]\d)(\d{4})(\d{4})(?!\d)")
_IDCARD_RE = re.compile(r"(?<![\dXx])(\d{6})(\d{8})(\d{3})([\dXx])(?![\dXx])")
_BANKCARD_RE = re.compile(r"(?<!\d)(\d{4})\d{8,11}(\d{4})(?!\d)")
_EMAIL_RE = re.compile(r"([A-Za-z0-9._%+-]{1,3})[A-Za-z0-9._%+-]*(@[A-Za-z0-9.-]+\.[A-Za-z]{2,})")
_WECHAT_RE = re.compile(r"(微信号|微信|QQ号|QQ)\s*[:：]?\s*([A-Za-z0-9_-]{4,20})")


def mask_pii(text: str) -> str:
    """手机号、身份证、银行卡、邮箱、微信号脱敏。日志与对外文案必须过一遍。"""
    if not text:
        return ""
    text = _IDCARD_RE.sub(lambda m: f"{m.group(1)}********{m.group(3)}*", text)
    text = _BANKCARD_RE.sub(lambda m: f"{m.group(1)}********{m.group(2)}", text)
    text = _MOBILE_RE.sub(lambda m: f"{m.group(1)}****{m.group(3)}", text)
    text = _EMAIL_RE.sub(lambda m: f"{m.group(1)}***{m.group(2)}", text)
    text = _WECHAT_RE.sub(lambda m: f"{m.group(1)}：***", text)
    return text


# ---------------------------------------------------------------- 定性词过滤
# 第八节红线：只说「这条招聘信息存在 xx 风险」，不下「这家公司是骗子」的定论。
BANNED_WORDS = {
    "骗子公司": "存在高风险信号的企业",
    "黑心企业": "存在高风险信号的企业",
    "无良企业": "存在高风险信号的企业",
    "犯罪团伙": "高风险组织",
    "诈骗团伙": "高风险组织",
    "诈骗犯": "存在高风险行为的人",
    "骗子": "存在高风险行为的人",
    "黑中介": "存在高风险行为的机构",
    "人贩子": "存在高风险行为的人",
}

_BANNED_RE = re.compile("|".join(sorted(map(re.escape, BANNED_WORDS), key=len, reverse=True)))


def filter_banned_words(text: str) -> tuple[str, list[str]]:
    """替换定性词，返回（过滤后文本，命中的词表）。"""
    if not text:
        return "", []
    hits = _BANNED_RE.findall(text)
    return _BANNED_RE.sub(lambda m: BANNED_WORDS[m.group(0)], text), hits


def mask_and_filter(text: str) -> tuple[str, list[str]]:
    filtered, banned = filter_banned_words(text)
    return mask_pii(filtered), banned


# ---------------------------------------------------------------- PII 泄漏扫描
# 输出层硬断言：报告 JSON 全文不得出现完整手机号/身份证/银行卡/微信号（§8）。
PII_PATTERNS = {
    "mobile": re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"),
    "idcard": re.compile(r"(?<!\d)\d{17}[\dXx](?![\dXx])"),
    "bankcard": re.compile(r"(?<!\d)\d{16,19}(?!\d)"),
    "wechat": re.compile(r"(微信号|微信|QQ号|QQ)\s*[:：]\s*[A-Za-z0-9_-]{4,20}"),
    "email": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
}


def find_pii(text: str) -> list[dict]:
    """返回泄漏项列表（类型 + 命中片段，片段本身也打码，避免日志二次泄漏）。"""
    leaks: list[dict] = []
    if not text:
        return leaks
    for kind, pattern in PII_PATTERNS.items():
        for match in pattern.finditer(text):
            raw = match.group(0)
            leaks.append({"type": kind, "snippet": raw[:4] + "***" + raw[-2:] if len(raw) > 6 else "***"})
    return leaks


# ---------------------------------------------------------------- 证据片段提取
_TRAILING = "，,。.；;：:、 \t\r\n"


def _strip_keep_offsets(text: str, start: int, end: int) -> tuple[int, int]:
    while start < end and text[start] in _TRAILING:
        start += 1
    while end > start and text[end - 1] in _TRAILING:
        end -= 1
    return start, end


def extract_evidence(text: str, start: int, end: int, max_len: int = 90) -> str:
    """把正则命中位置扩展成「可读的原文片段」，保证是 OCR 原文的连续子串。

    优先整行；行太长则退到句子（。！？；!?）边界。
    """
    if not text:
        return ""
    start = max(0, min(start, len(text)))
    end = max(start, min(end, len(text)))

    line_start = text.rfind("\n", 0, start) + 1
    line_end = text.find("\n", end)
    if line_end == -1:
        line_end = len(text)

    if line_end - line_start <= max_len:
        s, e = _strip_keep_offsets(text, line_start, line_end)
        return text[s:e]

    # 行太长：扩大到句边界
    sent_start = line_start
    for i in range(start - 1, line_start - 1, -1):
        if text[i] in "。！？!?；;":
            sent_start = i + 1
            break
    sent_end = line_end
    for i in range(end, line_end):
        if text[i] in "。！？!?；;":
            sent_end = i + 1
            break
    s, e = _strip_keep_offsets(text, sent_start, sent_end)
    if e - s > max_len:
        # 极端情况仍超长：从命中处取固定窗口，保证仍是连续原文子串
        center = max(s, min(start, max(s, e - max_len)))
        s2, e2 = _strip_keep_offsets(text, center, min(e, center + max_len))
        return text[s2:e2]
    return text[s:e]


# ---------------------------------------------------------------- 切句（v2）
_SENT_DELIMS = "。！？!?；;\n"


def split_sentences(text: str) -> list[str]:
    """按句号/问号/感叹号/分号/换行切句，返回去掉首尾标点的句子（保持出现顺序）。"""
    if not text:
        return []
    sentences: list[str] = []
    buf: list[str] = []
    for ch in text:
        if ch in _SENT_DELIMS:
            piece = "".join(buf).strip(" ，,、：: \t\r\n")
            if piece:
                sentences.append(piece)
            buf = []
        else:
            buf.append(ch)
    tail = "".join(buf).strip(" ，,、：: \t\r\n")
    if tail:
        sentences.append(tail)
    return sentences


def context_containing(text: str, evidence: str, max_len: int = 160) -> str:
    """v2 finding.context：保证是包含 evidence 的原文片段，且不超长。"""
    ev = (evidence or "").strip()
    if not ev:
        return ""
    candidates: list[str] = []
    sentence = sentence_for(text, ev)
    if sentence:
        candidates.append(sentence)
    index = text.find(ev)
    if index >= 0:
        start = max(0, index - 40)
        end = min(len(text), index + len(ev) + 40)
        candidates.append(text[start:end].strip())
    for cand in candidates:
        if normalize(ev) in normalize(cand) and len(cand) <= max_len:
            return cand
    for cand in candidates:
        if normalize(ev) not in normalize(cand):
            continue
        pos = cand.find(ev)
        if pos < 0:
            continue
        start = max(0, pos - 20)
        end = min(len(cand), pos + len(ev) + 20)
        if end - start > max_len:
            end = start + max_len
        piece = cand[start:end]
        if normalize(ev) in normalize(piece):
            return piece
    return ev if len(ev) <= max_len else ev[:max_len]


def sentence_for(text: str, evidence: str) -> str | None:
    """取包含 evidence 的整句（v2 的 finding.context）。找不到返回 None。"""
    if not text or not evidence:
        return None
    ev = normalize(evidence)
    if not ev:
        return None
    for sentence in split_sentences(text):
        if ev in normalize(sentence):
            return sentence
    # evidence 跨句：退化为从命中位置到行尾
    raw = text.find(evidence)
    if raw >= 0:
        start = text.rfind("\n", 0, raw) + 1
        end = text.find("\n", raw)
        if end == -1:
            end = len(text)
        return text[start:end].strip()
    return None


# ---------------------------------------------------------------- 分类常量（v2：6 维度 + 四档结论）
DIMENSIONS = (
    ("fee", "收费与借贷"),
    ("work", "工作内容"),
    ("title", "岗位名称"),
    ("pay", "薪资待遇"),
    ("company", "公司信息"),
    ("contract", "合同社保"),
)
DIMENSION_KEYS = tuple(key for key, _ in DIMENSIONS)
DIMENSION_LABELS = dict(DIMENSIONS)
FINDING_LEVELS = ("red", "amber", "green")
DIM_LEVELS = ("red", "amber", "green", "none")
OVERALL_LEVELS = ("red", "amber", "green", "unknown")
LEVEL_RANK = {"none": 0, "green": 1, "amber": 2, "red": 3}
RULE_LEVEL_TO_FINDING = {"high": "red", "warn": "amber", "notice": "amber", "green": "green"}
SOURCE_KINDS = ("rule", "pattern")

# 整体结论对应的一句话（前端标题用；v1 的 verdict 已作废）
OVERALL_TO_HEADLINE = {
    "red": "先别去，这些地方不对劲",
    "amber": "先问清楚，再决定去不去",
    "green": "目前看没大问题，可以去面试",
    "unknown": "信息不足，再补一张截图",
}

# ---- 兼容旧命名（v1 代码/测试仍可能 import，留常量避免 ImportError，逻辑已不用）----
RISK_LEVELS = ("high", "warn", "notice")
REPORT_LEVELS = ("high", "warn", "notice", "safe", "unknown")
VERDICTS = ("不建议前往", "先核实再去", "可以去，带着问题去", "可以去", "信息不足")
RISK_TYPES = ("scam", "train_loan", "bait_switch", "exaggerate", "illegal_clause")
LEVEL_TO_VERDICT = {
    "high": "不建议前往",
    "warn": "先核实再去",
    "notice": "可以去，带着问题去",
    "safe": "可以去",
    "unknown": "信息不足",
}
LEVEL_ORDER = {"notice": 1, "warn": 2, "high": 3}
