"""唯一来源生成器：rules/patterns_v1.json -> 提示词 + 前端清单。

为什么要这个脚本（老板规定）：
**套路清单只留一份**。提示词、前端 patterns.js、测试脚本，全部从 rules/patterns_v1.json 生成，
不许手抄第二份——手抄一定会漂移，漂移之后模型能选的编号和前端校验白名单就对不上。

产物：
  1. rules/prompt_v1.txt            发给模型的 system 提示词（前端、测试脚本共用）
  2. src/src/common/patterns.js     前端白名单 + 话术模板

用法：
  python scripts/gen_prompt.py           # 重新生成两个产物
  python scripts/gen_prompt.py --check   # 只校验产物是否与源一致（CI 用，不一致则 exit 1）
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "rules" / "patterns_v1.json"
PROMPT = ROOT / "rules" / "prompt_v1.txt"
FRONT = ROOT / "src" / "src" / "common" / "patterns.js"
FRONT_PROMPT = ROOT / "src" / "src" / "common" / "prompt.js"


def build_prompt(patterns: list[dict], version: str) -> str:
    lines = [f"{p['pattern_id']}｜{p['name']}｜{p.get('hint') or p.get('why') or ''}" for p in patterns]
    return (
        "你是招聘信息风险筛查器。用户给你 1-3 张招聘截图。\n"
        "第一步：把截图里的全部文字完整、原样抄进 text 字段，保留换行，不要概括、不要删减。\n"
        "第二步：判断这段文字是不是招聘信息或和 HR 的聊天；不是就 is_job_posting=false，hits 为空。\n"
        "第三步：从下面的套路清单里找出命中的编号。\n"
        "\n"
        f"套路清单（共 {len(patterns)} 条，只能从这里选；不在清单里的编号一律不许用，不许自己编造）：\n"
        + "\n".join(lines)
        + "\n\n"
        "规则：\n"
        "1. 每条命中必须给 evidence：从 text 里原样复制一句（不超过 60 字），一个字都不能改。\n"
        "2. 没把握的不要选；没有命中就返回空数组。\n"
        "3. 正常薪资范围（例如「7000-8000元」「月薪 6000 元」）不是套路，不要因为出现薪资区间就命中。\n"
        "4. 正常公司信息（公司名称、地址、五险一金）不是套路。\n"
        "5. 软性套路（P-SOFT 开头）看整体意思，不要求原文出现清单里的字。\n"
        "6. 只输出 JSON，不要任何解释：\n"
        '{"is_job_posting": true, "text": "截图里的全部文字", '
        '"hits": [{"pattern_id": "P-XXX", "evidence": "原文"}]}\n'
        "\n"
        f"<!-- 本文件由 scripts/gen_prompt.py 从 rules/patterns_v1.json 生成，版本 {version}，"
        f"共 {len(patterns)} 条；不要手改。 -->\n"
    )


def build_front(patterns: list[dict], version: str) -> str:
    items = [
        {
            "pattern_id": p["pattern_id"],
            "name": p.get("name", ""),
            "dimension": p.get("dimension", "work"),
            "level": p.get("level", "amber"),
            "why": p.get("why", ""),
            "how": p.get("how", ""),
        }
        for p in patterns
    ]
    header = (
        "// 由 scripts/gen_prompt.py 从 rules/patterns_v1.json 生成，不要手改。\n"
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
    return header + body


def build_front_prompt(prompt: str, version: str, count: int) -> str:
    """把同一份提示词打包成前端模块，保证前端用的和测试脚本用的是同一份文字。"""
    return (
        "// 由 scripts/gen_prompt.py 从 rules/patterns_v1.json 生成，不要手改。\n"
        f"// 来源：rules/prompt_v1.txt（版本 {version}，{count} 条）\n"
        "// 前端与测试脚本用同一份提示词，避免两处漂移。\n"
        "export const SYSTEM_PROMPT = " + json.dumps(prompt, ensure_ascii=False) + ";\n"
    )


def main() -> int:
    check = "--check" in sys.argv
    src = json.loads(SRC.read_text(encoding="utf-8"))
    patterns = src.get("patterns") or []
    version = str(src.get("version", "unknown"))
    if not patterns:
        print("[FAIL] rules/patterns_v1.json 里没有 patterns")
        return 2

    prompt = build_prompt(patterns, version)
    front = build_front(patterns, version)
    front_prompt = build_front_prompt(prompt, version, len(patterns))

    if check:
        bad = []
        for path, expected in ((PROMPT, prompt), (FRONT, front), (FRONT_PROMPT, front_prompt)):
            if not path.is_file() or path.read_text(encoding="utf-8") != expected:
                bad.append(str(path.relative_to(ROOT)))
        if bad:
            print("[FAIL] 产物与 rules/patterns_v1.json 不一致，请运行 python scripts/gen_prompt.py：")
            for b in bad:
                print("   ", b)
            return 1
        print(f"[OK] 产物一致（{len(patterns)} 条，版本 {version}）")
        return 0

    PROMPT.write_text(prompt, encoding="utf-8", newline="\n")
    FRONT.write_text(front, encoding="utf-8", newline="\n")
    FRONT_PROMPT.write_text(front_prompt, encoding="utf-8", newline="\n")
    print(
        f"[OK] 已生成 {PROMPT.relative_to(ROOT)}、{FRONT.relative_to(ROOT)}、"
        f"{FRONT_PROMPT.relative_to(ROOT)}，共 {len(patterns)} 条"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
