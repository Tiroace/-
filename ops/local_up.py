"""本地服务编排（docker compose 的降级路径）。

为什么有这个脚本
    本机 Windows 未启用 WSL2 / VirtualMachinePlatform / Hyper-V，Docker Desktop 的 Linux
    引擎起不来（证据见 var/docker-probe.txt），`docker compose up` 在本机跑不通。
    为了满足「本地一键跑通整套服务并附命令输出」这条验收，这里提供等价的本地编排：
    用同一个 ops/docker-compose.yml 的服务拓扑（api 进程 + 数据落盘目录），在 Windows
    上直接起进程。生产环境仍然走 docker compose，脚本本身不改变任何服务行为。

用法（在仓库根目录执行）：
    python ops/local_up.py up            # 起 api（后台），打印 PID 与健康检查结果
    python ops/local_up.py status        # 看进程与健康状态
    python ops/local_up.py down          # 停 api
    python ops/local_up.py logs          # 看最近 50 行日志

环境变量：
    QBL_LOCAL_PORT      默认 8010（避开队里占用的 8000）
    QBL_LOCAL_DB        默认 var/local/qbl.db
    QBL_LOCAL_LOG_DIR   默认 var/local/logs

注意：只管理本脚本自己拉起的进程（PID 记在 var/local/api.pid）；不会碰别人起的服务。
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VAR = ROOT / "var" / "local"
PID_FILE = VAR / "api.pid"
LOG_DIR = Path(os.environ.get("QBL_LOCAL_LOG_DIR", VAR / "logs"))
PORT = int(os.environ.get("QBL_LOCAL_PORT", "8010"))
DB_PATH = Path(os.environ.get("QBL_LOCAL_DB", VAR / "qbl.db"))


def _pid_alive(pid: int) -> bool:
    """Windows 下用 tasklist 判断进程是否还在（不依赖 psutil）。"""
    try:
        out = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
            capture_output=True, text=True, timeout=10,
        ).stdout
    except Exception:
        return False
    return str(pid) in out


def _read_pid() -> int | None:
    if not PID_FILE.exists():
        return None
    try:
        return int(PID_FILE.read_text(encoding="utf-8").strip())
    except ValueError:
        return None


def _health() -> dict | None:
    url = f"http://127.0.0.1:{PORT}/health"
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            return {"status": resp.status, "body": resp.read().decode("utf-8")}
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return {"status": None, "body": f"不可达：{exc}"}


def cmd_up() -> int:
    pid = _read_pid()
    if pid and _pid_alive(pid):
        print(f"[up] 已在运行 pid={pid}，先 down 再 up")
        return 1
    VAR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    env = dict(os.environ)
    env.update({
        "QBL_ENV": env.get("QBL_ENV", "local"),
        "QBL_DB_PATH": str(DB_PATH),
        "QBL_UPLOAD_DIR": str(VAR / "uploads"),
        "QBL_REPORT_DIR": str(VAR / "reports"),
        "QBL_CACHE_DIR": str(VAR / "cache" / "dedupe"),
        "QBL_USE_LLM": "0",
        "QBL_FEATURE_COMMUNITY": "0",
        "QBL_WORKER_THREADS": env.get("QBL_WORKER_THREADS", "2"),
    })
    log_path = LOG_DIR / "api.log"
    log_file = open(log_path, "ab")
    # cwd=仓库根：backend.app.main:app 才能按包路径导入；rules/ 也按相对根目录找
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "backend.app.main:app",
         "--host", "127.0.0.1", "--port", str(PORT)],
        cwd=str(ROOT), env=env, stdout=log_file, stderr=subprocess.STDOUT,
        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
    )
    PID_FILE.write_text(str(proc.pid), encoding="utf-8")
    print(f"[up] api 启动中 pid={proc.pid} port={PORT} 日志={log_path}")

    for _ in range(60):  # 最多等 30 秒
        time.sleep(0.5)
        h = _health()
        if h["status"] == 200:
            print(f"[up] 健康检查通过：GET http://127.0.0.1:{PORT}/health -> {h['body']}")
            return 0
        if proc.poll() is not None:
            print(f"[up] 启动失败，进程已退出 code={proc.returncode}，日志尾部：")
            print("\n".join(log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-30:]))
            return 1
    print("[up] 30 秒内未通过健康检查")
    return 1


def cmd_down() -> int:
    pid = _read_pid()
    if not pid or not _pid_alive(pid):
        print("[down] 没有由本脚本启动的进程")
        if PID_FILE.exists():
            PID_FILE.unlink()
        return 0
    subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, text=True, timeout=20)
    for _ in range(20):
        time.sleep(0.5)
        if not _pid_alive(pid):
            break
    PID_FILE.unlink(missing_ok=True)
    print(f"[down] 已停止 pid={pid}")
    return 0


def cmd_status() -> int:
    pid = _read_pid()
    alive = bool(pid and _pid_alive(pid))
    h = _health()
    print(f"[status] pid={pid} 存活={alive} 端口={PORT}")
    print(f"[status] GET /health -> status={h['status']} body={h['body']}")
    return 0 if alive and h["status"] == 200 else 1


def cmd_logs() -> int:
    log_path = LOG_DIR / "api.log"
    if not log_path.exists():
        print("[logs] 还没有日志")
        return 1
    lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    print("\n".join(lines[-50:]))
    return 0


def main() -> int:
    action = sys.argv[1] if len(sys.argv) > 1 else "status"
    handlers = {"up": cmd_up, "down": cmd_down, "status": cmd_status, "logs": cmd_logs}
    if action not in handlers:
        print(__doc__)
        return 2
    return handlers[action]()


if __name__ == "__main__":
    raise SystemExit(main())
