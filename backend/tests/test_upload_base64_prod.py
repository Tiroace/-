"""prod 模式联调：base64 上传 → 真实 OCR → 出报告（全程不传 ocr_text）。

个人助理要求：别只在 mock 下调通就交差，要在「prod 模式 + OCR 真跑」下验证。
这条链路等同云托管上线后的真实路径：
    小程序 wx.cloud.callContainer → POST /analysis/upload-base64
    → POST /analysis（只给 image_ids）→ worker 真实 OCR → 报告

与 test_upload_base64.py 的分工：
- 那边测端点契约（封套、非法入参、data URI）；
- 这里测端到端：生产环境闸门打开时，base64 这条路还能不能正常出报告。
"""
from __future__ import annotations

import base64
from pathlib import Path

import pytest

from .conftest import PROJECT_ROOT, auth, balance, login, wait_task

REAL_SHOT = PROJECT_ROOT / "data" / "testset" / "_raw" / "raw-01.png"


@pytest.fixture()
def prod_client(tmp_path, monkeypatch):
    """生产模式：QBL_ENV=prod、旁路关闭、真实 OCR（不设 QBL_OCR_SIDECAR）。"""
    monkeypatch.setenv("QBL_DB_PATH", str(tmp_path / "prod.db"))
    monkeypatch.setenv("QBL_UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("QBL_REPORT_DIR", str(tmp_path / "reports"))
    monkeypatch.setenv("QBL_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("QBL_ENGINE_MODEL", "mock")
    monkeypatch.setenv("QBL_POLL_AFTER_MS", "20")
    monkeypatch.setenv("QBL_ADMIN_TOKEN", "dev-admin-token")
    monkeypatch.setenv("QBL_ENV", "prod")
    monkeypatch.setenv("QBL_DEV_BYPASS", "0")
    # 生产环境必须换掉三处默认口令（DEFAULT_SECRETS），否则 assert_production_ready 拒绝启动
    monkeypatch.setenv("QBL_TOKEN_SECRET", "prod-test-secret-0123456789abcdef")
    monkeypatch.setenv("QBL_PAY_SECRET", "prod-pay-secret-0123456789abcdef")
    monkeypatch.setenv("QBL_ADMIN_TOKEN", "prod-admin-token-0123456789abcdef")
    monkeypatch.setenv("QBL_DEV_MODE", "0")
    monkeypatch.delenv("QBL_OCR_SIDECAR", raising=False)

    from backend.app import deps, worker
    from backend.app.main import app
    from fastapi.testclient import TestClient

    deps.reset_db()
    with TestClient(app) as test_client:
        yield test_client
    worker.shutdown(wait=True)


@pytest.mark.skipif(not REAL_SHOT.is_file(), reason="缺真实截图样本")
def test_prod_base64_end_to_end_with_real_ocr(prod_client):
    """prod 下 base64 上传 + 真实 OCR，能拿到 done 报告。"""
    token = login(prod_client, platform="weixin")["token"]

    raw = REAL_SHOT.read_bytes()
    up = prod_client.post(
        "/analysis/upload-base64",
        json={"image_b64": base64.b64encode(raw).decode("ascii"), "mime": "image/png"},
        headers=auth(token),
    )
    assert up.status_code == 200, up.text
    image_id = up.json()["data"]["image_id"]

    before = balance(prod_client, token)
    created = prod_client.post(
        "/analysis",
        json={"image_ids": [image_id], "idempotency_key": "prod-e2e-base64"},
        headers=auth(token),
    )
    assert created.status_code == 200, created.text
    assert created.json()["data"]["status"] in ("pending", "running")
    assert balance(prod_client, token) == before - 1, "预扣 1 次"

    task = wait_task(prod_client, token, created.json()["data"]["task_id"], timeout=90)
    assert task["status"] == "done", f"prod 链路失败：{task.get('error_code')} {task.get('error_message')}"
    report = task["report"]
    assert report and report.get("overall") in ("red", "amber", "green", "unknown")
    # 证据必须能指回截图原文（引擎的硬要求）
    for f in report.get("findings", []):
        assert f.get("evidence"), "findings 里必须有 evidence"


@pytest.mark.skipif(not REAL_SHOT.is_file(), reason="缺真实截图样本")
def test_prod_rejects_ocr_text_bypass_before_quota(prod_client):
    """prod 下传 ocr_text 必须 400，且不扣次数（闸门在预扣之前）。"""
    token = login(prod_client, platform="weixin")["token"]
    raw = REAL_SHOT.read_bytes()
    up = prod_client.post(
        "/analysis/upload-base64",
        json={"image_b64": base64.b64encode(raw).decode("ascii"), "mime": "image/png"},
        headers=auth(token),
    )
    image_id = up.json()["data"]["image_id"]
    before = balance(prod_client, token)

    resp = prod_client.post(
        "/analysis",
        json={"image_ids": [image_id], "ocr_text": "任意预置文本"},
        headers=auth(token),
    )
    assert resp.status_code == 400, resp.text
    assert resp.json()["error"]["code"] == "BYPASS_FORBIDDEN"
    assert balance(prod_client, token) == before, "被闸门拦下的请求不该扣次数"


@pytest.mark.skipif(not REAL_SHOT.is_file(), reason="缺真实截图样本")
def test_prod_multipart_end_to_end_still_works(prod_client):
    """旧 multipart 端点在生产模式下同样可用（本地/公网链路回归）。"""
    token = login(prod_client, platform="weixin")["token"]
    raw = REAL_SHOT.read_bytes()
    up = prod_client.post(
        "/analysis/upload",
        headers=auth(token),
        files={"image": ("shot.png", raw, "image/png")},
    )
    assert up.status_code == 200, up.text
    image_id = up.json()["data"]["image_id"]
    created = prod_client.post(
        "/analysis",
        json={"image_ids": [image_id], "idempotency_key": "prod-e2e-multipart"},
        headers=auth(token),
    )
    task = wait_task(prod_client, token, created.json()["data"]["task_id"], timeout=90)
    assert task["status"] == "done", f"multipart 在 prod 下失败：{task.get('error_code')}"
