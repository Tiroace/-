"""后台接口（§5.4 /admin/*：词库管理、复核池、数据看板）。

鉴权用 X-Admin-Token（原型期），真实实现换成后台账号 + 权限。
词库改动必须过引擎的规则校验，坏词库不许发布——否则线上直接大面积误报/漏报。
"""
from __future__ import annotations

import datetime as dt
import json
import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, Body, Depends, Request

from engine.lexicon import LexiconError, load_lexicon

from ..config import get_settings
from ..deps import envelope, get_db, require_admin
from ..errors import validation_error
from ..quota import reconcile

router = APIRouter(tags=["后台"], dependencies=[Depends(require_admin)])


def _lexicon_path() -> Path:
    """词库文件路径以引擎默认配置为准（v2 起是 lexicon_v2.json）。"""
    from engine.config import default_config

    return default_config().lexicon_path


@router.get("/admin/rules")
def get_lexicon(request: Request) -> dict:
    path = _lexicon_path()
    lexicon = load_lexicon(path)
    stat = path.stat()
    return envelope(
        {
            "path": str(path),
            "version": lexicon.version,
            "rule_count": len(lexicon.rules),
            "hard_rule_count": sum(1 for r in lexicon.rules if r.hard),
            "by_type": {t: sum(1 for r in lexicon.rules if r.type == t) for t in lexicon.type_names},
            "updated_at": dt.datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
            "rules": [r.raw for r in lexicon.rules],
        },
        request,
    )


@router.put("/admin/rules")
def put_lexicon(request: Request, payload: dict = Body(...)) -> dict:
    """整体替换词库。先写临时文件用引擎校验，通过才替换，并留一份 .bak。"""
    if not isinstance(payload, dict) or not isinstance(payload.get("rules"), list) or not payload["rules"]:
        raise validation_error("词库必须是包含非空 rules 数组的 JSON 对象")

    target = _lexicon_path()
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as tmp:
        json.dump(payload, tmp, ensure_ascii=False, indent=2)
        tmp_path = Path(tmp.name)
    try:
        lexicon = load_lexicon(tmp_path)
    except LexiconError as exc:
        tmp_path.unlink(missing_ok=True)
        raise validation_error(f"词库校验不通过：{exc}") from exc

    backup = target.with_suffix(".json.bak")
    if target.is_file():
        shutil.copy2(target, backup)
    shutil.move(str(tmp_path), str(target))

    return envelope(
        {
            "version": lexicon.version,
            "rule_count": len(lexicon.rules),
            "backup": str(backup),
            "notice": "词库已发布，下一批分析生效；请立刻跑一次 engine.evaluate 回归",
        },
        request,
    )


@router.get("/admin/review-pool")
def review_pool(request: Request, limit: int = 50) -> dict:
    limit = max(1, min(limit, 200))
    with get_db().connect() as conn:
        rows = conn.execute(
            "SELECT * FROM feedback WHERE type IN ('inaccurate', 'appeal') AND status = 'open'"
            " ORDER BY created_at ASC LIMIT ?",
            (limit,),
        ).fetchall()
        total = conn.execute(
            "SELECT COUNT(*) AS c FROM feedback WHERE type IN ('inaccurate', 'appeal') AND status = 'open'"
        ).fetchone()["c"]
    return envelope(
        {
            "total": int(total),
            "items": [
                {
                    "feedback_id": row["id"],
                    "user_id": row["user_id"],
                    "report_id": row["report_id"],
                    "type": row["type"],
                    "content": row["content"],
                    "status": row["status"],
                    "created_at": row["created_at"],
                }
                for row in rows
            ],
        },
        request,
    )


@router.get("/admin/stats")
def stats(request: Request) -> dict:
    with get_db().connect() as conn:
        counts = {
            "users": conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"],
            "analysis_tasks": conn.execute("SELECT COUNT(*) AS c FROM analysis_tasks").fetchone()["c"],
            "tasks_failed": conn.execute("SELECT COUNT(*) AS c FROM analysis_tasks WHERE status = 'failed'").fetchone()["c"],
            "reports": conn.execute("SELECT COUNT(*) AS c FROM reports").fetchone()["c"],
        }
        level_rows = conn.execute("SELECT risk_level, COUNT(*) AS c FROM reports GROUP BY risk_level").fetchall()
        revenue = conn.execute(
            "SELECT COALESCE(SUM(amount_fen), 0) AS s FROM orders WHERE status = 'paid'"
        ).fetchone()["s"]
        paid_orders = conn.execute("SELECT COUNT(*) AS c FROM orders WHERE status = 'paid'").fetchone()["c"]
        ad_today = conn.execute(
            "SELECT COUNT(*) AS c FROM ad_rewards WHERE granted = 1 AND reward_day = ?",
            (dt.date.today().isoformat(),),
        ).fetchone()["c"]
        check = reconcile(conn)
    return envelope(
        {
            "counts": counts,
            "reports_by_level": {row["risk_level"]: row["c"] for row in level_rows},
            "orders": {"paid": paid_orders, "revenue_fen": int(revenue)},
            "ad_rewards_today": ad_today,
            "quota_reconcile": check,
        },
        request,
    )
