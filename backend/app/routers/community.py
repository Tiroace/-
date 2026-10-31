"""求助广场接口（R3，D14 开关默认关）。

规则要点：
- FEATURE_COMMUNITY=0 时所有 /community/* 返回 404（不对用户可见）；
- 先审后发：发帖/经历默认 pending，后台审核通过才展示；
- 投票：一人一帖一票可改、发帖人不能投自己、新号 24h 内禁投；
- 举报满 3 次自动隐藏；企业申诉 24h SLA；
- 发布前：敏感词 + 模型两层审核、图片走内容安全（第二道）、隐私打码后入库。
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import uuid
from pathlib import Path

from fastapi import APIRouter, Body, Depends, Query, Request
from pydantic import BaseModel, Field

from engine.adapters.content_safety import LocalContentSafetyStub

from ..community.moderation import mask_only, moderate
from ..community.privacy import mask_community_text
from ..config import get_settings
from ..deps import current_user, envelope, get_db, require_admin
from ..errors import AppError, forbidden, not_found, validation_error

router = APIRouter(tags=["求助广场"])
admin_router = APIRouter(tags=["求助广场-后台"], dependencies=[Depends(require_admin)])

_TS = "%Y-%m-%d %H:%M:%S"


def _now() -> str:
    return dt.datetime.now().strftime(_TS)


def _ip_prefix(ip: str) -> str:
    ip = (ip or "").strip()
    if not ip:
        return ""
    if ":" in ip:                      # IPv6 取前 4 段当 /64
        return ":".join(ip.split(":")[:4]) + "::/64"
    parts = ip.split(".")
    if len(parts) == 4:
        return ".".join(parts[:3]) + ".0/24"
    return ip[:24]


def _vote_identity(request: Request, user: dict) -> tuple[str, str]:
    """设备号哈希 + /24 网段。缺 X-Device-Id 时退回 openid+IP，不报错。"""
    forwarded = (request.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
    ip = forwarded or (request.client.host if request.client else "") or ""
    device_id = (request.headers.get("X-Device-Id") or "").strip()
    seed = device_id or f"{user.get('openid', '')}|{ip}"
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:32], _ip_prefix(ip)


def _vote_risk(conn, settings, device_hash: str, ip_prefix: str) -> str | None:
    """窗口期内同设备超 N 票 / 同网段超 M 票 → 可疑票（计入记录、不计展示）。"""
    since = (dt.datetime.now() - dt.timedelta(minutes=settings.community_vote_window_minutes)).strftime(_TS)
    device_count = conn.execute(
        "SELECT COUNT(*) AS c FROM votes WHERE device_hash = ? AND created_at >= ?", (device_hash, since)
    ).fetchone()["c"]
    if device_count >= settings.community_vote_device_limit:
        return "device_flood"
    if ip_prefix:
        ip_count = conn.execute(
            "SELECT COUNT(*) AS c FROM votes WHERE ip_prefix = ? AND created_at >= ?", (ip_prefix, since)
        ).fetchone()["c"]
        if ip_count >= settings.community_vote_ip_limit:
            return "ip_flood"
    return None


def _nid(prefix: str) -> str:
    return prefix + "_" + uuid.uuid4().hex[:16]


def _require_enabled():
    settings = get_settings()
    if not settings.feature_community:
        raise not_found("求助广场暂未开放")
    return settings


def _age_hours(created_at: str) -> float:
    try:
        created = dt.datetime.strptime(created_at, _TS)
    except (TypeError, ValueError):
        return 0.0
    return (dt.datetime.now() - created).total_seconds() / 3600


def _assert_not_new_account(user: dict, settings, action: str) -> None:
    if _age_hours(user["created_at"]) < settings.community_new_account_hours:
        raise AppError(
            "NEW_ACCOUNT_RESTRICTED",
            f"新注册账号 {settings.community_new_account_hours} 小时内不能{action}",
            403,
            {"required_hours": settings.community_new_account_hours},
        )


def _moderate_or_raise(conn, text: str) -> str:
    """两级审核 + 打码：block 直接 400，rewrite 返回「请改成描述事实」，mask 打码放行。"""
    result = moderate(conn, text)
    if result.ok:
        return result.masked_text
    if result.action == "rewrite":
        raise AppError(
            "NEEDS_REWRITE",
            "请改成描述事实后再提交",
            400,
            {
                "layer": result.layer,
                "prompt": result.prompt or "请改成描述事实后再提交",
                "reasons": result.reasons,
            },
        )
    raise AppError(
        "CONTENT_BLOCKED",
        f"内容未通过审核：{result.reasons[0] if result.reasons else ''}",
        400,
        result.to_dict(),
    )


def _masked(value: str | None) -> str | None:
    if not value:
        return value
    return mask_community_text(value)[0]


def _validate_image_ids(conn, user_id: str, image_ids: list[str], settings) -> str | None:
    """图片：必须是本人上传且未过期；再过一遍内容安全（上传时已过第一道）。"""
    if not image_ids:
        return None
    if len(image_ids) > 3:
        raise validation_error("最多 3 张图片")
    paths: list[Path] = []
    for image_id in image_ids:
        row = conn.execute("SELECT * FROM uploads WHERE id = ?", (image_id,)).fetchone()
        if row is None or row["user_id"] != user_id:
            raise AppError("IMAGE_NOT_FOUND", "图片不存在或已过期，请重新上传", 400)
        if row["expires_at"] <= _now():
            raise AppError("IMAGE_EXPIRED", "图片已过期，请重新上传", 400)
        paths.append(Path(row["path"]))
    safety = LocalContentSafetyStub(max_files=3, max_mb=settings.max_image_mb).check(paths)
    if not safety.passed:
        raise AppError("CONTENT_BLOCKED", f"图片未通过内容安全检测：{safety.reason}", 422)
    return json.dumps(image_ids)


def _post_payload(row, my_vote: int | None = None) -> dict:
    return {
        "post_id": row["id"],
        "company": row["company"],
        "position": row["position"],
        "city": row["city"],
        "question": row["question"],
        "anonymous": bool(row["anonymous"]),
        "risk_overall": row["risk_overall"],
        "status": row["status"],
        "vote_up": row["vote_up"],
        "vote_down": row["vote_down"],
        "report_count": row["report_count"],
        "created_at": row["created_at"],
        "my_vote": my_vote,
    }


class PostCreate(BaseModel):
    question: str = Field(min_length=5, max_length=200)
    company: str | None = Field(default=None, max_length=60)
    position: str | None = Field(default=None, max_length=60)
    city: str | None = Field(default=None, max_length=40)
    report_id: str | None = None
    anonymous: bool = True
    image_ids: list[str] = Field(default_factory=list)


class VoteRequest(BaseModel):
    value: int = Field(ge=-1, le=1)          # 1 有帮助 / -1 没用 / 0 取消
    reason: str | None = Field(default=None, max_length=40)


class ExperienceCreate(BaseModel):
    content: str = Field(min_length=5, max_length=500)


class PostReportCreate(BaseModel):
    reason: str | None = Field(default=None, max_length=40)


class AppealCreate(BaseModel):
    post_id: str | None = None
    company: str | None = Field(default=None, max_length=60)
    contact: str | None = Field(default=None, max_length=80)
    content: str = Field(min_length=10, max_length=1000)


@router.get("/community/posts")
def list_posts(
    request: Request,
    user: dict = Depends(current_user),
    sort: str = Query(default="latest", pattern="^(latest|active|voted)$"),
    q: str | None = Query(default=None, max_length=40),
    limit: int = Query(default=20, ge=1, le=20),
    cursor: str | None = None,
) -> dict:
    """帖子列表：最新 / 参与最多（票数）/ 我投过的；只返回审核通过的。"""
    _require_enabled()
    db = get_db()
    args: list = []
    where = ["status = 'approved'"]
    if q:
        like = f"%{q.replace('%', '').replace('_', '')}%"
        where.append("(company LIKE ? OR position LIKE ? OR city LIKE ? OR question LIKE ?)")
        args += [like, like, like, like]
    if sort == "voted":
        where.append("id IN (SELECT post_id FROM votes WHERE user_id = ?)")
        args.append(user["id"])
    if cursor:
        where.append("created_at < ?")
        args.append(cursor)
    sql = "SELECT * FROM posts WHERE " + " AND ".join(where)
    sql += " ORDER BY (vote_up - vote_down) DESC, created_at DESC" if sort == "active" else " ORDER BY created_at DESC"
    sql += " LIMIT ?"
    args.append(limit + 1)
    with db.connect() as conn:
        rows = conn.execute(sql, args).fetchall()
        page = rows[:limit]
        my_votes: dict[str, int] = {}
        if page:
            placeholders = ",".join(["?"] * len(page))
            my_votes = {
                row["post_id"]: row["value"]
                for row in conn.execute(
                    f"SELECT post_id, value FROM votes WHERE user_id = ? AND post_id IN ({placeholders})",
                    [user["id"]] + [r["id"] for r in page],
                ).fetchall()
            }
    items = []
    for row in rows[:limit]:
        items.append(_post_payload(row, my_votes.get(row["id"])))
    return envelope(
        {"items": items, "next_cursor": rows[limit]["created_at"] if len(rows) > limit else None},
        request,
    )


@router.post("/community/posts")
def create_post(body: PostCreate, request: Request, user: dict = Depends(current_user)) -> dict:
    """发帖（先审后发）：审核两层 + 隐私打码 + 图片内容安全。"""
    settings = _require_enabled()
    _assert_not_new_account(user, settings, "发帖")
    db = get_db()
    masked = {
        "company": _masked(body.company),
        "position": _masked(body.position),
        "city": _masked(body.city),
        "question": _masked(body.question) or "",
    }
    audit_text = " ".join(str(v) for v in masked.values() if v)
    with db.transaction() as conn:
        audit = moderate(conn, audit_text)
        if not audit.ok:
            _moderate_or_raise(conn, audit_text)  # 抛 400（block / NEEDS_REWRITE）
        for key in ("company", "position", "city", "question"):
            if masked.get(key):
                masked[key] = mask_only(conn, masked[key])
        images_json = _validate_image_ids(conn, user["id"], body.image_ids, settings)
        post_id = _nid("p")
        now = _now()
        conn.execute(
            "INSERT INTO posts (id, user_id, report_id, company, position, city, question, anonymous,"
            " risk_overall, status, images, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, 'pending', ?, ?, ?)",
            (
                post_id,
                user["id"],
                body.report_id,
                masked["company"],
                masked["position"],
                masked["city"],
                masked["question"],
                1 if body.anonymous else 0,
                images_json,
                now,
                now,
            ),
        )
    return envelope(
        {
            "post_id": post_id,
            "status": "pending",
            "message": "已提交，审核通过后展示（先审后发）",
            "moderation": {"layer": audit.layer or "pass", "layer2": "local-stub"},
        },
        request,
    )


@router.get("/community/posts/{post_id}")
def post_detail(post_id: str, request: Request, user: dict = Depends(current_user)) -> dict:
    _require_enabled()
    with get_db().connect() as conn:
        row = conn.execute("SELECT * FROM posts WHERE id = ?", (post_id,)).fetchone()
        if row is None:
            raise not_found("帖子不存在")
        if row["status"] != "approved" and row["user_id"] != user["id"]:
            raise not_found("帖子不存在")
        vote = conn.execute("SELECT value FROM votes WHERE post_id = ? AND user_id = ?", (post_id, user["id"])).fetchone()
        experience_count = conn.execute(
            "SELECT COUNT(*) AS c FROM experiences WHERE post_id = ? AND status = 'approved'", (post_id,)
        ).fetchone()["c"]
    payload = _post_payload(row, vote["value"] if vote else None)
    payload["experience_count"] = int(experience_count)
    return envelope(payload, request)


@router.post("/community/posts/{post_id}/vote")
def vote(post_id: str, body: VoteRequest, request: Request, user: dict = Depends(current_user)) -> dict:
    """投票：一人一票可改；发帖人不能投自己；新号 24h 内禁投。

    D18 防刷：窗口期内同设备/同网段超阈值的票**照常收下**（用户无感、接口照常成功），
    但 `counted=0` 且记 `risk_reason`，公开展示与排序只统计 `counted=1` 的票。
    """
    settings = _require_enabled()
    _assert_not_new_account(user, settings, "投票")
    db = get_db()
    device_hash, ip_prefix = _vote_identity(request, user)
    with db.transaction() as conn:
        row = conn.execute("SELECT id, user_id, status FROM posts WHERE id = ?", (post_id,)).fetchone()
        if row is None or row["status"] != "approved":
            raise not_found("帖子不存在")
        if row["user_id"] == user["id"]:
            raise forbidden("不能给自己的帖子投票")
        if body.value == 0:
            conn.execute("DELETE FROM votes WHERE post_id = ? AND user_id = ?", (post_id, user["id"]))
        else:
            risk_reason = _vote_risk(conn, settings, device_hash, ip_prefix)
            counted = 0 if risk_reason else 1
            conn.execute(
                "INSERT INTO votes (post_id, user_id, value, reason, counted, risk_reason, device_hash, ip_prefix, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
                " ON CONFLICT(post_id, user_id) DO UPDATE SET value = excluded.value, reason = excluded.reason,"
                " counted = excluded.counted, risk_reason = excluded.risk_reason,"
                " device_hash = excluded.device_hash, ip_prefix = excluded.ip_prefix, created_at = excluded.created_at",
                (post_id, user["id"], body.value, body.reason, counted, risk_reason, device_hash, ip_prefix, _now()),
            )
        conn.execute(
            "UPDATE posts SET vote_up = (SELECT COUNT(*) FROM votes WHERE post_id = ? AND value = 1 AND counted = 1),"
            " vote_down = (SELECT COUNT(*) FROM votes WHERE post_id = ? AND value = -1 AND counted = 1),"
            " updated_at = ? WHERE id = ?",
            (post_id, post_id, _now(), post_id),
        )
        updated = conn.execute("SELECT vote_up, vote_down FROM posts WHERE id = ?", (post_id,)).fetchone()
    return envelope(
        {"post_id": post_id, "my_vote": body.value, "vote_up": updated["vote_up"], "vote_down": updated["vote_down"]},
        request,
    )


@router.post("/community/posts/{post_id}/experiences")
def create_experience(post_id: str, body: ExperienceCreate, request: Request, user: dict = Depends(current_user)) -> dict:
    settings = _require_enabled()
    _assert_not_new_account(user, settings, "补充经历")
    db = get_db()
    text, _ = mask_community_text(body.content)
    with db.transaction() as conn:
        row = conn.execute("SELECT id FROM posts WHERE id = ? AND status = 'approved'", (post_id,)).fetchone()
        if row is None:
            raise not_found("帖子不存在")
        stored = _moderate_or_raise(conn, text)
        exp_id = _nid("e")
        conn.execute(
            "INSERT INTO experiences (id, post_id, user_id, content, status, created_at) VALUES (?, ?, ?, ?, 'pending', ?)",
            (exp_id, post_id, user["id"], stored, _now()),
        )
    return envelope({"experience_id": exp_id, "status": "pending", "message": "审核通过后展示"}, request)


@router.get("/community/posts/{post_id}/experiences")
def list_experiences(post_id: str, request: Request, user: dict = Depends(current_user)) -> dict:
    _require_enabled()
    with get_db().connect() as conn:
        rows = conn.execute(
            "SELECT * FROM experiences WHERE post_id = ? AND status = 'approved' ORDER BY created_at ASC",
            (post_id,),
        ).fetchall()
    return envelope(
        {
            "items": [
                {
                    "experience_id": r["id"],
                    "content": r["content"],
                    "created_at": r["created_at"],
                    "is_mine": r["user_id"] == user["id"],
                }
                for r in rows
            ]
        },
        request,
    )


@router.post("/community/posts/{post_id}/report")
def report_post(post_id: str, body: PostReportCreate, request: Request, user: dict = Depends(current_user)) -> dict:
    """举报：同一人只能举报一次；满阈值先自动隐藏，再进人工复核队列（可恢复）。

    只统计「本轮举报」（created_at >= 上一轮复核时间），恢复后的帖子不会被旧举报立刻再压下去。
    """
    settings = _require_enabled()
    db = get_db()
    with db.transaction() as conn:
        row = conn.execute(
            "SELECT id, status, report_count, reviewed_at, needs_review FROM posts WHERE id = ?", (post_id,)
        ).fetchone()
        if row is None:
            raise not_found("帖子不存在")
        existing = conn.execute(
            "SELECT id FROM post_reports WHERE post_id = ? AND user_id = ?", (post_id, user["id"])
        ).fetchone()
        if existing:
            count = _round_report_count(conn, post_id, row["reviewed_at"])
            return envelope(
                {
                    "report_count": int(count),
                    "hidden": row["status"] == "hidden",
                    "needs_review": int(row["needs_review"] or 0) == 1,
                    "duplicated": True,
                },
                request,
            )
        now = _now()
        conn.execute(
            "INSERT INTO post_reports (id, post_id, user_id, reason, created_at) VALUES (?, ?, ?, ?, ?)",
            (_nid("r"), post_id, user["id"], body.reason, now),
        )
        count = _round_report_count(conn, post_id, row["reviewed_at"])
        hidden = count >= settings.community_report_hide_threshold
        if hidden:
            # 被举报隐藏 ≠ 违规：直接进人工复核队列，管理员确认违规才留隐藏，误报可 restore。
            # 人工隐藏（hidden_reason='manual'）的帖子不因为再多几条举报就变成可恢复。
            conn.execute(
                "UPDATE posts SET report_count = ?, status = 'hidden', needs_review = 1,"
                " hidden_reason = CASE WHEN hidden_reason = 'manual' THEN 'manual' ELSE 'reported' END,"
                " updated_at = ? WHERE id = ?",
                (int(count), now, post_id),
            )
        else:
            conn.execute(
                "UPDATE posts SET report_count = ?, updated_at = ? WHERE id = ?",
                (int(count), now, post_id),
            )
    return envelope(
        {"report_count": int(count), "hidden": hidden, "needs_review": hidden, "duplicated": False},
        request,
    )


@router.post("/community/appeals")
def create_appeal(body: AppealCreate, request: Request, user: dict = Depends(current_user)) -> dict:
    """企业申诉：任何人（含企业）都能提，24h 内答复（§8）。"""
    settings = _require_enabled()
    content = _masked(body.content) or ""
    db = get_db()
    with db.transaction() as conn:
        content = _moderate_or_raise(conn, content)
        appeal_id = _nid("a")
        conn.execute(
            "INSERT INTO appeals (id, post_id, company, contact, content, status, sla_hours, created_at)"
            " VALUES (?, ?, ?, ?, ?, 'open', ?, ?)",
            (
                appeal_id,
                body.post_id,
                _masked(body.company),
                _masked(body.contact),
                content,
                settings.community_appeal_sla_hours,
                _now(),
            ),
        )
    return envelope(
        {
            "appeal_id": appeal_id,
            "status": "open",
            "sla_hours": settings.community_appeal_sla_hours,
            "message": f"已受理，{settings.community_appeal_sla_hours} 小时内答复",
        },
        request,
    )


# ---------------------------------------------------------------- 后台
def _reviewer(payload: dict | None) -> str:
    """审核人：后台令牌没有具体账号，允许 body 里带 operator 记录，默认 admin。"""
    if isinstance(payload, dict) and payload.get("operator"):
        return str(payload["operator"])[:40]
    return "admin"


def _round_report_count(conn, post_id: str, reviewed_at: str | None) -> int:
    """本轮举报数：只看上一轮复核之后新增的举报，恢复后的帖子不被旧举报重新压下去。"""
    if reviewed_at:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM post_reports WHERE post_id = ? AND created_at >= ?", (post_id, reviewed_at)
        ).fetchone()
    else:
        row = conn.execute("SELECT COUNT(*) AS c FROM post_reports WHERE post_id = ?", (post_id,)).fetchone()
    return int(row["c"])


def _report_detail(conn, post_id: str) -> list[dict]:
    """举报明细：恢复后仍然保留，用来识别恶意举报。"""
    rows = conn.execute(
        "SELECT user_id, reason, created_at FROM post_reports WHERE post_id = ? ORDER BY created_at ASC", (post_id,)
    ).fetchall()
    return [{"user_id": r["user_id"], "reason": r["reason"], "created_at": r["created_at"]} for r in rows]


def _review_post(conn, post_id: str, action: str, payload: dict | None = None) -> dict:
    allowed = ("approve", "reject", "hide", "restore")
    if action not in allowed:
        raise validation_error("action 必须是 approve/reject/hide/restore")
    db = get_db()
    now = _now()
    operator = _reviewer(payload)
    reason = str((payload or {}).get("reason") or "")[:200] or None
    with db.transaction() as conn2:
        row = conn2.execute(
            "SELECT id, status, hidden_reason, needs_review FROM posts WHERE id = ?", (post_id,)
        ).fetchone()
        if row is None:
            raise not_found("帖子不存在")
        if action == "restore":
            # 只有「被举报隐藏 + 在复核队列里」的帖子能恢复；人工隐藏/驳回的帖子不能绕过审核恢复
            if row["status"] != "hidden" or row["hidden_reason"] != "reported":
                raise validation_error("只有被举报隐藏的帖子可以恢复")
            if int(row["needs_review"] or 0) != 1:
                raise validation_error("该帖子不在复核队列中")
            commit = (
                "UPDATE posts SET status = 'approved', needs_review = 0, hidden_reason = NULL,"
                " review_round = review_round + 1, reviewed_by = ?, reviewed_at = ?,"
                " reject_reason = ?, updated_at = ? WHERE id = ?"
            )
            params = (operator, now, reason, now, post_id)
            new_status = "approved"
        elif action == "hide":
            # 复核维持隐藏：不再挂在复核队列里，标记为人工隐藏；举报明细保留
            commit = (
                "UPDATE posts SET status = 'hidden', needs_review = 0, hidden_reason = 'manual',"
                " reviewed_by = ?, reviewed_at = ?, reject_reason = ?, updated_at = ? WHERE id = ?"
            )
            params = (operator, now, reason, now, post_id)
            new_status = "hidden"
        else:
            new_status = {"approve": "approved", "reject": "rejected"}[action]
            commit = (
                "UPDATE posts SET status = ?, needs_review = 0, hidden_reason = NULL,"
                " reviewed_by = ?, reviewed_at = ?, reject_reason = ?, updated_at = ? WHERE id = ?"
            )
            params = (new_status, operator, now, reason, now, post_id)
        conn2.execute(commit, params)
    return {
        "post_id": post_id,
        "status": new_status,
        "reviewed_by": operator,
        "reviewed_at": now,
        "reason": reason,
    }


@admin_router.get("/admin/community/review-queue")
def admin_review_queue(request: Request, limit: int = Query(default=50, ge=1, le=200)) -> dict:
    """被举报自动隐藏的帖子：单独排一个复核队列，逐条确认是违规还是被恶意举报。"""
    with get_db().connect() as conn:
        rows = conn.execute(
            "SELECT * FROM posts WHERE status = 'hidden' AND needs_review = 1"
            " ORDER BY updated_at ASC LIMIT ?",
            (limit,),
        ).fetchall()
        items = []
        for row in rows:
            payload = _post_payload(row)
            payload["reviewed_by"] = row["reviewed_by"]
            payload["reviewed_at"] = row["reviewed_at"]
            payload["hidden_reason"] = row["hidden_reason"]
            payload["needs_review"] = 1
            payload["report_count"] = _round_report_count(conn, row["id"], row["reviewed_at"])
            payload["reports"] = _report_detail(conn, row["id"])
            items.append(payload)
    return envelope({"items": items, "total": len(items)}, request)


@admin_router.post("/admin/community/posts/{post_id}/restore")
def admin_restore_post(post_id: str, request: Request, payload: dict = Body(default={})) -> dict:
    """复核结论「举报不成立」：hidden → approved，保留举报计数与明细，方便识别人恶意举报。"""
    return envelope(_review_post(None, post_id, "restore", payload), request)


@admin_router.post("/admin/community/posts/{post_id}/hide")
def admin_hide_post(post_id: str, request: Request, payload: dict = Body(default={})) -> dict:
    """复核结论「确实违规」或管理员直接隐藏：hidden，记处理人与理由。"""
    return envelope(_review_post(None, post_id, "hide", payload), request)


@admin_router.get("/admin/community/posts")
def admin_list_posts(
    request: Request,
    status: str = Query(default="pending"),
    queue: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict:
    """后台审核列表（先审后发）：status=pending/approved/rejected/hidden/needs_review。

    needs_review（或 queue=report）= 被举报自动隐藏、等人工复核的那一队。
    """
    if queue in ("report", "needs_review"):
        status = "needs_review"
    if status == "needs_review":
        cond, params = "status = 'hidden' AND needs_review = 1", []
    else:
        cond, params = "status = ?", [status]
    with get_db().connect() as conn:
        rows = conn.execute(
            f"SELECT * FROM posts WHERE {cond} ORDER BY updated_at ASC LIMIT ?", (*params, limit)
        ).fetchall()
        items = []
        for row in rows:
            payload = _post_payload(row)
            payload["reviewed_by"] = row["reviewed_by"]
            payload["reviewed_at"] = row["reviewed_at"]
            payload["reject_reason"] = row["reject_reason"]
            payload["needs_review"] = int(row["needs_review"] or 0)
            payload["hidden_reason"] = row["hidden_reason"]
            if status == "needs_review":
                payload["report_count"] = _round_report_count(conn, row["id"], row["reviewed_at"])
                payload["reports"] = _report_detail(conn, row["id"])
            items.append(payload)
    return envelope({"items": items, "total": len(items)}, request)


@admin_router.post("/admin/community/posts/{post_id}/approve")
def admin_approve_post(post_id: str, request: Request, payload: dict = Body(default={})) -> dict:
    """D-08：审核通过（pending → approved）。"""
    return envelope(_review_post(None, post_id, "approve", payload), request)


@admin_router.post("/admin/community/posts/{post_id}/reject")
def admin_reject_post(post_id: str, request: Request, payload: dict = Body(default={})) -> dict:
    """D-08：审核驳回（pending → rejected），可带 reason。"""
    return envelope(_review_post(None, post_id, "reject", payload), request)


@admin_router.post("/admin/community/posts/{post_id}/review")
def admin_review_post(post_id: str, request: Request, payload: dict = Body(...)) -> dict:
    """兼容入口：{action: approve|reject|hide}。"""
    return envelope(_review_post(None, post_id, str(payload.get("action", "")).strip(), payload), request)


@admin_router.get("/admin/community/experiences")
def admin_list_experiences(request: Request, status: str = Query(default="pending"), limit: int = Query(default=50, ge=1, le=200)) -> dict:
    with get_db().connect() as conn:
        rows = conn.execute(
            "SELECT * FROM experiences WHERE status = ? ORDER BY created_at ASC LIMIT ?", (status, limit)
        ).fetchall()
    return envelope(
        {
            "items": [
                {
                    "experience_id": r["id"],
                    "post_id": r["post_id"],
                    "content": r["content"],
                    "status": r["status"],
                    "reviewed_by": r["reviewed_by"],
                    "reviewed_at": r["reviewed_at"],
                    "created_at": r["created_at"],
                }
                for r in rows
            ],
            "total": len(rows),
        },
        request,
    )


def _review_experience(experience_id: str, action: str, payload: dict | None = None) -> dict:
    if action not in ("approve", "reject"):
        raise validation_error("action 必须是 approve/reject")
    new_status = "approved" if action == "approve" else "rejected"
    with get_db().transaction() as conn:
        row = conn.execute("SELECT id FROM experiences WHERE id = ?", (experience_id,)).fetchone()
        if row is None:
            raise not_found("经历不存在")
        conn.execute(
            "UPDATE experiences SET status = ?, reviewed_by = ?, reviewed_at = ? WHERE id = ?",
            (new_status, _reviewer(payload), _now(), experience_id),
        )
    return {"experience_id": experience_id, "status": new_status, "reviewed_by": _reviewer(payload), "reviewed_at": _now()}


@admin_router.post("/admin/community/experiences/{experience_id}/approve")
def admin_approve_experience(experience_id: str, request: Request, payload: dict = Body(default={})) -> dict:
    return envelope(_review_experience(experience_id, "approve", payload), request)


@admin_router.post("/admin/community/experiences/{experience_id}/reject")
def admin_reject_experience(experience_id: str, request: Request, payload: dict = Body(default={})) -> dict:
    return envelope(_review_experience(experience_id, "reject", payload), request)


@admin_router.get("/admin/community/votes")
def admin_list_votes(
    request: Request,
    counted: int | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict:
    """后台查票（D18）：counted=0 即可疑票；只返回设备号哈希与网段摘要，不返回明文。"""
    where = ""
    args: list = []
    if counted is not None:
        where = "WHERE v.counted = ?"
        args.append(counted)
    args.append(limit)
    with get_db().connect() as conn:
        rows = conn.execute(
            "SELECT v.id, v.post_id, v.user_id, v.value, v.counted, v.risk_reason, v.device_hash, v.ip_prefix,"
            " v.created_at, p.status AS post_status FROM votes v LEFT JOIN posts p ON p.id = v.post_id "
            + where
            + " ORDER BY v.created_at DESC LIMIT ?",
            args,
        ).fetchall()
        total = conn.execute(
            "SELECT COUNT(*) AS c FROM votes v " + where, args[:-1]
        ).fetchone()["c"]
    return envelope(
        {
            "total": int(total),
            "items": [
                {
                    "vote_id": r["id"],
                    "post_id": r["post_id"],
                    "user_id": r["user_id"],
                    "value": r["value"],
                    "counted": r["counted"],
                    "risk_reason": r["risk_reason"],
                    "device_digest": (r["device_hash"] or "")[:12],
                    "ip_prefix": r["ip_prefix"],
                    "post_status": r["post_status"],
                    "created_at": r["created_at"],
                }
                for r in rows
            ],
        },
        request,
    )


@admin_router.get("/admin/sensitive-words")
def list_sensitive_words(request: Request) -> dict:
    with get_db().connect() as conn:
        rows = conn.execute(
            "SELECT word, level, kind, prompt, as_type, category, created_at FROM sensitive_words ORDER BY id"
        ).fetchall()
    return envelope({"total": len(rows), "items": [dict(r) for r in rows]}, request)


@admin_router.put("/admin/sensitive-words")
def replace_sensitive_words(request: Request, payload: dict = Body(...)) -> dict:
    words = payload.get("words")
    if not isinstance(words, list) or not words:
        raise validation_error("words 必须是非空数组，格式 [{word, level, kind?, prompt?, as_type?}]")
    import re as _re

    normalized = []
    for item in words:
        if isinstance(item, str):
            item = {"word": item}
        if not isinstance(item, dict) or not item.get("word"):
            raise validation_error("words 每项必须是字符串或 {word, level}")
        word = str(item["word"]).strip()
        level = str(item.get("level", "block"))
        kind = str(item.get("kind", "word"))
        if level not in ("block", "review", "mask"):
            raise validation_error(f"level 只能是 block/review/mask：{word}")
        if kind not in ("word", "regex"):
            raise validation_error(f"kind 只能是 word/regex：{word}")
        if kind == "regex":
            try:
                _re.compile(word)
            except _re.error as exc:
                raise validation_error(f"正则无法编译：{word}（{exc}）") from exc
        normalized.append((word, level, kind, str(item.get("prompt") or ""), str(item.get("as_type") or item.get("as") or "")))
    with get_db().transaction() as conn:
        conn.execute("DELETE FROM sensitive_words")
        for word, level, kind, prompt, as_type in normalized:
            conn.execute(
                "INSERT INTO sensitive_words (word, level, kind, prompt, as_type, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (word, level, kind, prompt, as_type, _now()),
            )
    return envelope(
        {
            "total": len(normalized),
            "items": [{"word": w, "level": lv, "kind": k} for w, lv, k, _, _ in normalized],
            "notice": "已热更新，下一次请求立即生效（无需重启）",
        },
        request,
    )
