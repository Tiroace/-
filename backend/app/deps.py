"""FastAPI 依赖：数据库、当前用户、管理员。"""
from __future__ import annotations

from fastapi import Header, Request

from .config import Settings, get_settings
from .db import Database
from .errors import forbidden, unauthorized
from .security import constant_time_equals, verify_token

_db: Database | None = None


def get_db(settings: Settings | None = None) -> Database:
    """取全局库单例。

    QBL_DB_URL 指向 MySQL 时用 MySQL；否则用 SQLite（cfg.db_path）。
    切换判断带上 db_url：测试里改连接串也能正确重建。
    """
    global _db
    cfg = settings or get_settings()
    db_url = getattr(cfg, "db_url", "") or ""
    if _db is None or _db.path != cfg.db_path or (getattr(_db, "db_url", "") or "") != db_url:
        _db = Database(cfg.db_path, db_url=db_url or None)
        _db.init()
    return _db


def reset_db() -> None:
    """测试用：切库后重置单例。"""
    global _db
    _db = None


def current_user(authorization: str | None = Header(default=None)) -> dict:
    cfg = get_settings()
    if not authorization or not authorization.lower().startswith("bearer "):
        raise unauthorized()
    user_id = verify_token(authorization.split(" ", 1)[1].strip(), cfg.token_secret)
    if not user_id:
        raise unauthorized()
    with get_db(cfg).connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if row is None or row["status"] != "active":
        raise unauthorized("账号不可用")
    return dict(row)


def require_admin(x_admin_token: str | None = Header(default=None)) -> None:
    if not constant_time_equals(x_admin_token or "", get_settings().admin_token):
        raise forbidden("需要管理员权限")


def envelope(data: object, request: Request) -> dict:
    return {"ok": True, "data": data, "request_id": getattr(request.state, "request_id", "")}
