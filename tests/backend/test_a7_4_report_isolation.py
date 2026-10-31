"""A7-4 提审自查证据：「报告仅本人可见」的越权测试。

提审自查表（docs/06-合规与文案/06-平台提审材料清单.md）A7-4 要求：
「用 A 账号访问 B 账号的报告应 404」，并且要有可复核的证据。

**为什么单独写一份**：原有 `tests/backend/test_security.py::test_A拿不到B的报告`
只用了编造的 id（`r_does_not_exist` 等），访问的是 `/reports/{rid}`。
实测该路由**根本不存在**——它返回 404 是因为「没有这个接口」，
而不是因为越权拦住了。那种用例永远绿，却证明不了任何事。

本文件用**真实存在的他人报告**验证：B 先生成一份真报告拿到真 id，
再用 A 的令牌去访问，必须是 404/403，且响应里不许出现报告内容。

对应关系：A7-4 ↔ 合规清单；证据路径回填到 06 号表。
"""
from __future__ import annotations

import importlib
import sys

import pytest

from conftest import ROOT

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

pytest.importorskip("fastapi", reason="后端测试需要 fastapi")
pytest.importorskip("httpx", reason="TestClient 需要 httpx")

TestClient = pytest.importorskip("fastapi.testclient").TestClient

OCR_TEXT = """高薪招聘 兼职刷单 日结300元
入职需缴纳服装费980元、押金500元，离职退还
流程：加客服微信领取任务单，垫付货款后截图返款
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
    monkeypatch.setenv("QBL_POLL_AFTER_MS", "10")

    # 【不要 reload backend 模块树】2026-10-31 实测踩坑：
    # 本文件最初照抄 test_security.py 的写法（删 sys.modules 里的 backend.* 再
    # importlib.reload(main)）。单独跑没事，但全量跑时会让同目录后面的
    # test_r03_r04_retention.py 全部失败（5 条），因为它是在模块级 `from ... import`
    # 拿到的 Settings/get_db，reload 之后拿到的对象与它引用的不是同一批。
    # 这里改为：进程内只 import 一次，靠 monkeypatch 改环境变量 + deps.reset_db() 隔离。
    from backend.app import deps, main
    from backend.app.config import get_settings

    # 【必须备份并还原全局 logging handler】2026-10-31 实测踩坑：
    # 建 TestClient 会触发 setup_logging()，往 root logger 挂一个
    # TimedRotatingFileHandler 指向**本用例的临时目录**。而 setup_logging 是
    # 「先挂上的赢」——之后 test_r03_r04_retention 再调 setup_logging 只会
    # 返回旧路径、不会换 handler，于是它的「日志落盘」用例永远找不到文件。
    # 单独跑都绿、全量跑就红，正是这个原因。这里用完还原，不给别人留脏状态。
    import logging

    root = logging.getLogger()
    saved_handlers = list(root.handlers)
    saved_level = root.level

    # get_settings() 每次直接读环境变量、不做缓存，所以改完 env 即可生效。
    deps.reset_db()
    settings = get_settings()
    client = TestClient(main.app)
    yield client, settings
    try:
        from backend.app import worker

        worker.shutdown(wait=True)
    except Exception:
        pass
    deps.reset_db()

    # 还原 root logger：摘掉本次新增的 handler，放回原来的
    for h in list(root.handlers):
        if h not in saved_handlers:
            root.removeHandler(h)
            try:
                h.close()
            except Exception:
                pass
    root.handlers[:] = saved_handlers
    root.setLevel(saved_level)


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _register(client, code: str) -> tuple[str, str]:
    r = client.post("/auth/login", json={"platform": "toutiao", "code": code})
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    return data["user_id"], data["token"]


def _make_real_report(client, token: str) -> dict:
    """用 OCR 旁路造一份**真实存在**的报告，返回 {"task_id", "report_id"}。"""
    import time

    r = client.post("/analysis", data={"ocr_text": OCR_TEXT}, headers=_auth(token))
    assert r.status_code == 200, r.text
    task_id = r.json()["data"]["task_id"]

    deadline = time.time() + 30
    last = None
    while time.time() < deadline:
        rr = client.get(f"/analysis/{task_id}", headers=_auth(token))
        assert rr.status_code == 200, rr.text
        last = rr.json()["data"]
        if last["status"] in ("done", "failed"):
            break
        time.sleep(0.05)
    assert last and last["status"] == "done", f"报告未生成成功：{last}"

    report = last.get("report") or {}
    report_id = report.get("report_id") or last.get("report_id")
    return {"task_id": task_id, "report_id": report_id, "detail": last}


class TestA7_4报告仅本人可见:
    def test_前置_能造出真实报告(self, env):
        """先证明「确实有东西可越权」，否则后面的 404 没意义。"""
        client, _ = env
        uid_b, tok_b = _register(client, "code-b")
        info = _make_real_report(client, tok_b)
        assert info["task_id"], "B 没拿到 task_id"
        # B 自己能读到自己刚生成的报告
        r = client.get(f"/analysis/{info['task_id']}", headers=_auth(tok_b))
        assert r.status_code == 200, f"本人读自己的报告都失败：{r.status_code}"

    def test_A用B的真实任务id访问必须404(self, env):
        """核心证据：A 拿着 B 真实存在的 task_id，必须 404/403，且不泄漏内容。"""
        client, _ = env
        uid_a, tok_a = _register(client, "code-a")
        uid_b, tok_b = _register(client, "code-b")

        info = _make_real_report(client, tok_b)
        task_id = info["task_id"]

        # B 自己读得到（对照组，排除「谁都读不到」的假象）
        own = client.get(f"/analysis/{task_id}", headers=_auth(tok_b))
        assert own.status_code == 200, "对照组失败：B 自己都读不到自己的报告"

        # A 来越权
        r = client.get(f"/analysis/{task_id}", headers=_auth(tok_a))
        assert r.status_code in (403, 404), (
            f"越权！A 用 B 的真实任务 {task_id} 拿到 {r.status_code}：{r.text[:300]}"
        )

        # 响应体里不许出现报告内容
        body = r.text
        report = own.json()["data"].get("report") or {}
        for key in ("summary", "findings", "overall"):
            val = report.get(key)
            if isinstance(val, str) and val:
                assert val not in body, f"404 响应里泄漏了报告字段 {key}：{val!r}"
        assert "服装费" not in body and "押金" not in body, f"404 响应泄漏了报告正文：{body[:300]}"

    def test_A的报告列表里不出现B的报告(self, env):
        """列表接口不能把他人报告混进来——只按 id 猜不到，但列表会直接漏出来。"""
        client, _ = env
        uid_a, tok_a = _register(client, "code-a")
        uid_b, tok_b = _register(client, "code-b")

        info_b = _make_real_report(client, tok_b)
        info_a = _make_real_report(client, tok_a)

        r = client.get("/reports", headers=_auth(tok_a))
        assert r.status_code == 200, r.text
        items = r.json()["data"]["items"]
        task_ids = {it.get("task_id") for it in items}

        assert info_b["task_id"] not in task_ids, "A 的报告列表里出现了 B 的报告"
        assert info_a["task_id"] in task_ids, "A 的报告列表里没有自己的报告（用例前提不成立）"

    def test_未登录访问他人任务被拒(self, env):
        """没有令牌时，连 404 都不该给内容——应是 401/403。"""
        client, _ = env
        _, tok_b = _register(client, "code-b")
        info = _make_real_report(client, tok_b)

        r = client.get(f"/analysis/{info['task_id']}")
        assert r.status_code in (401, 403), f"未登录访问他人任务返回 {r.status_code}"

    def test_不存在的任务与无权访问返回一致(self, env):
        """他人的任务与不存在的任务返回值一致，避免靠状态差异探测任务是否存在。"""
        client, _ = env
        _, tok_a = _register(client, "code-a")
        _, tok_b = _register(client, "code-b")
        info = _make_real_report(client, tok_b)

        other = client.get(f"/analysis/{info['task_id']}", headers=_auth(tok_a))
        missing = client.get("/analysis/t_does_not_exist_at_all", headers=_auth(tok_a))
        assert other.status_code == missing.status_code, (
            f"他人任务 {other.status_code} 与不存在任务 {missing.status_code} 不一致，"
            "可被用来探测任务是否存在"
        )
