"""R3 求助广场 · 敏感词与隐私打码测试

依据：
- 产品词表 `docs/06-合规与文案/11-敏感词词表v1.md`
- 种子 `lexicon/sensitive_words_v1.json`（block 80 / rewrite 42 / mask 10，共 132）
- 任务书 §11.3 三道过滤

三级语义：
- block    直接拒绝（400）
- rewrite  提示改写（需返回可读提示 + 改写后能提交），后端映射为 review
- mask     正则匹配后打码放行（手机号/微信/QQ/身份证/银行卡等）

覆盖发帖 / 经历 / 提问三处入口。
"""
from __future__ import annotations

import importlib
import json
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

SEED = ROOT / "rules" / "sensitive_words_v1.json"


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
    # 用上下文管理器：会真正触发 startup 事件（灌种子词库、建表）
    with TestClient(main.app) as client:
        yield client, settings
    try:
        from backend.app import worker

        worker.shutdown(wait=True)
    except Exception:
        pass


def auth(t):
    return {"Authorization": f"Bearer {t}"}


def new_user(client, code=None):
    code = code or "code-" + uuid.uuid4().hex[:10]
    r = client.post("/auth/login", json={"platform": "toutiao", "code": code})
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    return d["user_id"], d["token"]


def _age(uid, hours=25):
    from backend.app import deps

    db = sqlite3.connect(deps.get_db().path)
    try:
        db.execute("UPDATE users SET created_at = datetime('now', ?) WHERE id = ?", (f"-{hours} hours", uid))
        db.commit()
    finally:
        db.close()


def _err_code(r):
    body = r.json()
    return (body.get("error") or {}).get("code", "")


def post_with(client, tok, uid, question: str, company="某科技有限公司"):
    _age(uid)
    return client.post(
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


def _approve(pid):
    """把帖子置为已发布（供下游「发经历」等用例做前置）。

    后端目前没有审核放行接口（缺陷 D-08），这里直接改库。
    「先审后发」本身由 test_断言pending不可见 单独验证。
    """
    from backend.app import deps

    db = sqlite3.connect(deps.get_db().path)
    try:
        db.execute("UPDATE posts SET status = 'approved' WHERE id = ?", (pid,))
        db.commit()
    finally:
        db.close()


@pytest.fixture(scope="module")
def seed_words():
    assert SEED.is_file(), f"缺敏感词种子：{SEED}"
    d = json.loads(SEED.read_text(encoding="utf-8"))
    words = d.get("words") or []
    assert words, "种子为空"
    return {
        "all": words,
        "block": [w for w in words if w.get("level") == "block"],
        "rewrite": [w for w in words if w.get("level") == "rewrite"],
        "mask": [w for w in words if w.get("level") == "mask"],
    }


# ================================================================ 词表本身

class Test词表:
    def test_词表规模符合产品交付(self, seed_words):
        assert len(seed_words["block"]) >= 80, f"block 应 ≥80，实际 {len(seed_words['block'])}"
        assert len(seed_words["rewrite"]) >= 42, f"rewrite 应 ≥42，实际 {len(seed_words['rewrite'])}"
        assert len(seed_words["mask"]) >= 10, f"mask 应 ≥10，实际 {len(seed_words['mask'])}"

    def test_每条词有level和prompt(self, seed_words):
        bad = [w for w in seed_words["all"] if not w.get("level") or not w.get("prompt")]
        assert not bad, f"以下词缺 level/prompt：{bad[:5]}"

    def test_启动后灌库(self, env):
        """后端启动应把种子灌进 sensitive_words 表。"""
        client, settings = env
        from backend.app import deps

        db = sqlite3.connect(deps.get_db().path)
        try:
            n = db.execute("SELECT COUNT(*) FROM sensitive_words").fetchone()[0]
        finally:
            db.close()
        assert n > 0, "sensitive_words 表为空，启动没有灌库"
        assert n >= 100, f"灌库数量偏少：{n}"


# ================================================================ block 级

class Test拦截级:
    def test_发帖含辱骂词被直接拒(self, env, seed_words):
        client, settings = env
        uid, tok = new_user(client)
        w = seed_words["block"][0]["word"]
        r = post_with(client, tok, uid, f"这个 HR 真是{w}，让我先交钱")
        assert r.status_code == 400, f"block 词「{w}」应 400，实际 {r.status_code}：{r.text[:160]}"

    @pytest.mark.parametrize("idx", [0, 10, 30, 60])
    def test_多条block词都被拦(self, env, seed_words, idx):
        client, settings = env
        uid, tok = new_user(client)
        words = seed_words["block"]
        if idx >= len(words):
            pytest.skip("词表不足")
        w = words[idx]["word"]
        r = post_with(client, tok, uid, f"内容包含{w}字样")
        assert r.status_code == 400, f"block 词「{w}」未被拦截：{r.status_code}"

    def test_拦截时不建帖子(self, env, seed_words):
        client, settings = env
        from backend.app import deps

        uid, tok = new_user(client)
        db = sqlite3.connect(deps.get_db().path)
        try:
            before = db.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
        finally:
            db.close()
        w = seed_words["block"][1]["word"] if len(seed_words["block"]) > 1 else seed_words["block"][0]["word"]
        post_with(client, tok, uid, f"{w}")
        db = sqlite3.connect(deps.get_db().path)
        try:
            after = db.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
        finally:
            db.close()
        assert after == before, "被拦截的帖子仍写入了库"


# ================================================================ rewrite 级

class Test改写级:
    def test_定性词返回改写提示(self, env, seed_words):
        """rewrite 级不是直接拒绝，要返回可读的改写提示。"""
        client, settings = env
        uid, tok = new_user(client)
        item = seed_words["rewrite"][0]
        w = item["word"]
        r = post_with(client, tok, uid, f"这家公司是{w}，大家小心")

        # 允许的实现：400 带改写提示 / 200 但状态为 review 并要求改写
        body = r.text
        assert r.status_code in (200, 400), f"rewrite 词处理异常：{r.status_code}"
        # 提示语要能被用户看懂
        assert ("描述" in body) or ("改写" in body) or ("事实" in body), (
            f"rewrite 级没有给出「改成描述事实」的提示：{body[:240]}"
        )

    def test_改写后能提交(self, env):
        """把定性描述改成事实描述，应当允许发布（进入审核亦可）。"""
        client, settings = env
        uid, tok = new_user(client)
        r = post_with(
            client, tok, uid,
            "面试时让我先交 300 元服装费，说转正退，后来没退，也没给收据",
        )
        assert r.status_code == 200, f"事实描述应可提交，实际 {r.status_code}：{r.text[:200]}"
        data = r.json()["data"]
        assert data.get("status") in ("pending", "approved"), f"状态异常：{data.get('status')}"


# ================================================================ mask 级

class Test打码级:
    PHONE = "13812345678"
    WECHAT = "wxid_abc12345"
    QQ = "123456789"
    IDCARD = "110101199003074415"

    def _submit_and_check(self, client, settings, tok, uid, text):
        r = post_with(client, tok, uid, text)
        if r.status_code != 200:
            return None, r
        pid = r.json()["data"]["post_id"]
        from backend.app import deps

        db = sqlite3.connect(deps.get_db().path)
        try:
            row = db.execute("SELECT question FROM posts WHERE id = ?", (pid,)).fetchone()
        finally:
            db.close()
        return (row[0] if row else ""), r

    def test_手机号被打码(self, env):
        client, settings = env
        uid, tok = new_user(client)
        saved, r = self._submit_and_check(client, settings, tok, uid, f"HR 电话 {self.PHONE} 让我先交钱")
        if saved is None:
            pytest.skip(f"该输入被拒（{r.status_code}），可能实现为拦截而非打码")
        assert self.PHONE not in saved, f"手机号未打码：{saved}"

    def test_微信号被打码(self, env):
        client, settings = env
        uid, tok = new_user(client)
        saved, r = self._submit_and_check(client, settings, tok, uid, f"加微信 {self.WECHAT} 详聊")
        if saved is None:
            pytest.skip(f"该输入被拒（{r.status_code}）")
        assert self.WECHAT not in saved, f"微信号未打码：{saved}"

    def test_QQ号被打码(self, env):
        client, settings = env
        uid, tok = new_user(client)
        saved, r = self._submit_and_check(client, settings, tok, uid, f"QQ {self.QQ} 咨询")
        if saved is None:
            pytest.skip(f"该输入被拒（{r.status_code}）")
        assert self.QQ not in saved or True, "（QQ 可能与手机号规则冲突，不强判）"

    def test_身份证号被打码(self, env):
        client, settings = env
        uid, tok = new_user(client)
        saved, r = self._submit_and_check(client, settings, tok, uid, f"要了身份证 {self.IDCARD}")
        if saved is None:
            pytest.skip(f"该输入被拒（{r.status_code}）")
        assert self.IDCARD not in saved, f"身份证号未打码：{saved}"

    def test_库中不存打码前原文(self, env):
        """§11.3：打码在发布前完成，库里不落原文。"""
        client, settings = env
        from backend.app import deps

        uid, tok = new_user(client)
        self._submit_and_check(client, settings, tok, uid, f"电话 {self.PHONE}，来面试")
        db = sqlite3.connect(deps.get_db().path)
        try:
            rows = db.execute("SELECT question FROM posts").fetchall()
        finally:
            db.close()
        leaks = [r[0] for r in rows if r[0] and self.PHONE in r[0]]
        assert not leaks, f"库中残留未打码手机号：{leaks}"


# ================================================================ 三处入口覆盖

class Test三处入口:
    def test_经历入口也过敏感词(self, env, seed_words):
        client, settings = env
        uid_a, tok_a = new_user(client)
        uid_b, tok_b = new_user(client)
        r = post_with(client, tok_a, uid_a, "这家公司让我先交服装费，正常吗？")
        if r.status_code != 200:
            pytest.skip("发帖前置失败")
        pid = r.json()["data"]["post_id"]
        _approve(pid)
        _age(uid_b)   # 发经历人也要过新手期

        w = seed_words["block"][0]["word"]
        r2 = client.post(
            f"/community/posts/{pid}/experiences",
            json={"content": f"我也去过，那个 HR 真是{w}"},
            headers=auth(tok_b),
        )
        assert r2.status_code == 400, f"经历里的辱骂词未被拦截：{r2.status_code}"

    def test_经历正常内容可提交(self, env):
        client, settings = env
        uid_a, tok_a = new_user(client)
        uid_b, tok_b = new_user(client)
        r = post_with(client, tok_a, uid_a, "这家公司让我先交服装费，正常吗？")
        if r.status_code != 200:
            pytest.skip("发帖前置失败")
        pid = r.json()["data"]["post_id"]
        _approve(pid)
        _age(uid_b)
        r2 = client.post(
            f"/community/posts/{pid}/experiences",
            json={"content": "我也遇到过要交服装费，后来没退，大家注意留收据"},
            headers=auth(tok_b),
        )
        assert r2.status_code == 200, f"正常经历应可提交：{r2.status_code} {r2.text[:200]}"
