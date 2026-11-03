"""base64 上传端点（云托管链路）与 multipart 端点的等价性测试。

背景：微信云托管关闭公网访问后，小程序只能走 wx.cloud.callContainer，
它不支持 multipart，所以新增 POST /analysis/upload-base64。
两条通道必须产出同一种 image_id 封套、走同一套内容安全与落盘逻辑。
"""
from __future__ import annotations

import base64

import pytest

from .conftest import PNG_1X1, auth, login


def _post_b64(client, token, payload: bytes, mime: str = "image/png", **extra):
    body = {"image_b64": base64.b64encode(payload).decode("ascii"), "mime": mime}
    body.update(extra)
    return client.post("/analysis/upload-base64", json=body, headers=auth(token))


def test_base64_upload_returns_same_envelope_as_multipart(client):
    user = login(client, platform="weixin")
    token = user["token"]

    resp = _post_b64(client, token, PNG_1X1 + b"b64-marker")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    data = body["data"]
    # 与 multipart 端点同一套字段
    for field in ("image_id", "hash", "size", "expires_at", "safety"):
        assert field in data, f"缺字段 {field}"
    assert data["image_id"].startswith("i_")
    assert data["safety"]["passed"] is True
    assert data["size"] == len(PNG_1X1) + len(b"b64-marker")


def test_base64_upload_image_id_usable_by_analysis(client):
    user = login(client, platform="weixin")
    token = user["token"]
    up = _post_b64(client, token, PNG_1X1 + b"usable").json()["data"]
    resp = client.post(
        "/analysis",
        json={"image_ids": [up["image_id"]], "ocr_text": ""},
        headers=auth(token),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["status"] in ("pending", "running")


def test_base64_upload_accepts_data_uri_prefix(client):
    user = login(client, platform="weixin")
    token = user["token"]
    uri = "data:image/png;base64," + base64.b64encode(PNG_1X1 + b"uri").decode("ascii")
    resp = client.post("/analysis/upload-base64", json={"image_b64": uri}, headers=auth(token))
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["image_id"].startswith("i_")


@pytest.mark.parametrize(
    "body,needle",
    [
        ({}, "image_b64"),
        ({"image_b64": ""}, "image_b64"),
        ({"image_b64": "!!!not base64!!!"}, "base64"),
        ({"image_b64": base64.b64encode(b"").decode()}, "image_b64"),
    ],
)
def test_base64_upload_rejects_bad_payload(client, body, needle):
    user = login(client, platform="weixin")
    resp = client.post("/analysis/upload-base64", json=body, headers=auth(user["token"]))
    assert resp.status_code in (400, 422), resp.text
    assert needle in resp.text


def test_base64_upload_rejects_oversized_image(client, monkeypatch):
    settings = __import__("backend.app.config", fromlist=["get_settings"]).get_settings()
    user = login(client, platform="weixin")
    big = PNG_1X1 + b"x" * (settings.max_image_mb * 1024 * 1024 + 10)
    resp = _post_b64(client, user["token"], big)
    assert resp.status_code in (400, 413, 422), resp.text


def test_multipart_endpoint_still_works(client):
    """旧端点保留不删：本地开发仍在用。"""
    user = login(client, platform="weixin")
    resp = client.post(
        "/analysis/upload",
        headers=auth(user["token"]),
        files={"image": ("a.png", PNG_1X1 + b"mp", "image/png")},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["image_id"].startswith("i_")
