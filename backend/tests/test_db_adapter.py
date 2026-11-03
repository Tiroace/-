"""数据库双引擎适配：方言翻译、配置解析、SQLite 兼容回归。

MySQL 真连接要等云托管 MySQL 开通（本机没装驱动也连不上），
但**方言翻译和配置解析可以完整验证**——这些是迁移最容易出错的地方。
"""
from __future__ import annotations

import pytest

from backend.app import db_adapter as ad
from backend.app.db import SCHEMA, Database


class Test连接串解析:
    def test_不配置时用SQLite(self):
        assert ad.db_kind("") == "sqlite"
        assert ad.db_kind(None) == "sqlite"
        assert ad.db_kind("sqlite:///tmp/a.db") == "sqlite"

    def test_mysql连接串解析(self):
        cfg = ad.mysql_from_url("mysql://qbl:p%40ss@10.0.0.5:3307/qbl_prod?charset=utf8mb4")
        assert cfg["host"] == "10.0.0.5"
        assert cfg["port"] == 3307
        assert cfg["user"] == "qbl"
        assert cfg["password"] == "p@ss", "口令里的 %40 要解码"
        assert cfg["database"] == "qbl_prod"
        assert cfg["charset"] == "utf8mb4"

    def test_默认端口与字符集(self):
        cfg = ad.mysql_from_url("mysql://u:p@db.example.com/qbl")
        assert cfg["port"] == 3306
        assert cfg["charset"] == "utf8mb4"

    def test_缺库名要报错(self):
        with pytest.raises(ad.DatabaseError):
            ad.mysql_from_url("mysql://u:p@host:3306")

    def test_未知scheme要报错(self):
        with pytest.raises(ad.DatabaseError):
            ad.db_kind("postgres://u:p@h/db")

    def test_describe不泄漏口令(self):
        d = Database(None, db_url="mysql://qbl:TOPSECRET@h:3306/qbl", schema=SCHEMA)
        text = d.describe()
        assert "TOPSECRET" not in text, "连接串回显里不能出现口令"
        assert "qbl" in text


class Test方言翻译:
    def test_INSERT_OR_IGNORE转INSERT_IGNORE(self):
        assert ad.to_mysql_sql("INSERT OR IGNORE INTO t (a) VALUES (?)") == "INSERT IGNORE INTO t (a) VALUES (?)"

    def test_INSERT_OR_REPLACE转REPLACE(self):
        assert ad.to_mysql_sql("INSERT OR REPLACE INTO t (a) VALUES (?)") == "REPLACE INTO t (a) VALUES (?)"

    def test_普通SQL不动(self):
        sql = "SELECT * FROM posts WHERE status = ? ORDER BY created_at DESC"
        assert ad.to_mysql_sql(sql) == sql

    def test_占位符转换且百分号被保护(self):
        assert ad.MysqlConn._adapt_params("SELECT ? , '50%'") == "SELECT %s , '50%%'"

    def test_AUTOINCREMENT转AUTO_INCREMENT(self):
        ddl = ad.to_mysql_ddl("CREATE TABLE t (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT);")
        assert "BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY" in ddl
        assert "AUTOINCREMENT" not in ddl

    def test_建索引IF_NOT_EXISTS去掉(self):
        ddl = ad.to_mysql_ddl("CREATE INDEX IF NOT EXISTS idx_a ON t (a);")
        assert "IF NOT EXISTS" not in ddl
        assert ddl.startswith("CREATE INDEX")

    def test_真实SCHEMA能全部翻译(self):
        ddl = ad.to_mysql_ddl(SCHEMA)
        assert "AUTOINCREMENT" not in ddl, "还有 SQLite 自增语法没翻译，MySQL 建表会失败"
        assert "IF NOT EXISTS idx" not in ddl
        # TEXT 主键在 MySQL 里建不出来
        import re

        bad = re.findall(r"\bTEXT\s+PRIMARY\s+KEY", ddl, re.I)
        assert not bad, f"MySQL 不允许 TEXT 作主键：{bad[:3]}"

    def test_建表脚本拆分(self):
        parts = ad.split_ddl("CREATE TABLE a (id INT);\nCREATE TABLE b (id INT);")
        assert len(parts) == 2


class TestSQLite回归:
    """切适配层后，SQLite 行为必须和以前完全一致。"""

    def test_建表与按列名取值(self, tmp_path):
        d = Database(tmp_path / "t.db", schema=SCHEMA)
        d.init()
        with d.transaction() as c:
            c.execute(
                "INSERT OR IGNORE INTO users (id, platform, openid, created_at) VALUES (?,?,?,?)",
                ("u1", "wechat", "o1", "2026-11-03 00:00:00"),
            )
            row = c.execute("SELECT * FROM users WHERE id = ?", ("u1",)).fetchone()
        assert row["id"] == "u1", "行必须能按列名取（sqlite3.Row 行为）"

    def test_事务回滚(self, tmp_path):
        d = Database(tmp_path / "t.db", schema=SCHEMA)
        d.init()
        with pytest.raises(RuntimeError):
            with d.transaction() as c:
                c.execute(
                    "INSERT INTO users (id, platform, openid, created_at) VALUES (?,?,?,?)",
                    ("u2", "wechat", "o2", "2026-11-03 00:00:00"),
                )
                raise RuntimeError("boom")
        with d.connect() as c:
            n = c.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
        assert n == 0, "事务失败必须回滚"

    def test_迁移补列在SQLite上仍可用(self, tmp_path):
        d = Database(tmp_path / "t.db", schema=SCHEMA)
        d.init()
        with d.connect() as c:
            cols = {r["name"] for r in c.execute("PRAGMA table_info(analysis_tasks)")}
        assert "ocr_parallel" in cols

    def test_配置了db_url但没装驱动时报清晰错误(self, tmp_path):
        d = Database(None, db_url="mysql://u:p@127.0.0.1:3306/x", schema=SCHEMA)
        pytest.importorskip  # 只在没装 pymysql 时验证
        try:
            import pymysql  # noqa: F401

            pytest.skip("本机装了 pymysql，跳过驱动缺失用例")
        except ImportError:
            pass
        with pytest.raises(ad.DatabaseError) as exc:
            with d.connect():
                pass
        assert "pymysql" in str(exc.value)
