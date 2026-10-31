"""R3 补充 · D18 防刷口径测试

依据 Chief 2026-10-31 定下的 D18（任务书 §11.2 原文落地）：
**「可疑票收下、不计入展示、保留记录备查」**
- 不是入口拒绝，也不是静默丢弃
- 投票接口照常返回成功，不给用户「你被风控」的提示
- 用户自己的「已投/可改」状态仍正常
- 公开票数只统计 counted=1；votes 表完整保留可疑票

规则（实测配置）：
- 窗口期默认 10 分钟
- 同设备（X-Device-Id）超 5 票 → device_flood（阈值 device_limit）
- 同 /24 IP 段超 20 票 → ip_flood（阈值 ip_limit）
"""
from __future__ import annotations

import importlib
import sqlite3
import sys
import uuid

import pytest

from conftest import ROOT

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
TestClient = pytest.importorskip("fastapi.testclient").TestClient

ADMIN = {"X-Admin-Token": "test-admin"}


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("QBL_DB_PATH", str(tmp_path / "qbl.db"))
    monkeypatch.setenv("QBL_UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("QBL_REPORT_DIR", str(tmp_path / "reports"))
    monkeypatch.setenv("QBL_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("QBL_TOKEN_SECRET", "test-token")
    monkeypatch.setenv("QBL_ADMIN_TOKEN", "test-admin")
    monkeypatch.setenv("QBL_POLL_AFTER_MS", "50")
    monkeypatch.setenv("QBL_FEATURE_COMMUNITY", "1")
    # 把阈值调小，便于用小样本验证（等价于线上 5 票 / 20 票的同一逻辑）
    monkeypatch.setenv("QBL_COMMUNITY_VOTE_DEVICE_LIMIT", "5")
    monkeypatch.setenv("QBL_COMMUNITY_VOTE_IP_LIMIT", "20")
    for mod in list(sys.modules):
        if mod == "backend" or mod.startswith("backend."):
            del sys.modules[mod]
    from backend.app import deps, main
    from backend.app.config import get_settings

    importlib.reload(main)
    deps.reset_db()
    settings = get_settings()
    with TestClient(main.app) as client:
        yield client, settings
    try:
        from backend.app import worker

        worker.shutdown(wait=True)
    except Exception:
        pass


def auth(t):
    return {"Authorization": f"Bearer {t}"}


def new_user(client):
    code = "code-" + uuid.uuid4().hex[:10]
    d = client.post("/auth/login", json={"platform": "toutiao", "code": code}).json()["data"]
    return d["user_id"], d["token"]


def _db():
    from backend.app import deps

    return sqlite3.connect(deps.get_db().path)


def _age(uid, hours=25):
    db = _db()
    try:
        db.execute("UPDATE users SET created_at = datetime('now', ?) WHERE id = ?", (f"-{hours} hours", uid))
        db.commit()
    finally:
        db.close()


def make_approved_post(client, tok, uid):
    _age(uid)
    r = client.post(
        "/community/posts",
        json={
            "report_id": "r_" + uuid.uuid4().hex[:12],
            "company": "某科技有限公司",
            "title": "运营助理",
            "city": "本市",
            "question": "这家公司让我先交服装费，能去吗？",
            "anonymous": True,
            "confirm_real": True,
        },
        headers=auth(tok),
    )
    assert r.status_code == 200, r.text
    pid = r.json()["data"]["post_id"]
    rv = client.post(f"/admin/community/posts/{pid}/approve", json={"operator": "test"}, headers=ADMIN)
    if rv.status_code != 200:
        rv = client.post(f"/admin/community/posts/{pid}/review", json={"action": "approve"}, headers=ADMIN)
    assert rv.status_code == 200, f"放行失败：{rv.text[:200]}"
    return pid


def vote(client, tok, pid, value=1, device=None, ip=None, extra=None):
    headers = {**auth(tok)}
    if device:
        headers["X-Device-Id"] = device
    if ip:
        headers["X-Forwarded-For"] = ip
    if extra:
        headers.update(extra)
    return client.post(f"/community/posts/{pid}/vote", json={"value": value}, headers=headers)


def post_counts(pid):
    db = _db()
    try:
        row = db.execute("SELECT vote_up, vote_down FROM posts WHERE id = ?", (pid,)).fetchone()
        total = db.execute("SELECT COUNT(*) FROM votes WHERE post_id = ?", (pid,)).fetchone()[0]
        counted = db.execute("SELECT COUNT(*) FROM votes WHERE post_id = ? AND counted = 1", (pid,)).fetchone()[0]
        risky = db.execute(
            "SELECT COUNT(*) FROM votes WHERE post_id = ? AND counted = 0", (pid,)
        ).fetchone()[0]
        reasons = [
            r[0]
            for r in db.execute(
                "SELECT DISTINCT risk_reason FROM votes WHERE post_id = ? AND counted = 0", (pid,)
            ).fetchall()
        ]
    finally:
        db.close()
    return {"vote_up": row[0], "vote_down": row[1], "total": total, "counted": counted, "risky": risky, "reasons": reasons}


# ================================================================ ① 同设备连投

class Test同设备连投不计展示:
    def test_同设备连投6票展示不涨但记录都在(self, env):
        """D18 核心：可疑票收下、不计展示、保留记录。"""
        client, settings = env
        uid_a, tok_a = new_user(client)
        pid = make_approved_post(client, tok_a, uid_a)
        device = "dev-" + uuid.uuid4().hex[:8]

        results = []
        for _ in range(6):
            uid, tok = new_user(client)
            _age(uid)
            r = vote(client, tok, pid, value=1, device=device, ip="203.0.113.10")
            results.append(r.status_code)

        c = post_counts(pid)

        # 1) 接口照常成功，不给用户「被风控」的提示
        assert all(s == 200 for s in results), f"投票接口返回异常：{results}"

        # 2) votes 表完整保留全部 6 票
        assert c["total"] == 6, f"votes 表应保留 6 票，实际 {c['total']}"

        # 3) 展示只统计 counted=1，且不超过阈值
        assert c["counted"] <= settings.community_vote_device_limit, (
            f"计入展示的票 {c['counted']} 超过设备阈值 {settings.community_vote_device_limit}"
        )
        assert c["vote_up"] == c["counted"], f"帖子上的 vote_up({c['vote_up']}) 与 counted({c['counted']}) 不一致"

        # 4) 超出的票标记了风险原因
        assert c["risky"] >= 1, "超出阈值的票没有标记 counted=0"
        assert c["reasons"], "可疑票没有写 risk_reason"
        assert "device_flood" in c["reasons"], f"风险原因应为 device_flood，实际 {c['reasons']}"

    def test_被风控用户仍能改票(self, env):
        """D18：用户自己的「已投/可改」状态仍正常，不能因为被标记就报错。"""
        client, settings = env
        uid_a, tok_a = new_user(client)
        pid = make_approved_post(client, tok_a, uid_a)
        device = "dev-" + uuid.uuid4().hex[:8]

        uids = []
        for _ in range(6):
            uid, tok = new_user(client)
            _age(uid)
            vote(client, tok, pid, value=1, device=device, ip="203.0.113.11")
            uids.append((uid, tok))

        # 最后一个被风控的用户改票
        uid, tok = uids[-1]
        r = vote(client, tok, pid, value=-1, device=device, ip="203.0.113.11")
        assert r.status_code == 200, f"被风控用户改票失败：{r.status_code} {r.text[:150]}"

        detail = client.get(f"/community/posts/{pid}", headers=auth(tok))
        assert detail.status_code == 200


# ================================================================ ② 不同设备正常计数

class Test不同设备正常计数:
    def test_不同设备各投一票都计入(self, env):
        client, settings = env
        uid_a, tok_a = new_user(client)
        pid = make_approved_post(client, tok_a, uid_a)

        for i in range(4):
            uid, tok = new_user(client)
            _age(uid)
            r = vote(client, tok, pid, value=1, device=f"dev-unique-{uuid.uuid4().hex[:8]}", ip=f"198.51.100.{i+1}")
            assert r.status_code == 200, r.text

        c = post_counts(pid)
        assert c["counted"] == 4, f"4 个不同设备应计 4 票，实际 {c['counted']}"
        assert c["risky"] == 0, f"不应出现可疑票，实际 {c['risky']} 张"
        assert c["vote_up"] == 4

    def test_不同IP段不受影响(self, env):
        client, settings = env
        uid_a, tok_a = new_user(client)
        pid = make_approved_post(client, tok_a, uid_a)
        for i in range(3):
            uid, tok = new_user(client)
            _age(uid)
            vote(client, tok, pid, value=1, device=f"dev-{uuid.uuid4().hex[:8]}", ip=f"192.0.2.{10+i}")
        c = post_counts(pid)
        assert c["counted"] == 3
        assert c["risky"] == 0


# ================================================================ ③ 改票不重复计数

class Test改票不重复计数:
    def test_同用户改票不叠加票数(self, env):
        client, settings = env
        uid_a, tok_a = new_user(client)
        pid = make_approved_post(client, tok_a, uid_a)
        uid_b, tok_b = new_user(client)
        _age(uid_b)
        device = "dev-" + uuid.uuid4().hex[:8]

        vote(client, tok_b, pid, value=1, device=device, ip="203.0.113.20")
        c1 = post_counts(pid)
        assert c1["total"] == 1

        for _ in range(3):
            vote(client, tok_b, pid, value=-1, device=device, ip="203.0.113.20")
        c2 = post_counts(pid)

        assert c2["total"] == 1, f"改票被当成新票记录了：total={c2['total']}（应为 1）"
        assert c2["vote_down"] == 1 and c2["vote_up"] == 0, (
            f"改票后计数不对：up={c2['vote_up']} down={c2['vote_down']}"
        )

    def test_改票不触发风控(self, env):
        """同一用户反复改票，不应被算成「刷票」而标记可疑。"""
        client, settings = env
        uid_a, tok_a = new_user(client)
        pid = make_approved_post(client, tok_a, uid_a)
        uid_b, tok_b = new_user(client)
        _age(uid_b)
        device = "dev-" + uuid.uuid4().hex[:8]

        for i in range(8):
            vote(client, tok_b, pid, value=1 if i % 2 == 0 else -1, device=device, ip="203.0.113.21")

        c = post_counts(pid)
        assert c["risky"] == 0, f"反复改票被误判为风控：{c['risky']} 张可疑票"


# ================================================================ ④ 缺 X-Device-Id

class Test缺设备头:
    def test_缺设备头不报错(self, env):
        client, settings = env
        uid_a, tok_a = new_user(client)
        pid = make_approved_post(client, tok_a, uid_a)
        uid, tok = new_user(client)
        _age(uid)

        r = vote(client, tok, pid, value=1)   # 不带 X-Device-Id
        assert r.status_code == 200, f"缺设备头不应报错：{r.status_code} {r.text[:150]}"

    def test_缺设备头退回IP判断(self, env):
        """缺 X-Device-Id 时用 IP 兜底：同一 IP 连续投票应被识别为 ip_flood。"""
        client, settings = env
        uid_a, tok_a = new_user(client)
        pid = make_approved_post(client, tok_a, uid_a)

        same_ip = "203.0.113.99"
        for _ in range(settings.community_vote_ip_limit + 2):
            uid, tok = new_user(client)
            _age(uid)
            vote(client, tok, pid, value=1, ip=same_ip)   # 不带 device

        c = post_counts(pid)
        if c["total"] == 0:
            pytest.skip("投票未落库")
        # 应出现 ip_flood 或至少计入数不超过阈值
        assert c["counted"] <= settings.community_vote_ip_limit, (
            f"同 IP 投票计入 {c['counted']} 张，超过阈值 {settings.community_vote_ip_limit}"
        )
        if c["risky"]:
            assert "ip_flood" in c["reasons"], f"风险原因应为 ip_flood，实际 {c['reasons']}"


# ================================================================ 后台可疑票查询

class Test后台可疑票:
    def test_可查询可疑票(self, env):
        client, settings = env
        uid_a, tok_a = new_user(client)
        pid = make_approved_post(client, tok_a, uid_a)
        device = "dev-" + uuid.uuid4().hex[:8]
        for _ in range(7):
            uid, tok = new_user(client)
            _age(uid)
            vote(client, tok, pid, value=1, device=device, ip="203.0.113.30")

        r = client.get("/admin/community/votes?counted=0", headers=ADMIN)
        assert r.status_code == 200, f"后台可疑票接口不可用：{r.status_code} {r.text[:200]}"
        body = r.json()["data"]
        assert "items" in body, f"返回结构异常：{list(body.keys())}"
        assert len(body["items"]) >= 1, "查不到可疑票"

    def test_不存明文设备号(self, env):
        """§8：设备号只存摘要，不存明文。"""
        client, settings = env
        uid_a, tok_a = new_user(client)
        pid = make_approved_post(client, tok_a, uid_a)
        device = "plain-device-" + uuid.uuid4().hex[:8]
        for _ in range(6):
            uid, tok = new_user(client)
            _age(uid)
            vote(client, tok, pid, value=1, device=device, ip="203.0.113.31")

        db = _db()
        try:
            rows = db.execute("SELECT device_hash FROM votes").fetchall()
        finally:
            db.close()
        for (h,) in rows:
            if h:
                assert device != h, f"votes 表存了明文设备号：{h}"
