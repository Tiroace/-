"""求助广场：隐私打码（§11.4 / §8）。

发布前把手机号、微信/QQ、身份证、银行卡、门牌号、人名打码再入库，
从源头避免把第三方的个人信息公开发布。
"""
from __future__ import annotations

import re

from engine.textnorm import mask_pii

# 中文人名：姓 +（1–2 字名）+ 称谓，例如「王经理」「李晓雯女士」
_NAME_RE = re.compile(r"([\u4e00-\u9fa5])([\u4e00-\u9fa5]{1,2})(先生|女士|经理|老师|主管|HR|hr)")
# 门牌号：3 栋 / 12 号 / 501 室 / 18 层
_ADDRESS_RE = re.compile(r"(\d{1,4})\s*(号|栋|号楼|单元|室|层)")
# QQ / 微信号（mask_pii 已覆盖带前缀的，这里补裸号与「加V」）
_QQ_RE = re.compile(r"(?<![0-9A-Za-z])([Qq]{2}|扣扣)\s*[:：]?\s*(\d{5,11})")
_WECHAT_PLAIN_RE = re.compile(r"(加|加V|加v|微)\s*[:：]?\s*([A-Za-z][A-Za-z0-9_-]{5,19})")


def mask_name_text(text: str) -> str:
    """把「王经理」类人名替换成「王**经理」。"""
    return _NAME_RE.sub(lambda m: f"{m.group(1)}**{m.group(3)}", text or "")


def mask_community_text(text: str) -> tuple[str, list[str]]:
    """返回（打码后文本, 命中类型清单）。"""
    hits: list[str] = []
    if not text:
        return "", hits

    masked = mask_pii(text)
    if masked != text:
        hits.append("contact")   # 手机号/身份证/银行卡/微信带前缀/邮箱
    masked = _QQ_RE.sub(lambda m: f"{m.group(1)}：***", masked)
    masked = _WECHAT_PLAIN_RE.sub(lambda m: f"{m.group(1)}：***", masked)
    masked = _ADDRESS_RE.sub(lambda m: f"**{m.group(2)}", masked)
    masked = mask_name_text(masked)
    if masked != text and not hits:
        hits.append("detail")
    return masked, hits
