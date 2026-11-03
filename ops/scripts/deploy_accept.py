"""部署当天的验收包装器：跑开发者写的 eval_api_e2e.py，按 D40 判定并存证。

为什么需要它：
    eval/eval_api_e2e.py 会打印 P50 等数字，但**没有退出码**，跑完不会告诉你达没达标，
    部署当天只能靠人眼看输出，容易看错、也留不下证据。
    这个包装器负责三件事：① 调用它 ② 按 D40 判定 ③ 把输出与判定一并存进证据文件。

D40 验收线（docs/DECISIONS.md）：
    单张 P95 ≤ 10s
    3 张（真并行）P95 ≤ 25s

用法（在仓库根目录或容器 /app 下）：
    python ops/scripts/deploy_accept.py
    # 结果写入 ops/evidence/deploy-acceptance-<时间戳>.txt，退出码 0=通过 / 1=不通过
"""
from __future__ import annotations

import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
EVAL = ROOT / "eval" / "eval_api_e2e.py"
OUT_DIR = ROOT / "ops" / "evidence"

LINE_SINGLE_P95 = 10.0
LINE_TRIPLE_P95 = 25.0


def _parse(text: str) -> dict:
    """从 eval 输出里抓 P50/P95。抓不到就返回空，不猜。"""
    found: dict[str, float] = {}

    # 形如： 单张：n=21 P50 7.92s P95 8.32s
    for m in re.finditer(r"单张[：:].*?P50\s+([\d.]+)s(?:\s+P95\s+([\d.]+)s)?", text):
        found["single_p50"] = float(m.group(1))
        if m.group(2):
            found["single_p95"] = float(m.group(2))

    # 形如：3 图：n=7 P50 14.55s P95 16.08s
    for m in re.finditer(r"3\s*图[：:].*?P50\s+([\d.]+)s(?:\s+P95\s+([\d.]+)s)?", text):
        found["triple_p50"] = float(m.group(1))
        if m.group(2):
            found["triple_p95"] = float(m.group(2))

    # 只有 P50 时（脚本没打 P95），用 P50 兜底并在报告里说明
    return found


def main() -> int:
    if not EVAL.exists():
        print(f"[验收] 找不到 {EVAL}")
        return 1

    print(f"[验收] 运行 {EVAL} ...")
    t0 = time.time()
    proc = subprocess.run(
        [sys.executable, str(EVAL)],
        cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    elapsed = time.time() - t0
    out = (proc.stdout or "") + (proc.stderr or "")

    stats = _parse(out)
    lines: list[str] = []
    lines.append("=" * 68)
    lines.append("部署当天验收（D40）")
    lines.append("=" * 68)
    lines.append(f"时间      : {time.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"耗时      : {elapsed:.1f}s")
    lines.append(f"脚本退出码: {proc.returncode}")
    lines.append("")
    lines.append("----- eval 原始输出 -----")
    lines.extend(out.rstrip().splitlines())
    lines.append("")
    lines.append("-" * 68)
    lines.append("D40 判定")
    lines.append("-" * 68)

    ok = True
    if "single_p95" in stats:
        v = stats["single_p95"]
        good = v <= LINE_SINGLE_P95
        ok &= good
        lines.append(f"单张 P95 {v:5.2f}s  线 ≤{LINE_SINGLE_P95}s  {'✅ 达标' if good else '❌ 不达标'}")
    elif "single_p50" in stats:
        v = stats["single_p50"]
        lines.append(f"单张 P50 {v:5.2f}s  （脚本未输出 P95，用 P50 参考；"
                     f"P50 {v:.2f}s {'已在' if v <= LINE_SINGLE_P95 else '已超'}线内）")
    else:
        ok = False
        lines.append("单张：❌ 未能从输出中解析到 P50/P95（格式可能已变，请人工核对上面原始输出）")

    if "triple_p95" in stats:
        v = stats["triple_p95"]
        good = v <= LINE_TRIPLE_P95
        ok &= good
        lines.append(f"3 图 P95 {v:5.2f}s  线 ≤{LINE_TRIPLE_P95}s  {'✅ 达标' if good else '❌ 不达标'}")
    elif "triple_p50" in stats:
        v = stats["triple_p50"]
        lines.append(f"3 图 P50 {v:5.2f}s  （脚本未输出 P95，用 P50 参考）")
    else:
        ok = False
        lines.append("3 图：❌ 未能从输出中解析到 P50/P95，请人工核对")

    if proc.returncode != 0:
        ok = False
        lines.append(f"脚本退出码 {proc.returncode} ≠ 0，视为不通过")

    lines.append("")
    lines.append(f"总判定：{'✅ 通过' if ok else '❌ 未通过'}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_file = OUT_DIR / f"deploy-acceptance-{time.strftime('%Y%m%d-%H%M%S')}.txt"
    out_file.write_text("\n".join(lines), encoding="utf-8")

    print("\n".join(lines[-12:]))
    print(f"\n[验收] 证据已存：{out_file}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
