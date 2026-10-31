"""本地 SQLite 备份/恢复（原型期可用，不依赖 Docker）。

生产用 ops/backup.sh（MySQL + Redis，走 docker compose）。
本脚本用于：本机没有 Docker 引擎时（本项目开发机就是，见 var/docker-probe.txt），
仍能对原型期的 SQLite 库做**可验证**的备份与恢复演练。

用法（仓库根目录）：
    python ops/backup_local.py backup  [--db var/local/qbl.db]
    python ops/backup_local.py restore <备份文件> [--db var/local/qbl.db]
    python ops/backup_local.py verify  <备份文件>

备份方式：sqlite3 的 `VACUUM INTO`，一致性快照，不会拿到半截写入的数据。
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import shutil
import sqlite3
import sys
import tempfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = ROOT / "var" / "local" / "qbl.db"
BACKUP_DIR = ROOT / "var" / "backup"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _tables(db: Path) -> list[str]:
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        return [r[0] for r in conn.execute(
            "select name from sqlite_master where type='table' and name not like 'sqlite_%' order by name"
        )]
    finally:
        conn.close()


def cmd_backup(db: Path) -> int:
    if not db.exists():
        print(f"[backup] 数据库不存在：{db}")
        return 1
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    raw = BACKUP_DIR / f"qbl-{stamp}.db"
    out = BACKUP_DIR / f"qbl-{stamp}.db.gz"

    # VACUUM INTO：一致性快照备份，比直接拷文件安全
    src = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        src.execute("VACUUM INTO ?", (str(raw),))
    finally:
        src.close()

    with open(raw, "rb") as f_in, gzip.open(out, "wb") as f_out:
        shutil.copyfileobj(f_in, f_out)
    raw.unlink()

    tables = _tables(db) if db.exists() else []
    digest = _sha256(out)
    print(f"[backup] 源库：{db}（{db.stat().st_size} 字节，{len(tables)} 张表）")
    print(f"[backup] 产物：{out}（{out.stat().st_size} 字节）")
    print(f"[backup] sha256：{digest}")
    return 0


def _decompress(path: Path, tmpdir: str) -> Path:
    if path.suffix == ".gz":
        dest = Path(tmpdir) / "restored.db"
        with gzip.open(path, "rb") as f_in, open(dest, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)
        return dest
    return path


def cmd_verify(path: Path) -> int:
    if not path.exists():
        print(f"[verify] 找不到备份文件：{path}")
        return 1
    with tempfile.TemporaryDirectory() as tmp:
        db = _decompress(path, tmp)
        tables = _tables(db)
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        try:
            integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        finally:
            conn.close()
    print(f"[verify] 文件：{path}")
    print(f"[verify] integrity_check：{integrity}")
    print(f"[verify] 表数量：{len(tables)}")
    print(f"[verify] sha256：{_sha256(path)}")
    return 0 if integrity == "ok" and tables else 1


def cmd_restore(path: Path, db: Path) -> int:
    if not path.exists():
        print(f"[restore] 找不到备份文件：{path}")
        return 1
    if db.exists():
        safety = db.with_suffix(db.suffix + ".before-restore")
        shutil.copy2(db, safety)
        print(f"[restore] 现库已另存：{safety}")
    db.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        src = _decompress(path, tmp)
        shutil.copy2(src, db)
    print(f"[restore] 已恢复：{path} -> {db}（{len(_tables(db))} 张表）")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="SQLite 备份/恢复/校验")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_backup = sub.add_parser("backup", help="备份数据库")
    p_backup.add_argument("--db", type=Path, default=DEFAULT_DB)

    p_restore = sub.add_parser("restore", help="从备份恢复")
    p_restore.add_argument("file", type=Path)
    p_restore.add_argument("--db", type=Path, default=DEFAULT_DB)

    p_verify = sub.add_parser("verify", help="校验备份完整性")
    p_verify.add_argument("file", type=Path)

    args = parser.parse_args()
    if args.cmd == "backup":
        return cmd_backup(args.db)
    if args.cmd == "restore":
        return cmd_restore(args.file, args.db)
    return cmd_verify(args.file)


if __name__ == "__main__":
    sys.exit(main())
