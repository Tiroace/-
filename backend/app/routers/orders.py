"""会员订单与支付回调（§5.4：POST /orders、POST /pay/notify；§6.3）。

要点：
- 金额、套餐、有效期一律服务端按配置算，不信客户端传的价格；
- 回调必须验签，否则任何人伪造一次回调就能白拿会员；
- 按 platform_order_id 幂等：平台会重复推送回调，重复推送不得重复发货；
- 会员只改「每日上限」，不发额度流水（§6.1）。
"""
from __future__ import annotations

import datetime as dt
import uuid

from fastapi import APIRouter, Depends, Request

from ..config import get_settings
from ..deps import current_user, envelope, get_db
from ..errors import AppError, validation_error
from ..models import OrderCreateRequest, PayNotifyRequest
from ..platform import PlatformError, get_adapter

router = APIRouter(tags=["订单/支付"])


def _now() -> dt.datetime:
    return dt.datetime.now()


def _fmt(value: dt.datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S")


PLAN_NAMES = {"week": "周卡", "month": "月卡", "quarter": "季卡"}
PLAN_BENEFITS = ["每日检测次数上限 20 次", "历史报告保存 30 天", "不含免广告（平台红线）"]


@router.get("/plans")
def list_plans(request: Request, user: dict = Depends(current_user)) -> dict:
    """只读定价表（D9 补）。前端不要写死价格常量，一律以这里为准。"""
    settings = get_settings()
    plans = [
        {
            "plan": plan,
            "name": PLAN_NAMES.get(plan, plan),
            "amount_fen": amount,
            "days": settings.plan_days.get(plan, 0),
            "benefits": PLAN_BENEFITS,
            "available_ios": False,      # iOS 需平台虚拟支付，未接入前不展示（§6.3）
            "available_android": True,
        }
        for plan, amount in settings.prices_fen.items()
    ]
    return envelope(
        {
            "currency": "CNY",
            "plans": plans,
            "max_single_order_fen": settings.max_order_amount_fen,
            "notice": "价格待老板拍板，当前为 §11 建议值；iOS 端在虚拟支付接入前隐藏会员入口",
        },
        request,
    )


@router.post("/orders")
def create_order(body: OrderCreateRequest, request: Request, user: dict = Depends(current_user)) -> dict:
    settings = get_settings()
    amount = settings.prices_fen.get(body.plan)
    if amount is None:
        raise validation_error(f"未知套餐：{body.plan}")
    if amount > settings.max_order_amount_fen:      # 风控：单笔不得超过 300 元
        raise AppError(
            "ORDER_AMOUNT_EXCEEDED",
            f"单笔订单不能超过 {settings.max_order_amount_fen / 100:.0f} 元",
            400,
            {"amount_fen": amount, "max_fen": settings.max_order_amount_fen},
        )
    order_id = "o_" + uuid.uuid4().hex[:16]
    with get_db(settings).transaction() as conn:
        conn.execute(
            "INSERT INTO orders (id, user_id, plan, amount_fen, channel, status, created_at) VALUES (?, ?, ?, ?, ?, 'pending', ?)",
            (order_id, user["id"], body.plan, amount, body.channel, _fmt(_now())),
        )
    # 走平台适配层：真实支付未接入时返回 mock 参数（mock: true），前端不得据此发货
    adapter = get_adapter(body.channel, settings)
    pay_params = adapter.build_pay_params({"order_id": order_id, "amount_fen": amount})
    return envelope(
        {
            "order_id": order_id,
            "plan": body.plan,
            "amount_fen": amount,
            "channel": body.channel,
            "status": "pending",
            "pay_params": pay_params,
            "notice": "原型期未接真实支付，此参数不可用于发起真实扣款",
        },
        request,
    )


@router.post("/pay/notify")
def pay_notify(body: PayNotifyRequest, request: Request) -> dict:
    """支付平台回调。验签 → 幂等 → 发货。"""
    settings = get_settings()
    db = get_db(settings)
    with db.transaction() as conn:
        order = conn.execute("SELECT * FROM orders WHERE id = ?", (body.order_id,)).fetchone()
        if order is None:
            raise AppError("ORDER_NOT_FOUND", "订单不存在", 404)

        # 验签走平台适配层（Mock 模式按 HMAC；真实平台接入后换平台签名算法）
        adapter = get_adapter(order["channel"], settings)
        fields = {
            "order_id": body.order_id,
            "platform_order_id": body.platform_order_id,
            "amount_fen": str(body.amount_fen),
            "status": body.status,
            "signature": body.signature,
        }
        try:
            verified = adapter.verify_notify(fields)
        except PlatformError as exc:
            raise AppError("SIGNATURE_INVALID", f"回调验签失败：{exc}", 401) from exc
        if not verified:
            raise AppError("SIGNATURE_INVALID", "回调验签失败", 401)
        if body.amount_fen != order["amount_fen"]:
            raise AppError(
                "AMOUNT_MISMATCH",
                "回调金额与订单金额不一致",
                400,
                {"order_amount_fen": order["amount_fen"], "notify_amount_fen": body.amount_fen},
            )

        # 幂等：同一平台单号重复推送，直接返回已发货结果
        if order["status"] == "paid":
            if order["platform_order_id"] == body.platform_order_id:
                return envelope({"order_id": order["id"], "status": "paid", "replayed": True}, request)
            raise AppError("IDEMPOTENCY_CONFLICT", "订单已由其他平台单号支付", 409)

        other = conn.execute(
            "SELECT id FROM orders WHERE platform_order_id = ?", (body.platform_order_id,)
        ).fetchone()
        if other is not None:
            raise AppError("IDEMPOTENCY_CONFLICT", "平台单号已用于其他订单", 409)

        if body.status != "paid":
            conn.execute(
                "UPDATE orders SET status = ?, platform_order_id = ? WHERE id = ?",
                ("failed" if body.status == "failed" else "refunded", body.platform_order_id, order["id"]),
            )
            return envelope({"order_id": order["id"], "status": body.status, "replayed": False}, request)

        # 发货：更新订单 + 延长会员（从「现在」和「现有到期时间」的较大值起算）
        conn.execute(
            "UPDATE orders SET status = 'paid', platform_order_id = ?, paid_at = ? WHERE id = ?",
            (body.platform_order_id, _fmt(_now()), order["id"]),
        )
        days = settings.plan_days.get(order["plan"], 30)
        existing = conn.execute("SELECT * FROM memberships WHERE user_id = ?", (order["user_id"],)).fetchone()
        base = _now()
        if existing is not None:
            try:
                existing_expiry = dt.datetime.strptime(existing["expires_at"], "%Y-%m-%d %H:%M:%S")
                base = max(base, existing_expiry)
            except ValueError:
                pass
        expires_at = base + dt.timedelta(days=days)
        conn.execute(
            "INSERT INTO memberships (user_id, plan, expires_at, updated_at) VALUES (?, ?, ?, ?)"
            " ON CONFLICT(user_id) DO UPDATE SET plan = excluded.plan, expires_at = excluded.expires_at, updated_at = excluded.updated_at",
            (order["user_id"], order["plan"], _fmt(expires_at), _fmt(_now())),
        )
        result = {
            "order_id": order["id"],
            "status": "paid",
            "replayed": False,
            "membership": {"plan": order["plan"], "expires_at": _fmt(expires_at)},
        }
    return envelope(result, request)
