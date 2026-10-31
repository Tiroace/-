"""合规文案扫描：禁用词 / AI 标识 / 免责声明 / safe 档措辞

依据 `docs/06-合规与文案/05-报告页文案模板与禁用词清单.md` §7.1、§9 自检清单。
产品经理明确要求：对「全部页面文案 + 测试集报告输出」各跑一遍，要求 0 命中。

两级：
- 一级禁用词：出现即缺陷（对企业定性、夸大能力、绝对化用语、诱导传播）
- safe 档措辞：不得出现「安全」「没问题」「放心」等背书式表达

注意：本模块同时被 pytest 和手工排查脚本复用。
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# ---------------------------------------------------------------- 一级禁用词
# 每条：(词, 原因)
TIER1_BANNED: list[tuple[str, str]] = [
    ("骗子公司", "对企业定性，名誉侵权"),
    ("黑心企业", "对企业定性"),
    ("黑心公司", "对企业定性"),
    ("无良公司", "对企业定性"),
    ("无良企业", "对企业定性"),
    ("垃圾公司", "对企业定性"),
    ("100%识别", "夸大能力"),
    ("100％识别", "夸大能力"),
    ("百分百准确", "夸大能力"),
    ("绝不漏判", "夸大能力"),
    ("一查一个准", "夸大能力"),
    ("最准", "绝对化用语"),
    ("最权威", "绝对化用语"),
    ("唯一权威", "绝对化用语"),
    ("官方认证", "无依据"),
    ("权威认证", "无依据"),
    ("曝光", "隐含事实认定"),
    ("打假", "隐含事实认定"),
    ("揭穿", "隐含事实认定"),
    ("挂出来", "诱导传播"),
    ("挂网上", "诱导传播"),
    ("让大家都知道", "诱导传播"),
]

# safe 档不得出现的背书式措辞
SAFE_FORBIDDEN = ["安全", "没问题", "放心去", "放心", "正规可靠", "可以放心"]

# 定性词（与「这家公司」「该企业」连用时违法）
QUALIFIER_WORDS = ["骗子", "诈骗", "黑心", "违法", "无良", "坑人"]
SUBJECT_WORDS = ["这家公司", "该公司", "该企业", "这家企业", "此公司"]

# 合规必须出现的内容
AI_LABEL_TOKENS = ["AI 生成", "AI生成"]
DISCLAIMER_TOKENS = ["仅供参考", "不构成法律意见"]


@dataclass
class Finding:
    where: str
    word: str
    reason: str
    excerpt: str

    def __str__(self) -> str:
        return f"{self.where}: 出现禁用词「{self.word}」（{self.reason}）… {self.excerpt}"


def _norm(text: str) -> str:
    """去掉空白，避免「骗子公司」被断行/空格拆开而漏检。"""
    return re.sub(r"\s+", "", text or "")


def scan_banned(text: str, where: str = "") -> list[Finding]:
    """扫一级禁用词 + 定性词连用。"""
    flat = _norm(text)
    findings: list[Finding] = []

    for word, reason in TIER1_BANNED:
        w = _norm(word)
        idx = flat.find(w)
        if idx >= 0:
            findings.append(Finding(where, word, reason, flat[max(0, idx - 15): idx + 25]))

    # 「这家公司 + 定性词」连用
    for subj in SUBJECT_WORDS:
        for q in QUALIFIER_WORDS:
            pat = re.escape(subj) + r".{0,6}" + re.escape(q)
            m = re.search(pat, flat)
            if m:
                findings.append(
                    Finding(where, f"{subj}+{q}", "主语是具体主体又下定性结论", flat[max(0, m.start() - 10): m.end() + 10])
                )
    return findings


def check_safe_wording(summary: str, verdict: str, level: str) -> list[Finding]:
    """「无风险」档的措辞检查：只能「暂未发现明显风险」，不能背书。

    兼容两代等级口径：
    - v1：level == "safe"
    - v2：overall == "green"
    """
    findings: list[Finding] = []
    if level not in ("safe", "green"):
        return findings
    blob = f"{summary}{verdict}"
    for w in SAFE_FORBIDDEN:
        if w in blob:
            findings.append(Finding("safe/green 档文案", w, "无风险档不得背书写「安全/没问题/放心」", blob))
    return findings


def check_ai_label_and_disclaimer(text: str, where: str = "") -> list[str]:
    """检查免责声明是否在，以及是否违规出现「AI」字样。

    【2026-10-31 路线调整令】一期不用大模型、**产品中不出现「AI」字样**。
    要求从「必须有 AI 标识」反转为「AI 标识必须为 0」：
    - 免责声明仍需存在（已换成"由系统根据截图文字和规则库自动生成"）
    - 「AI 生成」「AI 服务」等对外字样必须为 0

    注意：变量名 `DISCLAIMER` 里天然含 "AI"（D-IS-CLAIMER），
    所以判定必须针对**中文语境下的 AI 字样**，不能裸查 "AI" 两个字母。
    见 check_no_ai_wording()。
    """
    missing = []
    # 免责声明（新版：仅供参考 / 不构成法律意见）
    if not any(tok in text for tok in DISCLAIMER_TOKENS):
        missing.append(f"{where} 缺少免责声明（仅供参考/不构成法律意见）")
    # 旧版「AI 生成」标识：路线令后应为 0，不是缺失项
    return missing


# 对外可见的 AI 字样（路线令禁止）。只匹配真正的产品文案，不匹配英文变量名。
AI_WORDING_PATTERNS = [
    "AI 生成",
    "AI生成",
    "AI 服务",
    "AI服务",
    "AI 检查",
    "AI检查",
    "AI 判断",
    "人工智能",
    "大模型",
    "模型公示",
]


def check_no_ai_wording(text: str, where: str = "") -> list[str]:
    """路线调整令：产品中不出现「AI」字样。返回命中列表（应为空）。"""
    hits = []
    for pat in AI_WORDING_PATTERNS:
        if pat in text:
            hits.append(f"{where} 出现禁用字样「{pat}」")
    return hits


def check_emergency_numbers(text: str, where: str = "") -> list[str]:
    """高危报告必须出现 110 / 96110 / 12333。"""
    missing = [n for n in ("110", "96110", "12333") if n not in text]
    return [f"{where} 高危报告缺少应急号码 {n}" for n in missing] if missing else []
