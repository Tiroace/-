"""规则版（全手机本地）唯一来源生成器：rules/local_rules_v1.json -> 前端规则模块。

为什么要脚本：
- 规则版提审上线，规则必须是确定的、可自查的。规则源只有一份 JSON。
- 前端 ruleKeywords.js 由此生成，仓库里任何地方都不手抄第二份关键词。

产物：
  src/src/common/ruleKeywords.js   前端规则数据（纯数据，无逻辑）

注意：引号里的中文和「App/QQ/VX」这类大小写写法是**规则的一部分**，不要「顺便统一」，
      改了匹配行为就变了。生成产物带 don't 手改标记。

用法：
  python scripts/gen_local_rules.py           # 生成
  python scripts/gen_local_rules.py --check   # 校验产物与源是否一致（CI 用）
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "rules" / "local_rules_v1.json"
FRONT = ROOT / "src" / "src" / "common" / "ruleKeywords.js"

DIMENSIONS = ("fee", "work", "title", "pay", "company", "contract")


def build_front(src: dict) -> str:
    dims = src.get("dimensions") or []
    data = {
        "version": src.get("version", "v3.0-local"),
        "minChars": src.get("min_chars", 20),
        "recruitKeywords": src.get("recruit_keywords") or [],
        "dimensions": dims,
    }
    header = (
        "// 由 scripts/gen_local_rules.py 从 rules/local_rules_v1.json 生成，不要手改。\n"
        f"// 来源版本：{data['version']}　维度：{len(dims)} 个\n"
        "// 引号里的中文与大小写写法是规则的一部分，改了匹配行为就变了。\n"
    )
    body = "export const LOCAL_RULES = " + json.dumps(data, ensure_ascii=False, indent=2) + ";\n"
    return header + body


def validate(src: dict) -> list[str]:
    errs = []
    dims = src.get("dimensions") or []
    keys = [d.get("dimension") for d in dims]
    if keys != list(DIMENSIONS):
        errs.append(f"维度必须依次为 {list(DIMENSIONS)}，实际 {keys}")
    seen = set()
    for d in dims:
        for lv in ("red", "amber", "green"):
            for rule in d.get(lv) or []:
                rid = rule.get("rule_id")
                if not rid:
                    errs.append(f"{d.get('dimension')} 有规则缺 rule_id")
                    continue
                if rid in seen:
                    errs.append(f"rule_id 重复：{rid}")
                seen.add(rid)
                if lv in ("red", "amber"):
                    if not rule.get("title"):
                        errs.append(f"{rid} 缺 title")
                    # 两种判定方式二选一：关键词组合（require_all），或代码里的专用逻辑（logic）
                    if not (rule.get("require_all") or rule.get("logic")):
                        errs.append(f"{rid} 既没有 require_all 也没有专用判定逻辑 logic")
                if lv == "green" and not (rule.get("require_all") or rule.get("duty_terms")):
                    errs.append(f"{rid} 绿灯规则没有判定条件")
    return errs


def main() -> int:
    check = "--check" in sys.argv
    src = json.loads(SRC.read_text(encoding="utf-8"))
    errs = validate(src)
    if errs:
        print("[FAIL] rules/local_rules_v1.json 有问题：")
        for e in errs:
            print("   ", e)
        return 2
    front = build_front(src)
    if check:
        if not FRONT.is_file() or FRONT.read_text(encoding="utf-8") != front:
            print(f"[FAIL] {FRONT.relative_to(ROOT)} 与源不一致，请运行 python scripts/gen_local_rules.py")
            return 1
        print(f"[OK] 规则版产物一致（{src.get('version')}，{len(src.get('dimensions') or [])} 个维度）")
        return 0
    FRONT.write_text(front, encoding="utf-8", newline="\n")
    print(f"[OK] 已生成 {FRONT.relative_to(ROOT)}（{src.get('version')}，{len(src.get('dimensions') or [])} 个维度）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
