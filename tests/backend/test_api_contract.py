"""后端 API 契约测试（按 docs/04-后端接口契约.md 逐条断言）

【分工】开发者写实现级单测（`backend/tests/`：额度三段式、流水、内部状态机）。
我写**接口契约测试**：只认 HTTP 表面行为 —— 路径、状态码、错误码、响应字段、幂等规则、
异步状态机语义。**不 import 他的内部模块**（除签名工具/配置用于构造合法请求），
这样两边用例不会写成同一批，且他的重构不会误伤我的断言。

依据：docs/04-后端接口契约.md §1.4 错误码表、§1.5 幂等要求、§2.x 逐接口、§3.1 异步状态机。
"""
from __future__ import annotations

import importlib
import json
import sys
import time
import uuid
from pathlib import Path

import pytest

from conftest import ROOT

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

pytest.importorskip("fastapi", reason="需要 fastapi")
pytest.importorskip("httpx", reason="TestClient 需要 httpx")
TestClient = pytest.importorskip("fastapi.testclient").TestClient


# ----------------------------------------------------------------- 夹具

@pytest.fixture()
def env(tmp_path, monkeypatch):
    """每例一套干净库。返回 client + settings。"""
    monkeypatch.setenv("QBL_DB_PATH", str(tmp_path / "qbl.db"))
    monkeypatch.setenv("QBL_UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("QBL_REPORT_DIR", str(tmp_path / "reports"))
    monkeypatch.setenv("QBL_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("QBL_TOKEN_SECRET", "test-token-secret")
    monkeypatch.setenv("QBL_PAY_SECRET", "test-pay-secret")
    monkeypatch.setenv("QBL_ADMIN_TOKEN", "test-admin-token")
    # 让后台线程池尽快跑完，避免用例等太久
    monkeypatch.setenv("QBL_POLL_AFTER_MS", "50")

    for mod in list(sys.modules):
        if mod == "backend" or mod.startswith("backend."):
            del sys.modules[mod]

    from backend.app import deps, main
    from backend.app.config import get_settings

    importlib.reload(main)
    deps.reset_db()
    settings = get_settings()
    client = TestClient(main.app)
    yield client, settings

    # 本轮任务跑完再交给下一个用例，避免线程池跨用例串扰
    wait_worker_idle()


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def login(client, code: str = None) -> dict:
    code = code or ("code-" + uuid.uuid4().hex[:10])
    r = client.post("/auth/login", json={"platform": "toutiao", "code": code})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True, body
    return body["data"]


def new_user(client, code: str = None) -> tuple[str, dict]:
    d = login(client, code)
    return d["user_id"], d


OCR_OK = """高薪招聘 兼职刷单 日结300元
入职需缴纳服装费980元、押金500元，离职退还
"""


def create_analysis(client, token, *, ocr_text=OCR_OK, idem=None, files=None):
    headers = auth(token)
    if idem:
        headers["Idempotency-Key"] = idem
    data = {"ocr_text": ocr_text}
    return client.post("/analysis", data=data, headers=headers, files=files or [])


def poll_until_terminal(client, token, task_id, timeout=20.0):
    """按契约轮询到 done/failed，返回最后一个响应 data。"""
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        r = client.get(f"/analysis/{task_id}", headers=auth(token))
        assert r.status_code == 200, r.text
        last = r.json()["data"]
        if last["status"] in ("done", "failed"):
            return last
        time.sleep(0.05)
    pytest.fail(f"任务 {task_id} 在 {timeout}s 内未到终态，最后状态：{last}")


def settle(client, token, task_id, timeout=20.0):
    """提交后等它跑完，用于「先造一份已完成的报告」这类前置。"""
    return poll_until_terminal(client, token, task_id, timeout=timeout)


def wait_worker_idle(timeout=30.0):
    """等后台线程池把已提交的任务消化完。

    背景：`POST /analysis` 是异步的（契约 §3.1），上一个用例刚提交的任务
    可能在本例运行时仍在跑，落盘/改状态会与本例的余额、去重断言串扰。
    **实测踩到**：同一用例单独跑通过、全量跑失败。

    用 worker 的公开接口 `shutdown(wait=True)` 收尾（它会等所有任务结束并置空单例）。
    """
    try:
        from backend.app import worker as worker_mod
    except Exception:
        time.sleep(0.3)
        return
    try:
        worker_mod.shutdown(wait=True)
    except Exception:
        time.sleep(0.3)


def balance_of(client, token) -> int:
    r = client.get("/me", headers=auth(token))
    assert r.status_code == 200
    return r.json()["data"]["quota"]["balance"]


def error_code(response) -> str:
    body = response.json()
    assert body.get("ok") is False, f"期望失败封套，实际：{body}"
    return body["error"]["code"]


# ================================================================ 一、登录与 /me

class Test登录契约:
    def test_新用户首次登录送3次(self, env):
        client, settings = env
        d = login(client, "code-brand-new")
        assert d["quota"]["balance"] == 3, f"新用户应送 3 次，实际 {d['quota']['balance']}"
        assert d["is_new_user"] is True
        assert d["token"], "缺少 token"
        assert d["user_id"], "缺少 user_id"

    def test_响应字段齐全(self, env):
        client, settings = env
        d = login(client, "code-fields")
        for key in ("token", "user_id", "platform", "created_at", "is_new_user",
                    "quota", "membership", "platform_mode", "ad"):
            assert key in d, f"登录响应缺字段：{key}"
        assert isinstance(d["quota"]["balance"], int)
        assert set(d["membership"]) >= {"active", "plan", "expires_at", "daily_limit"}
        # 广告位配置：mode=mock 时前端不得发真实广告请求
        assert d["ad"]["mode"] in ("mock", "live")
        assert d["platform_mode"] in ("mock", "live")

    def test_重复登录不重复赠送(self, env):
        client, settings = env
        login(client, "code-same-user")
        d2 = login(client, "code-same-user")
        assert d2["quota"]["balance"] == 3, f"重复登录又送额度：{d2['quota']['balance']}"
        assert d2["is_new_user"] is False

    def test_参数非法返回VALIDATION_ERROR(self, env):
        client, settings = env
        r = client.post("/auth/login", json={"platform": "bogus", "code": "x"})
        assert r.status_code == 400
        assert error_code(r) == "VALIDATION_ERROR"

    def test_me未登录返回401(self, env):
        client, settings = env
        r = client.get("/me")
        assert r.status_code == 401
        assert error_code(r) == "UNAUTHORIZED"

    def test_me响应无token字段(self, env):
        client, settings = env
        d = login(client, "code-me")
        r = client.get("/me", headers=auth(d["token"]))
        body = r.json()["data"]
        assert "token" not in body, "/me 不应回传 token"
        assert body["user_id"] == d["user_id"]


# ================================================================ 二、异步分析状态机（D5）

class Test分析创建契约:
    def test_创建立即返回pending并已预扣(self, env):
        """契约 D8（Chief 2026-10-31 定）：创建响应 status 允许 pending 或 running，
        但**不得是 done/failed、不得带报告**。

        异步改造后后台线程可能已经开跑，写死 pending 就会 flaky。
        **不用 sleep 等 pending**——那是把不确定性藏起来，不是消除它。
        """
        client, settings = env
        uid, d = new_user(client)
        before = d["quota"]["balance"]

        r = create_analysis(client, d["token"])
        assert r.status_code == 200, r.text
        data = r.json()["data"]

        assert data["status"] in ("pending", "running"), (
            f"创建响应 status 只能是 pending/running，实际 {data['status']}"
        )
        assert data["status"] not in ("done", "failed"), "创建接口不该直接返回终态"
        if not data.get("dedupe_hit"):
            assert data.get("report") is None, "非去重场景创建接口不得携带报告"
        assert data["task_id"], "缺少 task_id"
        assert isinstance(data.get("poll_after_ms"), int), "应下发 poll_after_ms"
        assert data["quota"]["balance"] == before - 1, "创建时未预扣"

    def test_创建不等结果(self, env):
        """契约明令：本接口不等分析结果。响应里不应直接带 report（去重除外）。"""
        client, settings = env
        uid, d = new_user(client)
        data = create_analysis(client, d["token"]).json()["data"]
        assert data.get("report") is None or data.get("dedupe_hit"), (
            "非去重场景下创建接口直接返回了报告，违反「立即返回 task_id」语义"
        )

    def test_次数不足返回402且不扣(self, env):
        client, settings = env
        uid, d = new_user(client)
        # 用光 3 次
        for _ in range(3):
            assert create_analysis(client, d["token"]).status_code == 200
        bal = balance_of(client, d["token"])
        assert bal == 0

        r = create_analysis(client, d["token"])
        assert r.status_code == 402, f"次数不足应 402，实际 {r.status_code}"
        assert error_code(r) == "QUOTA_EXHAUSTED"
        assert balance_of(client, d["token"]) == 0, "402 时不应扣次数"

    def test_参数非法不建任务不扣(self, env):
        client, settings = env
        uid, d = new_user(client)
        before = balance_of(client, d["token"])
        r = client.post("/analysis", data={"ocr_text": ""}, headers=auth(d["token"]))
        assert r.status_code == 400
        assert error_code(r) == "VALIDATION_ERROR"
        assert balance_of(client, d["token"]) == before, "参数非法却扣了次数"

    def test_超过3张图片被拒(self, env):
        client, settings = env
        uid, d = new_user(client)
        png = b"\x89PNG\r\n\x1a\n" + b"0" * 64
        files = [("files", (f"{i}.png", png, "image/png")) for i in range(4)]
        r = client.post("/analysis", files=files, headers=auth(d["token"]))
        assert r.status_code == 400
        assert error_code(r) == "VALIDATION_ERROR"


class Test分析轮询契约:
    def test_成功路径done且报告合法(self, env):
        client, settings = env
        uid, d = new_user(client)
        task_id = create_analysis(client, d["token"]).json()["data"]["task_id"]

        final = poll_until_terminal(client, d["token"], task_id)
        assert final["status"] == "done", f"应成功，实际 {final}"
        assert final["error_code"] is None
        assert final["report"] is not None, "done 时必须带报告"
        assert final["poll_after_ms"] is None, "终态应停止轮询（poll_after_ms=null）"

        # 报告结构（v2，见 docs/09 §二）
        rep = final["report"]
        for key in ("is_job_posting", "overall", "summary", "dimensions", "findings",
                    "questions_to_ask", "how_to_verify", "rules_version", "pattern_db_version"):
            assert key in rep, f"报告 v2 缺字段：{key}"
        assert len(rep["dimensions"]) == 6, f"维度应为 6 项，实际 {len(rep['dimensions'])}"
        # 路线令：版本号随规则迭代上升，只校验格式，不写死具体版本
        import re as _re

        assert _re.match(r"^v\d+\.\d+$", str(rep["rules_version"])), (
            f"rules_version 格式应为 vX.Y，实际 {rep['rules_version']!r}"
        )

    def test_成功路径余额保持预扣后的值(self, env):
        """成功：analysis_mark delta=0，余额不应回补。"""
        client, settings = env
        uid, d = new_user(client)
        after_create = create_analysis(client, d["token"]).json()["data"]
        task_id = after_create["task_id"]
        assert after_create["quota"]["balance"] == 2

        poll_until_terminal(client, d["token"], task_id)
        # 注意：去重只会让余额「不被扣」，不会回补；这里换一处独立用户确认
        assert balance_of(client, d["token"]) == 2, "成功后余额被回补了，等于白嫖一次分析"

    def test_越权看他人任务返回404(self, env):
        client, settings = env
        uid_a, a = new_user(client)
        uid_b, b = new_user(client)
        task_a = create_analysis(client, a["token"]).json()["data"]["task_id"]

        r = client.get(f"/analysis/{task_a}", headers=auth(b["token"]))
        assert r.status_code == 404, f"越权应 404，实际 {r.status_code}"
        assert error_code(r) == "NOT_FOUND"

    def test_不存在任务返回404(self, env):
        client, settings = env
        uid, d = new_user(client)
        r = client.get("/analysis/t_does_not_exist", headers=auth(d["token"]))
        assert r.status_code == 404
        assert error_code(r) == "NOT_FOUND"

    def test_轮询响应字段齐全(self, env):
        client, settings = env
        uid, d = new_user(client)
        task_id = create_analysis(client, d["token"]).json()["data"]["task_id"]
        data = client.get(f"/analysis/{task_id}", headers=auth(d["token"])).json()["data"]
        for key in ("task_id", "status", "report", "error_code", "error_message",
                    "duration_ms", "model", "rules_version", "elapsed_ms",
                    "poll_after_ms", "background_mode", "quota"):
            assert key in data, f"轮询响应缺字段：{key}"
        assert data["status"] in ("pending", "running", "done", "failed")


class Test失败必退次数:
    def test_OCR不可用时失败并退次数(self, env):
        """契约 §3.1 规则 4：任何分析期失败都必须 analysis_refund +1，
        status=failed，report=null。

        真实可达的失败路径（原型期）：只传图片、不传 ocr_text ——
        worker 读不到 uploads/<task_id>/ocr.txt，OCR 不可用 → failed。
        这是前端在没接真 OCR 时最可能踩到的路径，必须退次数。
        """
        client, settings = env
        uid, d = new_user(client)
        before = balance_of(client, d["token"])

        png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 128
        r = client.post(
            "/analysis",
            files=[("files", ("a.png", png, "image/png"))],
            headers=auth(d["token"]),
        )
        assert r.status_code == 200, f"只传图片应被接受（创建期不校验 OCR）：{r.text}"
        task_id = r.json()["data"]["task_id"]

        # 契约 §3.1 规则 1：创建即预扣。接口返回体里带的是预扣后的余额。
        created = r.json()["data"]
        assert created["quota"]["balance"] == before - 1, (
            f"创建响应里的余额应为预扣后 {before - 1}，实际 {created['quota']['balance']}"
        )

        final = poll_until_terminal(client, d["token"], task_id)
        assert final["status"] == "failed", (
            f"没有 OCR 文本时任务应失败，实际 {final['status']}"
        )
        assert final["report"] is None, "失败时不得返回报告"
        assert final["error_code"] in (
            "CONTENT_BLOCKED", "ANALYSIS_UNAVAILABLE", "ANALYSIS_FAILED",
        ), f"失败错误码不在契约枚举内：{final['error_code']}"

        assert balance_of(client, d["token"]) == before, (
            f"失败未退次数：{before} → {balance_of(client, d['token'])}"
        )


# ================================================================ 三、幂等（§1.5）

class Test幂等契约:
    def test_IdempotencyKey重放不重复扣(self, env):
        client, settings = env
        uid, d = new_user(client)
        key = "idem-" + uuid.uuid4().hex[:12]

        r1 = create_analysis(client, d["token"], idem=key)
        r2 = create_analysis(client, d["token"], idem=key)
        assert r1.status_code == 200 and r2.status_code == 200

        d1, d2 = r1.json()["data"], r2.json()["data"]
        assert d1["task_id"] == d2["task_id"], "同一 Idempotency-Key 建了两个任务"
        assert balance_of(client, d["token"]) == 2, "重放多扣了次数"
        assert d2.get("idempotent_replay") is True, "重放未标记 idempotent_replay"

    def test_不同用户同一key互不影响(self, env):
        client, settings = env
        uid_a, a = new_user(client)
        uid_b, b = new_user(client)
        key = "shared-key-001"
        ra = create_analysis(client, a["token"], idem=key).json()["data"]
        rb = create_analysis(client, b["token"], idem=key).json()["data"]
        assert ra["task_id"] != rb["task_id"], "不同用户复用了同一个任务"
        assert balance_of(client, b["token"]) == 2, "B 的额度异常"

    def test_24小时同图去重不扣次数(self, env):
        """同用户同组图 24h 内第二次提交，直接拿旧报告且不扣次数（契约 §1.5）。

        注意：去重只认 status=done 的任务，所以第一次必须真的跑成功。
        原型期 OCR 是旁路（worker 读 uploads/<task_id>/ocr.txt），
        只传图片不传 ocr_text 会因 OCR 不可用而 failed，永远等不到 done——
        因此这里同时带 ocr_text，与前端原型期用法一致。
        """
        client, settings = env
        uid, d = new_user(client)
        png = b"\x89PNG\r\n\x1a\n" + b"dedupe-test-image-bytes"
        files = [("files", ("same.png", png, "image/png"))]

        r1 = client.post("/analysis", data={"ocr_text": OCR_OK}, files=files, headers=auth(d["token"]))
        assert r1.status_code == 200, r1.text
        first = poll_until_terminal(client, d["token"], r1.json()["data"]["task_id"])
        assert first["status"] == "done", f"第一次任务没成功，无法验证去重：{first.get('error_code')}"
        bal_after_first = balance_of(client, d["token"])

        files2 = [("files", ("same.png", png, "image/png"))]
        r2 = client.post("/analysis", data={"ocr_text": OCR_OK}, files=files2, headers=auth(d["token"]))
        assert r2.status_code == 200, r2.text
        d2 = r2.json()["data"]
        assert d2.get("dedupe_hit") is True, (
            f"同图 24h 内未命中去重；返回={json.dumps(d2, ensure_ascii=False)[:300]}"
        )
        assert balance_of(client, d["token"]) == bal_after_first, "去重命中却扣了次数"


# ================================================================ 四、广告奖励（§6.2）

class Test广告奖励契约:
    def test_看完广告加1次(self, env):
        client, settings = env
        uid, d = new_user(client)
        before = balance_of(client, d["token"])
        r = client.post("/ad/reward", json={
            "request_id": "req-" + uuid.uuid4().hex[:12], "ad_unit_id": "u1", "result": "completed",
        }, headers=auth(d["token"]))
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert data["granted"] is True
        assert balance_of(client, d["token"]) == before + 1

    @pytest.mark.parametrize("result", ["no_fill", "error"])
    def test_无填充和失败也必须兜底发次数(self, result, env):
        """§6.2 平台硬性要求：广告拉不出来也得给次数，否则算违规。"""
        client, settings = env
        uid, d = new_user(client)
        before = balance_of(client, d["token"])
        r = client.post("/ad/reward", json={
            "request_id": "req-" + uuid.uuid4().hex[:12], "ad_unit_id": "u1", "result": result,
        }, headers=auth(d["token"]))
        assert r.status_code == 200, r.text
        assert r.json()["data"]["granted"] is True, f"result={result} 未兜底发放"
        assert balance_of(client, d["token"]) == before + 1, f"result={result} 未加次数"

    def test_同一request_id只发一次(self, env):
        client, settings = env
        uid, d = new_user(client)
        before = balance_of(client, d["token"])
        payload = {"request_id": "req-fixed-001", "ad_unit_id": "u1", "result": "completed"}
        for _ in range(4):
            r = client.post("/ad/reward", json=payload, headers=auth(d["token"]))
            assert r.status_code == 200
        assert balance_of(client, d["token"]) == before + 1, "同一 request_id 重复发放"

    def test_每日上限5次(self, env):
        client, settings = env
        uid, d = new_user(client)
        before = balance_of(client, d["token"])
        for i in range(8):
            client.post("/ad/reward", json={
                "request_id": f"req-cap-{i:04d}", "ad_unit_id": "u1", "result": "completed",
            }, headers=auth(d["token"]))
        after = balance_of(client, d["token"])
        assert after - before == 5, f"每日上限 5 次，实际发放 {after - before} 次"

    def test_响应字段齐全(self, env):
        client, settings = env
        uid, d = new_user(client)
        data = client.post("/ad/reward", json={
            "request_id": "req-fields-01", "ad_unit_id": "u1", "result": "completed",
        }, headers=auth(d["token"])).json()["data"]
        for key in ("granted", "replayed", "reason", "quota", "today_count", "daily_cap", "remaining_today"):
            assert key in data, f"广告奖励响应缺字段：{key}"
        assert data["daily_cap"] == 5


# ================================================================ 五、订单与支付回调

class Test支付契约:
    def _order(self, client, token, plan="month"):
        r = client.post("/orders", json={"plan": plan, "channel": "toutiao"}, headers=auth(token))
        assert r.status_code == 200, r.text
        return r.json()["data"]

    def _sign(self, order_id, platform_order_id, amount_fen, status="paid"):
        from backend.app.security import sign_pay_payload
        from backend.app.config import get_settings

        fields = {
            "order_id": order_id,
            "platform_order_id": platform_order_id,
            "amount_fen": str(amount_fen),
            "status": status,
        }
        return sign_pay_payload(fields, get_settings().pay_secret)

    def test_价格服务端定价(self, env):
        client, settings = env
        uid, d = new_user(client)
        prices = {"week": 690, "month": 1990, "quarter": 3990}
        for plan, fen in prices.items():
            o = self._order(client, d["token"], plan)
            assert o["amount_fen"] == fen, f"{plan} 价格应为 {fen}，实际 {o['amount_fen']}"
            assert o["status"] == "pending"

    def test_支付参数是占位不可真扣款(self, env):
        client, settings = env
        uid, d = new_user(client)
        o = self._order(client, d["token"])
        assert o["pay_params"].get("mock") is True, "原型期 pay_params 必须标 mock:true"

    def test_伪造签名返回401(self, env):
        client, settings = env
        uid, d = new_user(client)
        o = self._order(client, d["token"])
        r = client.post("/pay/notify", json={
            "order_id": o["order_id"], "platform_order_id": "p-1",
            "amount_fen": o["amount_fen"], "status": "paid", "signature": "forged-signature",
        })
        assert r.status_code == 401, f"伪造签名应 401，实际 {r.status_code}"
        assert error_code(r) == "SIGNATURE_INVALID"

    def test_金额不符返回400(self, env):
        client, settings = env
        uid, d = new_user(client)
        o = self._order(client, d["token"])
        sig = self._sign(o["order_id"], "p-2", 1)
        r = client.post("/pay/notify", json={
            "order_id": o["order_id"], "platform_order_id": "p-2",
            "amount_fen": 1, "status": "paid", "signature": sig,
        })
        assert r.status_code == 400, f"金额不符应 400，实际 {r.status_code}"
        assert error_code(r) == "AMOUNT_MISMATCH"

    def test_订单不存在返回404(self, env):
        client, settings = env
        sig = self._sign("o_nope", "p-3", 1990)
        r = client.post("/pay/notify", json={
            "order_id": "o_nope", "platform_order_id": "p-3",
            "amount_fen": 1990, "status": "paid", "signature": sig,
        })
        assert r.status_code == 404
        assert error_code(r) == "ORDER_NOT_FOUND"

    def test_重复推送幂等不重复加会员(self, env):
        client, settings = env
        uid, d = new_user(client)
        o = self._order(client, d["token"], "week")
        sig = self._sign(o["order_id"], "p-4", 690)
        payload = {
            "order_id": o["order_id"], "platform_order_id": "p-4",
            "amount_fen": 690, "status": "paid", "signature": sig,
        }
        r1 = client.post("/pay/notify", json=payload)
        assert r1.status_code == 200, r1.text
        exp1 = r1.json()["data"]["membership"]["expires_at"]

        r2 = client.post("/pay/notify", json=payload)
        assert r2.status_code == 200, r2.text
        data2 = r2.json()["data"]
        assert data2.get("replayed") is True, "重复推送未标记 replayed"
        if "membership" in data2:
            assert data2["membership"]["expires_at"] == exp1, "重复推送又延长了会员"

    def test_会员开通后每日上限20(self, env):
        client, settings = env
        uid, d = new_user(client)
        o = self._order(client, d["token"], "month")
        sig = self._sign(o["order_id"], "p-5", 1990)
        client.post("/pay/notify", json={
            "order_id": o["order_id"], "platform_order_id": "p-5",
            "amount_fen": 1990, "status": "paid", "signature": sig,
        })
        me = client.get("/me", headers=auth(d["token"])).json()["data"]
        assert me["membership"]["active"] is True, "支付成功但会员未激活"
        assert me["membership"]["daily_limit"] == 20, (
            f"会员每日上限应为 20，实际 {me['membership']['daily_limit']}"
        )


# ================================================================ 六、历史报告与反馈

class Test报告与反馈契约:
    def test_历史报告分页且只含自己(self, env):
        client, settings = env
        uid, d = new_user(client)
        task_id = create_analysis(client, d["token"]).json()["data"]["task_id"]
        poll_until_terminal(client, d["token"], task_id)

        r = client.get("/reports", headers=auth(d["token"]))
        assert r.status_code == 200, r.text
        body = r.json()["data"]
        assert "items" in body and "next_cursor" in body
        assert len(body["items"]) >= 1, "刚生成报告却没出现在历史里"
        item = body["items"][0]
        # v2：risk_level/verdict/risk_count → overall/finding_count
        for key in ("report_id", "task_id", "overall", "summary", "finding_count", "created_at", "expires_at"):
            assert key in item, f"历史报告项缺字段：{key}"
        assert item["overall"] in {"red", "amber", "green", "unknown"}, f"overall 非法：{item['overall']}"

    def test_limit超上限被拒或截断(self, env):
        client, settings = env
        uid, d = new_user(client)
        r = client.get("/reports?limit=999", headers=auth(d["token"]))
        assert r.status_code in (200, 400), f"limit 越界应截断或拒绝，实际 {r.status_code}"

    def test_反馈提交成功(self, env):
        client, settings = env
        uid, d = new_user(client)
        r = client.post("/feedback", json={
            "type": "inaccurate", "content": "这个报告判断偏高，实际是正常岗位",
        }, headers=auth(d["token"]))
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        for key in ("feedback_id", "type", "status", "expect_reply_within_days", "created_at"):
            assert key in data, f"反馈响应缺字段：{key}"
        assert data["expect_reply_within_days"] == 7, "目标答复期应为 7 个工作日"


# ================================================================ 七、后台与对账

class Test后台契约:
    ADMIN = {"X-Admin-Token": "test-admin-token"}

    def test_非管理员访问后台返回403(self, env):
        client, settings = env
        r = client.get("/admin/stats", headers={"X-Admin-Token": "wrong"})
        assert r.status_code == 403, f"错误的 admin token 应 403，实际 {r.status_code}"
        assert error_code(r) == "FORBIDDEN"

    def test_对账balanced为true(self, env):
        client, settings = env
        uid, d = new_user(client)
        create_analysis(client, d["token"])
        client.post("/ad/reward", json={
            "request_id": "req-recon-001", "ad_unit_id": "u1", "result": "no_fill",
        }, headers=auth(d["token"]))

        r = client.get("/admin/stats", headers=self.ADMIN)
        assert r.status_code == 200, r.text
        recon = r.json()["data"]["quota_reconcile"]
        assert recon["balanced"] is True, f"对账不平衡：{recon}"
        assert recon.get("negative_balance_users") == []
        assert recon.get("orphan_holds") == []

    def test_看板字段齐全(self, env):
        client, settings = env
        data = client.get("/admin/stats", headers=self.ADMIN).json()["data"]
        for key in ("counts", "reports_by_level", "orders", "ad_rewards_today", "quota_reconcile"):
            assert key in data, f"看板缺字段：{key}"
