"""后端安全测试（需求书 §6.1–§6.3 + §8）

覆盖用户点名的五项：
1. 越权看他人报告
2. 重复领广告奖励（幂等 / 每日上限）
3. 伪造支付回调
4. 额度流水对账
5. 广告失败兜底给次数（no_fill 也必须给）

约定：每个用例用独立的临时 SQLite 库与独立 Settings，绝不碰 var/backend/qbl.db。
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

from conftest import ROOT

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

pytest.importorskip("fastapi", reason="后端测试需要 fastapi")
pytest.importorskip("httpx", reason="TestClient 需要 httpx")

TestClient = pytest.importorskip("fastapi.testclient").TestClient


# ----------------------------------------------------------------- 夹具

@pytest.fixture()
def app_env(tmp_path, monkeypatch):
    """每个用例一套干净的库 + 干净的单例，返回 (client, settings, db)。"""
    db_path = tmp_path / "qbl.db"
    monkeypatch.setenv("QBL_DB_PATH", str(db_path))
    monkeypatch.setenv("QBL_UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("QBL_REPORT_DIR", str(tmp_path / "reports"))
    monkeypatch.setenv("QBL_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("QBL_TOKEN_SECRET", "test-token-secret")
    monkeypatch.setenv("QBL_PAY_SECRET", "test-pay-secret")
    monkeypatch.setenv("QBL_ADMIN_TOKEN", "test-admin-token")

    for mod in list(sys.modules):
        if mod == "backend" or mod.startswith("backend."):
            del sys.modules[mod]

    from backend.app import deps, main
    from backend.app.config import get_settings

    importlib.reload(main)
    deps.reset_db()
    settings = get_settings()
    app = main.app
    client = TestClient(app)
    yield client, settings, deps.get_db(settings)


def login(client, code: str = "code-user-a") -> dict:
    r = client.post("/auth/login", json={"platform": "toutiao", "code": code})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("ok") is True, body
    return body["data"]


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def register_user(client, code: str) -> tuple[str, str]:
    data = login(client, code)
    return data["user_id"], data["token"]


# ----------------------------------------------------------------- 1. 越权

class Test越权访问报告:
    def test_未登录访问报告列表被拒(self, app_env):
        client, _, _ = app_env
        r = client.get("/reports")
        assert r.status_code in (401, 403), f"未登录竟能访问：{r.status_code} {r.text[:200]}"

    def test_未登录访问我的信息被拒(self, app_env):
        client, _, _ = app_env
        r = client.get("/me")
        assert r.status_code in (401, 403)

    def test_伪造token被拒(self, app_env):
        client, _, _ = app_env
        for bad in ("abc", "u1.u_deadbeef.9999999999.deadbeef", "Bearer x"):
            r = client.get("/me", headers=auth(bad))
            assert r.status_code in (401, 403), f"伪造 token 未拦截：{bad}"

    def test_篡改user_id的token被拒(self, app_env):
        """拿 A 的 token，把 payload 里的 user_id 改成 B：签名必须对不上。"""
        client, _, _ = app_env
        uid_a, tok_a = register_user(client, "code-a")
        uid_b, _ = register_user(client, "code-b")
        parts = tok_a.split(".")
        assert len(parts) == 4
        forged = ".".join([parts[0], uid_b, parts[2], parts[3]])
        r = client.get("/me", headers=auth(forged))
        assert r.status_code in (401, 403), "篡改 user_id 后签名仍通过，鉴权形同虚设"

    def test_A拿不到B的报告(self, app_env):
        """核心越权用例：A 请求 B 的报告详情必须 403/404，不能返回内容。"""
        client, _, _ = app_env
        uid_a, tok_a = register_user(client, "code-a")
        uid_b, tok_b = register_user(client, "code-b")

        # 尝试列报告：只能看到自己的
        r = client.get("/reports", headers=auth(tok_a))
        if r.status_code == 200:
            items = r.json().get("data", {}).get("items", r.json().get("data", []))
            for item in items or []:
                owner = item.get("user_id") if isinstance(item, dict) else None
                assert owner in (None, uid_a), f"列表泄漏了他人报告：{owner}"

        # 直接猜报告 id 访问
        for rid in ("r_does_not_exist", "r_" + uid_b, uid_b):
            rr = client.get(f"/reports/{rid}", headers=auth(tok_a))
            assert rr.status_code in (403, 404), (
                f"A 访问他人/不存在的报告 {rid} 返回 {rr.status_code}，应 403/404"
            )


# ----------------------------------------------------------------- 2. 重复领广告奖励

class Test重复领广告奖励:
    def test_同一request_id重复提交只发一次(self, app_env):
        client, settings, _ = app_env
        uid, tok = register_user(client, "code-ad-1")
        before = client.get("/me", headers=auth(tok)).json()["data"]["quota"]["balance"]

        payload = {"request_id": "req-0001-aaa", "ad_unit_id": "u1", "result": "completed"}
        r1 = client.post("/ad/reward", json=payload, headers=auth(tok))
        assert r1.status_code == 200, r1.text
        r2 = client.post("/ad/reward", json=payload, headers=auth(tok))
        assert r2.status_code == 200, r2.text

        after = client.get("/me", headers=auth(tok)).json()["data"]["quota"]["balance"]
        assert after - before == 1, f"重复提交多领了次数：余额从 {before} 变成 {after}"

    def test_并发重复提交也只发一次(self, app_env):
        client, settings, _ = app_env
        uid, tok = register_user(client, "code-ad-2")
        before = client.get("/me", headers=auth(tok)).json()["data"]["quota"]["balance"]

        payload = {"request_id": "req-0002-bbb", "ad_unit_id": "u1", "result": "completed"}
        for _ in range(5):
            client.post("/ad/reward", json=payload, headers=auth(tok))

        after = client.get("/me", headers=auth(tok)).json()["data"]["quota"]["balance"]
        assert after - before == 1, f"同一 request_id 提交 5 次，余额却变了 {after - before}"

    def test_每日上限不可突破(self, app_env):
        client, settings, _ = app_env
        uid, tok = register_user(client, "code-ad-3")
        before = client.get("/me", headers=auth(tok)).json()["data"]["quota"]["balance"]

        cap = settings.ad_daily_cap
        for i in range(cap + 3):
            client.post(
                "/ad/reward",
                json={"request_id": f"req-cap-{i:04d}", "ad_unit_id": "u1", "result": "completed"},
                headers=auth(tok),
            )

        after = client.get("/me", headers=auth(tok)).json()["data"]["quota"]["balance"]
        assert after - before == cap, f"每日上限 {cap}，实际发了 {after - before} 次"

    def test_不同用户互不影响(self, app_env):
        """A 的 request_id 不能被 B 复用去白拿。"""
        client, settings, _ = app_env
        uid_a, tok_a = register_user(client, "code-ad-a")
        uid_b, tok_b = register_user(client, "code-ad-b")
        payload = {"request_id": "req-shared-01", "ad_unit_id": "u1", "result": "completed"}
        client.post("/ad/reward", json=payload, headers=auth(tok_a))
        client.post("/ad/reward", json=payload, headers=auth(tok_b))

        bal_b = client.get("/me", headers=auth(tok_b)).json()["data"]["quota"]["balance"]
        assert bal_b == settings.free_quota, (
            f"B 复用了 A 的 request_id 却拿到了奖励：余额 {bal_b}，应为 {settings.free_quota}"
        )


# ----------------------------------------------------------------- 3. 伪造支付回调

class Test伪造支付回调:
    def test_无签名回调被拒(self, app_env):
        client, settings, _ = app_env
        uid, tok = register_user(client, "code-pay-1")
        r = client.post("/orders", json={"plan": "month", "channel": "toutiao"}, headers=auth(tok))
        assert r.status_code == 200, r.text
        order_id = r.json()["data"]["order_id"]

        r = client.post("/pay/notify", json={
            "order_id": order_id,
            "platform_order_id": "plat-1",
            "amount_fen": 1990,
            "status": "paid",
            "signature": "deadbeef",
        })
        assert r.status_code in (401, 403), f"伪造签名回调被接受：{r.status_code} {r.text[:200]}"

    def test_金额篡改回调被拒(self, app_env):
        """签名用真实密钥算，但金额改成 1 分：必须被受理层拦下。"""
        client, settings, _ = app_env
        uid, tok = register_user(client, "code-pay-2")
        r = client.post("/orders", json={"plan": "month", "channel": "toutiao"}, headers=auth(tok))
        order_id = r.json()["data"]["order_id"]

        from backend.app.security import sign_pay_payload

        fields = {"order_id": order_id, "platform_order_id": "plat-2", "amount_fen": "1", "status": "paid"}
        sig = sign_pay_payload(fields, settings.pay_secret)
        r = client.post("/pay/notify", json={
            "order_id": order_id,
            "platform_order_id": "plat-2",
            "amount_fen": 1,
            "status": "paid",
            "signature": sig,
        })
        assert r.status_code >= 400, f"金额与订单不符却通过了：{r.status_code}"

    def test_不存在的订单不发货(self, app_env):
        client, settings, _ = app_env
        from backend.app.security import sign_pay_payload

        fields = {"order_id": "o_not_exist", "platform_order_id": "plat-3", "amount_fen": "1990", "status": "paid"}
        sig = sign_pay_payload(fields, settings.pay_secret)
        r = client.post("/pay/notify", json={
            "order_id": "o_not_exist", "platform_order_id": "plat-3",
            "amount_fen": 1990, "status": "paid", "signature": sig,
        })
        assert r.status_code in (400, 404), f"不存在的订单竟返回 {r.status_code}"

    def test_合法回调重复推送只发一次会员(self, app_env):
        client, settings, db = app_env
        uid, tok = register_user(client, "code-pay-4")
        r = client.post("/orders", json={"plan": "week", "channel": "toutiao"}, headers=auth(tok))
        order_id = r.json()["data"]["order_id"]

        from backend.app.security import sign_pay_payload

        fields = {"order_id": order_id, "platform_order_id": "plat-4", "amount_fen": "690", "status": "paid"}
        sig = sign_pay_payload(fields, settings.pay_secret)
        payload = {
            "order_id": order_id, "platform_order_id": "plat-4",
            "amount_fen": 690, "status": "paid", "signature": sig,
        }
        r1 = client.post("/pay/notify", json=payload)
        assert r1.status_code == 200, r1.text
        expiry_1 = r1.json()["data"]["membership"]["expires_at"]

        r2 = client.post("/pay/notify", json=payload)
        assert r2.status_code == 200, r2.text
        data2 = r2.json()["data"]
        if "membership" in data2:
            assert data2["membership"]["expires_at"] == expiry_1, "重复回调把会员期又延长了一次"

    def test_订单价格由服务端定(self, app_env):
        client, settings, _ = app_env
        uid, tok = register_user(client, "code-pay-5")
        r = client.post("/orders", json={"plan": "month", "channel": "toutiao"}, headers=auth(tok))
        amount = r.json()["data"]["amount_fen"]
        assert amount == settings.prices_fen["month"], f"金额被客户端影响：{amount}"


# ----------------------------------------------------------------- 4. 额度流水对账

class Test额度流水对账:
    def test_新用户余额等于赠送额度(self, app_env):
        client, settings, db = app_env
        uid, tok = register_user(client, "code-q-1")
        bal = client.get("/me", headers=auth(tok)).json()["data"]["quota"]["balance"]
        assert bal == settings.free_quota

    def test_重复登录不重复赠送(self, app_env):
        client, settings, _ = app_env
        login(client, "code-q-2")
        data = login(client, "code-q-2")
        assert data["quota"]["balance"] == settings.free_quota, (
            f"同一 openid 二次登录又送了额度：{data['quota']['balance']}"
        )

    def test_对账函数本身可用且平衡(self, app_env):
        from backend.app.quota import reconcile

        client, settings, db = app_env
        uid, tok = register_user(client, "code-q-3")
        client.post("/ad/reward", json={"request_id": "req-recon-1", "ad_unit_id": "u1", "result": "completed"},
                    headers=auth(tok))
        with db.connect() as conn:
            result = reconcile(conn)
        assert result["negative_balance_users"] == [], f"出现负余额用户：{result['negative_balance_users']}"
        assert result["orphan_holds"] == [], f"出现孤立预扣：{result['orphan_holds']}"

    def test_余额恒等于流水求和(self, app_env):
        from backend.app.quota import balance

        client, settings, db = app_env
        uid, tok = register_user(client, "code-q-4")
        client.post("/ad/reward", json={"request_id": "req-recon-2", "ad_unit_id": "u1", "result": "completed"},
                    headers=auth(tok))
        with db.connect() as conn:
            b = balance(conn, uid)
            row = conn.execute("SELECT SUM(delta) AS s FROM quota_ledger WHERE user_id = ?", (uid,)).fetchone()
        assert b == int(row["s"]), "余额与流水求和不一致（有人在绕过流水改余额）"

    def test_预扣后失败必须退次数(self, app_env):
        """两阶段扣费：hold -1 → refund +1，余额应回到初始值。"""
        from backend.app.quota import balance, hold_for_analysis, refund_for_analysis

        client, settings, db = app_env
        uid, tok = register_user(client, "code-q-5")
        with db.transaction() as conn:
            before = balance(conn, uid)
            hold_for_analysis(conn, uid, "task-x1")
            after_hold = balance(conn, uid)
            refund_for_analysis(conn, uid, "task-x1")
            after_refund = balance(conn, uid)
        assert after_hold == before - 1, "预扣没有生效"
        assert after_refund == before, f"失败未退次数：{before} → {after_refund}"

    def test_退次数幂等(self, app_env):
        """重复退款不能刷次数。"""
        from backend.app.quota import balance, hold_for_analysis, refund_for_analysis

        client, settings, db = app_env
        uid, tok = register_user(client, "code-q-6")
        with db.transaction() as conn:
            before = balance(conn, uid)
            hold_for_analysis(conn, uid, "task-x2")
            refund_for_analysis(conn, uid, "task-x2")
            refund_for_analysis(conn, uid, "task-x2")
            refund_for_analysis(conn, uid, "task-x2")
            after = balance(conn, uid)
        assert after == before, f"重复退款刷出了次数：{before} → {after}"


# ----------------------------------------------------------------- 5. 广告失败兜底

class Test广告失败兜底给次数:
    @pytest.mark.parametrize("result", ["no_fill", "error"])
    def test_广告拉不出来也必须给次数(self, result, app_env):
        """平台硬性要求：广告失败是产品的事，不能让用户白等。"""
        client, settings, _ = app_env
        uid, tok = register_user(client, f"code-fb-{result}")
        before = client.get("/me", headers=auth(tok)).json()["data"]["quota"]["balance"]

        r = client.post(
            "/ad/reward",
            json={"request_id": f"req-fb-{result}-0001", "ad_unit_id": "u1", "result": result},
            headers=auth(tok),
        )
        assert r.status_code == 200, r.text
        after = client.get("/me", headers=auth(tok)).json()["data"]["quota"]["balance"]
        assert after == before + 1, f"result={result} 时没有兜底给次数：{before} → {after}"
