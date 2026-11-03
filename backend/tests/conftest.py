"""实现级单测夹具（backend/tests）。

与测试者的 tests/ 契约测试分工：
- 这里测「实现细节」：额度三段式、幂等键、状态机；
- tests/ 测「对外契约」：schema、证据可追溯、接口字段、验收门槛。
"""
from __future__ import annotations

import base64
import os
import sys
import time
import uuid
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)
OCR_TEXT = (PROJECT_ROOT / "data" / "testset" / "ocr" / "T002.txt").read_text(encoding="utf-8")


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """每个用例一套临时库 + 临时目录，互不污染。"""
    monkeypatch.setenv("QBL_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("QBL_UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("QBL_REPORT_DIR", str(tmp_path / "reports"))
    monkeypatch.setenv("QBL_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("QBL_ENGINE_MODEL", "mock")
    monkeypatch.setenv("QBL_POLL_AFTER_MS", "20")
    monkeypatch.setenv("QBL_ADMIN_TOKEN", "dev-admin-token")
    # 第 2 关起，worker 默认走真实 OCR；但这里的用例上传的是 1x1 假 PNG，
    # 真实 OCR 读不出字（ANALYSIS_UNAVAILABLE）。测试要验的是业务逻辑与状态机，
    # 不是 OCR 质量，所以显式打开旁路读 ocr.txt。
    # 真实 OCR 链路由 eval/eval_raw_e2e.py 和 tests/backend 里专门的 OCR 用例覆盖。
    monkeypatch.setenv("QBL_OCR_SIDECAR", "1")

    from backend.app import deps, worker
    from backend.app.main import app
    from fastapi.testclient import TestClient

    deps.reset_db()
    with TestClient(app) as test_client:
        yield test_client
    worker.shutdown(wait=True)


def login(client, code: str | None = None, platform: str = "toutiao") -> dict:
    resp = client.post("/auth/login", json={"platform": platform, "code": code or f"code-{uuid.uuid4().hex[:8]}"})
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def upload_image(client, token: str, marker: str) -> str:
    """D9：先上传单图拿 image_id。"""
    payload = PNG_1X1 + marker.encode()
    resp = client.post(
        "/analysis/upload",
        headers=auth(token),
        files={"image": (f"{marker}.png", payload, "image/png")},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["image_id"]


def create_task(client, token: str, marker: str, ocr_text: str = OCR_TEXT, headers: dict | None = None):
    image_id = upload_image(client, token, marker)
    body = {"image_ids": [image_id], "idempotency_key": (headers or {}).get("Idempotency-Key")}
    if ocr_text:
        body["ocr_text"] = ocr_text
    return client.post("/analysis", headers=auth(token), json=body)


def wait_task(client, token: str, task_id: str, timeout: float = 15.0) -> dict:
    deadline = time.time() + timeout
    last: dict = {}
    while time.time() < deadline:
        resp = client.get(f"/analysis/{task_id}", headers=auth(token))
        assert resp.status_code == 200, resp.text
        last = resp.json()["data"]
        if last["status"] in ("done", "failed"):
            return last
        time.sleep(0.02)
    raise AssertionError(f"任务 {task_id} 超时：{last}")


def balance(client, token: str) -> int:
    return client.get("/me", headers=auth(token)).json()["data"]["quota"]["balance"]
