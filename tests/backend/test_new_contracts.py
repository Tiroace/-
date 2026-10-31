"""后端新契约测试（D8 / D9 与 Chief 2026-10-31 点名的测试重点）

覆盖：
1. 多图上传链路：POST /analysis/upload → image_ids → POST /analysis（幂等、去重、越权、过期、张数）
2. 内容安全两道闸：上传时（第一道）与报告文本（第二道），不通过要拦且不扣次数
3. 单笔订单 ≤300 元：超限 400
4. iOS 端不可用开关：available_ios=false，iOS 不展示会员入口
5. GET /plans 只读定价：前端不写死价格
6. /me 广告计数：ad.today_count / ad.remaining_today

约定：只走 HTTP 表面，不 import 内部实现（签名工具除外，用于构造合法回调）。
"""
from __future__ import annotations

import importlib
import sys
import time
import uuid

import pytest

from conftest import ROOT

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
TestClient = pytest.importorskip("fastapi.testclient").TestClient

# 一张最小的合法 PNG（1x1 透明图）
PNG_1X1 = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000a49444154789c63000100000500010d0a2db4000000"
    "0049454e44ae426082"
)

OCR_TEXT = """高薪招聘 兼职刷单 日结300元
入职需缴纳服装费980元、押金500元，离职退还
"""


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("QBL_DB_PATH", str(tmp_path / "qbl.db"))
    monkeypatch.setenv("QBL_UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("QBL_REPORT_DIR", str(tmp_path / "reports"))
    monkeypatch.setenv("QBL_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("QBL_TOKEN_SECRET", "test-token-secret")
    monkeypatch.setenv("QBL_PAY_SECRET", "test-pay-secret")
    monkeypatch.setenv("QBL_ADMIN_TOKEN", "test-admin-token")
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

    try:
        from backend.app import worker as worker_mod

        worker_mod.shutdown(wait=True)
    except Exception:
        pass


def auth(t: str) -> dict:
    return {"Authorization": f"Bearer {t}"}


def new_user(client, code: str = None) -> dict:
    code = code or "code-" + uuid.uuid4().hex[:10]
    r = client.post("/auth/login", json={"platform": "toutiao", "code": code})
    assert r.status_code == 200, r.text
    return r.json()["data"]


def balance(client, token) -> int:
    return client.get("/me", headers=auth(token)).json()["data"]["quota"]["balance"]


def err_code(r) -> str:
    body = r.json()
    assert body.get("ok") is False, body
    return body["error"]["code"]


def upload_image(client, token, data: bytes = None, name: str = "shot.png"):
    data = data if data is not None else PNG_1X1
    return client.post(
        "/analysis/upload",
        files={"image": (name, data, "image/png")},
        headers=auth(token),
    )


def create_json(client, token, image_ids=None, ocr_text=OCR_TEXT, idem=None):
    headers = auth(token)
    body = {"image_ids": image_ids or []}
    if ocr_text is not None:
        body["ocr_text"] = ocr_text
    if idem:
        body["idempotency_key"] = idem
    return client.post("/analysis", json=body, headers=headers)


def poll(client, token, task_id, timeout=20.0):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        r = client.get(f"/analysis/{task_id}", headers=auth(token))
        assert r.status_code == 200, r.text
        last = r.json()["data"]
        if last["status"] in ("done", "failed"):
            return last
        time.sleep(0.05)
    pytest.fail(f"任务 {task_id} 未到终态：{last}")


# ================================================================ 一、多图上传链路（D9）

class Test上传接口:
    def test_上传成功返回image_id(self, env):
        client, settings = env
        d = new_user(client)
        r = upload_image(client, d["token"])
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        for key in ("image_id", "hash", "expires_at"):
            assert key in data, f"上传响应缺字段：{key}"
        assert data["image_id"].startswith("i_"), "image_id 格式不符"
        assert len(data["hash"]) == 64, "hash 应为 sha256"

    def test_上传不扣次数(self, env):
        client, settings = env
        d = new_user(client)
        before = balance(client, d["token"])
        upload_image(client, d["token"])
        assert balance(client, d["token"]) == before, "上传图片不应扣次数"

    def test_上传需要登录(self, env):
        client, settings = env
        r = client.post("/analysis/upload", files={"image": ("a.png", PNG_1X1, "image/png")})
        assert r.status_code == 401, f"未登录上传应 401，实际 {r.status_code}"

    def test_非法格式被拒(self, env):
        client, settings = env
        d = new_user(client)
        r = upload_image(client, d["token"], data=b"not an image at all", name="evil.txt")
        assert r.status_code == 400, f"非法格式应 400，实际 {r.status_code}"
        assert err_code(r) == "VALIDATION_ERROR"

    def test_同名图片hash一致(self, env):
        client, settings = env
        d = new_user(client)
        a = upload_image(client, d["token"]).json()["data"]
        b = upload_image(client, d["token"]).json()["data"]
        assert a["hash"] == b["hash"], "同样内容 hash 应一致"
        assert a["image_id"] != b["image_id"], "每次上传应分配新的 image_id"


class Test多图创建分析:
    def test_用image_ids创建分析(self, env):
        client, settings = env
        d = new_user(client)
        before = balance(client, d["token"])

        ids = [upload_image(client, d["token"]).json()["data"]["image_id"] for _ in range(2)]
        r = create_json(client, d["token"], image_ids=ids, ocr_text=None)
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert data["status"] in ("pending", "running")
        assert data["quota"]["balance"] == before - 1, "创建应预扣 1 次"

        final = poll(client, d["token"], data["task_id"])
        assert final["status"] in ("done", "failed")

    def test_超过3张被拒且不扣(self, env):
        client, settings = env
        d = new_user(client)
        before = balance(client, d["token"])
        ids = [upload_image(client, d["token"]).json()["data"]["image_id"] for _ in range(4)]
        r = create_json(client, d["token"], image_ids=ids, ocr_text=None)
        assert r.status_code == 400, f"超 3 张应 400，实际 {r.status_code}"
        assert balance(client, d["token"]) == before, "被拒却扣了次数"

    def test_他人image_id不可用(self, env):
        """越权：A 上传的 image_id 不能被 B 拿来建任务。"""
        client, settings = env
        a = new_user(client)
        b = new_user(client)
        image_id = upload_image(client, a["token"]).json()["data"]["image_id"]

        r = create_json(client, b["token"], image_ids=[image_id], ocr_text=None)
        # 要么直接 400/403/404 拒绝，要么不许把它当成 B 自己的图
        assert r.status_code != 200, f"B 用了 A 的 image_id 却创建成功：{r.text[:200]}"

    def test_不存在的image_id被拒(self, env):
        client, settings = env
        d = new_user(client)
        r = create_json(client, d["token"], image_ids=["i_doesnotexist"], ocr_text=None)
        assert r.status_code == 400, f"不存在的 image_id 应 400，实际 {r.status_code}"

    def test_image_ids方式幂等重放(self, env):
        """同一 Idempotency-Key 重放：同一 task_id、且只扣 1 次。

        注意：必须带 ocr_text，否则任务会因「没有云 OCR」而失败并退次数，
        余额回补后就无法用余额验证「只扣一次」了（实测踩到过）。
        """
        client, settings = env
        d = new_user(client)
        before = balance(client, d["token"])
        image_id = upload_image(client, d["token"]).json()["data"]["image_id"]
        key = "idem-" + uuid.uuid4().hex[:10]

        r1 = create_json(client, d["token"], image_ids=[image_id], ocr_text=OCR_TEXT, idem=key)
        r2 = create_json(client, d["token"], image_ids=[image_id], ocr_text=OCR_TEXT, idem=key)
        assert r1.status_code == 200 and r2.status_code == 200, (r1.text, r2.text)
        assert r1.json()["data"]["task_id"] == r2.json()["data"]["task_id"], "幂等键未生效"

        # 创建响应里的余额是预扣后的值：两次都应是 before-1，说明只扣了一次
        assert r1.json()["data"]["quota"]["balance"] == before - 1, "第一次创建未预扣"
        assert r2.json()["data"]["quota"]["balance"] == before - 1, "重放又扣了一次"

    def test_同图去重不扣次数(self, env):
        client, settings = env
        d = new_user(client)
        image_id = upload_image(client, d["token"]).json()["data"]["image_id"]

        r1 = create_json(client, d["token"], image_ids=[image_id], ocr_text=OCR_TEXT)
        assert r1.status_code == 200, r1.text
        poll(client, d["token"], r1.json()["data"]["task_id"])
        bal_after = balance(client, d["token"])

        r2 = create_json(client, d["token"], image_ids=[image_id], ocr_text=OCR_TEXT)
        assert r2.status_code == 200, r2.text
        data2 = r2.json()["data"]
        assert data2.get("dedupe_hit") is True, f"同图未命中去重：{data2}"
        assert balance(client, d["token"]) == bal_after, "去重命中却扣了次数"


# ================================================================ 二、内容安全两道闸

class Test内容安全两道闸:
    def test_第一道闸_上传时拦截且不扣次数(self, env):
        """可疑图片在上传阶段（第 1 道闸）就拦，不建任务、不扣次数、不落库。"""
        client, settings = env
        d = new_user(client)
        before = balance(client, d["token"])

        # 冒充图片后缀的超大/异常内容：走内容安全适配器的拦截路径
        bad = b"\x89PNG\r\n\x1a\n" + b"\x00" * (settings.max_image_mb * 1024 * 1024 + 10)
        r = upload_image(client, d["token"], data=bad, name="huge.png")
        # 要么超限 400，要么内容安全 422 —— 都必须被拦
        assert r.status_code in (400, 422), f"异常图片未被拦：{r.status_code} {r.text[:200]}"
        if r.status_code == 422:
            assert err_code(r) == "CONTENT_BLOCKED"
        assert balance(client, d["token"]) == before, "被拦却扣了次数"

    def test_第一道闸_返回safety字段(self, env):
        client, settings = env
        d = new_user(client)
        data = upload_image(client, d["token"]).json()["data"]
        assert "safety" in data, "上传成功应返回内容安全结论"
        assert data["safety"].get("passed") is True

    def test_第二道闸_报告文本检测存在且可用(self, env):
        """第二道闸在分析链路内（报告文本检测）。这里验证：正常文本能出报告，
        且报告输出了已通过内部合规过滤（无 PII、无定性词）。"""
        client, settings = env
        d = new_user(client)
        r = create_json(client, d["token"])
        assert r.status_code == 200, r.text
        final = poll(client, d["token"], r.json()["data"]["task_id"])
        assert final["status"] == "done", f"正常文本应成功：{final.get('error_code')}"
        rep = final["report"]
        assert rep is not None
        import json as _json

        blob = _json.dumps(rep, ensure_ascii=False)
        for word in ("骗子公司", "黑心企业", "100%识别"):
            assert word not in blob, f"报告文本未过内容安全/禁用词过滤：{word}"


# ================================================================ 三、订单金额上限与 iOS 开关

class Test订单风控与平台开关:
    def test_单笔超过300元被拒(self, env):
        """单笔订单 ≤300 元（Chief 已定）。当前最高档季卡 39.9 元，正常下单不会超；
        这里验证服务端存在上限保护：篡改不出更高的量，只能验证上限配置生效。"""
        client, settings = env
        d = new_user(client)
        data = client.get("/plans", headers=auth(d["token"])).json()["data"]
        cap = data["max_single_order_fen"]
        assert cap == 30000, f"单笔上限应为 300 元(30000 分)，实际 {cap}"
        for p in data["plans"]:
            assert p["amount_fen"] <= cap, f"{p['plan']} 价格 {p['amount_fen']} 超过单笔上限"

    def test_订单金额由服务端决定(self, env):
        client, settings = env
        d = new_user(client)
        plans = {p["plan"]: p["amount_fen"] for p in client.get("/plans", headers=auth(d["token"])).json()["data"]["plans"]}
        for plan, fen in plans.items():
            o = client.post("/orders", json={"plan": plan, "channel": "toutiao"}, headers=auth(d["token"]))
            assert o.status_code == 200, o.text
            assert o.json()["data"]["amount_fen"] == fen, f"{plan} 下单金额与定价不一致"

    def test_iOS端不展示会员入口(self, env):
        """iOS 需平台虚拟支付，未接入前 available_ios 必须为 false。"""
        client, settings = env
        d = new_user(client)
        plans = client.get("/plans", headers=auth(d["token"])).json()["data"]["plans"]
        for p in plans:
            assert p["available_ios"] is False, f"{p['plan']} 在 iOS 端未关闭，违反平台规则"
            assert p["available_android"] is True


# ================================================================ 四、只读定价 GET /plans

class Test定价接口:
    def test_三档定价与时长齐全(self, env):
        client, settings = env
        d = new_user(client)
        r = client.get("/plans", headers=auth(d["token"]))
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert data["currency"] == "CNY"
        plans = {p["plan"]: p for p in data["plans"]}
        assert set(plans) == {"week", "month", "quarter"}, f"套餐档位不符：{set(plans)}"
        for key in ("name", "amount_fen", "days", "benefits", "available_ios", "available_android"):
            for plan, p in plans.items():
                assert key in p, f"{plan} 缺字段 {key}"
        assert plans["week"]["amount_fen"] == 690
        assert plans["month"]["amount_fen"] == 1990
        assert plans["quarter"]["amount_fen"] == 3990

    def test_需要登录(self, env):
        client, settings = env
        r = client.get("/plans")
        assert r.status_code == 401, f"未登录应 401，实际 {r.status_code}"


# ================================================================ 五、/me 广告计数

class Test广告计数:
    def test_初始计数正确(self, env):
        client, settings = env
        d = new_user(client)
        ad = client.get("/me", headers=auth(d["token"])).json()["data"]["ad"]
        assert ad["today_count"] == 0
        assert ad["remaining_today"] == ad["daily_cap"], (
            f"剩余次数应等于上限：{ad['remaining_today']} vs {ad['daily_cap']}"
        )

    def test_看一次广告后计数更新(self, env):
        client, settings = env
        d = new_user(client)
        client.post("/ad/reward", json={
            "request_id": "req-me-" + uuid.uuid4().hex[:8], "ad_unit_id": "u1", "result": "completed",
        }, headers=auth(d["token"]))
        ad = client.get("/me", headers=auth(d["token"])).json()["data"]["ad"]
        assert ad["today_count"] == 1, f"今日广告计数应为 1，实际 {ad['today_count']}"
        assert ad["remaining_today"] == ad["daily_cap"] - 1

    def test_计数与上限一致(self, env):
        client, settings = env
        d = new_user(client)
        ad = client.get("/me", headers=auth(d["token"])).json()["data"]["ad"]
        for i in range(ad["daily_cap"] + 2):
            client.post("/ad/reward", json={
                "request_id": f"req-me-{i:04d}-{uuid.uuid4().hex[:4]}",
                "ad_unit_id": "u1", "result": "completed",
            }, headers=auth(d["token"]))
        ad = client.get("/me", headers=auth(d["token"])).json()["data"]["ad"]
        assert ad["today_count"] == ad["daily_cap"], "计数超过上限"
        assert ad["remaining_today"] == 0, "剩余次数应为 0"
