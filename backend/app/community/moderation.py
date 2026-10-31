"""求助广场：内容审核（敏感词两级 + 正则 + 模型降级）。

规则来自产品词表 v1.0（132 条）：
- block（80 词/正则）：直接拒收，HTTP 400 `CONTENT_BLOCKED`；
- rewrite（42 词，入库映射 review）：拒收并返回「请改成描述事实」提示，HTTP 400 `NEEDS_REWRITE`；
- mask（10 条正则：手机号/身份证/银行卡/微信/QQ/群号/邮箱/门牌号/车牌）：打码后放行；
- 模型层（D13 本地降级）：外链/引流/招工广告话术拦截。
后台热更：每次请求实时读 sensitive_words 表，改完立即生效，不用重启。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

MODEL_BLOCK_PATTERNS = [
    (re.compile(r"(招聘|兼职)\s*[：:]?\s*日[结入]", re.I), "疑似招工广告"),
]


@dataclass
class ModerationResult:
    ok: bool
    action: str = "pass"            # pass / block / rewrite
    layer: str = ""                 # sensitive_word / regex / model
    reasons: list[str] = field(default_factory=list)
    prompt: str = ""
    masked_text: str = ""
    masked_count: int = 0

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "action": self.action,
            "layer": self.layer,
            "reasons": self.reasons,
            "prompt": self.prompt,
            "masked_count": self.masked_count,
        }


def _mask_value(value: str, as_type: str) -> str:
    """按 as 类型打码：保留可辨识的头尾，中间用 * 盖住。"""
    v = value.strip()
    if not v:
        return "***"
    if as_type == "phone" and len(v) >= 7:
        return f"{v[:3]}****{v[-4:]}"
    if as_type == "idcard" and len(v) >= 10:
        return f"{v[:6]}********{v[-2:]}"
    if as_type == "bankcard" and len(v) >= 8:
        return f"{v[:4]}********{v[-4:]}"
    if as_type in ("wechat", "qq", "qqgroup", "email") and len(v) >= 4:
        return f"{v[:2]}***"
    if as_type == "address":
        return "**号**室"
    if as_type == "plate":
        return f"{v[:2]}***"
    return "***" if len(v) <= 6 else f"{v[:2]}***{v[-1:]}"


def _load_rules(conn):
    return conn.execute(
        "SELECT word, level, kind, prompt, as_type FROM sensitive_words ORDER BY id"
    ).fetchall()


def mask_only(conn, text: str) -> str:
    """只做 mask 级正则打码（不做拦截判定），用于入库前的二次打码。"""
    masked = text or ""
    for row in _load_rules(conn):
        if row["level"] != "mask" or row["kind"] != "regex":
            continue
        try:
            pattern = re.compile(row["word"])
        except re.error:
            continue
        masked = pattern.sub(lambda m: _mask_value(m.group(0), row["as_type"] or ""), masked)
    return masked


def moderate(conn, text: str) -> ModerationResult:
    """两级审核 + 正则打码。返回打码后的文本（masked_text）供入库使用。"""
    if not (text or "").strip():
        return ModerationResult(False, "block", "rule", ["内容为空"], "请填写内容", "", 0)

    masked = text
    masked_count = 0
    rules = _load_rules(conn)

    # 第一遍：正则（mask 先打码；block/review 直接拒）
    for row in rules:
        if row["kind"] != "regex":
            continue
        try:
            pattern = re.compile(row["word"])
        except re.error:
            continue
        if not pattern.search(masked):
            continue
        if row["level"] == "mask":
            before = masked
            masked = pattern.sub(lambda m: _mask_value(m.group(0), row["as_type"] or ""), masked)
            if masked != before:
                masked_count += 1
            continue
        if row["level"] == "block":
            return ModerationResult(False, "block", "regex", [row["word"]], row["prompt"] or "", masked, masked_count)
        return ModerationResult(False, "rewrite", "regex", [row["word"]], row["prompt"] or "", masked, masked_count)

    # 第二遍：关键词（block / review）
    lowered = masked.lower()
    for row in rules:
        if row["kind"] != "word":
            continue
        word = str(row["word"]).lower()
        if not word or word not in lowered:
            continue
        if row["level"] == "block":
            return ModerationResult(False, "block", "sensitive_word", [word], row["prompt"] or "", masked, masked_count)
        return ModerationResult(False, "rewrite", "sensitive_word", [word], row["prompt"] or "", masked, masked_count)

    # 第三层：模型（本地降级，接云内容安全只改这里）
    for pattern, label in MODEL_BLOCK_PATTERNS:
        if pattern.search(masked):
            return ModerationResult(False, "block", "model", [label], "广场不允许发布外部链接或广告", masked, masked_count)

    return ModerationResult(True, "pass", "model", [], "", masked, masked_count)
