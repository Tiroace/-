"""实现级单测：幂等（任务/去重/回调/流水）与越权。"""
from __future__ import annotations

from backend.tests.conftest import OCR_TEXT, auth, balance, create_task, login, wait_task


def test_idempotency_key_returns_same_task(client):
    user = login(client)
    token = user["token"]
    headers = {"Idempotency-Key": "idem-abc"}
    first = create_task(client, token, "idem-1", headers=headers).json()["data"]
    second = create_task(client, token, "idem-1", headers=headers).json()["data"]
    assert first["task_id"] == second["task_id"]
    assert second["idempotent_replay"] is True
    assert second["quota"]["balance"] == first["quota"]["balance"]
    assert balance(client, token) == 2, "只扣一次"


def test_dedupe_same_image_within_24h_does_not_charge(client):
    user = login(client)
    token = user["token"]
    created = create_task(client, token, "same-image").json()["data"]
    wait_task(client, token, created["task_id"])
    assert balance(client, token) == 2

    dup = create_task(client, token, "same-image").json()["data"]
    assert dup["dedupe_hit"] is True
    assert dup["task_id"] == created["task_id"]
    assert balance(client, token) == 2, "去重命中不扣次数"


def test_other_users_task_is_invisible(client):
    alice = login(client)
    bob = login(client)
    task_id = create_task(client, alice["token"], "alice-task").json()["data"]["task_id"]
    resp = client.get(f"/analysis/{task_id}", headers=auth(bob["token"]))
    assert resp.status_code == 404, "越权必须 404，不暴露任务是否存在"


def test_pay_notify_replay_is_idempotent(client):
    user = login(client)
    token = user["token"]
    order = client.post("/orders", headers=auth(token), json={"plan": "month", "channel": "toutiao"}).json()["data"]
    from backend.app.config import get_settings
    from backend.app.platform.mock import MockAdapter

    fields = {
        "order_id": order["order_id"],
        "platform_order_id": "tt-1",
        "amount_fen": "1990",
        "status": "paid",
    }
    sig = MockAdapter("toutiao", get_settings()).sign(fields)
    first = client.post("/pay/notify", json={**fields, "amount_fen": 1990, "signature": sig})
    second = client.post("/pay/notify", json={**fields, "amount_fen": 1990, "signature": sig})
    assert first.json()["data"]["replayed"] is False
    assert second.json()["data"]["replayed"] is True


def test_pay_notify_rejects_forged_signature(client):
    user = login(client)
    token = user["token"]
    order = client.post("/orders", headers=auth(token), json={"plan": "week", "channel": "toutiao"}).json()["data"]
    resp = client.post(
        "/pay/notify",
        json={"order_id": order["order_id"], "platform_order_id": "x", "amount_fen": 690, "status": "paid", "signature": "forged"},
    )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "SIGNATURE_INVALID"


def test_platform_order_id_conflict(client):
    user = login(client)
    token = user["token"]
    from backend.app.config import get_settings
    from backend.app.platform.mock import MockAdapter

    adapter = MockAdapter("toutiao", get_settings())
    o1 = client.post("/orders", headers=auth(token), json={"plan": "week", "channel": "toutiao"}).json()["data"]
    o2 = client.post("/orders", headers=auth(token), json={"plan": "week", "channel": "toutiao"}).json()["data"]
    f1 = {"order_id": o1["order_id"], "platform_order_id": "same-id", "amount_fen": "690", "status": "paid"}
    assert client.post("/pay/notify", json={**f1, "amount_fen": 690, "signature": adapter.sign(f1)}).status_code == 200
    f2 = {"order_id": o2["order_id"], "platform_order_id": "same-id", "amount_fen": "690", "status": "paid"}
    resp = client.post("/pay/notify", json={**f2, "amount_fen": 690, "signature": adapter.sign(f2)})
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"


def test_ledger_has_single_hold_per_task(client):
    """实现细节：一个任务只能有一条预扣流水（幂等键唯一索引兜住）。"""
    user = login(client)
    token = user["token"]
    created = create_task(client, token, "ledger-1").json()["data"]
    wait_task(client, token, created["task_id"])
    from backend.app.deps import get_db

    with get_db().connect() as conn:
        holds = conn.execute(
            "SELECT COUNT(*) AS c FROM quota_ledger WHERE ref = ? AND reason = 'analysis_hold'",
            (created["task_id"],),
        ).fetchone()["c"]
        marks = conn.execute(
            "SELECT COUNT(*) AS c FROM quota_ledger WHERE ref = ? AND reason = 'analysis_mark'",
            (created["task_id"],),
        ).fetchone()["c"]
        total = conn.execute(
            "SELECT COALESCE(SUM(delta),0) AS s FROM quota_ledger WHERE user_id = ?", (user["user_id"],)
        ).fetchone()["s"]
    assert holds == 1 and marks == 1
    assert total == 2, "余额就是流水汇总"
