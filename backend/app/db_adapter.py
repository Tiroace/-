"""数据库双引擎适配：SQLite（本地/默认）与 MySQL（云托管）。

设计目标（第 2 关要求）：
- **业务代码一行不改**：全网 33 个文件都在用 `Database.connect()` / `Database.transaction()`，
  拿到的 conn 只要能 `.execute(sql, params)` / `.fetchone()` / `.fetchall()` 就行；
- `?` 占位符照写：MySQL 侧由这一层自动改成 `%s`，业务层不用区分方言；
- SQLite 方言（`INSERT OR IGNORE`、`AUTOINCREMENT`）由这一层翻译成 MySQL 等价写法；
- 驱动**延迟导入**：本地没装 pymysql 也能跑 SQLite 回归，不强制依赖。

配置：`QBL_DB_URL`
- 不配 / 以 `sqlite` 开头 → SQLite（默认沿用 QBL_DB_PATH）
- `mysql://user:pass@host:3306/dbname?charset=utf8mb4` → MySQL
"""
from __future__ import annotations

import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse


class DatabaseError(RuntimeError):
    """数据库配置/连接错误。"""


def mysql_from_url(url: str) -> dict:
    """解析 MySQL 连接串。"""
    parsed = urlparse(url)
    if parsed.scheme not in ("mysql", "mysql+pymysql"):
        raise DatabaseError(f"不支持的数据库 scheme：{parsed.scheme}（只支持 mysql / sqlite）")
    if not parsed.hostname or not parsed.path:
        raise DatabaseError("MySQL 连接串缺少 host 或库名：mysql://user:pass@host:3306/dbname")
    query = parse_qs(parsed.query or "")
    return {
        "host": parsed.hostname,
        "port": parsed.port or 3306,
        "user": unquote(parsed.username or ""),
        "password": unquote(parsed.password or ""),
        "database": parsed.path.lstrip("/"),
        "charset": (query.get("charset") or ["utf8mb4"])[0],
    }


def db_kind(db_url: str | None) -> str:
    if not db_url:
        return "sqlite"
    if db_url.startswith("sqlite"):
        return "sqlite"
    if db_url.startswith(("mysql://", "mysql+pymysql://")):
        return "mysql"
    raise DatabaseError(f"无法识别的 QBL_DB_URL：{db_url[:20]}…（支持 sqlite:// 或 mysql://）")


# ---------------------------------------------------------------- 方言翻译

_QBL_SQLITE_TO_MYSQL = (
    # INSERT OR IGNORE -> INSERT IGNORE
    (re.compile(r"\bINSERT\s+OR\s+IGNORE\s+INTO\b", re.I), "INSERT IGNORE INTO"),
    # INSERT OR REPLACE -> REPLACE（MySQL 语义一致）
    (re.compile(r"\bINSERT\s+OR\s+REPLACE\s+INTO\b", re.I), "REPLACE INTO"),
    # SQLite 的 strftime → MySQL 用 DATE_FORMAT（业务里几乎不用，兜底）
    (re.compile(r"datetime\('now'\)", re.I), "NOW()"),
)


def to_mysql_sql(sql: str) -> str:
    """把 SQLite 风格 SQL 翻成 MySQL 能跑的写法（占位符由 Adapter 处理）。"""
    out = sql
    for pattern, repl in _QBL_SQLITE_TO_MYSQL:
        out = pattern.sub(repl, out)
    return out


def to_mysql_ddl(schema: str) -> str:
    """把 SQLite 建表语句翻成 MySQL 建表语句。

    已知差异：
    - `INTEGER PRIMARY KEY AUTOINCREMENT` → `BIGINT AUTO_INCREMENT PRIMARY KEY`
    - MySQL 不支持 `CREATE INDEX IF NOT EXISTS`（MySQL 8 也只在部分版本支持），
      改成去掉 IF NOT EXISTS；重复建索引会报错，由 init 时忽略重复错误处理
    - TEXT 字段不能作主键/唯一键（无长度），统一给 VARCHAR 长度
    """
    out = schema
    out = re.sub(
        r"(\w+)\s+INTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT",
        r"\1 BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY",
        out,
        flags=re.I,
    )
    out = re.sub(r"CREATE\s+INDEX\s+IF\s+NOT\s+EXISTS", "CREATE INDEX", out, flags=re.I)
    out = re.sub(r"CREATE\s+UNIQUE\s+INDEX\s+IF\s+NOT\s+EXISTS", "CREATE UNIQUE INDEX", out, flags=re.I)
    # 主键/唯一列必须是带长度的类型
    out = re.sub(r"(\w+)\s+TEXT\s+PRIMARY\s+KEY", r"\1 VARCHAR(64) PRIMARY KEY", out, flags=re.I)
    out = re.sub(r"\bTEXT\b(?=[^\n]*UNIQUE)", "VARCHAR(191)", out, flags=re.I)
    return out


def split_ddl(script: str) -> list[str]:
    """把建表脚本拆成单条语句（MySQL 驱动不接受一次多条）。"""
    return [stmt.strip() for stmt in script.split(";") if stmt.strip()]


# ---------------------------------------------------------------- 连接包装

class SqliteConn:
    """SQLite 连接的薄包装，补上与 MySQL 一致的行访问方式。"""

    def __init__(self, raw):
        self._raw = raw

    def execute(self, sql, params=()):
        return self._raw.execute(sql, params)

    def executescript(self, script):
        return self._raw.executescript(script)

    def close(self):
        self._raw.close()

    def __getattr__(self, name):
        return getattr(self._raw, name)


class MysqlCursor:
    """MySQL 游标包装：支持 execute / fetchone / fetchall，字段名访问同 sqlite3.Row。"""

    def __init__(self, cursor, columns):
        self._cursor = cursor
        self._columns = columns

    def _row(self, row):
        if row is None:
            return None
        return {col: row[i] for i, col in enumerate(self._columns)}

    def fetchone(self):
        return self._row(self._cursor.fetchone())

    def fetchall(self):
        return [self._row(r) for r in self._cursor.fetchall()]

    @property
    def rowcount(self) -> int:
        return self._cursor.rowcount


class MysqlConn:
    """MySQL 连接包装：把 `?` 占位符换成 `%s`，并把结果包成可按键访问的行。

    业务代码里大量使用 `row["id"]` 这种按列名取值（sqlite3.Row 的行为），
    MySQL 默认返回元组，这里统一成 dict，业务代码不用改。
    """

    def __init__(self, raw, cursorclass=None):
        self._raw = raw
        self._cursorclass = cursorclass

    @staticmethod
    def _adapt_params(sql: str) -> str:
        # 只有业务 SQL 用 ?；MySQL 原生用 %s。转义字面量里的 % 以防 format 报错。
        return sql.replace("%", "%%").replace("?", "%s")

    def execute(self, sql, params=()):
        cursor = self._raw.cursor()
        cursor.execute(self._adapt_params(to_mysql_sql(sql)), params)
        columns = [d[0] for d in (cursor.description or [])]
        return MysqlCursor(cursor, columns)

    def executescript(self, script):
        cursor = self._raw.cursor()
        for stmt in split_ddl(to_mysql_ddl(script)):
            try:
                cursor.execute(stmt)
            except Exception as exc:  # 建索引重复等：初始化阶段不该因此失败
                text = str(exc)
                if "Duplicate key name" in text or "already exists" in text:
                    continue
                raise
        return cursor

    def close(self):
        self._raw.close()

    def __getattr__(self, name):
        return getattr(self._raw, name)


class Database:
    """数据库门面：SQLite 或 MySQL，业务代码只认 connect() / transaction()。"""

    # 建表脚本由调用方注入（db.py 持有唯一一份 SCHEMA，避免两处漂移）
    schema: str = ""

    def __init__(self, path: str | Path | None = None, *, db_url: str | None = None, schema: str | None = None):
        self.db_url = db_url
        self.kind = db_kind(db_url)
        self.path = Path(path) if path else None
        if schema is not None:
            self.schema = schema
        if self.kind == "mysql":
            self.mysql = mysql_from_url(db_url or "")
        else:
            self.mysql = {}

    # ---------------- 连接 ----------------
    def _connect_raw(self):
        if self.kind == "mysql":
            try:
                import pymysql  # 延迟导入：本地不装也能跑 SQLite
            except ImportError as exc:
                raise DatabaseError(
                    "QBL_DB_URL 指向 MySQL 但没装驱动：pip install pymysql"
                ) from exc
            conn = pymysql.connect(
                host=self.mysql["host"],
                port=self.mysql["port"],
                user=self.mysql["user"],
                password=self.mysql["password"],
                database=self.mysql["database"],
                charset=self.mysql["charset"],
                autocommit=False,
                cursorclass=pymysql.cursors.Cursor,
            )
            return MysqlConn(conn)

        assert self.path is not None, "SQLite 模式必须给 path"
        conn = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        return SqliteConn(conn)

    def describe(self) -> str:
        if self.kind == "mysql":
            return f"mysql://{self.mysql['user']}@{self.mysql['host']}:{self.mysql['port']}/{self.mysql['database']}"
        return f"sqlite://{self.path}"

    # ---------------- 初始化 ----------------
    def init(self) -> None:
        if self.kind == "sqlite":
            assert self.path is not None
            self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            if not self.schema:
                raise DatabaseError("没有建表脚本：Database(schema=SCHEMA) 必须传入")
            conn.executescript(self.schema)
            self._migrate(conn)

    @staticmethod
    def _migrate(conn) -> None:
        """轻量迁移：老库补列，不破坏已有数据（正式版交给 Alembic）。

        列是否存在用 PRAGMA（SQLite）/ information_schema（MySQL）分别查。
        """
        is_mysql = isinstance(conn, MysqlConn)
        wanted = {
            "analysis_tasks": {
                "started_at": "TEXT",
                "background_notified": "INTEGER NOT NULL DEFAULT 0",
                "ocr_ms": "INTEGER",
                "ocr_parallel": "INTEGER",
                "ocr_images": "INTEGER",
            },
            "posts": {
                "reviewed_by": "VARCHAR(40)",
                "reviewed_at": "VARCHAR(19)",
                "reject_reason": "VARCHAR(200)",
                "needs_review": "INTEGER NOT NULL DEFAULT 0",
                "hidden_reason": "VARCHAR(20)",
                "review_round": "INTEGER NOT NULL DEFAULT 0",
            },
            "experiences": {
                "reviewed_by": "VARCHAR(40)",
                "reviewed_at": "VARCHAR(19)",
            },
            "votes": {
                "counted": "INTEGER NOT NULL DEFAULT 1",
                "risk_reason": "VARCHAR(40)",
                "device_hash": "VARCHAR(64)",
                "ip_prefix": "VARCHAR(40)",
            },
            "sensitive_words": {
                "kind": "VARCHAR(10) NOT NULL DEFAULT 'word'",
                "prompt": "VARCHAR(200)",
                "as_type": "VARCHAR(20)",
                "category": "VARCHAR(20)",
            },
        }
        for table, columns in wanted.items():
            if is_mysql:
                rows = conn.execute(
                    "SELECT COLUMN_NAME AS name FROM information_schema.COLUMNS"
                    " WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = ?",
                    (table,),
                ).fetchall()
                existing = {r["name"] for r in rows}
            else:
                existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
            for name, ddl in columns.items():
                if name not in existing:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")

    # ---------------- 会话 ----------------
    @contextmanager
    def connect(self):
        conn = self._connect_raw()
        try:
            yield conn
        finally:
            try:
                conn.close()
            except Exception:
                pass

    @contextmanager
    def transaction(self):
        """事务：额度类操作必须原子，防止并发超扣。

        SQLite 用 BEGIN IMMEDIATE（写锁立即拿到，避免升级锁死锁）；
        MySQL 用 START TRANSACTION + InnoDB 行锁。
        """
        with self.connect() as conn:
            if isinstance(conn, MysqlConn):
                conn.execute("START TRANSACTION")
            else:
                conn.execute("BEGIN IMMEDIATE")
            try:
                yield conn
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
