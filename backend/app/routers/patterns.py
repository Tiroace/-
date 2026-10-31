"""套路库接口（R1：首页「最近常见」Top3 + 套路列表）。"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from fastapi import APIRouter, Depends, Query, Request

from ..config import get_settings
from ..deps import current_user, envelope, get_db

router = APIRouter(tags=["套路库"])

_LEVEL_ORDER = {"red": 0, "amber": 1, "green": 2}


def _row_payload(row) -> dict:
    return {
        "pattern_id": row["id"],
        "name": row["name"],
        "dimension": row["dimension"],
        "level": row["level"],
        "why": row["why"],
        "how": row["how"],
        "hits_7d": row["hits_7d"] if "hits_7d" in row.keys() else 0,
    }


def _query(conn, limit: int, dimension: str | None, since: str | None):
    sql = (
        "SELECT p.*, COALESCE(SUM(CASE WHEN h.hit_at >= ? THEN 1 ELSE 0 END), 0) AS hits_7d"
        " FROM patterns p LEFT JOIN pattern_hits h ON h.pattern_id = p.id"
        " WHERE p.status = 'active'"
    )
    args: list = [since or "0000-00-00 00:00:00"]
    if dimension:
        sql += " AND p.dimension = ?"
        args.append(dimension)
    sql += " GROUP BY p.id ORDER BY hits_7d DESC, p.id LIMIT ?"
    args.append(limit)
    return conn.execute(sql, args).fetchall()


@router.get("/patterns")
def list_patterns(
    request: Request,
    user: dict = Depends(current_user),
    dimension: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
) -> dict:
    """套路列表（运营可增删；只描述话术，不含公司名）。"""
    with get_db(get_settings()).connect() as conn:
        rows = _query(conn, limit, dimension, None)
        total = conn.execute("SELECT COUNT(*) AS c FROM patterns WHERE status = 'active'").fetchone()["c"]
    version = ""
    path = get_settings().project_root / "rules" / "patterns_v1.json"
    if path.is_file():
        version = str(json.loads(path.read_text(encoding="utf-8")).get("version", ""))
    return envelope({"total": int(total), "items": [_row_payload(row) for row in rows], "version": version}, request)


@router.get("/patterns/recent")
def recent_patterns(request: Request, user: dict = Depends(current_user), limit: int = Query(default=3, ge=1, le=10)) -> dict:
    """最近常见的套路 TopN：默认近 7 天 pattern_hits 真实命中次数排序，没有命中时按等级兜底。"""
    since = (dt.datetime.now() - dt.timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
    with get_db(get_settings()).connect() as conn:
        rows = _query(conn, limit, None, since)
    items = []
    for rank, row in enumerate(rows):
        payload = _row_payload(row)
        payload["rank"] = rank + 1
        items.append(payload)
    return envelope({"window_days": 7, "items": items}, request)
