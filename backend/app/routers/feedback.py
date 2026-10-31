"""反馈与申诉（§5.4：POST /feedback；§8 申诉入口）。"""
from __future__ import annotations

import datetime as dt
import uuid

from fastapi import APIRouter, Depends, Request

from ..deps import current_user, envelope, get_db
from ..models import FeedbackRequest

router = APIRouter(tags=["反馈/申诉"])

_TYPE_NAMES = {"inaccurate": "判断不准", "appeal": "申诉", "suggestion": "建议"}


@router.post("/feedback")
def create_feedback(body: FeedbackRequest, request: Request, user: dict = Depends(current_user)) -> dict:
    """判断不准 / 申诉 / 建议。申诉承诺 7 个工作日内答复（§8），状态进后台复核池。"""
    feedback_id = "f_" + uuid.uuid4().hex[:12]
    created_at = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_db().transaction() as conn:
        conn.execute(
            "INSERT INTO feedback (id, user_id, report_id, type, content, status, created_at)"
            " VALUES (?, ?, ?, ?, ?, 'open', ?)",
            (feedback_id, user["id"], body.report_id, body.type, body.content.strip(), created_at),
        )
    return envelope(
        {
            "feedback_id": feedback_id,
            "type": body.type,
            "type_name": _TYPE_NAMES.get(body.type, body.type),
            "status": "open",
            "expect_reply_within_days": 7,
            "created_at": created_at,
        },
        request,
    )
