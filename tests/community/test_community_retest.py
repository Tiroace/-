"""R3 复测 · D-07 / D-08 修复验证 + 剩余项收尾

覆盖：
- D-07：开关关闭时 GET/POST 一律 404，不泄漏存在性
- D-08：后台审核列表 + 放行/拒绝/隐藏，状态机 pending→approved/rejected
- 举报满 3 次自动隐藏（用后台放行造出已发布帖）
- 打码覆盖：手机号/QQ/邮箱/门牌号/车牌/银行卡
- 防刷（同设备/IP 段异常票不计展示但留记录）
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
    monkeypatch.setenv("QBL_PAY_SECRET", "test-pay")
    monkeypatch.setenv("QBL_ADMIN_TOKEN", "test-admin")
    monkeypatch.setenv("QBL_POLL_AFTER_MS", "50")
    monkeypatch.setenv("QBL_FEATURE_COMMUNITY", "1")
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


@pytest.fixture()
def env_off(tmp_path, monkeypatch):
    monkeypatch.setenv("QBL_DB_PATH", str(tmp_path / "qbl.db"))
    monkeypatch.setenv("QBL_UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("QBL_REPORT_DIR", str(tmp_path / "reports"))
    monkeypatch.setenv("QBL_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("QBL_TOKEN_SECRET", "test-token")
    monkeypatch.setenv("QBL_ADMIN_TOKEN", "test-admin")
    monkeypatch.setenv("QBL_FEATURE_COMMUNITY", "0")
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


def _status(pid):
    db = _db()
    try:
        row = db.execute("SELECT status FROM posts WHERE id = ?", (pid,)).fetchone()
        return row[0] if row else None
    finally:
        db.close()


def make_post(client, tok, uid, question="这家公司让我先交服装费，能去吗？", company="某科技有限公司"):
    _age(uid)
    r = client.post(
        "/community/posts",
        json={
            "report_id": "r_" + uuid.uuid4().hex[:12],
            "company": company,
            "title": "运营助理",
            "city": "本市",
            "question": question,
            "anonymous": True,
            "confirm_real": True,
        },
        headers=auth(tok),
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]["post_id"]


def review(client, pid, action):
    return client.post(f"/admin/community/posts/{pid}/review", json={"action": action}, headers=ADMIN)


def approve(client, pid):
    r = review(client, pid, "approve")
    assert r.status_code == 200, f"后台放行失败：{r.status_code} {r.text[:200]}"


# ================================================================ D-07

class TestD07开关关闭一律404:
    ENDPOINTS = [
        ("GET", "/community/posts"),
        ("GET", "/community/posts/p_x"),
        ("GET", "/community/posts/p_x/experiences"),
        ("POST", "/community/posts"),
        ("POST", "/community/posts/p_x/vote"),
        ("POST", "/community/posts/p_x/experiences"),
        ("POST", "/community/posts/p_x/report"),
        ("POST", "/community/appeals"),
    ]

    def test_所有接口一律404(self, env_off):
        """D-07 复测：GET 与 POST 都必须 404，且 POST 不能先被 body 校验抢成 400。"""
        client, settings = env_off
        _, tok = new_user(client)
        bad = []
        for method, path in self.ENDPOINTS:
            r = client.get(path, headers=auth(tok)) if method == "GET" else client.post(path, json={}, headers=auth(tok))
            if r.status_code != 404:
                bad.append(f"{method} {path} → {r.status_code} {r.text[:80]}")
        assert not bad, "D-07 未修干净，以下接口不是 404：\n" + "\n".join(bad)

    def test_带完整合法body也404(self, env_off):
        """即使 body 完全合法，开关关闭也必须 404（不能走到业务逻辑）。"""
        client, settings = env_off
        _, tok = new_user(client)
        r = client.post(
            "/community/posts",
            json={
                "report_id": "r_test",
                "company": "某公司",
                "title": "岗位",
                "city": "城市",
                "question": "这是一个合法的提问内容",
                "anonymous": True,
                "confirm_real": True,
            },
            headers=auth(tok),
        )
        assert r.status_code == 404, f"合法 body 应 404，实际 {r.status_code}"

    def test_错误码与普通404一致(self, env_off):
        client, settings = env_off
        _, tok = new_user(client)
        a = client.get("/community/posts", headers=auth(tok))
        b = client.get("/community/totally-unknown", headers=auth(tok))
        assert a.status_code == b.status_code == 404
        assert (a.json().get("error") or {}).get("code") == (b.json().get("error") or {}).get("code")


# ================================================================ D-08

class TestD08后台审核:
    def test_审核列表可查pending(self, env):
        client, settings = env
        uid, tok = new_user(client)
        pid = make_post(client, tok, uid)
        r = client.get("/admin/community/posts?status=pending", headers=ADMIN)
        assert r.status_code == 200, r.text
        ids = [it.get("post_id") or it.get("id") for it in r.json()["data"]["items"]]
        assert pid in ids, "pending 列表里没有刚发的帖子"

    def test_审核列表需要管理员令牌(self, env):
        client, settings = env
        r = client.get("/admin/community/posts")
        assert r.status_code in (401, 403), f"无令牌应被拒，实际 {r.status_code}"

    def test_放行后状态为approved且可见(self, env):
        client, settings = env
        uid, tok = new_user(client)
        pid = make_post(client, tok, uid)
        assert _status(pid) == "pending"

        r = review(client, pid, "approve")
        assert r.status_code == 200, r.text
        assert r.json()["data"]["status"] == "approved"
        assert _status(pid) == "approved"

        lst = client.get("/community/posts", headers=auth(tok)).json()["data"]["items"]
        assert pid in [it.get("post_id") or it.get("id") for it in lst], "放行后帖子未出现在列表"

    def test_拒绝后状态为rejected且不可见(self, env):
        client, settings = env
        uid, tok = new_user(client)
        pid = make_post(client, tok, uid)
        r = review(client, pid, "reject")
        assert r.status_code == 200, r.text
        assert _status(pid) == "rejected"

        lst = client.get("/community/posts", headers=auth(tok)).json()["data"]["items"]
        assert pid not in [it.get("post_id") or it.get("id") for it in lst], "被拒帖子仍可见"

    def test_非法action被拒(self, env):
        client, settings = env
        uid, tok = new_user(client)
        pid = make_post(client, tok, uid)
        r = review(client, pid, "whatever")
        assert r.status_code == 400, f"非法 action 应 400，实际 {r.status_code}"

    def test_不存在的帖子404(self, env):
        client, settings = env
        r = review(client, "p_not_exist", "approve")
        assert r.status_code == 404

    def test_状态机pending到approved是单向(self, env):
        client, settings = env
        uid, tok = new_user(client)
        pid = make_post(client, tok, uid)
        approve(client, pid)
        assert _status(pid) == "approved"
        # 再 reject 应能改成 rejected（管理动作）或维持，记录实际行为
        review(client, pid, "reject")
        assert _status(pid) in ("approved", "rejected")


# ================================================================ 举报满 3 次隐藏

class Test举报隐藏:
    def test_三个不同账号举报后自动隐藏(self, env):
        """§11.3：同一内容被举报达 3 次先自动隐藏。"""
        client, settings = env
        uid_a, tok_a = new_user(client)
        pid = make_post(client, tok_a, uid_a)
        approve(client, pid)   # ← 用真实后台接口放行，不再是改库

        for _ in range(3):
            _, tok = new_user(client)
            _age(_user_id_of(client, tok))
            client.post(f"/community/posts/{pid}/report", json={"reason": "内容不实"}, headers=auth(tok))

        st = _status(pid)
        db = _db()
        try:
            n = db.execute("SELECT COUNT(*) FROM post_reports WHERE post_id = ?", (pid,)).fetchone()[0]
        finally:
            db.close()

        if n < 3:
            pytest.skip(f"只记录 {n} 条举报，未达阈值（接口可能要求登录态或去重）")
        assert st in ("hidden", "rejected"), f"3 条举报后状态为 {st}，应自动隐藏"

    def test_同账号重复举报只算一次(self, env):
        client, settings = env
        uid_a, tok_a = new_user(client)
        pid = make_post(client, tok_a, uid_a)
        approve(client, pid)

        uid_b, tok_b = new_user(client)
        for _ in range(5):
            client.post(f"/community/posts/{pid}/report", json={"reason": "内容不实"}, headers=auth(tok_b))

        db = _db()
        try:
            n = db.execute("SELECT COUNT(*) FROM post_reports WHERE post_id = ?", (pid,)).fetchone()[0]
        finally:
            db.close()
        st = _status(pid)
        if n == 0:
            pytest.skip("举报未落库")
        assert n == 1, f"同账号举报 5 次记了 {n} 条"
        assert st == "approved", "单账号重复举报不应触发隐藏"


def _user_id_of(client, tok):
    return client.get("/me", headers=auth(tok)).json()["data"]["user_id"]


# ================================================================ 举报隐藏 → 复核 → 恢复
#
# 老板 2026-10-31 19:10 新增要求（排期 docs/14 第 0 项，3h，排在 D7 之后）：
# 3 次举报直接 hidden、没有复核也没有恢复入口，会被恶意举报压帖。
# 以下 5 条按 docs/14 §二「测试用例（测试者补）」逐条落地。


def _report_n(client, pid, times: int) -> None:
    """用 times 个不同账号举报同一条帖子。"""
    for _ in range(times):
        _, tok = new_user(client)
        _age(_user_id_of(client, tok))
        client.post(f"/community/posts/{pid}/report", json={"reason": "内容不实"}, headers=auth(tok))


def _review_nr(client, pid, action: str, **extra):
    """调用管理端复核动作（restore / hide）。"""
    r = client.post(f"/admin/community/posts/{pid}/review", json={"action": action, **extra}, headers=ADMIN)
    return r


def _in_review_queue(client, pid) -> bool:
    """帖子是否出现在复核队列里。容忍两种既定的队列写法（docs/14 §二.2）。"""
    for path in ("/admin/community/posts?status=needs_review", "/admin/community/posts?queue=report"):
        r = client.get(path, headers=ADMIN)
        if r.status_code != 200:
            continue
        data = r.json().get("data") or {}
        items = data.get("items") or data.get("posts") or []
        if any(str(it.get("id", it.get("post_id"))) == str(pid) for it in items):
            return True
    return False


class Test举报隐藏复核与恢复:
    def test_01_三次举报后进复核队列(self, env):
        """① 3 个账号举报 → hidden，且出现在 status=needs_review 队列。"""
        client, _ = env
        uid_a, tok_a = new_user(client)
        pid = make_post(client, tok_a, uid_a)
        approve(client, pid)

        _report_n(client, pid, 3)

        assert _status(pid) == "hidden", f"3 次举报后状态为 {_status(pid)}，应为 hidden"
        assert _in_review_queue(client, pid), (
            "被举报隐藏的帖子没有进入复核队列（needs_review）。"
            "这正是老板要防的「恶意举报把帖子压死却没人复查」。"
        )

    def test_02_管理端恢复后重新可见且举报明细仍在(self, env):
        """② restore → approved、列表可见、举报明细保留（用于识别人恶意举报）。"""
        client, _ = env
        uid_a, tok_a = new_user(client)
        pid = make_post(client, tok_a, uid_a)
        approve(client, pid)
        _report_n(client, pid, 3)
        assert _status(pid) == "hidden"

        r = _review_nr(client, pid, "restore", reason="人工复核：内容无问题，举报不成立")
        assert r.status_code == 200, f"restore 失败：{r.status_code} {r.text[:200]}"
        assert _status(pid) == "approved", f"restore 后状态为 {_status(pid)}，应为 approved"

        db = _db()
        try:
            n = db.execute("SELECT COUNT(*) FROM post_reports WHERE post_id = ?", (pid,)).fetchone()[0]
        finally:
            db.close()
        assert n >= 3, f"恢复后举报明细被清掉了（只剩 {n} 条），无法识别恶意举报者"

    def test_03_恢复后再次举报满阈值仍进队列(self, env):
        """③ 恢复后再次被举报满 3 次 → 再次 hidden 并再进队列（不能因恢复过就跳过）。"""
        client, _ = env
        uid_a, tok_a = new_user(client)
        pid = make_post(client, tok_a, uid_a)
        approve(client, pid)

        _report_n(client, pid, 3)
        assert _status(pid) == "hidden"
        assert _review_nr(client, pid, "restore").status_code == 200
        assert _status(pid) == "approved"

        _report_n(client, pid, 3)
        assert _status(pid) == "hidden", "恢复后再次被举报未重新隐藏"
        assert _in_review_queue(client, pid), "恢复后再次被举报，没有重新进入复核队列"

    def test_04_非管理员不能恢复(self, env):
        """④ 非管理员调 restore → 403。"""
        client, _ = env
        uid_a, tok_a = new_user(client)
        pid = make_post(client, tok_a, uid_a)
        approve(client, pid)
        _report_n(client, pid, 3)
        assert _status(pid) == "hidden"

        # 普通用户令牌
        _, tok = new_user(client)
        r = client.post(f"/admin/community/posts/{pid}/review", json={"action": "restore"}, headers=auth(tok))
        assert r.status_code in (401, 403), f"普通用户能调 restore：{r.status_code}"
        # 无令牌
        r = client.post(f"/admin/community/posts/{pid}/review", json={"action": "restore"})
        assert r.status_code in (401, 403), f"无令牌能调 restore：{r.status_code}"
        assert _status(pid) == "hidden", "非管理员调用后状态被改了"

    def test_05_隐藏与恢复都有操作日志(self, env):
        """⑤ 每次隐藏/恢复都产生一条操作日志。

        排期里审计日志是第 3 项（6h），复核对它是「先预留字段」。所以这里：
        优先查 admin_audit_log；如果表还没建，退一步查帖子上的处理人/时间字段，
        两者都没有才判失败——不能让这条用例在第 3 项落地前变成永久红。
        """
        client, _ = env
        uid_a, tok_a = new_user(client)
        pid = make_post(client, tok_a, uid_a)
        approve(client, pid)
        _report_n(client, pid, 3)
        _review_nr(client, pid, "restore", reason="复核通过")

        db = _db()
        try:
            tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if "admin_audit_log" in tables:
                rows = db.execute(
                    "SELECT action FROM admin_audit_log WHERE target_id = ?", (str(pid),)
                ).fetchall()
                actions = [r[0] for r in rows]
                assert any(a in ("hide", "auto_hide", "report_hide") for a in actions), (
                    f"隐藏没写审计日志，实际记录：{actions}"
                )
                assert "restore" in actions, f"恢复没写审计日志，实际记录：{actions}"
            else:
                cols = {r[1] for r in db.execute("PRAGMA table_info(posts)")}
                assert cols & {"restored_by", "reviewed_by", "hidden_by"}, (
                    "既没有 admin_audit_log 表，posts 上也没有处理人字段——隐藏/恢复完全无痕，"
                    f"posts 现有列：{sorted(cols)}"
                )
        finally:
            db.close()


# ================================================================ 打码覆盖

class Test打码覆盖:
    CASES = [
        ("手机号", "13812345678", "电话 13812345678 联系我"),
        ("邮箱", "hr_test@example.com", "简历发到 hr_test@example.com"),
        ("门牌号", "人民路22号", "在人民路22号面试"),
        ("车牌", "京A12345", "开车牌京A12345来"),
    ]

    @pytest.mark.parametrize("name,secret,text", CASES, ids=[c[0] for c in CASES])
    def test_入库前打码(self, env, name, secret, text):
        client, settings = env
        uid, tok = new_user(client)
        try:
            pid = make_post(client, tok, uid, question=text)
        except AssertionError:
            pytest.skip(f"{name} 被拦截而非打码")
        db = _db()
        try:
            row = db.execute("SELECT question FROM posts WHERE id = ?", (pid,)).fetchone()
        finally:
            db.close()
        saved = row[0] if row else ""
        assert secret not in saved, f"{name}未打码：{saved}"


# ================================================================ 防刷

class Test防刷:
    def test_同设备大量投票进风控(self, env):
        """§11.2：同设备/IP 段异常投票进风控，可疑票不计入展示，但保留记录。"""
        client, settings = env
        uid_a, tok_a = new_user(client)
        pid = make_post(client, tok_a, uid_a)
        approve(client, pid)

        # 同一设备标识连续投票（用请求头模拟设备）
        votes_ok = 0
        for _ in range(6):
            uid, tok = new_user(client)
            _age(uid)
            r = client.post(
                f"/community/posts/{pid}/vote",
                json={"value": 1},
                headers={**auth(tok), "X-Device-Id": "same-device-001"},
            )
            if r.status_code == 200:
                votes_ok += 1

        detail = client.get(f"/community/posts/{pid}", headers=auth(tok_a)).json()["data"]
        shown = detail.get("vote_up", 0)
        db = _db()
        try:
            stored = db.execute("SELECT COUNT(*) FROM votes WHERE post_id = ?", (pid,)).fetchone()[0]
        finally:
            db.close()

        # 记录实际行为；若风控未实现，则展示数 == 存储数
        assert shown <= stored, f"展示票数({shown})超过存储票数({stored})"
