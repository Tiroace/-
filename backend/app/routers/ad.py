"""激励视频奖励（§5.4：POST /ad/reward；§6.2 硬性规范）。

- 用户主动点、广告确实播完才请求；请求号 request_id 幂等，重复提交不重复发放；
- 广告拉不出来（no_fill / error）也必须直接给奖励，这是平台强制要求；
- 每日上限 5 次（后台可调），服务端计数，防刷。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ..config import get_settings
from ..deps import current_user, envelope, get_db
from ..models import AdRewardRequest
from ..quota import balance, grant_ad_reward, today_ad_count

router = APIRouter(tags=["激励视频"])


@router.post("/ad/reward")
def ad_reward(body: AdRewardRequest, request: Request, user: dict = Depends(current_user)) -> dict:
    settings = get_settings()
    db = get_db(settings)
    with db.transaction() as conn:
        result = grant_ad_reward(
            conn,
            user["id"],
            request_id=body.request_id,
            ad_unit_id=body.ad_unit_id,
            result=body.result,
            daily_cap=settings.ad_daily_cap,
        )
        current_balance = balance(conn, user["id"])
        today = today_ad_count(conn, user["id"])

    return envelope(
        {
            "granted": result["granted"],
            "replayed": result["replayed"],
            "reason": result["reason"],
            "quota": {"balance": current_balance},
            "today_count": today,
            "daily_cap": settings.ad_daily_cap,
            "remaining_today": max(0, settings.ad_daily_cap - today),
        },
        request,
    )
