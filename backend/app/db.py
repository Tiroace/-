"""SQLite 存储（原型期）。表结构对齐需求书 §5.3，T4 正式版换 MySQL 只改这一层。

设计要点：
- 余额不落字段，全部由 quota_ledger 汇总（流水是唯一事实来源）；
- 幂等键落唯一索引，重复请求直接返回第一次的结果；
- 会员不发额度流水，只改「每日上限」（§6.1）。
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

from .db_adapter import Database as DatabaseAdapter

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            TEXT PRIMARY KEY,
    platform      TEXT NOT NULL,
    openid        TEXT NOT NULL,
    unionid       TEXT,
    status        TEXT NOT NULL DEFAULT 'active',
    created_at    TEXT NOT NULL,
    UNIQUE (platform, openid)
);

CREATE TABLE IF NOT EXISTS quota_ledger (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       TEXT NOT NULL,
    delta         INTEGER NOT NULL,
    reason        TEXT NOT NULL,           -- register_bonus / ad_reward / analysis_hold / analysis_refund / analysis_mark / manual
    ref           TEXT,                    -- 关联单号（任务号 / 广告请求号 / 订单号）
    idem_key      TEXT,                    -- 幂等键（唯一）
    created_at    TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_ledger_idem ON quota_ledger(idem_key);

CREATE TABLE IF NOT EXISTS patterns (
    id           TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    dimension    TEXT NOT NULL,
    level        TEXT NOT NULL,
    why          TEXT,
    how          TEXT,
    status       TEXT NOT NULL DEFAULT 'active',
    source       TEXT NOT NULL DEFAULT 'seed',
    updated_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pattern_examples (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern_id TEXT NOT NULL,
    text       TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (pattern_id, text),
    FOREIGN KEY (pattern_id) REFERENCES patterns(id)
);

CREATE TABLE IF NOT EXISTS pattern_hits (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern_id TEXT NOT NULL,
    report_id  TEXT NOT NULL,
    hit_at     TEXT NOT NULL,
    FOREIGN KEY (pattern_id) REFERENCES patterns(id)
);
CREATE INDEX IF NOT EXISTS idx_pattern_hits_time ON pattern_hits(hit_at);

CREATE TABLE IF NOT EXISTS uploads (
    id           TEXT PRIMARY KEY,
    user_id      TEXT NOT NULL,
    file_hash    TEXT NOT NULL,
    path         TEXT NOT NULL,
    size         INTEGER NOT NULL,
    content_type TEXT,
    expires_at   TEXT NOT NULL,
    created_at   TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id)
);
CREATE INDEX IF NOT EXISTS idx_uploads_user ON uploads(user_id, created_at);

CREATE TABLE IF NOT EXISTS analysis_tasks (
    id             TEXT PRIMARY KEY,
    user_id        TEXT NOT NULL,
    idem_key       TEXT,                   -- 客户端 Idempotency-Key
    image_hashes   TEXT NOT NULL DEFAULT '[]',
    status         TEXT NOT NULL,          -- pending / done / failed
    error_code     TEXT,
    error_message  TEXT,
    duration_ms    INTEGER,
    ocr_ms         INTEGER,                -- 第 2 关：真实 OCR 耗时（验收 D40 / 线上排障）
    ocr_parallel   INTEGER,                -- 1 = 多图并行识别
    ocr_images     INTEGER,                -- 本次识别了几张图
    model          TEXT,
    prompt_version TEXT,
    created_at     TEXT NOT NULL,
    finished_at    TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_task_idem ON analysis_tasks(user_id, idem_key);

CREATE TABLE IF NOT EXISTS reports (
    id            TEXT PRIMARY KEY,
    task_id       TEXT NOT NULL UNIQUE,
    user_id       TEXT NOT NULL,
    report_json   TEXT NOT NULL,
    risk_level    TEXT NOT NULL,
    expires_at    TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    FOREIGN KEY (task_id) REFERENCES analysis_tasks(id)
);

CREATE TABLE IF NOT EXISTS ad_rewards (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       TEXT NOT NULL,
    ad_unit_id    TEXT,
    request_id    TEXT NOT NULL UNIQUE,
    result        TEXT NOT NULL,           -- completed / no_fill / error
    granted       INTEGER NOT NULL,
    reward_day    TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS orders (
    id                TEXT PRIMARY KEY,
    user_id           TEXT NOT NULL,
    plan              TEXT NOT NULL,
    amount_fen        INTEGER NOT NULL,
    channel           TEXT NOT NULL,
    platform_order_id TEXT,
    status            TEXT NOT NULL,       -- pending / paid / failed / refunded
    created_at        TEXT NOT NULL,
    paid_at           TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_orders_platform ON orders(platform_order_id);

CREATE TABLE IF NOT EXISTS memberships (
    user_id       TEXT PRIMARY KEY,
    plan          TEXT NOT NULL,
    expires_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS feedback (
    id          TEXT PRIMARY KEY,
    user_id     TEXT,
    report_id   TEXT,
    type        TEXT NOT NULL,             -- inaccurate / appeal / suggestion
    content     TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'open',
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS posts (
    id           VARCHAR(32) PRIMARY KEY,
    user_id      VARCHAR(32) NOT NULL,
    report_id    VARCHAR(32),
    company      VARCHAR(60),
    position     VARCHAR(60),
    city         VARCHAR(40),
    question     VARCHAR(200) NOT NULL,
    anonymous    TINYINT NOT NULL DEFAULT 1,
    risk_overall VARCHAR(10),
    images       VARCHAR(500),
    status       VARCHAR(10) NOT NULL DEFAULT 'pending',   -- pending / approved / hidden / rejected
    vote_up      INTEGER NOT NULL DEFAULT 0,
    vote_down    INTEGER NOT NULL DEFAULT 0,
    report_count INTEGER NOT NULL DEFAULT 0,
    reviewed_by  VARCHAR(40),
    reviewed_at  VARCHAR(19),
    reject_reason VARCHAR(200),
    needs_review INTEGER NOT NULL DEFAULT 0,               -- 1：被举报隐藏后等人工复核
    hidden_reason VARCHAR(20),                             -- reported（被举报） / manual（管理员手动隐藏）
    review_round INTEGER NOT NULL DEFAULT 0,               -- 第几轮复核，防止旧举报把恢复后的帖子再压下去
    created_at   VARCHAR(19) NOT NULL,
    updated_at   VARCHAR(19) NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_posts_status_time ON posts(status, created_at);
CREATE INDEX IF NOT EXISTS idx_posts_user ON posts(user_id);

CREATE TABLE IF NOT EXISTS votes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id     VARCHAR(32) NOT NULL,
    user_id     VARCHAR(32) NOT NULL,
    value       INTEGER NOT NULL,                           -- 1 有帮助 / -1 没用
    reason      VARCHAR(40),
    counted     INTEGER NOT NULL DEFAULT 1,                 -- D18：可疑票置 0，保留记录不计展示
    risk_reason VARCHAR(40),                                -- device_flood / ip_flood
    device_hash VARCHAR(64),                                -- 设备号哈希，不存明文
    ip_prefix   VARCHAR(40),                                -- /24 网段
    created_at  VARCHAR(19) NOT NULL,
    UNIQUE (post_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_votes_post ON votes(post_id);

CREATE TABLE IF NOT EXISTS experiences (
    id         VARCHAR(32) PRIMARY KEY,
    post_id    VARCHAR(32) NOT NULL,
    user_id    VARCHAR(32) NOT NULL,
    content    VARCHAR(500) NOT NULL,
    status     VARCHAR(10) NOT NULL DEFAULT 'pending',      -- pending / approved / rejected
    reviewed_by VARCHAR(40),
    reviewed_at VARCHAR(19),
    created_at VARCHAR(19) NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_experiences_post ON experiences(post_id, status);

CREATE TABLE IF NOT EXISTS post_reports (
    id         VARCHAR(32) PRIMARY KEY,
    post_id    VARCHAR(32) NOT NULL,
    user_id    VARCHAR(32) NOT NULL,
    reason     VARCHAR(40),
    created_at VARCHAR(19) NOT NULL,
    UNIQUE (post_id, user_id)
);

CREATE TABLE IF NOT EXISTS appeals (
    id         VARCHAR(32) PRIMARY KEY,
    post_id    VARCHAR(32),
    company    VARCHAR(60),
    contact    VARCHAR(80),
    content    VARCHAR(1000) NOT NULL,
    status     VARCHAR(10) NOT NULL DEFAULT 'open',         -- open / handled / rejected
    sla_hours  INTEGER NOT NULL DEFAULT 24,
    created_at VARCHAR(19) NOT NULL,
    handled_at VARCHAR(19)
);
CREATE INDEX IF NOT EXISTS idx_appeals_status ON appeals(status, created_at);

CREATE TABLE IF NOT EXISTS sensitive_words (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    word       VARCHAR(120) NOT NULL,
    level      VARCHAR(10) NOT NULL DEFAULT 'block',        -- block / review / mask
    kind       VARCHAR(10) NOT NULL DEFAULT 'word',         -- word / regex
    prompt     VARCHAR(200),
    as_type    VARCHAR(20),
    category   VARCHAR(20),
    created_at VARCHAR(19) NOT NULL,
    UNIQUE (word, kind)
);
"""


class Database(DatabaseAdapter):
    """保留原类名与构造签名，实现委托给 DatabaseAdapter（SQLite / MySQL 双引擎）。

    - Database(path)                    -> SQLite（本地与测试用）
    - Database(path, db_url="mysql://…") -> MySQL（云托管用）
    """

    def __init__(
        self, path: str | Path | None = None, *, db_url: str | None = None, schema: str | None = None
    ):
        super().__init__(path, db_url=db_url, schema=schema or SCHEMA)
