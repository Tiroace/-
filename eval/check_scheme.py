"""验证报告升级规则（老板 2026-11-04 定的三条）与 scheme 白名单。"""
import sys

sys.path.insert(0, r"D:\qiuzhibilei")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import json
from pathlib import Path

ROOT = Path(r"D:\qiuzhibilei")
src = json.loads((ROOT / "rules/patterns_v1.json").read_text(encoding="utf-8"))
schemes = {s["scheme_id"]: s for s in src.get("schemes") or []}
local = (ROOT / "src/src/services/localReport.js").read_text(encoding="utf-8")

checks = []


def check(name, cond):
    checks.append((name, bool(cond)))


# 1) 9 个 scheme 齐全，且都有五件套字段
need = ["S-01", "S-02", "S-03", "S-04", "S-05", "S-06", "S-07", "S-08", "S-00"]
check("9 个 scheme 齐全", all(k in schemes for k in need))
check("每个 scheme 有 title/how_harm/consequence/ask",
      all(all(s.get(f) for f in ("title", "how_harm", "consequence", "ask")) for s in schemes.values()))

# 2) 新增红灯套路
pids = {p["pattern_id"]: p for p in src["patterns"]}
check("P-PROMISE-01 已入唯一来源", "P-PROMISE-01" in pids)
check("P-PROMISE-01 是红灯", pids.get("P-PROMISE-01", {}).get("level") == "red")

# 3) 升级规则常量
check("升级 scheme 集合 = S-01/02/03/07/08",
      "SCHEME_ESCALATE = new Set(['S-01', 'S-02', 'S-03', 'S-07', 'S-08'])" in local)
check("升级维度 = work/pay/title", "ESCALATE_DIMS = ['work', 'pay', 'title']" in local)
check("升级阈值 >= 3", "amberCount >= 3" in local)
check("把握需为 high 才升级", "=== 'high'" in local)

# 4) 前端 scheme 清单与源码一致
front = (ROOT / "src/src/common/patterns.js").read_text(encoding="utf-8")
check("前端 SCHEMES 与源一致（9 个）", front.count('"scheme_id"') == len(schemes))
check("前端含 S-00", '"S-00"' in front)

# 5) 提示词包含 scheme 段
prompt = (ROOT / "rules/prompt_v1.txt").read_text(encoding="utf-8")
check("提示词含整体套路清单", "整体套路清单" in prompt)
check("提示词要求输出 scheme_id", '"scheme_id"' in prompt)
check("提示词要求 confidence", "confidence" in prompt)

bad = 0
for name, ok in checks:
    print(("[OK]   " if ok else "[FAIL] ") + name)
    bad += 0 if ok else 1
print()
print("全部通过" if bad == 0 else f"{bad} 项未通过")
raise SystemExit(0 if bad == 0 else 1)
