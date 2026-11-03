"""匿名统计接口：隐私底线 + 入参校验 + TopN 聚合。"""
from __future__ import annotations

import json

from backend.tests.conftest import auth, login


class Test匿名上报:
    def test_不需要登录也能上报(self, client):
        r = client.post("/stats/pattern", json={"overall": "red", "pattern_ids": ["P-FEE-01"], "scheme_id": "S-08"})
        assert r.status_code == 200, r.text
        assert r.json()["data"]["recorded"] is True

    def test_只存结论与编号_不存身份(self, client):
        """隐私底线：表里不能有 user_id / openid / 设备号 / 原文。"""
        token = login(client)["token"]
        client.post(
            "/stats/pattern",
            json={"overall": "amber", "pattern_ids": ["P-SOFT-01"], "scheme_id": "S-05",
                  "text": "这段文字不该被存", "openid": "o_should_not_store"},
            headers={**auth(token), "X-Device-Id": "dev-should-not-store"},
        )
        from backend.app.deps import get_db

        with get_db().connect() as conn:
            cols = {r["name"] for r in conn.execute("PRAGMA table_info(check_stats)")}
            row = conn.execute("SELECT * FROM check_stats ORDER BY id DESC LIMIT 1").fetchone()
        assert "user_id" not in cols and "openid" not in cols and "device_id" not in cols, f"表里出现了身份字段：{cols}"
        blob = json.dumps(dict(row), ensure_ascii=False)
        assert "o_should_not_store" not in blob
        assert "dev-should-not-store" not in blob
        assert "这段文字不该被存" not in blob

    def test_非法overall被拒(self, client):
        r = client.post("/stats/pattern", json={"overall": "purple"})
        assert r.status_code == 400

    def test_未知套路编号被丢弃(self, client):
        r = client.post("/stats/pattern", json={"overall": "red", "pattern_ids": ["P-NOT-EXIST", "P-FEE-01"]})
        assert r.status_code == 200
        from backend.app.deps import get_db

        with get_db().connect() as conn:
            row = conn.execute("SELECT patterns FROM check_stats ORDER BY id DESC LIMIT 1").fetchone()
        ids = json.loads(row["patterns"])
        assert ids == ["P-FEE-01"], f"未知编号没被过滤：{ids}"

    def test_未知scheme被清空(self, client):
        client.post("/stats/pattern", json={"overall": "red", "scheme_id": "S-999"})
        from backend.app.deps import get_db

        with get_db().connect() as conn:
            row = conn.execute("SELECT scheme_id FROM check_stats ORDER BY id DESC LIMIT 1").fetchone()
        assert row["scheme_id"] is None

    def test_正文不是JSON被拒(self, client):
        r = client.post("/stats/pattern", content=b"not json", headers={"Content-Type": "application/json"})
        assert r.status_code == 400


class TestTopN:
    def test_按命中次数排序(self, client):
        for _ in range(3):
            client.post("/stats/pattern", json={"overall": "red", "pattern_ids": ["P-FEE-01"]})
        for _ in range(2):
            client.post("/stats/pattern", json={"overall": "amber", "pattern_ids": ["P-SOFT-01"]})
        r = client.get("/stats/patterns/top?days=7&limit=5")
        assert r.status_code == 200, r.text
        items = r.json()["data"]["items"]
        assert items[0]["pattern_id"] == "P-FEE-01" and items[0]["count"] == 3
        assert items[1]["pattern_id"] == "P-SOFT-01" and items[1]["count"] == 2

    def test_返回套路名与典型说法(self, client):
        client.post("/stats/pattern", json={"overall": "red", "pattern_ids": ["P-FEE-01"]})
        items = client.get("/stats/patterns/top").json()["data"]["items"]
        assert items[0]["name"], "必须带套路名"
        assert items[0]["example"], "必须带典型说法"
        assert items[0]["why"], "必须带原因"

    def test_不返回任何公司名(self, client):
        client.post("/stats/pattern", json={"overall": "red", "pattern_ids": ["P-FEE-01"]})
        text = client.get("/stats/patterns/top").text
        for word in ("有限公司", "集团", "科技"):
            assert word not in text, f"统计结果里出现了公司字样：{word}"
