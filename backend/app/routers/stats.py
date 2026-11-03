"""匿名统计接口（老板 2026-11-04 定）。

POST /stats/pattern   上报一次检查的结论（匿名）
GET  /stats/patterns/top   按周统计 Top N（首页「最近常见的」）

隐私底线：
- **不接收**文字、截图、用户身份（不用 current_user，不收设备号/openid/IP 落库）；
- 只记 overall、scheme_id、命中的 pattern_id 列表和时间；
- 校验严格：overall 只允许 red/amber/green，pattern_id 必须在套路库里，
  不认识的一律丢弃——不让客户端往统计里灌脏数据。
"""
from __future__ import annotations

import datetime as dt
import json

from fastapi import APIRouter, Query, Request

from ..config import get_settings
from ..deps import envelope, get_db
from ..errors import validation_error

router = APIRouter(tags=["统计"])

ALLOWED_OVERALL = ("red", "amber", "green")
MAX_PATTERNS = 12


def _known_ids() -> set[str]:
    path = get_settings().project_root / "rules" / "patterns_v1.json"
    if not path.is_file():
        return set()
    data = json.loads(path.read_text(encoding="utf-8"))
    return {p["pattern_id"] for p in (data.get("patterns") or [])}


def _known_schemes() -> set[str]:
    path = get_settings().project_root / "rules" / "patterns_v1.json"
    if not path.is_file():
        return set()
    data = json.loads(path.read_text(encoding="utf-8"))
    return {s["scheme_id"] for s in (data.get("schemes") or [])}


@router.post("/stats/pattern")
async def report_pattern_stats(request: Request) -> dict:
    """匿名上报：只要结论与套路编号，不要任何可识别信息。"""
    try:
        body = await request.json()
    except Exception as exc:  # noqa: BLE001
        raise validation_error("请求体必须是 JSON") from exc
    if not isinstance(body, dict):
        raise validation_error("请求体必须是 JSON 对象")

    overall = str(body.get("overall") or "").strip().lower()
    if overall not in ALLOWED_OVERALL:
        raise validation_error("overall 必须是 red/amber/green 之一")

    known = _known_ids()
    raw_ids = body.get("pattern_ids") or []
    if not isinstance(raw_ids, list):
        raise validation_error("pattern_ids 必须是数组")
    ids = [str(x) for x in raw_ids if str(x) in known][:MAX_PATTERNS]

    scheme_id = str(body.get("scheme_id") or "").strip()
    if scheme_id and scheme_id not in _known_schemes():
        scheme_id = ""

    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_db(get_settings()).transaction() as conn:
        conn.execute(
            "INSERT INTO check_stats (overall, scheme_id, patterns, created_at) VALUES (?, ?, ?, ?)",
            (overall, scheme_id or None, json.dumps(ids, ensure_ascii=False), now),
        )
    return envelope({"ok": True, "recorded": True}, request)


@router.get("/stats/patterns/top")
def top_patterns(request: Request, days: int = Query(default=7, ge=1, le=30), limit: int = Query(default=5, ge=1, le=10)) -> dict:
    """近 N 天命中次数 TopN（首页「最近常见的」）。只返回套路本身，不含任何公司名。"""
    since = (dt.datetime.now() - dt.timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    with get_db(get_settings()).connect() as conn:
        rows = conn.execute(
            "SELECT patterns FROM check_stats WHERE created_at >= ?", (since,)
        ).fetchall()
        total = conn.execute("SELECT COUNT(*) AS c FROM check_stats WHERE created_at >= ?", (since,)).fetchone()["c"]

    counter: dict[str, int] = {}
    for row in rows:
        try:
            ids = json.loads(row["patterns"] or "[]")
        except json.JSONDecodeError:
            continue
        for pid in ids:
            counter[pid] = counter.get(pid, 0) + 1

    path = get_settings().project_root / "rules" / "patterns_v1.json"
    meta = {}
    if path.is_file():
        data = json.loads(path.read_text(encoding="utf-8"))
        meta = {p["pattern_id"]: p for p in (data.get("patterns") or [])}

    items = []
    for rank, (pid, count) in enumerate(sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))[:limit]):
        p = meta.get(pid) or {}
        items.append(
            {
                "rank": rank + 1,
                "pattern_id": pid,
                "name": p.get("name", ""),
                "level": p.get("level", ""),
                "count": count,
                "example": (p.get("examples") or [""])[0],
                "why": p.get("why", ""),
            }
        )
    return envelope({"window_days": days, "samples": int(total), "items": items}, request)
