"""后台分析执行器（D5：POST 立即返回 task_id，前端轮询）。

原型期用进程内 ThreadPoolExecutor，不引 Celery/Redis；接口语义与正式版一致：
    pending（已建任务、已预扣） → running（后台开始跑） → done / failed
失败退回次数；成功把预扣标记为正式扣除。正式版换 Celery 只改本文件。
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from engine.pipeline import AnalysisError

from .config import Settings, get_settings
from .deps import get_db
from .engine_runner import run_engine, translate_engine_error
from .quota import balance, mark_analysis_consumed, refund_for_analysis

logger = logging.getLogger("qbl.worker")

_executor: ThreadPoolExecutor | None = None
_lock = threading.Lock()


def _now() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def get_executor(settings: Settings) -> ThreadPoolExecutor:
    global _executor
    with _lock:
        if _executor is None:
            _executor = ThreadPoolExecutor(
                max_workers=max(1, settings.worker_threads), thread_name_prefix="qbl-analysis"
            )
        return _executor


def submit(task_id: str) -> None:
    """把任务丢进线程池。调用方已完成预扣与建任务。"""
    get_executor(get_settings()).submit(_run_task, task_id)


def shutdown(wait: bool = True) -> None:
    global _executor
    with _lock:
        if _executor is not None:
            _executor.shutdown(wait=wait)
            _executor = None


def _read_ocr_text(settings: Settings, task_id: str) -> str | None:
    """原型期旁路：OCR 文本存在 uploads/<task_id>/ocr.txt。正式版由云 OCR 出文本。"""
    path = settings.upload_dir / task_id / "ocr.txt"
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8").strip()
    return text or None


def _images(settings: Settings, task_id: str) -> list[Path]:
    task_dir = settings.upload_dir / task_id
    if not task_dir.is_dir():
        return []
    return sorted(p for p in task_dir.iterdir() if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"))


def _record_pattern_hits(conn, report_id: str, report: dict) -> int:
    """套路命中落库（首页「最近常见」按近 7 天真实命中次数排）。"""
    count = 0
    for finding in report.get("findings") or []:
        pattern_id = finding.get("pattern_id")
        if not pattern_id:
            continue
        conn.execute(
            "INSERT INTO pattern_hits (pattern_id, report_id, hit_at) VALUES (?, ?, ?)",
            (pattern_id, report_id, _now()),
        )
        count += 1
    return count


def _report_row(conn, task_id: str, user_id: str, report: dict, settings: Settings) -> str:
    member = conn.execute(
        "SELECT expires_at FROM memberships WHERE user_id = ? AND expires_at > ?", (user_id, _now())
    ).fetchone()
    ttl_days = settings.member_report_ttl_days if member else settings.report_ttl_days
    expires_at = (dt.datetime.now() + dt.timedelta(days=ttl_days)).strftime("%Y-%m-%d %H:%M:%S")
    report_id = "r_" + uuid.uuid4().hex[:12]
    conn.execute(
        "INSERT INTO reports (id, task_id, user_id, report_json, risk_level, expires_at, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            report_id,
            task_id,
            user_id,
            json.dumps(report, ensure_ascii=False),
            report["overall"],
            expires_at,
            _now(),
        ),
    )
    _record_pattern_hits(conn, report_id, report)
    return report_id


def _run_task(task_id: str) -> None:
    settings = get_settings()
    db = get_db(settings)
    started_ts = time.perf_counter()
    try:
        with db.transaction() as conn:
            row = conn.execute("SELECT * FROM analysis_tasks WHERE id = ?", (task_id,)).fetchone()
            if row is None or row["status"] != "pending":
                return
            user_id = row["user_id"]
            conn.execute(
                "UPDATE analysis_tasks SET status = 'running', started_at = ? WHERE id = ?", (_now(), task_id)
            )

        try:
            delay_ms = settings.fake_engine_delay_ms
            if delay_ms > 0:   # 仅测试用，生产为 0
                time.sleep(delay_ms / 1000)
            images = _images(settings, task_id)
            ocr_text = _read_ocr_text(settings, task_id)
            model_name = os.environ.get("QBL_ENGINE_MODEL", "mock")
            report, trace = run_engine(settings, model_name, images, ocr_text)
        except AnalysisError as exc:
            code, _status = translate_engine_error(exc)
            duration_ms = int((time.perf_counter() - started_ts) * 1000)
            with db.transaction() as conn:
                refund_for_analysis(conn, user_id, task_id)
                conn.execute(
                    "UPDATE analysis_tasks SET status = 'failed', error_code = ?, error_message = ?,"
                    " duration_ms = ?, finished_at = ? WHERE id = ?",
                    (code, exc.message, duration_ms, _now(), task_id),
                )
                logger.warning("任务失败退次数 task=%s code=%s", task_id, code)
            return
        except Exception as exc:  # 兜底：未预期异常也退次数，别把用户次数吞了
            duration_ms = int((time.perf_counter() - started_ts) * 1000)
            with db.transaction() as conn:
                refund_for_analysis(conn, user_id, task_id)
                conn.execute(
                    "UPDATE analysis_tasks SET status = 'failed', error_code = 'ANALYSIS_FAILED',"
                    " error_message = ?, duration_ms = ?, finished_at = ? WHERE id = ?",
                    (f"分析失败：{type(exc).__name__}", duration_ms, _now(), task_id),
                )
            logger.exception("任务异常 task=%s", task_id)
            return

        duration_ms = int((time.perf_counter() - started_ts) * 1000)
        with db.transaction() as conn:
            _report_row(conn, task_id, user_id, report, settings)
            mark_analysis_consumed(conn, user_id, task_id)
            conn.execute(
                "UPDATE analysis_tasks SET status = 'done', duration_ms = ?, model = ?, prompt_version = ?,"
                " finished_at = ? WHERE id = ?",
                (duration_ms, trace.get("model") or "rules", trace.get("rules_version"), _now(), task_id),
            )
            logger.info("任务完成 task=%s overall=%s %dms", task_id, report["overall"], duration_ms)
    except Exception:  # 事务/数据库层异常：至少留日志，下一次巡检可补偿
        logger.exception("任务执行外层异常 task=%s", task_id)
