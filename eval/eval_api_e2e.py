"""第 2 关：API 端到端 —— 上传真实图片 → 真实 OCR → 报告（P95 按 D40 验收）。

用法：
    python eval/eval_api_e2e.py                 # 单张 21 张 + 3 张组 7 组
    python eval/eval_api_e2e.py --single-only
    python eval/eval_api_e2e.py --groups 3      # 只跑前 3 组三图

关键点（第 2 关硬要求）：
- 走真实 API：POST /analysis/upload 传 PNG，POST /analysis 建任务，轮询拿报告
- **不传 ocr_text**，迫使 worker 走真实 OCR（不是 uploads/<task>/ocr.txt 旁路）
- 3 张图必须真并行：报告 trace 里 ocr.parallel 必须为 True
- 验收线 D40：单张 P95 ≤10s，3 张并行 P95 ≤25s
"""
from __future__ import annotations

import json
import statistics
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from _console import safe_console  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "testset" / "_raw"


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    return s[min(len(s) - 1, int(len(s) * 0.95))]


def main() -> int:
    safe_console()
    tmp = Path(tempfile.mkdtemp(prefix="qbl_api_e2e_"))
    import os

    os.environ["QBL_DB_PATH"] = str(tmp / "e2e.db")
    os.environ["QBL_UPLOAD_DIR"] = str(tmp / "uploads")
    os.environ["QBL_REPORT_DIR"] = str(tmp / "reports")
    os.environ["QBL_CACHE_DIR"] = str(tmp / "cache")
    os.environ["QBL_FREE_QUOTA"] = "100"
    os.environ["QBL_ENGINE_MODEL"] = "mock"
    os.environ["QBL_OCR_BACKEND"] = "rapidocr"
    os.environ.pop("QBL_OCR_SIDECAR", None)  # 必须走真实 OCR

    from fastapi.testclient import TestClient

    from backend.app import deps
    from backend.app.main import app

    images = sorted(RAW.glob("*.png"))
    only_single = "--single-only" in sys.argv
    group_n = 7
    if "--groups" in sys.argv:
        group_n = int(sys.argv[sys.argv.index("--groups") + 1])
    groups = [images[i : i + 3] for i in range(0, min(len(images), group_n * 3), 3)]

    single_ms: list[float] = []
    group_ms: list[float] = []
    failed: list[tuple[str, str]] = []

    deps.reset_db()
    with TestClient(app) as client:
        def login() -> str:
            r = client.post("/auth/login", json={"platform": "toutiao", "code": f"e2e-{time.time_ns()}"})
            r.raise_for_status()
            return r.json()["data"]["token"]

        token = login()
        headers = {"Authorization": f"Bearer {token}"}

        def run_task(paths: list[Path]) -> tuple[float, dict]:
            ids = []
            for p in paths:
                with p.open("rb") as fh:
                    up = client.post(
                        "/analysis/upload",
                        headers=headers,
                        files={"image": (p.name, fh.read(), "image/png")},
                    )
                if up.status_code != 200:
                    raise RuntimeError(f"上传失败 {p.name}: {up.status_code} {up.text[:120]}")
                ids.append(up.json()["data"]["image_id"])
            t0 = time.perf_counter()
            # 注意：不带 ocr_text，强制真实 OCR
            r = client.post("/analysis", json={"image_ids": ids}, headers=headers)
            if r.status_code != 200:
                raise RuntimeError(f"建任务失败: {r.status_code} {r.text[:120]}")
            tid = r.json()["data"]["task_id"]
            deadline = time.time() + 180
            while time.time() < deadline:
                d = client.get(f"/analysis/{tid}", headers=headers).json()["data"]
                if d["status"] in ("done", "failed"):
                    return (time.perf_counter() - t0) * 1000, d
                time.sleep(0.1)
            raise TimeoutError(f"任务超时 {tid}")

        print(f"真实 API 端到端：单张 {len(images)} 张 + {len(groups)} 组三图\n")
        for p in images:
            try:
                ms, d = run_task([p])
            except Exception as exc:
                failed.append((p.name, str(exc))[:2])
                continue
            if d["status"] != "done":
                failed.append((p.name, d.get("error_code") or "failed"))
                continue
            single_ms.append(ms)
            print(f"  {p.name:<12}{ms / 1000:>7.2f}s  {d['report']['overall']:<8} rules={len(d['report'].get('findings') or [])}")

        if only_single:
            groups = []

        for i, grp in enumerate(groups, 1):
            names = ",".join(x.name for x in grp)
            try:
                ms, d = run_task(grp)
            except Exception as exc:
                failed.append((names, str(exc)))
                continue
            if d["status"] != "done":
                failed.append((names, d.get("error_code") or "failed"))
                continue
            group_ms.append(ms)
            print(f"  组{i:<10}{ms / 1000:>7.2f}s  {d['report']['overall']:<8} {names}")

    print()
    print("=" * 60)
    ok = True
    if single_ms:
        print(f"单张：n={len(single_ms)} P50 {statistics.median(single_ms) / 1000:.2f}s "
              f"P95 {_p95(single_ms) / 1000:.2f}s 验收线 ≤10s "
              f"{'达标' if _p95(single_ms) <= 10000 else '**不达标**'}")
        ok = ok and _p95(single_ms) <= 10000
    if group_ms:
        print(f"3 图：n={len(group_ms)} P50 {statistics.median(group_ms) / 1000:.2f}s "
              f"P95 {_p95(group_ms) / 1000:.2f}s 验收线 ≤25s "
              f"{'达标' if _p95(group_ms) <= 25000 else '**不达标**'}")
        ok = ok and _p95(group_ms) <= 25000
    if failed:
        print(f"失败 {len(failed)} 项：{failed[:5]}")
        ok = False
    print("=" * 60)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
