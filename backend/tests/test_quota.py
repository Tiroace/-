"""实现级单测：额度三段式（预扣 → 正式扣 / 退回）+ 广告奖励。"""
from __future__ import annotations

from backend.tests.conftest import auth, balance, create_task, login, wait_task


def test_register_bonus_three_times(client):
    data = login(client, code="fixed-code-1")
    assert data["is_new_user"] is True
    assert data["quota"]["balance"] == 3
    again = login(client, code="fixed-code-1")   # 同一账号重登
    assert again["is_new_user"] is False
    assert again["quota"]["balance"] == 3, "注册赠送只发一次"


def test_hold_then_consume_keeps_deduction(client):
    user = login(client)
    token = user["token"]
    assert balance(client, token) == 3

    created = create_task(client, token, "hold-1").json()["data"]
    assert created["status"] in ("pending", "running"), "创建不阻塞、且不得是终态（D8）"
    assert created["quota"]["balance"] == 2, "提交即预扣"

    done = wait_task(client, token, created["task_id"])
    assert done["status"] == "done"
    assert balance(client, token) == 2, "成功后保持扣 1 次"


def test_failed_task_refunds(client, monkeypatch):
    user = login(client)
    token = user["token"]
    # 确定性规则引擎不会因「模型不可用」失败；失败路径要让大模型插件显式打开（路线调整令后）
    monkeypatch.setenv("QBL_ENGINE_MODEL", "deepseek")
    monkeypatch.setenv("QBL_USE_LLM", "1")
    created = create_task(client, token, "fail-1").json()["data"]
    assert created["status"] in ("pending", "running")
    failed = wait_task(client, token, created["task_id"])
    assert failed["status"] == "failed"
    assert failed["error_code"] == "ANALYSIS_FAILED"
    assert failed["report"] is None
    assert balance(client, token) == 3, "失败必须退回预扣"


def test_quota_exhausted_does_not_hold(client):
    user = login(client)
    token = user["token"]
    for i in range(3):
        create_task(client, token, f"use-{i}")
    assert balance(client, token) == 0
    resp = create_task(client, token, "over-1")
    assert resp.status_code == 402
    assert resp.json()["error"]["code"] == "QUOTA_EXHAUSTED"
    assert balance(client, token) == 0, "被拒时不能再扣"


def test_ad_reward_idempotent_and_capped(client):
    user = login(client)
    token = user["token"]
    headers = auth(token)
    first = client.post("/ad/reward", headers=headers, json={"request_id": "ad-req-0001", "ad_unit_id": "u", "result": "completed"})
    assert first.json()["data"]["granted"] is True
    replay = client.post("/ad/reward", headers=headers, json={"request_id": "ad-req-0001", "ad_unit_id": "u", "result": "completed"})
    assert replay.json()["data"]["replayed"] is True
    assert replay.json()["data"]["quota"]["balance"] == first.json()["data"]["quota"]["balance"]


def test_ad_reward_grants_even_without_fill(client):
    """§6.2：广告拉不出来也必须给奖励（平台强制兜底）。"""
    user = login(client)
    token = user["token"]
    before = balance(client, token)
    resp = client.post(
        "/ad/reward",
        headers=auth(token),
        json={"request_id": "ad-nofill", "ad_unit_id": "u", "result": "no_fill"},
    )
    assert resp.json()["data"]["granted"] is True
    assert balance(client, token) == before + 1


def test_ad_daily_cap(client):
    user = login(client)
    token = user["token"]
    for i in range(5):
        client.post("/ad/reward", headers=auth(token), json={"request_id": f"ad-cap-000{i}", "ad_unit_id": "u", "result": "completed"})
    over = client.post("/ad/reward", headers=auth(token), json={"request_id": "ad-cap-0099", "ad_unit_id": "u", "result": "completed"})
    body = over.json()["data"]
    assert body["granted"] is False
    assert body["reason"] == "daily_cap_reached"
    assert body["today_count"] == 5
