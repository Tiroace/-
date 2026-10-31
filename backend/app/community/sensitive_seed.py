"""敏感词种子：把产品交付的 sensitive_words_v1.json 灌进 sensitive_words 表。

- 启动时「表为空才灌」，不覆盖运营后台的热更结果；
- 级别映射：block → block；rewrite → review；mask（正则打码）→ mask；
- 后台 PUT /admin/sensitive-words 改的是数据库，下一次请求立即生效（不用重启）。
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path


def _now() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _normalize_level(level: str) -> str:
    return {"block": "block", "rewrite": "review", "review": "review", "mask": "mask"}.get(level, "block")


def seed_sensitive_words(db, path: str | Path) -> int:
    file_path = Path(path)
    if not file_path.is_file():
        return 0
    data = json.loads(file_path.read_text(encoding="utf-8"))
    with db.transaction() as conn:
        existing = conn.execute("SELECT COUNT(*) AS c FROM sensitive_words").fetchone()["c"]
        if existing:
            return 0
        now = _now()
        for item in data.get("words") or []:
            word = str(item.get("word") or "").strip()
            if not word:
                continue
            conn.execute(
                "INSERT OR IGNORE INTO sensitive_words (word, level, kind, prompt, as_type, category, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    word,
                    _normalize_level(str(item.get("level", "block"))),
                    "regex" if item.get("kind") == "regex" else "word",
                    str(item.get("prompt") or ""),
                    str(item.get("as") or ""),
                    str(item.get("category") or ""),
                    now,
                ),
            )
    return len(data.get("words") or [])
