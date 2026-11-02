"""测 OCR limit_side_len 对耗时与识别质量的影响（真实图片）。

用法：python eval/bench_ocr_limits.py [--limit 5]
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from _console import safe_console  # noqa: E402

RAW = ROOT / "data" / "testset" / "_raw"


def main() -> int:
    safe_console()
    from engine.adapters.ocr import RapidOCREngine

    limit = 3
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])
    images = sorted(RAW.glob("*.png"))[:limit]
    if not images:
        print("没有真实图片")
        return 1

    print(f"真实图片 OCR 基准：{len(images)} 张，{images[0].parent}\n")
    print(f"{'limit':>6}{'线程':>6}{'首张':>10}{'预热后中位':>12}{'行数':>6}")
    print("-" * 46)
    results = {}
    ref_text = {}
    for limit_len in (1000, 800, 640, 480):
        for threads in (8,):
            eng = RapidOCREngine(limit_side_len=limit_len, intra_op_num_threads=threads)
            t = time.perf_counter()
            first = eng.extract([images[0]])
            first_s = time.perf_counter() - t
            times, lines = [], []
            for img in images:
                t = time.perf_counter()
                r = eng.extract([img])
                times.append(time.perf_counter() - t)
                lines.append(len(r.lines))
                ref_text.setdefault(limit_len, []).append(r.text)
            times.sort()
            med = times[len(times) // 2]
            print(f"{limit_len:>6}{threads:>6}{first_s:>9.1f}s{med:>11.1f}s{sum(lines) // len(lines):>6}")
            results[limit_len] = med

    # 与 limit=1000 的结果比对：字符级差异当作质量指标（没有人工标注时的近似）
    base = ref_text.get(1000) or []
    print("\n与 limit=1000 的识别结果差异（越小越接近）：")
    for limit_len, texts in ref_text.items():
        if limit_len == 1000:
            continue
        same = sum(1 for a, b in zip(base, texts) if a == b)
        print(f"  limit={limit_len}: {same}/{len(base)} 张与 limit=1000 完全一致")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
