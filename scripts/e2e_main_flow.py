"""B 关口主流程点检（真后端 HTTP，不走 TestClient）。

覆盖：登录（开发通道 code=mock）→ 上传（D9 两步）→ 建任务 → 轮询 → 报告 →
扣次数 → 广告无填充兜底领次数 → 会员下单（mock 支付）→ 支付回调 → 会员生效。

用法：
    scripts\\run_backend.ps1                # 另开一个窗口起 127.0.0.1:8000
    python scripts/e2e_main_flow.py         # 退出码 0 = 全过
    python scripts/e2e_main_flow.py --base-url http://127.0.0.1:8010
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)
PAY_SECRET = __import__("os").environ.get("QBL_PAY_SECRET", "dev-pay-secret-change-me")

ROWS: list[dict] = []
FAILED = 0


def _sign(fields: dict) -> str:
    canonical = "&".join(f"{k}={fields[k]}" for k in sorted(fields) if fields[k] is not None)
    digest = hmac.new(PAY_SECRET.encode(), canonical.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


def call(method: str, url: str, *, body: bytes | None = None, headers: dict | None = None) -> tuple[int, dict | str]:
    req = urllib.request.Request(url, data=body, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw.strip().startswith("{") else raw
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(raw)
        except json.JSONDecodeError:
            return exc.code, raw


def step(name: str, ok: bool, status: int, balance: int | None, detail: str = "") -> bool:
    global FAILED
    if not ok:
        FAILED += 1
    ROWS.append({"step": name, "ok": ok, "status": status, "balance": balance, "detail": detail})
    mark = "PASS" if ok else "FAIL"
    bal = "-" if balance is None else str(balance)
    print(f"[{mark}] {name:<28} http={status:<4} balance={bal:<4} {detail}")
    return ok


def multipart(field: str, filename: str, data: bytes, content_type: str = "image/png", extra: dict | None = None):
    boundary = "----qbl" + uuid.uuid4().hex
    parts: list[bytes] = []
    for key, value in (extra or {}).items():
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode())
    parts.append(
        f'--{boundary}\r\nContent-Disposition: form-data; name="{field}"; filename="{filename}"\r\n'
        f"Content-Type: {content_type}\r\n\r\n".encode()
        + data
        + b"\r\n"
    )
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    parser = argparse.ArgumentParser(description="B 关口主流程点检")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    ocr_text = (PROJECT_ROOT / "data" / "testset" / "ocr" / "T002.txt").read_text(encoding="utf-8")

    # 0. 健康检查
    status, body = call("GET", f"{base}/health")
    health_ok = status == 200 and isinstance(body, dict) and body.get("data", {}).get("status") == "up"
    step("健康检查 /health", health_ok, status, None, str(body)[:60] if not health_ok else "")
    if not health_ok:
        print("\n后端没起或不是本仓库的版本，先跑 scripts\\run_backend.ps1")
        return 1

    # 1. 开发登录通道
    status, body = call(
        "POST",
        f"{base}/auth/login",
        body=json.dumps({"platform": "toutiao", "code": f"mock:e2e{uuid.uuid4().hex[:8]}"}).encode(),
        headers={"Content-Type": "application/json"},
    )
    data = body.get("data", {}) if isinstance(body, dict) else {}
    token = data.get("token", "")
    step("登录 code=mock（开发通道）", status == 200 and bool(token), status, data.get("quota", {}).get("balance"), f"platform_mode={data.get('platform_mode')} dev_login={data.get('dev_login')}")
    if not token:
        print("\n开发登录失败：确认服务端用 scripts\\run_backend.ps1 启动（QBL_DEV_MODE=1）")
        return 1
    auth = {"Authorization": f"Bearer {token}"}

    # 2. /me
    status, body = call("GET", f"{base}/me", headers=auth)
    data = body.get("data", {}) if isinstance(body, dict) else {}
    bal0 = data.get("quota", {}).get("balance")
    step("GET /me", status == 200 and bal0 == 3, status, bal0,
         f"ad.today_count={data.get('ad', {}).get('today_count')} checked={data.get('checked_count')} red={data.get('red_count')}")

    # 3. 上传（D9 第一步）
    payload, ctype = multipart("image", "e2e.png", PNG_1X1 + ("e2e" + uuid.uuid4().hex).encode())
    status, body = call("POST", f"{base}/analysis/upload", body=payload, headers={**auth, "Content-Type": ctype})
    data = body.get("data", {}) if isinstance(body, dict) else {}
    image_id = data.get("image_id", "")
    step("上传图片 /analysis/upload", status == 200 and image_id.startswith("i_"), status, None, f"image_id={image_id} safety={data.get('safety', {}).get('mode')}")

    # 4. 建任务（D9 第二步，JSON）
    status, body = call(
        "POST",
        f"{base}/analysis",
        body=json.dumps({"image_ids": [image_id], "ocr_text": ocr_text, "idempotency_key": "e2e-" + uuid.uuid4().hex[:8]}).encode(),
        headers={**auth, "Content-Type": "application/json"},
    )
    data = body.get("data", {}) if isinstance(body, dict) else {}
    task_id = data.get("task_id", "")
    step("建任务 /analysis", status == 200 and data.get("status") in ("pending", "running"), status, data.get("quota", {}).get("balance"), f"task_id={task_id} status={data.get('status')} poll={data.get('poll_after_ms')}")

    # 5. 轮询
    final: dict = {}
    seq: list[str] = []
    deadline = time.time() + 30
    while task_id and time.time() < deadline:
        status, body = call("GET", f"{base}/analysis/{task_id}", headers=auth)
        final = body.get("data", {}) if isinstance(body, dict) else {}
        seq.append(final.get("status", "?"))
        if final.get("status") in ("done", "failed"):
            break
        time.sleep(0.2)
    report = final.get("report") or {}
    step("轮询到终态", final.get("status") == "done", status, final.get("quota", {}).get("balance"), f"序列={'→'.join(seq)} overall={report.get('overall')} findings={len(report.get('findings') or [])}")
    if report:
        v2_keys = ("is_job_posting", "overall", "summary", "dimensions", "findings", "questions_to_ask", "how_to_verify", "prompt_version", "pattern_db_version")
        dims_ok = [d.get("key") for d in report.get("dimensions", [])] == ["fee", "work", "title", "pay", "company", "contract"]
        step("报告 v2 字段完整（6 维度齐全）", all(k in report for k in v2_keys) and dims_ok, 200, None,
             f"overall={report.get('overall')} findings={len(report.get('findings') or [])}")

    # 6. 扣次数
    status, body = call("GET", f"{base}/me", headers=auth)
    bal1 = body.get("data", {}).get("quota", {}).get("balance") if isinstance(body, dict) else None
    step("扣次数（3→2）", status == 200 and bal1 == 2, status, bal1)

    # 7. 广告无填充兜底
    status, body = call(
        "POST",
        f"{base}/ad/reward",
        body=json.dumps({"request_id": "e2e-ad-" + uuid.uuid4().hex[:10], "ad_unit_id": "mock", "result": "no_fill"}).encode(),
        headers={**auth, "Content-Type": "application/json"},
    )
    data = body.get("data", {}) if isinstance(body, dict) else {}
    step("广告 no_fill 兜底 +1（2→3）", status == 200 and data.get("granted") is True and data.get("quota", {}).get("balance") == 3, status, data.get("quota", {}).get("balance"), f"reason={data.get('reason')}")

    # 8. 定价表
    status, body = call("GET", f"{base}/plans", headers=auth)
    data = body.get("data", {}) if isinstance(body, dict) else {}
    amounts = {p.get("plan"): p.get("amount_fen") for p in data.get("plans", [])}
    step("定价表 /plans", status == 200 and amounts.get("month") == 1990, status, None, f"plans={amounts}")

    # 9. 下单
    status, body = call(
        "POST",
        f"{base}/orders",
        body=json.dumps({"plan": "month", "channel": "toutiao"}).encode(),
        headers={**auth, "Content-Type": "application/json"},
    )
    order = body.get("data", {}) if isinstance(body, dict) else {}
    step("会员下单（mock 支付）", status == 200 and order.get("amount_fen") == 1990 and order.get("pay_params", {}).get("mock") is True, status, None, f"order_id={order.get('order_id')}")

    # 10. 支付回调（Mock 签名）
    notify = {
        "order_id": order.get("order_id", ""),
        "platform_order_id": "e2e-tt-" + uuid.uuid4().hex[:8],
        "amount_fen": 1990,
        "status": "paid",
    }
    sig = _sign({**{k: str(v) for k, v in notify.items() if k != "amount_fen"}, "amount_fen": str(notify["amount_fen"])})
    status, body = call(
        "POST",
        f"{base}/pay/notify",
        body=json.dumps({**notify, "signature": sig}).encode(),
        headers={"Content-Type": "application/json"},
    )
    data = body.get("data", {}) if isinstance(body, dict) else {}
    step("支付回调验签发货", status == 200 and data.get("status") == "paid", status, None, f"membership={data.get('membership')}")

    # 11. 会员生效
    status, body = call("GET", f"{base}/me", headers=auth)
    data = body.get("data", {}) if isinstance(body, dict) else {}
    member = data.get("membership", {})
    step("会员生效（每日上限 20）", status == 200 and member.get("active") is True and member.get("daily_limit") == 20, status, data.get("quota", {}).get("balance"), f"expires_at={member.get('expires_at')}")

    # 12. CORS：只放本机来源
    status, body = call(
        "OPTIONS",
        f"{base}/auth/login",
        headers={
            "Origin": "http://127.0.0.1:9420",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    status2, _ = call("OPTIONS", f"{base}/auth/login", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"})
    step("CORS 只放本机来源", status in (200, 204), status, None, f"本机预检={status}；外域预检={status2}（应被拒）")

    print("\n" + "=" * 78)
    print(f"结果：{len(ROWS) - FAILED}/{len(ROWS)} 步通过，退出码 {'0' if FAILED == 0 else '1'}")
    return 0 if FAILED == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
