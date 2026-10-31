"""实现级单测：本轮新增契约（/plans、ad 今日次数、上传归属/过期、单笔上限、旧版 multipart 兼容）。"""
from __future__ import annotations

from backend.tests.conftest import OCR_TEXT, PNG_1X1, auth, login, upload_image


def test_plans_readonly(client):
    user = login(client)
    data = client.get("/plans", headers=auth(user["token"])).json()["data"]
    amounts = {p["plan"]: p["amount_fen"] for p in data["plans"]}
    assert amounts == {"week": 690, "month": 1990, "quarter": 3990}
    assert data["max_single_order_fen"] == 30000, "单笔上限 300 元"
    assert all(p["available_ios"] is False for p in data["plans"]), "iOS 未接虚拟支付前不展示"


def test_me_ad_counts(client):
    user = login(client)
    token = user["token"]
    for i in range(2):
        client.post("/ad/reward", headers=auth(token), json={"request_id": f"adcount-{i:02d}", "ad_unit_id": "u", "result": "completed"})
    ad = client.get("/me", headers=auth(token)).json()["data"]["ad"]
    assert ad["today_count"] == 2
    assert ad["remaining_today"] == ad["daily_cap"] - 2


def test_upload_image_ownership(client):
    alice = login(client)
    bob = login(client)
    image_id = upload_image(client, alice["token"], "alice-img")
    resp = client.post("/analysis", headers=auth(bob["token"]), json={"image_ids": [image_id], "ocr_text": OCR_TEXT})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "IMAGE_NOT_FOUND"


def test_upload_expired(client, monkeypatch):
    monkeypatch.setenv("QBL_UPLOAD_TTL_HOURS", "0")
    user = login(client)
    image_id = upload_image(client, user["token"], "expired-img")
    resp = client.post("/analysis", headers=auth(user["token"]), json={"image_ids": [image_id], "ocr_text": OCR_TEXT})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "IMAGE_EXPIRED"


def test_create_requires_images_or_ocr(client):
    user = login(client)
    resp = client.post("/analysis", headers=auth(user["token"]), json={"image_ids": []})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_order_single_amount_cap(client, monkeypatch):
    monkeypatch.setenv("QBL_MAX_ORDER_AMOUNT_FEN", "100")
    user = login(client)
    resp = client.post("/orders", headers=auth(user["token"]), json={"plan": "month", "channel": "toutiao"})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "ORDER_AMOUNT_EXCEEDED"


def test_legacy_multipart_still_accepted(client):
    """兼容期：旧版 multipart（files[]）调用仍然可用，正式版（T4）再删。"""
    user = login(client)
    resp = client.post(
        "/analysis",
        headers=auth(user["token"]),
        files=[("files", ("legacy.png", PNG_1X1 + b"legacy", "image/png"))],
        data={"ocr_text": OCR_TEXT},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] in ("pending", "running")
