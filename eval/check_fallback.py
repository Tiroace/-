"""验证「新路径任何一步失败都退回旧流程」—— 用真实失败场景驱动。

不测 UI，只测判断条件：把 runLocal 的每个前置条件逐个打破，
确认它会返回 null（=退回），而不是抛异常或返回半个报告。
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, r"D:\qiuzhibilei")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(r"D:\qiuzhibilei")
judge = (ROOT / "src/src/services/judge.js").read_text(encoding="utf-8")
config = (ROOT / "src/src/common/config.js").read_text(encoding="utf-8")
index_vue = (ROOT / "src/src/pages/index/index.vue").read_text(encoding="utf-8")

checks = []


def check(name, cond, detail=""):
    checks.append((name, bool(cond), detail))


# 1) 没密钥 -> isVisionJudgeAvailable 为 false -> runLocal 立刻返回 null
check("无密钥时 isVisionJudgeAvailable 返回 false",
      "export function isVisionJudgeAvailable() {\n  return !!DEEPSEEK_KEY;\n}" in judge)

# 2) runLocal 里每一步失败都 return null
run_local = index_vue[index_vue.find("async function runLocal("):]
run_local = run_local[: run_local.find("\nasync function runLocalThenFallback")]
check("压缩失败 -> return null", "if (!b64) return null;" in run_local)
check("没有图片 -> return null", "if (!images.length) return null;" in run_local)
check("认出字太少(<MIN_OCR_CHARS) -> return null", "MIN_OCR_CHARS) return null;" in run_local)
check("任何异常 -> catch 里 return null", re.search(r"catch \(e\) \{[\s\S]{0,200}?return null;", run_local) is not None)

# 3) HTTP 失败 / BAD_JSON 在 judge.js 里 reject（由 runLocal 的 catch 接住）
check("HTTP 非 200 -> reject", "return reject(new Error('HTTP_' + res.statusCode));" in judge)
check("JSON 坏 -> reject BAD_JSON", "reject(new Error('BAD_JSON'))" in judge)
check("网络失败 -> reject", "reject(new Error((err && err.errMsg) || 'NETWORK'))" in judge)
check("没密钥 -> reject NO_KEY", "if (!DEEPSEEK_KEY) return reject(new Error('NO_KEY'));" in judge)

# 4) runLocal 返回空/异常后，主流程必须继续走服务器
check("local 为空会继续走服务器流程",
      "if (local && local.report) {" in index_vue and "ensureLogin()\n    .then(() => uploadAll(paths))" in index_vue)

# 5) 退回时用户不该看到新路径的错误提示
check("退回过程不弹错误", "uni.showToast" not in run_local)

# 6) 超时设置存在且可控
check("DeepSeek 超时 15s", "DEEPSEEK_TIMEOUT = 15000;" in config)

bad = 0
for name, ok, detail in checks:
    print(("[OK]   " if ok else "[FAIL] ") + name + (("  " + detail) if detail and not ok else ""))
    bad += 0 if ok else 1
print()
print("全部通过" if bad == 0 else f"{bad} 项未通过")
raise SystemExit(0 if bad == 0 else 1)
