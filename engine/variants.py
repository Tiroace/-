"""变形写法表：把词库关键词展开成能容忍常见规避写法的正则。

规则（路线调整令第二节）：
- V信 / 薇信 / 威信 → 微信；扣扣 → QQ；「押 金」「ya金」→ 押金；
- 表放 `lexicon/variants_v1.json`，运营可随时加，无需发版。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class VariantGroup:
    canonical: str
    variants: list[str]

    @property
    def surface(self) -> list[str]:
        seen: list[str] = []
        for item in [self.canonical, *self.variants]:
            item = item.strip()
            if item and item not in seen:
                seen.append(item)
        return seen


@dataclass
class VariantTable:
    version: str = "v0"
    groups: list[VariantGroup] = field(default_factory=list)

    def _sorted_groups(self) -> list[VariantGroup]:
        # 长词优先，避免「押金费」被「押金」抢先匹配
        return sorted(self.groups, key=lambda g: len(g.canonical), reverse=True)

    def expand(self, keyword: str) -> str | None:
        """把一个关键词展开成正则片段；没有变形时返回 None（调用方用 re.escape）。"""
        keyword = keyword.strip()
        if not keyword:
            return None
        groups = self._sorted_groups()
        units: list[str] = []
        i = 0
        changed = False
        while i < len(keyword):
            matched: VariantGroup | None = None
            for group in groups:
                if keyword.startswith(group.canonical, i):
                    matched = group
                    break
            if matched is not None:
                alts = "|".join(re.escape(x) for x in matched.surface)
                units.append(f"(?:{alts})")
                i += len(matched.canonical)
                changed = True
            else:
                units.append(re.escape(keyword[i]))
                i += 1
        if not changed:
            return None
        # 每个单元之间容忍空格/零宽字符：押 金、V 信
        return r"[\s\u200b]*".join(units)

    def spaced(self, keyword: str) -> str:
        """即使没有变形，也允许字与字之间被插入空格。"""
        chars = [re.escape(ch) for ch in keyword.strip()]
        return r"[\s\u200b]*".join(chars)


def load_variants(path: str | Path | None) -> VariantTable:
    if not path:
        return VariantTable()
    p = Path(path)
    if not p.is_file():
        return VariantTable()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return VariantTable()
    groups = [
        VariantGroup(canonical=str(g["canonical"]).strip(), variants=[str(v).strip() for v in g.get("variants", [])])
        for g in data.get("groups", [])
        if g.get("canonical")
    ]
    return VariantTable(version=str(data.get("version", "v0")), groups=groups)
