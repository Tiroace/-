"""第 0 关 ①：RapidOCR 真实图片端到端（识别 → 分析 → 报告）。

用法：
    python eval/eval_raw_e2e.py                 # 跑 data/testset/_raw 全部图片
    python eval/eval_raw_e2e.py --limit 5       # 只跑前 5 张
    python eval/eval_raw_e2e.py --json           # 只输出 JSON（CI 用）

报每张：OCR 行数、OCR 耗时、分析耗时、总耗时、结论、命中的规则、证据是否可追溯、PII 是否泄漏。
这是「真实链路」的验收脚本：不是喂现成 OCR 文本，而是从 PNG 图片一路跑到报告。
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from _console import safe_console  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "testset" / "_raw"

PHONE_RE = re.compile(r"1[3-9]\d{9}")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")


def main() -> int:
    safe_console()
    as_json = "--json" in sys.argv
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])

    from engine.adapters.ocr import make_ocr_adapter
    from engine.config import default_config
    from engine.pipeline import analyze

    images = sorted(RAW_DIR.glob("*.png"))
    if limit:
        images = images[:limit]
    if not images:
        print(f"没有找到真实图片：{RAW_DIR}")
        return 1

    cfg = default_config()
    cfg.use_dedupe = False
    cfg.report_dir = None

    ocr = make_ocr_adapter(getattr(cfg, "ocr_backend", "rapidocr"))
    rows = []
    # 先预热一次：模型加载约 10 秒，不该算进第一张的耗时
    warm = images[0]
    t0 = time.perf_counter()
    ocr.extract([warm])
    warmup_ms = (time.perf_counter() - t0) * 1000

    for path in images:
        t0 = time.perf_counter()
        try:
            ocr_result = ocr.extract([path])
        except Exception as exc:  # 单张失败不影响整批，但要如实记
            rows.append({"image": path.name, "ok": False, "error": f"OCR_FAILED: {exc}"})
            continue
        ocr_ms = (time.perf_counter() - t0) * 1000
        text = ocr_result.text
        lines = ocr_result.lines

        t1 = time.perf_counter()
        try:
            result = analyze([str(path)], text, config=cfg)
            report = result.report
        except Exception as exc:
            rows.append({"image": path.name, "ok": False, "error": f"ANALYZE_FAILED: {exc}", "ocr_ms": round(ocr_ms, 1)})
            continue
        analyze_ms = (time.perf_counter() - t1) * 1000

        findings = report.get("findings") or []
        traceable = all(f["evidence"].replace(" ", "") in text.replace(" ", "") for f in findings)
        masked = not PHONE_RE.search(json.dumps(report, ensure_ascii=False)) and not EMAIL_RE.search(
            json.dumps(report, ensure_ascii=False)
        )
        dims = {d["key"]: d["level"] for d in report.get("dimensions") or []}
        rows.append(
            {
                "image": path.name,
                "ok": True,
                "ocr_lines": len(lines),
                "ocr_ms": round(ocr_ms, 1),
                "analyze_ms": round(analyze_ms, 1),
                "total_ms": round(ocr_ms + analyze_ms, 1),
                "overall": report.get("overall"),
                "is_job": report.get("is_job_posting"),
                "rules": [f.get("rule_id") for f in findings if f.get("rule_id")],
                "findings": len(findings),
                "traceable": traceable,
                "pii_masked": masked,
                "dims": dims,
                "text_head": (text.strip().split("\n")[0][:36] if text.strip() else ""),
            }
        )

    if as_json:
        print(json.dumps({"warmup_ms": round(warmup_ms, 1), "rows": rows}, ensure_ascii=False, indent=1))
        return 0

    ok_rows = [r for r in rows if r.get("ok")]
    print(f"真实图片端到端：{len(images)} 张（{RAW_DIR}）")
    print(f"模型预热：{warmup_ms:.0f} ms（不计入单张耗时）\n")
    print(f"{'图片':<12}{'行':>4}{'OCR':>9}{'分析':>9}{'合计':>9}  {'结论':<8}{'规则':<28}证据 PII")
    print("-" * 96)
    for r in rows:
        if not r.get("ok"):
            print(f"{r['image']:<12} 失败：{r['error']}")
            continue
        print(
            f"{r['image']:<12}{r['ocr_lines']:>4}{r['ocr_ms']:>8.0f}ms{r['analyze_ms']:>8.0f}ms"
            f"{r['total_ms']:>8.0f}ms  {str(r['overall']):<8}{','.join(r['rules'])[:26]:<28}"
            f"{'✓' if r['traceable'] else '✗'}   {'✓' if r['pii_masked'] else '✗'}"
        )

    if ok_rows:
        totals = sorted(r["total_ms"] for r in ok_rows)
        ocrs = sorted(r["ocr_ms"] for r in ok_rows)
        n = len(ok_rows)
        p50 = totals[n // 2]
        p95 = totals[min(n - 1, int(n * 0.95))]
        print("-" * 96)
        print(
            f"成功 {n}/{len(rows)}；单张合计 P50 {p50:.0f}ms / P95 {p95:.0f}ms / 最大 {totals[-1]:.0f}ms；"
            f"OCR P50 {ocrs[n // 2]:.0f}ms"
        )
        from collections import Counter

        print("结论分布：", dict(Counter(r["overall"] for r in ok_rows)))
        bad_trace = [r["image"] for r in ok_rows if not r["traceable"]]
        bad_pii = [r["image"] for r in ok_rows if not r["pii_masked"]]
        print(f"证据不可追溯：{len(bad_trace)} 张 {bad_trace}")
        print(f"输出含未脱敏手机号/邮箱：{len(bad_pii)} 张 {bad_pii}")
        failed = len(rows) - n
        return 0 if (failed == 0 and not bad_trace and not bad_pii) else 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
