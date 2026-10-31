"""文件日志 + 按天轮转、保留 190 天（≥6 个日历月，合规发现 R-04）。

原来日志只打到 console（`logging.basicConfig`），进程一停什么都没了；
《网络安全法》第二十一条要求网络日志留存不少于六个月，所以这里补上：

- `var/log/app.log`：按天轮转（TimedRotatingFileHandler, when="midnight"），
  `backupCount=190`，目录里实际保留 N+1 = 191 个文件，即 191 天覆盖
  （实测：backupCount=N 时保留 N+1 个文件）。6 个日历月最长 184 天，余 7 天。为什么不是 180：
  180 只覆盖 181 天，在 182–184 天的区间差 1–3 天，不严格够。
- 格式与 console 一致，带时间、级别、模块、消息。
- `setup_logging()` 幂等：多次调用不会重复挂 handler。
- 运维侧的对象存储/SLS 是部署层另一道，不互相替代。

注意：日志里不放个人信息。报告正文、截图路径里的用户标识按现有脱敏规则处理，
这里只保证「日志落盘并保留 6 个月」这件事在代码层成立。
"""
from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

LOG_DIR_NAME = Path("var") / "log"
LOG_FILE_NAME = "app.log"
# 保留 190 天，不是 180。
# backupCount=180 只能保住当前文件 + 180 个备份 ≈ 181 天的覆盖，
# 而「六个月」按日历算最长是 184 天（3–8 月：31+30+31+30+31+31），181 天不严格够。
# 多留 10 天余量，保证任何六个月窗口的日志都还在。
RETENTION_DAYS = 190
LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
_HANDLER_MARK = "_qbl_file_handler"


def log_dir(project_root: Path) -> Path:
    return Path(project_root) / LOG_DIR_NAME


def setup_logging(project_root: Path, level: int = logging.INFO) -> Path:
    """挂上「按天轮转 + 保留 190 天（≥6 个日历月）」的文件 handler，返回日志文件路径。"""
    directory = log_dir(project_root)
    directory.mkdir(parents=True, exist_ok=True)
    log_path = directory / LOG_FILE_NAME

    root = logging.getLogger()
    root.setLevel(level)

    for handler in root.handlers:
        if getattr(handler, _HANDLER_MARK, False):
            # 已经挂过：只确认路径，避免重复写两份
            if str(getattr(handler, "baseFilename", "")) == str(log_path.resolve()):
                return log_path
            return log_path

    file_handler = logging.handlers.TimedRotatingFileHandler(
        log_path,
        when="midnight",
        interval=1,
        backupCount=RETENTION_DAYS,
        encoding="utf-8",
    )
    file_handler.suffix = "%Y-%m-%d"
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
    file_handler.setLevel(level)
    setattr(file_handler, _HANDLER_MARK, True)
    root.addHandler(file_handler)

    if not any(isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler) for h in root.handlers):
        console = logging.StreamHandler()
        console.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
        console.setLevel(level)
        root.addHandler(console)

    return log_path
