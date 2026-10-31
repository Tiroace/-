"""实现级单测：异步状态机 pending → running → done/failed + 30 秒转后台语义。"""
from __future__ import annotations

import time

from backend.tests.conftest import OCR_TEXT, auth, balance, create_task, login, wait_task


def test_create_returns_immediately_with_pending(client):
    user = login(client)
    resp = create_task(client, user["token"], "async-1")
    body = resp.json()["data"]
    assert resp.status_code == 200
    assert body["status"] in ("pending", "running"), "POST 不得阻塞到分析完成，也不得已是终态（D8）"
    assert body["poll_after_ms"] and body["poll_after_ms"] > 0


def test_status_transitions_to_done(client):
    user = login(client)
    token = user["token"]
    created = create_task(client, token, "async-2").json()["data"]
    seen = set()
    deadline = time.time() + 10
    while time.time() < deadline:
        data = client.get(f"/analysis/{created['task_id']}", headers=auth(token)).json()["data"]
        seen.add(data["status"])
        if data["status"] in ("done", "failed"):
            break
        time.sleep(0.02)
    assert data["status"] == "done"
    # 中间态用 test_running_state_observable 单独覆盖（Mock 太快，首轮轮询可能已经是 done）
    assert data["started_at"] and data["finished_at"]
    assert data["report"] is not None
    assert data["poll_after_ms"] is None, "结束后不再给轮询间隔"


def test_running_state_observable(client, monkeypatch):
    """给引擎加人为延迟，确认中间态是 running 而不是一直 pending。"""
    monkeypatch.setenv("QBL_FAKE_ENGINE_DELAY_MS", "600")
    user = login(client)
    token = user["token"]
    created = create_task(client, token, "async-3").json()["data"]
    time.sleep(0.25)
    mid = client.get(f"/analysis/{created['task_id']}", headers=auth(token)).json()["data"]
    assert mid["status"] in ("running", "done"), mid["status"]
    done = wait_task(client, token, created["task_id"])
    assert done["status"] == "done"


def test_background_mode_after_threshold(client, monkeypatch):
    """超过 background_after_seconds 仍没结果：background_mode=true，服务端继续跑不取消。"""
    monkeypatch.setenv("QBL_BACKGROUND_AFTER_SECONDS", "1")
    monkeypatch.setenv("QBL_FAKE_ENGINE_DELAY_MS", "2000")
    user = login(client)
    token = user["token"]
    created = create_task(client, token, "async-4").json()["data"]

    time.sleep(1.2)
    mid = client.get(f"/analysis/{created['task_id']}", headers=auth(token)).json()["data"]
    assert mid["background_mode"] is True
    assert mid["status"] in ("pending", "running")
    assert mid["poll_after_ms"] is not None, "转后台后仍可继续轮询"

    final = wait_task(client, token, created["task_id"], timeout=20)
    assert final["status"] == "done", "转后台不等于取消"
    assert final["background_mode"] is False


def test_failed_task_reports_error_and_refunds(client, monkeypatch):
    # 一期默认走确定性规则引擎；这里显式打开大模型插件来构造失败场景
    monkeypatch.setenv("QBL_ENGINE_MODEL", "deepseek")
    monkeypatch.setenv("QBL_USE_LLM", "1")
    user = login(client)
    token = user["token"]
    created = create_task(client, token, "async-fail").json()["data"]
    failed = wait_task(client, token, created["task_id"])
    assert failed["status"] == "failed"
    assert failed["error_code"] in ("ANALYSIS_FAILED", "ANALYSIS_UNAVAILABLE", "SCHEMA_FAILED")
    assert failed["report"] is None
    assert failed["poll_after_ms"] is None
    assert balance(client, token) == 3


def test_concurrent_tasks_do_not_cross_quota(client, monkeypatch):
    """并发 5 单：每单各自预扣，互不串额度，总数正好扣 5。"""
    monkeypatch.setenv("QBL_FAKE_ENGINE_DELAY_MS", "300")
    user = login(client)
    token = user["token"]
    for i in range(5):
        client.post("/ad/reward", headers=auth(token), json={"request_id": f"concurrent-ad-{i:02d}", "ad_unit_id": "u", "result": "completed"})
    assert balance(client, token) == 8

    tasks = [create_task(client, token, f"c-{i}").json()["data"]["task_id"] for i in range(5)]
    results = [wait_task(client, token, tid) for tid in tasks]
    assert all(r["status"] == "done" for r in results)
    assert balance(client, token) == 3
