-- 求助广场（R3）数据表 DDL —— SQLite 可执行，语法保持 MySQL 兼容
-- 说明：举报表建为 post_reports（避免与报告表 reports 同名冲突），上线 MySQL 时按同名字段迁移。
-- 开关：FEATURE_COMMUNITY 默认 false，关闭时所有 /community/* 返回 404。

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
    images       VARCHAR(500),                             -- 图片 image_id JSON 数组
    status       VARCHAR(10) NOT NULL DEFAULT 'pending',   -- pending / approved / hidden / rejected
    vote_up      INTEGER NOT NULL DEFAULT 0,
    vote_down    INTEGER NOT NULL DEFAULT 0,
    report_count INTEGER NOT NULL DEFAULT 0,
    reviewed_by  VARCHAR(40),
    reviewed_at  VARCHAR(19),
    reject_reason VARCHAR(200),
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
