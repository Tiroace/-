"""登录与用户信息（§5.4：POST /auth/login、GET /me）。

登录走平台适配层：有 AppID/Secret 走真实 code2session，没有走 Mock，
响应里用 `platform_mode` 标明，前端/测试不会把 mock 当真实登录。
"""
from __future__ import annotations

import datetime as dt
import uuid

from fastapi import APIRouter, Depends, Request

from ..config import get_settings
from ..deps import current_user, envelope, get_db
from ..errors import AppError
from ..models import LoginRequest
from ..platform import PlatformError, SessionInfo, get_adapter
from ..quota import balance, grant_register_bonus, today_ad_count
from ..security import issue_token

router = APIRouter(tags=["登录/用户"])


def _now() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _membership(conn, user_id: str) -> dict:
    row = conn.execute("SELECT * FROM memberships WHERE user_id = ?", (user_id,)).fetchone()
    settings = get_settings()
    if row is None or row["expires_at"] <= _now():
        return {"active": False, "plan": None, "expires_at": None, "daily_limit": None}
    return {
        "active": True,
        "plan": row["plan"],
        "expires_at": row["expires_at"],
        "daily_limit": settings.member_daily_quota,
    }


def _user_payload(conn, user_id: str) -> dict:
    settings = get_settings()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    adapter = get_adapter(user["platform"], settings)
    stats = conn.execute(
        "SELECT COUNT(*) AS c, COALESCE(SUM(CASE WHEN risk_level = 'red' THEN 1 ELSE 0 END), 0) AS red"
        " FROM reports WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    ad = adapter.ad_config()
    today = today_ad_count(conn, user_id)
    ad["today_count"] = today
    ad["remaining_today"] = max(0, int(ad.get("daily_cap", 0)) - today)
    return {
        "user_id": user["id"],
        "platform": user["platform"],
        "created_at": user["created_at"],
        "quota": {"balance": balance(conn, user_id)},
        "membership": _membership(conn, user_id),
        "checked_count": int(stats["c"] or 0),
        "red_count": int(stats["red"] or 0),
        "ad": ad,
    }


@router.post("/auth/login")
def login(body: LoginRequest, request: Request) -> dict:
    """平台 code 换登录态。openid 由平台适配层给出（真实平台或 Mock）。

    开发登录通道（B 关口联调 / 没有正式 AppID 时用）：
    - 仅当服务端 `QBL_DEV_MODE=1` 时启用，生产必须关闭；
    - `code=mock` 换一个固定的开发账号；`code=mock:<任意串>` 或 `X-Debug-User` 头可换不同开发账号；
    - 响应带 `dev_login: true`，前端/测试一眼能看出这不是真实平台登录。
    """
    settings = get_settings()
    dev_code = body.code == "mock" or body.code.startswith("mock:")
    if dev_code:
        if not settings.dev_mode:
            raise AppError("DEV_LOGIN_DISABLED", "开发登录通道未开启（生产环境不允许）", 403)
        debug_user = (request.headers.get("X-Debug-User") or "").strip()
        suffix = debug_user or (body.code.split(":", 1)[1] if ":" in body.code else "default")
        suffix = "".join(ch for ch in suffix if ch.isalnum() or ch in "_-")[:32] or "default"
        session = SessionInfo(openid=f"dev-{body.platform}-{suffix}", mode="dev", raw={"dev": True})
        adapter = None
    else:
        adapter = get_adapter(body.platform, settings)
        try:
            session = adapter.code2session(body.code)
        except PlatformError as exc:
            raise AppError("PLATFORM_ERROR", str(exc), 502) from exc

    db = get_db(settings)
    with db.transaction() as conn:
        row = conn.execute(
            "SELECT id FROM users WHERE platform = ? AND openid = ?", (body.platform, session.openid)
        ).fetchone()
        if row is None:
            user_id = "u_" + uuid.uuid4().hex[:12]
            conn.execute(
                "INSERT INTO users (id, platform, openid, unionid, status, created_at) VALUES (?, ?, ?, ?, 'active', ?)",
                (user_id, body.platform, session.openid, session.unionid, _now()),
            )
            grant_register_bonus(conn, user_id, settings.free_quota)
        else:
            user_id = row["id"]

    with db.connect() as conn:
        payload = _user_payload(conn, user_id)
    payload["token"] = issue_token(user_id, settings.token_secret, settings.token_ttl_seconds)
    payload["is_new_user"] = row is None
    payload["platform_mode"] = session.mode          # mock / live / dev
    payload["dev_login"] = dev_code                  # 开发登录通道标记，前端不得在正式环境依赖
    return envelope(payload, request)


@router.get("/me")
def me(request: Request, user: dict = Depends(current_user)) -> dict:
    with get_db().connect() as conn:
        payload = _user_payload(conn, user["id"])
    settings = get_settings()
    payload["platform_mode"] = get_adapter(user["platform"], settings).login_mode
    return envelope(payload, request)
