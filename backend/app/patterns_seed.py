"""套路库种子：把 lexicon/patterns_v1.json 灌进 patterns / pattern_examples 三表。

正式版由运营后台维护；原型期以文件为准，启动时按「表为空才灌」避免覆盖运营改动。
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path


def _now() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def seed_patterns(db, path: str | Path) -> int:
    """返回本次灌入的套路条数（表里已有数据则返回 0）。"""
    file_path = Path(path)
    if not file_path.is_file():
        return 0
    data = json.loads(file_path.read_text(encoding="utf-8"))
    patterns = data.get("patterns") or []
    with db.transaction() as conn:
        existing = conn.execute("SELECT COUNT(*) AS c FROM patterns").fetchone()["c"]
        if existing:
            return 0
        now = _now()
        for item in patterns:
            conn.execute(
                "INSERT INTO patterns (id, name, dimension, level, why, how, status, source, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, 'active', 'seed', ?)",
                (
                    item["pattern_id"],
                    item.get("name", ""),
                    item.get("dimension", "work"),
                    item.get("level", "amber"),
                    item.get("why", ""),
                    item.get("how", ""),
                    now,
                ),
            )
            for example in item.get("examples") or []:
                conn.execute(
                    "INSERT OR IGNORE INTO pattern_examples (pattern_id, text, created_at) VALUES (?, ?, ?)",
                    (item["pattern_id"], str(example), now),
                )
    return len(patterns)
