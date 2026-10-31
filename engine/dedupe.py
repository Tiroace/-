"""去重缓存（§4.2 第一步）：同一用户 24 小时内重复上传同一组图，直接返回旧报告，不扣次数。

原型期没有用户体系，缓存按「图片哈希（或 OCR 文本哈希）+ 词库版本 + 模型 + 提示词版本」
建 key：任何一个变了都重新分析，避免改了词库还返回旧报告。
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path


def hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 256), b""):
            h.update(chunk)
    return h.hexdigest()


def hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_key(
    images: list[Path],
    ocr_text: str,
    lexicon_version: str,
    model_name: str,
    prompt_version: str,
    pattern_version: str = "",
) -> str:
    parts = [f"model={model_name}", f"lexicon={lexicon_version}", f"prompt={prompt_version}", f"patterns={pattern_version}"]
    if images:
        parts += [f"img={hash_file(p)}" for p in images]
    else:
        parts.append(f"text={hash_text(ocr_text)}")
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


class DedupeCache:
    def __init__(self, cache_dir: str | Path, ttl_hours: int = 24):
        self.cache_dir = Path(cache_dir)
        self.ttl_seconds = ttl_hours * 3600

    def _path(self, key: str) -> Path:
        return self.cache_dir / f"{key}.json"

    def get(self, key: str) -> dict | None:
        path = self._path(key)
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if time.time() - float(data.get("created_ts", 0)) > self.ttl_seconds:
            return None
        return data.get("report")

    def put(self, key: str, report: dict) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        payload = {"created_ts": time.time(), "created_at": time.strftime("%Y-%m-%d %H:%M:%S"), "report": report}
        self._path(key).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
