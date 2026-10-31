"""截图 24 小时删除：定时清理任务（合规发现 R-03）。

承诺的措辞：上传的截图 24 小时内删除。
只有 `expires_at` 字段不算兑现承诺——文件还躺在磁盘上。这里把承诺落成定时任务：

1. 扫描 `uploads` 里 `expires_at` 已过期的记录；
2. 删磁盘文件（删不掉也继续删记录，但要记日志，不能静默）；
3. 删数据库记录；
4. 每次删除写一条删除日志（`var/log/deletion.log`，纯文本、按天轮转），
   只记「删了哪个 image_id、路径、大小、什么时候删的、谁删的」，不记图片内容。

由 `main.py` 的 startup 拉起一个后台守护线程，每小时跑一次；也支持手工跑：
    python -m backend.app.retention
"""
from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

from .config import get_settings
from .deps import get_db

logger = logging.getLogger("qbl.retention")

CLEANUP_INTERVAL_SECONDS = 3600  # 每小时一次
DELETION_LOG_NAME = "deletion.log"


def deletion_log_path() -> Path:
    settings = get_settings()
    return Path(settings.project_root) / "var" / "log" / DELETION_LOG_NAME


def _write_deletion_log(lines: list[str]) -> None:
    """删除日志：只记元数据（id、路径、大小、时间），不记图片内容。"""
    if not lines:
        return
    path = deletion_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for line in lines:
            fh.write(line + "\n")


def purge_expired_uploads(now: str | None = None) -> dict:
    """删掉所有过期上传：文件 + 记录 + 日志。返回统计，便于测试和巡检。"""
    import datetime as dt

    ts = now or dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db = get_db()
    stats = {"scanned": 0, "file_deleted": 0, "file_missing": 0, "record_deleted": 0, "file_error": 0}
    log_lines: list[str] = []
    with db.transaction() as conn:
        rows = conn.execute(
            "SELECT id, user_id, path, size, expires_at FROM uploads WHERE expires_at <= ?", (ts,)
        ).fetchall()
        stats["scanned"] = len(rows)
        for row in rows:
            image_id, path_str, size = row["id"], row["path"], row["size"]
            outcome = "deleted"
            try:
                target = Path(path_str)
                if target.is_file():
                    target.unlink()
                    stats["file_deleted"] += 1
                else:
                    # 文件已不在（手工删过/从没落盘）：仍然删记录，但要标出来
                    outcome = "file_missing"
                    stats["file_missing"] += 1
            except OSError as exc:  # 权限、占用等：保留记录等下轮重试，不静默丢
                outcome = f"file_error:{exc.__class__.__name__}"
                stats["file_error"] += 1
                logger.warning("删除过期截图失败 id=%s path=%s：%s", image_id, path_str, exc)
            if outcome.startswith("file_error"):
                continue
            conn.execute("DELETE FROM uploads WHERE id = ?", (image_id,))
            stats["record_deleted"] += 1
            log_lines.append(
                f"{ts}\t{image_id}\tuser={row['user_id']}\tsize={size}\t"
                f"expired_at={row['expires_at']}\toutcome={outcome}\tpath={path_str}"
            )
    _write_deletion_log(log_lines)
    if log_lines:
        logger.info("清理过期截图 %d 张（文件 %d、记录 %d）", len(log_lines), stats["file_deleted"], stats["record_deleted"])
    return stats


def purge_expired_reports(now: str | None = None) -> dict:
    """报告也有过期时间（会员到期），过期后删除报告行，兑现「过期不再可见」。"""
    import datetime as dt

    ts = now or dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db = get_db()
    with db.transaction() as conn:
        rows = conn.execute("SELECT id, user_id, expires_at FROM reports WHERE expires_at <= ?", (ts,)).fetchall()
        for row in rows:
            conn.execute("DELETE FROM reports WHERE id = ?", (row["id"],))
    lines = [
        f"{ts}\treport:{row['id']}\tuser={row['user_id']}\texpired_at={row['expires_at']}\toutcome=deleted"
        for row in rows
    ]
    _write_deletion_log(lines)
    return {"record_deleted": len(rows)}


_stop = threading.Event()
_thread: threading.Thread | None = None


def _loop() -> None:
    while not _stop.wait(CLEANUP_INTERVAL_SECONDS):
        try:
            purge_expired_uploads()
            purge_expired_reports()
        except Exception:  # 守护线程不能因为一次异常就死掉
            logger.exception("定时清理任务出错")


def start() -> None:
    global _thread
    if _thread and _thread.is_alive():
        return
    _stop.clear()
    try:
        purge_expired_uploads()
    except Exception:
        logger.exception("启动时清理过期截图失败")
    _thread = threading.Thread(target=_loop, name="qbl-retention", daemon=True)
    _thread.start()
    logger.info("截图过期清理任务已启动（每 %d 秒一次）", CLEANUP_INTERVAL_SECONDS)


def stop() -> None:
    _stop.set()
    if _thread and _thread.is_alive():
        _thread.join(timeout=2)


def main() -> int:
    """手工清理一次：python -m backend.app.retention"""
    logging.basicConfig(level=logging.INFO)
    uploads = purge_expired_uploads()
    reports = purge_expired_reports()
    print(f"过期截图：扫描 {uploads['scanned']}，删文件 {uploads['file_deleted']}，"
          f"删记录 {uploads['record_deleted']}，文件缺失 {uploads['file_missing']}，失败 {uploads['file_error']}")
    print(f"过期报告：删除 {reports['record_deleted']} 行")
    print(f"删除日志：{deletion_log_path()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
