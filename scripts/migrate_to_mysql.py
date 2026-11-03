"""SQLite → MySQL 数据迁移脚本（第 2 关：换数据库）。

用法：
    # 1. 只建表，不搬数据（dry-run 看结构能否在 MySQL 建起来）
    python scripts/migrate_to_mysql.py --target "mysql://user:pass@host:3306/qbl" --schema-only

    # 2. 建表 + 搬数据（源库默认 var/backend/qbl.db）
    python scripts/migrate_to_mysql.py --source var/backend/qbl.db \
        --target "mysql://user:pass@host:3306/qbl"

特点：
- 表结构与后端完全同源（直接复用 backend.app.db.SCHEMA + Database.init），
  不会出现「脚本建的表和代码要的表不一致」
- 按外键依赖顺序搬，先父表后子表
- 幂等：目标已有数据默认跳过（--replace 才清空重搬）
- 搬完逐表比对行数，不一致就报错退出（不静默成功）
- **不打印任何口令**：连接串只回显 host/db

需要：pip install pymysql（本地跑 SQLite 回归不需要）
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.app.db import SCHEMA  # noqa: E402
from backend.app.db_adapter import Database, DatabaseError  # noqa: E402


def _table_order() -> list[str]:
    """按外键依赖排序：父表在前。没有外键的表放前面。"""
    preferred = [
        "users",
        "memberships",
        "quota_ledger",
        "uploads",
        "analysis_tasks",
        "reports",
        "ad_rewards",
        "orders",
        "feedback",
        "posts",
        "votes",
        "experiences",
        "post_reports",
        "appeals",
        "sensitive_words",
        "patterns",
        "pattern_examples",
        "pattern_hits",
    ]
    return preferred


def _columns(conn, table: str) -> list[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    if rows:
        return [r["name"] for r in rows]
    rows = conn.execute(f"SHOW COLUMNS FROM {table}").fetchall()
    return [r["Field"] for r in rows]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default=str(ROOT / "var" / "backend" / "qbl.db"))
    ap.add_argument("--target", required=True, help="mysql://user:pass@host:3306/dbname")
    ap.add_argument("--schema-only", action="store_true", help="只建表，不搬数据")
    ap.add_argument("--replace", action="store_true", help="目标表非空时清空重搬")
    args = ap.parse_args()

    try:
        target = Database(None, db_url=args.target, schema=SCHEMA)
    except DatabaseError as exc:
        print(f"[FAIL] 目标库配置有误：{exc}")
        return 2
    if target.kind != "mysql":
        print("[FAIL] --target 必须是 mysql:// 连接串")
        return 2

    print(f"目标库：{target.describe()}")
    print("建表…")
    try:
        target.init()
    except DatabaseError as exc:
        print(f"[FAIL] 连不上目标库：{exc}")
        return 2
    with target.connect() as conn:
        tables = [r["name"] if "name" in r else list(r.values())[0]
                  for r in conn.execute("SHOW TABLES").fetchall()]
    print(f"建表完成，共 {len(tables)} 张表")
    if args.schema_only:
        print("[OK] schema-only 完成")
        return 0

    src_path = Path(args.source)
    if not src_path.is_file():
        print(f"[FAIL] 源库不存在：{src_path}")
        return 2
    source = Database(src_path)
    source.init()
    print(f"源库：{source.describe()}")

    total = 0
    for table in _table_order():
        if table not in tables:
            continue
        with source.connect() as sc:
            has = sc.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
            ).fetchone()
            if not has:
                continue
            rows = sc.execute(f"SELECT * FROM {table}").fetchall()
        if not rows:
            print(f"  {table:22} 0 行，跳过")
            continue
        if args.replace:
            with target.transaction() as tc:
                tc.execute(f"DELETE FROM {table}")
        cols = list(rows[0].keys())
        placeholders = ",".join(["?"] * len(cols))
        sql = f"INSERT INTO {table} ({','.join(cols)}) VALUES ({placeholders})"
        inserted = 0
        with target.transaction() as tc:
            existing = tc.execute(f"SELECT COUNT(*) AS c FROM {table}").fetchone()["c"]
            if existing and not args.replace:
                print(f"  {table:22} 目标已有 {existing} 行，跳过（加 --replace 强制重搬）")
                total += existing
                continue
            for row in rows:
                try:
                    tc.execute(sql, tuple(row[c] for c in cols))
                    inserted += 1
                except Exception as exc:  # 单行失败要能定位，不要整批静默
                    print(f"  [WARN] {table} 某行插入失败：{type(exc).__name__} {str(exc)[:80]}")
        total += inserted
        print(f"  {table:22} 搬入 {inserted} 行")

    # 逐表比对行数
    print("\n行数比对：")
    bad = []
    for table in _table_order():
        if table not in tables:
            continue
        with source.connect() as sc:
            has = sc.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
            ).fetchone()
            if not has:
                continue
            src_n = sc.execute(f"SELECT COUNT(*) AS c FROM {table}").fetchone()["c"]
        with target.connect() as tc:
            dst_n = tc.execute(f"SELECT COUNT(*) AS c FROM {table}").fetchone()["c"]
        flag = "OK" if src_n == dst_n else "MISMATCH"
        if src_n != dst_n:
            bad.append((table, src_n, dst_n))
        print(f"  {table:22} 源 {src_n:>6}  目标 {dst_n:>6}  {flag}")

    if bad:
        print(f"\n[FAIL] {len(bad)} 张表行数不一致：{bad}")
        return 1
    print(f"\n[OK] 迁移完成，共 {total} 行，所有表行数一致（{time.strftime('%Y-%m-%d %H:%M:%S')}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
