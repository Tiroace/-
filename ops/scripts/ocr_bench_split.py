"""鎷嗚В OCR 鑰楁椂锛氭娴?det) / 鍒嗙被(cls) / 璇嗗埆(rec) 鍚勫崰澶氬皯銆?
鐪熷疄鎴浘 1290x2796锛屽崟寮?30s+锛岄渶瑕佸畾浣嶇摱棰堟墠鑳界粰浼樺寲鏂规銆?"""
from __future__ import annotations

import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
IMG = sorted((ROOT / "data" / "testset" / "_raw").glob("*.png"))[0]


def run(label: str, params: dict) -> None:
    from rapidocr import RapidOCR

    t0 = time.perf_counter()
    engine = RapidOCR(params=params)
    init = time.perf_counter() - t0
    t1 = time.perf_counter()
    res = engine(str(IMG))
    total = time.perf_counter() - t1
    n_txt = len(res.txts) if hasattr(res, "txts") and res.txts else 0
    print(f"{label:38s} 鍗曞浘 {total:6.2f}s  琛屾暟 {n_txt:3d}  鍒濆鍖?{init:.2f}s")


print(f"鍥剧墖: {IMG.name}")
run("榛樿(鍏ㄥ紑 det+cls+rec)", {})
run("鍏抽棴鏂瑰悜鍒嗙被 use_cls=False", {"Global.use_cls": False})
run("max_side_len=960", {"Global.max_side_len": 960})
run("鍙娴嬩笉璇嗗埆 use_rec=False", {"Global.use_rec": False})
run("threads=8", {"EngineConfig.onnxruntime.intra_op_num_threads": 8})

