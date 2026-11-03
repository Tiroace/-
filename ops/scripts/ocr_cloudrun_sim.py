"""云托管目标规格下的 OCR 基线对照（本地等价模拟）。

背景：云托管尚未开通，无法直连实测。本脚本用「限制线程数」模拟云托管容器的
CPU 分配，对比开发机全开与 2 核 / 1 核场景，回答一个问题：
**云托管 2 核 4G 上会不会比开发机慢很多？**

⚠️ 这是等效模拟，不是云托管真实测量。真实值必须部署当天在云上复测。

用法：python ops/scripts/ocr_cloudrun_sim.py
"""
from __future__ import annotations

import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
RAW_DIR = ROOT / "data" / "testset" / "_raw"
OUT = ROOT / "ops" / "evidence" / "ocr-cloudrun-sim.txt"

# 模拟场景：threads 数 ≈ 云托管可用核数
SCENARIOS = [
    ("开发机全开(4线程)", 4),
    ("云托管 2核4G 模拟(2线程)", 2),
    ("云托管最低配 模拟(1线程)", 1),
]


def env_snapshot() -> dict:
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "$os=Get-CimInstance Win32_OperatingSystem;"
             "$f=[math]::Round($os.FreePhysicalMemory/1KB);"
             "\"$f|\" + (Get-CimInstance Win32_Processor|Select-Object -First 1).LoadPercentage"],
            capture_output=True, text=True, timeout=30,
        ).stdout.strip()
        free, load = out.split("|")
        return {"free_mb": int(free), "cpu_load": int(load)}
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


def pct(v: list[float], p: float) -> float:
    s = sorted(v)
    return s[min(len(s) - 1, max(0, int(round(p / 100 * len(s))) - 1))]


def main() -> int:
    imgs = sorted(RAW_DIR.glob("*.png"))[:6]  # 抽样 6 张，控制耗时
    if not imgs:
        print(f"找不到图片：{RAW_DIR}")
        return 1

    env = env_snapshot()
    lines: list[str] = []

    def say(s: str = "") -> None:
        print(s)
        lines.append(s)

    say("=" * 72)
    say("云托管目标规格 OCR 基线对照（本地等效模拟，非云上实测）")
    say("=" * 72)
    say(f"测量时间 : {time.strftime('%Y-%m-%d %H:%M:%S')}")
    if "error" in env:
        say(f"环境探测失败: {env['error']}")
    else:
        say(f"可用内存 : {env['free_mb']} MB")
        say(f"CPU 负载 : {env['cpu_load']}%")
        if env.get("free_mb", 0) < 1500:
            say("⚠️  内存 < 1.5GB，绝对值可能偏高")
        if env.get("cpu_load", 0) > 60:
            say("⚠️  CPU 负载 > 60%，可能有其他任务")
    say(f"样本     : {len(imgs)} 张真实截图")
    say("")

    from rapidocr import RapidOCR

    results: dict[str, dict] = {}
    for name, threads in SCENARIOS:
        engine = RapidOCR(params={
            "EngineConfig.onnxruntime.intra_op_num_threads": threads,
            "EngineConfig.onnxruntime.inter_op_num_threads": threads,
        })
        engine(str(imgs[0]))  # 预热

        times = []
        for p in imgs:
            t = time.perf_counter()
            engine(str(p))
            times.append(time.perf_counter() - t)
        results[name] = {
            "p50": statistics.median(times),
            "p95": pct(times, 95),
            "min": min(times),
            "max": max(times),
        }
        r = results[name]
        say(f"{name:<28} P50 {r['p50']:5.2f}s  P95 {r['p95']:5.2f}s  "
            f"[{r['min']:.2f} ~ {r['max']:.2f}]")

    say("")
    base = results[SCENARIOS[0][0]]
    say("-" * 72)
    say("相对开发机全开（4线程）的倍数：")
    for name, _ in SCENARIOS[1:]:
        r = results[name]
        say(f"  {name:<26} P50 x{r['p50']/base['p50']:.2f}   P95 x{r['p95']/base['p95']:.2f}")
    say("")
    say("-" * 72)
    say("结论判读（D40：单张 P95 ≤10s、3 张并行 P95 ≤25s）：")
    for name, _ in SCENARIOS:
        r = results[name]
        ok1 = "✅" if r["p95"] <= 10 else "❌"
        say(f"  {name:<28} 单张 P95 {r['p95']:5.2f}s  {ok1} 验收线 10s")
    say("")
    say("⚠️ 本结果是**线程数模拟**，不等于云托管实测：")
    say("   云托管 2 核 4G 还受内存上限、CPU 配额、共享宿主机影响，通常更慢。")
    say("   **部署当天必须在云上跑同一批 21 张图复测，以实测为准。**")
    say("=" * 72)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n[模拟] 已保存：{OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

