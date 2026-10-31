"""请求体模型（§5.4 接口清单）。响应结构在 docs/04-后端接口契约.md 里逐字段写死。"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    platform: Literal["toutiao", "weixin"] = "toutiao"
    code: str = Field(min_length=1, max_length=256, description="平台登录 code（wx.login / tt.login 拿到）")


class AdRewardRequest(BaseModel):
    request_id: str = Field(min_length=8, max_length=64, description="客户端生成的唯一请求号，用于幂等")
    ad_unit_id: str = Field(default="", max_length=64)
    result: Literal["completed", "no_fill", "error"] = "completed"


class OrderCreateRequest(BaseModel):
    plan: Literal["week", "month", "quarter"] = "month"
    channel: Literal["toutiao", "weixin"] = "toutiao"


class PayNotifyRequest(BaseModel):
    order_id: str = Field(min_length=1, max_length=64)
    platform_order_id: str = Field(min_length=1, max_length=128)
    amount_fen: int = Field(ge=0)
    status: Literal["paid", "failed", "refunded"] = "paid"
    signature: str = Field(min_length=1, max_length=256)


class FeedbackRequest(BaseModel):
    report_id: str | None = None
    type: Literal["inaccurate", "appeal", "suggestion"] = "inaccurate"
    content: str = Field(min_length=1, max_length=1000)
