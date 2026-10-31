"""合规发现 R-03 / R-04 的回归用例。

R-03：截图「24 小时删除」必须由定时任务真正删文件、删记录并留删除日志，
      不能只有 expires_at 字段（那样承诺不成立）。
R-04：日志必须落盘并按天轮转、保留 180 天，不能只打 console。
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
    settings = Settings()
    settings.db_path = tmp_path / "r03.db"
    settings.upload_dir = tmp_path / "uploads"
    settings.report_dir = None
    monkeypatch.setattr("backend.app.deps.get_settings", lambda: settings)
    import backend.app.deps as deps

    deps._db = None
    db = get_db(settings)
    db.init()
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


def test_日志落盘且按天轮转保留180天(tmp_path):
    log_path = setup_logging(tmp_path)
    logging.getLogger("qbl.r04").info("R04 write test")
    handler = next(h for h in logging.getLogger().handlers if getattr(h, "_qbl_file_handler", False))
    for h in logging.getLogger().handlers:
        h.flush()

    assert log_path.is_file(), "日志没落盘，进程一停就没了"
    assert "R04 write test" in log_path.read_text(encoding="utf-8")
    assert handler.backupCount == RETENTION_DAYS == 180, "日志留存必须 ≥180 天（网络安全法要求 6 个月）"
    assert handler.when.upper() == "MIDNIGHT", "应按天轮转"


def test_重复初始化不会写两份日志(tmp_path):
    setup_logging(tmp_path)
    setup_logging(tmp_path)
    count = [h for h in logging.getLogger().handlers if getattr(h, "_qbl_file_handler", False)]
    assert len(count) == 1, "重复挂 handler 会导致每条日志写两遍"
