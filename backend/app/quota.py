"""额度流水（§6.1、§5.3）。

唯一事实来源是 quota_ledger：余额 = SUM(delta)，任何地方都不许直接改余额字段。
两阶段扣费：
  analysis_hold  -1  （预扣，进分析）
  analysis_mark   0  （分析成功，标记正式扣除）
  analysis_refund +1 （分析失败，退回）
广告奖励：ad_reward +1，幂等键 ad:{request_id}；每日上限由 ad_rewards 计数控制。
注册赠送：register_bonus +3，幂等键 user:{id}:register。
"""
from __future__ import annotations

import datetime as dt
import sqlite3

from .errors import quota_exhausted


def _now() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _today() -> str:
    return dt.date.today().isoformat()


def balance(conn: sqlite3.Connection, user_id: str) -> int:
    row = conn.execute("SELECT COALESCE(SUM(delta), 0) AS b FROM quota_ledger WHERE user_id = ?", (user_id,)).fetchone()
    return int(row["b"])


def append(
    conn: sqlite3.Connection,
    user_id: str,
    delta: int,
    reason: str,
    ref: str | None = None,
    idem_key: str | None = None,
) -> None:
    conn.execute(
        "INSERT INTO quota_ledger (user_id, delta, reason, ref, idem_key, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, delta, reason, ref, idem_key, _now()),
    )


def has_idem(conn: sqlite3.Connection, idem_key: str) -> bool:
    row = conn.execute("SELECT 1 FROM quota_ledger WHERE idem_key = ?", (idem_key,)).fetchone()
    return row is not None


def grant_register_bonus(conn: sqlite3.Connection, user_id: str, amount: int) -> bool:
    key = f"user:{user_id}:register"
    if has_idem(conn, key):
        return False
    append(conn, user_id, amount, "register_bonus", ref=user_id, idem_key=key)
    return True


def hold_for_analysis(conn: sqlite3.Connection, user_id: str, task_id: str) -> int:
    """预扣 1 次；余额不足抛 QUOTA_EXHAUSTED。返回预扣后余额。"""
    current = balance(conn, user_id)
    if current < 1:
        raise quota_exhausted(current)
    append(conn, user_id, -1, "analysis_hold", ref=task_id, idem_key=f"task:{task_id}:hold")
    return current - 1


def refund_for_analysis(conn: sqlite3.Connection, user_id: str, task_id: str) -> bool:
    key = f"task:{task_id}:refund"
    if has_idem(conn, key):
        return False
    append(conn, user_id, 1, "analysis_refund", ref=task_id, idem_key=key)
    return True


def mark_analysis_consumed(conn: sqlite3.Connection, user_id: str, task_id: str) -> bool:
    key = f"task:{task_id}:mark"
    if has_idem(conn, key):
        return False
    append(conn, user_id, 0, "analysis_mark", ref=task_id, idem_key=key)
    return True


def today_ad_count(conn: sqlite3.Connection, user_id: str, day: str | None = None) -> int:
    row = conn.execute(
        "SELECT COUNT(*) AS c FROM ad_rewards WHERE user_id = ? AND reward_day = ? AND granted = 1",
        (user_id, day or _today()),
    ).fetchone()
    return int(row["c"])


def grant_ad_reward(conn: sqlite3.Connection, user_id: str, request_id: str, ad_unit_id: str, result: str, daily_cap: int) -> dict:
    """广告奖励（§6.2）：广告拉不出来（no_fill）也必须直接给奖励。

    幂等：同一 request_id 重复调用返回第一次的结果，不重复发放。
    """
    existing = conn.execute(
        "SELECT * FROM ad_rewards WHERE request_id = ?", (request_id,)
    ).fetchone()
    if existing:
        return {
            "granted": bool(existing["granted"]),
            "replayed": True,
            "reason": "duplicate_request_id",
            "today_count": today_ad_count(conn, user_id),
        }

    today = _today()
    count = today_ad_count(conn, user_id, today)
    reason = "reward"
    granted = False
    if count >= daily_cap:
        reason = "daily_cap_reached"
    else:
        append(conn, user_id, 1, "ad_reward", ref=request_id, idem_key=f"ad:{request_id}")
        granted = True
        count += 1

    conn.execute(
        "INSERT INTO ad_rewards (user_id, ad_unit_id, request_id, result, granted, reward_day, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (user_id, ad_unit_id, request_id, result, int(granted), today, _now()),
    )
    return {"granted": granted, "replayed": False, "reason": reason, "today_count": count}


def reconcile(conn: sqlite3.Connection) -> dict:
    """额度对账：按 reason 汇总，检查是否有负数余额用户、孤立的预扣（没有 mark/refund）。"""
    by_reason = {
        row["reason"]: {"count": row["c"], "delta_sum": int(row["s"] or 0)}
        for row in conn.execute(
            "SELECT reason, COUNT(*) AS c, SUM(delta) AS s FROM quota_ledger GROUP BY reason ORDER BY reason"
        )
    }
    negative_users = [
        row["user_id"]
        for row in conn.execute(
            "SELECT user_id FROM quota_ledger GROUP BY user_id HAVING SUM(delta) < 0"
        )
    ]
    orphan_holds = [
        row["ref"]
        for row in conn.execute(
            """
            SELECT h.ref FROM quota_ledger h
            WHERE h.reason = 'analysis_hold'
              AND NOT EXISTS (SELECT 1 FROM quota_ledger m WHERE m.idem_key = 'task:' || h.ref || ':mark')
              AND NOT EXISTS (SELECT 1 FROM quota_ledger r WHERE r.idem_key = 'task:' || h.ref || ':refund')
            """
        )
    ]
    total_users = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
    return {
        "users": int(total_users),
        "by_reason": by_reason,
        "negative_balance_users": negative_users,
        "orphan_holds": orphan_holds,
        "balanced": not negative_users and not orphan_holds,
    }
