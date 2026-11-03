"""验证 env 判断：develop/trial 不限次数，release 照常扣。

用 node 跑（env.js 是纯 JS，不依赖 uni/wx 运行时，把 wx 注入 globalThis 即可）。
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(r"D:\qiuzhibilei")
ENV_JS = ROOT / "src/src/common/env.js"
OUT = ROOT / "var" / "_env_test.mjs"

body = f'''
globalThis.wx = {{
  getAccountInfoSync: () => ({{ miniProgram: {{ envVersion: process.env.EV }} }}),
}};
'''

cases = {
    "develop": True,
    "trial": True,
    "release": False,
    "未知值(abc)": False,
}
code_lines = []
for name, expect in cases.items():
    ev = name if name in ("develop", "trial", "release") else "abc"
    code_lines.append(
        f"""{{ process.env.EV = {json.dumps(ev)};
  const m = await import('./src/src/common/env.js?{name}');
  const v = m.getEnvVersion(); const u = m.isUnlimitedEnv();
  console.log(JSON.stringify({{ case: {json.dumps(name)}, envVersion: v, unlimited: u, expect: {str(expect).lower()} }}));
}}"""
    )

script = (
    "const results = [];\n"
    + "\n".join(code_lines)
    + "\n"
)
OUT.write_text(script, encoding="utf-8", newline="\n")

# 每个 case 需要在 import 前设置 wx 的返回值：用命令行参数分别跑
def run(ev: str) -> dict:
    one = OUT.parent / "_env_one.mjs"
    one.write_text(
        "globalThis.wx = { getAccountInfoSync: () => ({ miniProgram: { envVersion: %s } }) };\n"
        "const m = await import(%s);\n"
        "console.log(JSON.stringify({ envVersion: m.getEnvVersion(), unlimited: m.isUnlimitedEnv() }));\n"
        % (json.dumps(ev), json.dumps(ENV_JS.as_uri())),
        encoding="utf-8",
        newline="\n",
    )
    r = subprocess.run(["node", str(one)], capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        raise SystemExit(f"node 失败：{r.stderr[:400]}")
    return json.loads(r.stdout.strip().splitlines()[-1])


bad = 0
for name, expect in cases.items():
    ev = name if name in ("develop", "trial", "release") else "abc"
    got = run(ev)
    ok = got["unlimited"] == expect and (got["envVersion"] == (ev if ev in ("develop", "trial", "release") else "release"))
    bad += 0 if ok else 1
    print(("[OK]   " if ok else "[FAIL] ") + f"{name:12} -> envVersion={got['envVersion']:8} unlimited={got['unlimited']} 期望={expect}")

# 没有 wx 时（H5/旧基础库）必须按 release 处理，不能白嫖
one = OUT.parent / "_env_one.mjs"
one.write_text(
    "globalThis.wx = undefined;\n"
    "const m = await import(%s);\n"
    "console.log(JSON.stringify({ envVersion: m.getEnvVersion(), unlimited: m.isUnlimitedEnv() }));\n"
    % json.dumps(ENV_JS.as_uri()),
    encoding="utf-8",
    newline="\n",
)
r = subprocess.run(["node", str(one)], capture_output=True, text=True, encoding="utf-8")
got = json.loads(r.stdout.strip().splitlines()[-1])
ok = got["unlimited"] is False and got["envVersion"] == "release"
bad += 0 if ok else 1
print(("[OK]   " if ok else "[FAIL] ") + f"无 wx        -> envVersion={got['envVersion']} unlimited={got['unlimited']} 期望=False（不能白嫖）")

for f in (OUT, OUT.parent / "_env_one.mjs"):
    f.unlink(missing_ok=True)
print()
print("全部通过" if bad == 0 else f"{bad} 项未通过")
raise SystemExit(0 if bad == 0 else 1)
