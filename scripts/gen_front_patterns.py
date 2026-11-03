"""从 rules/patterns_v1.json 生成前端可用的套路清单 src/src/common/patterns.js。

前端只展示，不参与判断；模型返回的 pattern_id 必须在这里能找到，否则丢弃。
用法：python scripts/gen_front_patterns.py
"""
import io
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
src = json.loads((ROOT / "rules" / "patterns_v1.json").read_text(encoding="utf-8"))
patterns = src.get("patterns") or []
version = src.get("version", "unknown")

items = []
for p in patterns:
    items.append({
        "pattern_id": p.get("pattern_id"),
        "name": p.get("name", ""),
        "dimension": p.get("dimension", "work"),
        "level": p.get("level", "amber"),
        "why": p.get("why", ""),
        "how": p.get("how", ""),
    })

out = ROOT / "src" / "src" / "common" / "patterns.js"
header = (
    "// 由 scripts/gen_front_patterns.py 从 rules/patterns_v1.json 生成，不要手改。\n"
    f"// 来源版本：{version}　条数：{len(items)}\n"
    "// 前端只用于「校验模型返回的 pattern_id 是否合法」和「取话术模板」，不做判断。\n"
)
body = "export const PATTERNS = " + json.dumps(items, ensure_ascii=False, indent=2) + ";\n\n"
body += (
    "export const PATTERN_IDS = new Set(PATTERNS.map((p) => p.pattern_id));\n\n"
    "export function getPattern(id) {\n"
    "  return PATTERNS.find((p) => p.pattern_id === id) || null;\n"
    "}\n"
)
out.write_text(header + body, encoding="utf-8", newline="\n")
print(f"已生成 {out}，{len(items)} 条，版本 {version}")
