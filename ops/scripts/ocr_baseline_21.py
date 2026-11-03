"""21 张真实截图的 OCR 基线（单张 / 3 张串行 / 3 张并行，含 P95）。

为什么要单独写：之前的测量受本机内存打满与 CPU 争抢污染，数字不可信。
本脚本先把「环境是否干净」记录下来（可用内存、CPU 负载、是否有并发进程），
再跑全量，**如果环境不达标会直接提示，避免又得到一批废数**。

用法：
    python ops/scripts/ocr_baseline_21.py
    python ops/scripts/ocr_baseline_21.py --repeat 2      # 每张跑 2 次
"""
from __future__ import annotations

import argparse
import statistics
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
RAW_DIR = ROOT / "data" / "testset" / "_raw"
OUT = ROOT / "ops" / "evidence" / "ocr-baseline-21.txt"


def env_snapshot() -> dict:
    """记录测量时的环境状态（Windows）。"""
    info = {}
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "$os=Get-CimInstance Win32_OperatingSystem;"
             "$t=[math]::Round($os.TotalVisibleMemorySize/1KB);"
             "$f=[math]::Round($os.FreePhysicalMemory/1KB);"
             "\"$t|$f|\" + (Get-CimInstance Win32_Processor|Select-Object -First 1).LoadPercentage"],
            capture_output=True, text=True, timeout=30,
        ).stdout.strip()
        total, free, load = out.split("|")
        info = {"total_mb": int(total), "free_mb": int(free), "cpu_load": int(load)}
    except Exception as exc:  # noqa: BLE001
        info = {"error": str(exc)}
    return info


def pct(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    idx = min(len(s) - 1, max(0, int(round(p / 100 * len(s))) - 1))
    return s[idx]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--dir", default=None,
                    help="图片目录。云托管容器里没有 data/，需上传图片后指定，如 --dir /app/var/testset")
    args = ap.parse_args()

    img_dir = Path(args.dir) if args.dir else RAW_DIR
    imgs = sorted(img_dir.glob("*.png"))
    if not imgs:
        print(f"[基线] 找不到图片：{img_dir}")
        print("       云托管容器里请用 --dir 指定已上传的图片目录，")
        print("       例如：python /app/ops/scripts/ocr_baseline_21.py --dir /app/var/testset")
        return 1

    env = env_snapshot()
    lines: list[str] = []
    def say(s: str = "") -> None:
        print(s)
        lines.append(s)

    say("=" * 72)
    say("OCR 基线测量（21 张真实截图）")
    say("=" * 72)
    say(f"测量时间   : {time.strftime('%Y-%m-%d %H:%M:%S')}")
    if "error" in env:
        say(f"环境探测失败: {env['error']}")
    else:
        say(f"物理内存   : {env['total_mb']} MB")
        say(f"可用内存   : {env['free_mb']} MB")
        say(f"CPU 负载   : {env['cpu_load']}%")
        if env["free_mb"] < 1500:
            say("⚠️  可用内存 < 1.5GB，数字可能偏高，仅供参考")
        if env["cpu_load"] > 60:
            say("⚠️  CPU 负载 > 60%，可能有其他任务在跑，数字可能偏高")
    say(f"图片数量   : {len(imgs)} 张")
    say(f"每张重复   : {args.repeat} 次")
    say("")

    from rapidocr import RapidOCR

    t0 = time.perf_counter()
    engine = RapidOCR()
    init_s = time.perf_counter() - t0
    say(f"引擎初始化 : {init_s:.2f}s")
    say("")

    # ---------- 1. 单张 ----------
    single: list[float] = []
    say("-" * 72)
    say("【1】单张识别")
    say("-" * 72)
    say(f"{'图片':<14}{'耗时(s)':>10}{'行数':>8}")
    for p in imgs:
        best = None
        n_lines = 0
        for _ in range(args.repeat):
            t = time.perf_counter()
            res = engine(str(p))
            d = time.perf_counter() - t
            best = d if best is None else min(best, d)
            n_lines = len(res.txts) if getattr(res, "txts", None) else 0
        single.append(best)
        say(f"{p.stem:<14}{best:>10.2f}{n_lines:>8}")

    say("")
    say(f"单张 P50 = {statistics.median(single):.2f}s")
    say(f"单张 P95 = {pct(single, 95):.2f}s")
    say(f"单张 均值 = {statistics.mean(single):.2f}s")
    say(f"单张 最快 = {min(single):.2f}s / 最慢 = {max(single):.2f}s")
    say(f"→ 验收线「单张 ≤4s」: {'✅ 达标' if pct(single, 95) <= 4 else '❌ 不达标'}")
    say("")

    # ---------- 2. 三张串行 ----------
    say("-" * 72)
    say("【2】3 张串行（一次分析提交 3 张）")
    say("-" * 72)
    serial: list[float] = []
    for i in range(0, len(imgs) - 2, 3):
        batch = imgs[i:i + 3]
        t = time.perf_counter()
        for p in batch:
            engine(str(p))
        serial.append(time.perf_counter() - t)
    say(f"组数     = {len(serial)}")
    say(f"3 张 P50 = {statistics.median(serial):.2f}s")
    say(f"3 张 P95 = {pct(serial, 95):.2f}s")
    say(f"→ 验收线「3 张 ≤10s」: {'✅ 达标' if pct(serial, 95) <= 10 else '❌ 不达标'}")
    say("")

    # ---------- 3. 三张并行 ----------
    say("-" * 72)
    say("【3】3 张并行（前台并发识别，更接近真实并发）")
    say("-" * 72)
    parallel: list[float] = []
    for i in range(0, len(imgs) - 2, 3):
        batch = imgs[i:i + 3]

        def worker(path: str, box: list) -> None:
            t = time.perf_counter()
            engine(path)
            box.append(time.perf_counter() - t)

        t = time.perf_counter()
        threads = [threading.Thread(target=worker, args=(str(p), [])) for p in batch]
        for th in threads:
            th.start()
        for th in threads:
            th.join()
        parallel.append(time.perf_counter() - t)

    say(f"组数     = {len(parallel)}")
    say(f"3 张并行 P50 = {statistics.median(parallel):.2f}s")
    say(f"3 张并行 P95 = {pct(parallel, 95):.2f}s")
    say(f"→ 验收线「3 张 ≤10s」（并行）: {'✅ 达标' if pct(parallel, 95) <= 10 else '❌ 不达标'}")
    say("")
    say("=" * 72)
    say("说明：本机为 i7-10510U（4 物理核 / 8 逻辑核 / 8GB），非云托管环境；")
    say("      云托管 2 核 4G 预计更慢、4 核 8G 接近本机。**部署当天必须在云上复测。**")
    say("=" * 72)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n[基线] 已保存：{OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
