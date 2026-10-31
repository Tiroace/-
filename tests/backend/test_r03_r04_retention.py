"""合规发现 R-03 / R-04 的回归用例。

R-03：截图「24 小时删除」必须由定时任务真正删文件、删记录并留删除日志，
      不能只有 expires_at 字段（那样承诺不成立）。
R-04：日志必须落盘并按天轮转、保留 190 天（≥6 个日历月），不能只打 console。
"""
from __future__ import annotations

import logging
import tempfile
from pathlib import Path

import pytest

from backend.app import retention
from backend.app.config import Settings, get_settings
from backend.app.deps import get_db
from backend.app.logging_setup import RETENTION_DAYS, setup_logging


def _boom(*_a, **_k):
    raise FileNotFoundError("no db here")


@pytest.fixture()
def temp_db(monkeypatch, tmp_path):
    """给本用例一个独立的库，并且**强制** retention 用它。

    这里踩过两个坑（跨文件跑会红、单独跑却绿）：
    1. `backend.app.retention` 是 `from .deps import get_db`，导入时就把函数对象绑死在模块
       命名空间上；只把 `deps.get_db` 换成别的东西没用，必须替换 `retention.get_db` 本身。
    2. `deps._db` 是进程级全局单例，前面任何一个测试文件建过 TestClient 就会留下一个指向
       它自己临时目录的库，retention 无参 `get_db()` 拿到的是那个，不是这里建的。
       所以这里既重置单例，又把 `retention.get_db` 直接钉死到本用例的 db 上，双保险。
    """
    settings = Settings()
    settings.db_path = tmp_path / "r03.db"
    settings.upload_dir = tmp_path / "uploads"
    settings.report_dir = None
    monkeypatch.setattr("backend.app.deps.get_settings", lambda: settings)
    import backend.app.deps as deps

    deps._db = None
    db = get_db(settings)
    db.init()
    # 关键：retention 里用到的是自己模块命名空间里的 get_db，不是 deps.get_db
    monkeypatch.setattr(retention, "get_db", lambda *a, **k: db, raising=False)
    with db.transaction() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO users (id, platform, openid, created_at) VALUES (?,?,?,?)",
            ("u_r03", "wechat", "openid_r03", "2026-10-31 00:00:00"),
        )
    yield db, settings
    deps._db = None


def _add_upload(db, tmp_path, image_id: str, expires_at: str) -> Path:
    target = tmp_path / f"{image_id}.jpg"
    target.write_bytes(b"fake-image-bytes")
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO uploads (id,user_id,file_hash,path,size,content_type,expires_at,created_at)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (image_id, "u_r03", "h", str(target), 16, "image/jpeg", expires_at, "2026-10-31 00:00:00"),
        )
    return target


def test_过期截图被删文件删记录并写日志(temp_db, tmp_path, monkeypatch):
    db, _settings = temp_db
    log_path = tmp_path / "deletion.log"
    monkeypatch.setattr(retention, "deletion_log_path", lambda: log_path)

    expired = _add_upload(db, tmp_path, "i_expired", "2000-01-01 00:00:00")
    alive = _add_upload(db, tmp_path, "i_alive", "2999-01-01 00:00:00")

    stats = retention.purge_expired_uploads()

    assert stats["scanned"] == 1, "只应扫到 1 张过期图"
    assert stats["file_deleted"] == 1
    assert stats["record_deleted"] == 1
    assert not expired.exists(), "过期截图文件没被删——24 小时删除的承诺不成立"
    assert alive.exists(), "未过期截图被误删"
    with db.connect() as conn:
        left = {r["id"] for r in conn.execute("SELECT id FROM uploads")}
    assert left == {"i_alive"}
    assert log_path.is_file(), "删除没有留日志"
    text = log_path.read_text(encoding="utf-8")
    assert "i_expired" in text and "i_alive" not in text


def test_文件已不在时仍删记录但标注出来(temp_db, tmp_path, monkeypatch):
    db, _settings = temp_db
    log_path = tmp_path / "deletion.log"
    monkeypatch.setattr(retention, "deletion_log_path", lambda: log_path)
    target = _add_upload(db, tmp_path, "i_gone", "2000-01-01 00:00:00")
    target.unlink()

    stats = retention.purge_expired_uploads()

    assert stats["file_missing"] == 1
    assert stats["record_deleted"] == 1
    text = log_path.read_text(encoding="utf-8")
    assert "file_missing" in text


def test_删除失败时保留记录等下轮重试(temp_db, tmp_path, monkeypatch):
    db, _settings = temp_db
    monkeypatch.setattr(retention, "deletion_log_path", lambda: tmp_path / "deletion.log")
    _add_upload(db, tmp_path, "i_locked", "2000-01-01 00:00:00")

    def _fail(self):
        raise OSError("permission denied")

    monkeypatch.setattr(Path, "unlink", _fail)
    stats = retention.purge_expired_uploads()

    assert stats["file_error"] == 1
    with db.connect() as conn:
        left = {r["id"] for r in conn.execute("SELECT id FROM uploads")}
    assert left == {"i_locked"}, "文件删不掉却把记录删了，等于假装删过"


def test_过期报告也会被删(temp_db, tmp_path, monkeypatch):
    db, _settings = temp_db
    monkeypatch.setattr(retention, "deletion_log_path", lambda: tmp_path / "deletion.log")
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO analysis_tasks (id,user_id,status,created_at) VALUES (?,?,?,?)",
            ("t_r03", "u_r03", "done", "2026-10-31 00:00:00"),
        )
        conn.execute(
            "INSERT INTO reports (id,task_id,user_id,report_json,risk_level,expires_at,created_at)"
            " VALUES (?,?,?,?,?,?,?)",
            ("r_r03", "t_r03", "u_r03", "{}", "green", "2000-01-01 00:00:00", "2026-10-31 00:00:00"),
        )
    stats = retention.purge_expired_reports()
    assert stats["record_deleted"] == 1
    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) AS c FROM reports").fetchone()["c"] == 0


def _drop_qbl_handlers() -> None:
    """摘掉别的测试文件留下的 qbl 文件 handler。

    `setup_logging()` 是「先挂上的赢」：任何先建过 TestClient 的文件（main.py 导入时就会调
    setup_logging）都会在 root logger 上留一个指向它自己临时目录的 handler，于是这里再调
    setup_logging(tmp_path) 会直接返回别人那个路径，日志写不进 tmp_path。
    这是测试之间通过**进程级 logging 状态**串味，必须显式清理。
    """
    root = logging.getLogger()
    for handler in list(root.handlers):
        if getattr(handler, "_qbl_file_handler", False):
            root.removeHandler(handler)
            try:
                handler.close()
            except Exception:
                pass


@pytest.fixture()
def clean_logging():
    _drop_qbl_handlers()
    yield
    _drop_qbl_handlers()


def test_日志落盘且按天轮转保留190天(tmp_path, clean_logging):
    log_path = setup_logging(tmp_path)
    logging.getLogger("qbl.r04").info("R04 write test")
    handler = next(h for h in logging.getLogger().handlers if getattr(h, "_qbl_file_handler", False))
    for h in logging.getLogger().handlers:
        h.flush()

    assert log_path.is_file(), "日志没落盘，进程一停就没了"
    assert "R04 write test" in log_path.read_text(encoding="utf-8")
    # 取 190 不是 180：backupCount=N 实际保留 N+1 个文件（合规助理实测），
    # 190 → 191 天覆盖；6 个日历月最长 184 天（3–8 月），余 7 天。
    # 180 → 181 天，在 182–184 区间差 1–3 天，所以 180 不严格够。
    assert RETENTION_DAYS == 190, f"留存天数应为 190，实际 {RETENTION_DAYS}"
    assert handler.backupCount == RETENTION_DAYS, "backupCount 必须跟常量一致"
    assert RETENTION_DAYS + 1 >= 184, "N+1 个文件必须覆盖最长的 6 个日历月（184 天）"
    assert handler.when.upper() == "MIDNIGHT", "应按天轮转"


def test_重复初始化不会写两份日志(tmp_path, clean_logging):
    setup_logging(tmp_path)
    setup_logging(tmp_path)
    count = [h for h in logging.getLogger().handlers if getattr(h, "_qbl_file_handler", False)]
    assert len(count) == 1, "重复挂 handler 会导致每条日志写两遍"
