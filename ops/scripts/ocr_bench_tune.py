"""鐪熷疄鍥剧墖 OCR 鑰楁椂鍩哄噯锛堝惈鍙傛暟璋冧紭瀵规瘮锛夈€?
鐢ㄩ€旓細缁欍€屽崟寮?鈮? 绉掋€嶉獙鏀剁嚎鎻愪緵瀹炴祴渚濇嵁锛屽苟楠岃瘉 limit_side_len 璋冨皬鑳界渷澶氬皯銆?鐢ㄦ硶锛歱ython var/ocr_tune.py [--limit 1000,800,640] [--threads 4] [--n 6]
"""
from __future__ import annotations

import argparse
import statistics
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
RAW = ROOT / "data" / "testset" / "_raw"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", default="1000,800,640")
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--n", type=int, default=6, help="鐢ㄥ嚑寮犲浘")
    args = ap.parse_args()

    from rapidocr import RapidOCR

    imgs = sorted(RAW.glob("*.png"))[: args.n]
    if not imgs:
        print("娌℃湁鐪熷疄鍥剧墖")
        return

    print(f"鍥剧墖 {len(imgs)} 寮狅紝threads={args.threads}")
    print(f"{'limit_side_len':>15} | {'P50':>7} | {'P90':>7} | {'鏈€蹇?:>7} | {'鏈€鎱?:>7}")
    print("-" * 62)

    for limit in [int(x) for x in args.limit.split(",")]:
        # 姣忔閲嶅缓寮曟搸浠ュ簲鐢ㄦ柊鍙傛暟
        t0 = time.perf_counter()
        engine = RapidOCR(
            params={
                "Global.max_side_len": limit,
                "EngineConfig.onnxruntime.intra_op_num_threads": args.threads,
            }
        )
        init_s = time.perf_counter() - t0

        times = []
        for p in imgs:
            t = time.perf_counter()
            engine(str(p))
            times.append(time.perf_counter() - t)

        times.sort()
        n = len(times)
        p50 = statistics.median(times)
        p90 = times[min(n - 1, int(n * 0.9))] if n > 1 else times[0]
        print(f"{limit:>15} | {p50:7.2f} | {p90:7.2f} | {times[0]:7.2f} | {times[-1]:7.2f}  (鍒濆鍖?{init_s:.2f}s)")


if __name__ == "__main__":
    main()

