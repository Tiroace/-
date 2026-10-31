"""套路库（patterns）：数据结构 + 语义匹配适配层。

设计对标正式三表：
- patterns：id / 名称 / 维度 / 等级 / 为什么危险 / 怎么办 / 状态 / 来源
- pattern_examples：id / pattern_id / 话术原文 / 向量
- pattern_hits：pattern_id / report_id / 命中时间（后端落库）

本机没有云向量服务（D13），默认用 `LocalTfidfProvider`（字符 n-gram + TF-IDF 余弦），
将来接云向量只换 provider，不动上层：`PatternLibrary(path, provider=CloudProvider(...))`。
"""
from __future__ import annotations

import json
import math
import os
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from .textnorm import normalize, split_sentences


class EmbeddingProvider:
    """向量检索接口。接云服务时实现同名方法即可。"""

    name = "base"

    def build(self, documents: list[str]) -> None:
        raise NotImplementedError

    def similarity(self, text: str, doc_index: int) -> float:
        raise NotImplementedError


def _tokens(text: str) -> list[str]:
    """数字归一 + 字符 bigram：中文短句上比 unigram 稳，能压掉手机号/金额类噪声。"""
    raw = normalize(text)
    if not raw:
        return []
    # 连续数字压成一个 #：避免手机号/金额里的一串数字制造虚假相似度
    s = re.sub(r"[0-9]+", "#", raw)
    if len(s) < 2:
        return [s]
    return [s[i : i + 2] for i in range(len(s) - 1)]


class LocalTfidfProvider(EmbeddingProvider):
    """本地降级实现：TF-IDF + 余弦相似度（纯标准库）。"""

    name = "local-tfidf"

    def __init__(self) -> None:
        self._idf: dict[str, float] = {}
        self._doc_vectors: list[dict[str, float]] = []
        self._doc_norms: list[float] = []

    def _vector(self, text: str) -> dict[str, float]:
        tokens = _tokens(text)
        if not tokens:
            return {}
        counts = Counter(tokens)
        total = len(tokens)
        vec: dict[str, float] = {}
        for token, count in counts.items():
            idf = self._idf.get(token, math.log((len(self._doc_vectors) + 1) / 1) + 1)
            vec[token] = (count / total) * idf
        return vec

    @staticmethod
    def _norm(vec: dict[str, float]) -> float:
        return math.sqrt(sum(v * v for v in vec.values())) or 1.0

    def build(self, documents: list[str]) -> None:
        tokenized = [_tokens(doc) for doc in documents]
        df: Counter = Counter()
        for tokens in tokenized:
            df.update(set(tokens))
        n = len(documents)
        self._idf = {token: math.log((n + 1) / (count + 1)) + 1 for token, count in df.items()}
        self._doc_vectors = [self._vector(doc) for doc in documents]
        self._doc_norms = [self._norm(vec) for vec in self._doc_vectors]

    def similarity(self, text: str, doc_index: int) -> float:
        vec = self._vector(text)
        if not vec:
            return 0.0
        doc = self._doc_vectors[doc_index]
        dot = sum(weight * doc.get(token, 0.0) for token, weight in vec.items())
        return dot / (self._norm(vec) * self._doc_norms[doc_index])

    def similarity_all(self, text: str) -> list[float]:
        """一次算完这条文本和所有套路示例的相似度。

        原来按示例逐条调 similarity()，每调一次都把句子重新分词、重算向量，
        一个用例 5 句 × 168 条示例 = 840 次重复分词，这是整条链路最大的耗时来源。
        """
        vec = self._vector(text)
        if not vec:
            return [0.0] * len(self._doc_vectors)
        norm = self._norm(vec)
        scores: list[float] = []
        for doc, doc_norm in zip(self._doc_vectors, self._doc_norms):
            dot = 0.0
            for token, weight in vec.items():
                other = doc.get(token)
                if other:
                    dot += weight * other
            scores.append(dot / (norm * doc_norm))
        return scores


@dataclass
class Pattern:
    pattern_id: str
    name: str
    dimension: str
    level: str
    why: str
    how: str
    examples: list[str] = field(default_factory=list)


@dataclass
class PatternMatch:
    pattern: Pattern
    sentence: str
    score: float

    def to_dict(self) -> dict:
        return {
            "pattern_id": self.pattern.pattern_id,
            "name": self.pattern.name,
            "dimension": self.pattern.dimension,
            "level": self.pattern.level,
            "sentence": self.sentence,
            "score": round(self.score, 4),
        }


class PatternLibrary:
    """套路库：加载 JSON、建索引、按句匹配 Top-K。"""

    def __init__(
        self,
        path: str | Path,
        provider: EmbeddingProvider | None = None,
        threshold: float | None = None,
    ):
        self.path = Path(path)
        self.provider = provider or LocalTfidfProvider()
        self.threshold = threshold if threshold is not None else float(os.environ.get("QBL_PATTERN_THRESHOLD", "0"))
        self.version = "unknown"
        self.patterns: list[Pattern] = []
        self._load()

    def _load(self) -> None:
        if not self.path.is_file():
            raise FileNotFoundError(f"套路库文件不存在：{self.path}")
        data = json.loads(self.path.read_text(encoding="utf-8"))
        self.version = str(data.get("version", "unknown"))
        if self.threshold <= 0:
            self.threshold = float(data.get("threshold", 0.32))
        self.patterns = [
            Pattern(
                pattern_id=item["pattern_id"],
                name=item.get("name", ""),
                dimension=item.get("dimension", "work"),
                level=item.get("level", "amber"),
                why=item.get("why", ""),
                how=item.get("how", ""),
                examples=[str(e) for e in item.get("examples", [])],
            )
            for item in data.get("patterns", [])
        ]
        docs: list[str] = []
        for pattern in self.patterns:
            docs.extend(pattern.examples or [pattern.name])
        self._doc_owner: list[int] = []
        for idx, pattern in enumerate(self.patterns):
            self._doc_owner.extend([idx] * max(1, len(pattern.examples or [pattern.name])))
        self.provider.build(docs)

    @property
    def count(self) -> int:
        return len(self.patterns)

    def by_id(self, pattern_id: str) -> Pattern | None:
        for pattern in self.patterns:
            if pattern.pattern_id == pattern_id:
                return pattern
        return None

    @staticmethod
    def _fragments(sentence: str, min_len: int = 6) -> list[str]:
        """长句里的话术常集中在某个分句：按逗号/顿号再切一层，提升召回（证据仍用整句）。"""
        parts = re.split(r"[，,、：:；;]", sentence)
        return [p.strip() for p in parts if len(p.strip()) >= min_len]

    def match(self, text: str, top_k: int = 5) -> list[PatternMatch]:
        """每句（及分句）取相似度最高的套路；跨句取 Top K 个不重复套路。"""
        best: dict[str, PatternMatch] = {}
        for sentence in split_sentences(text):
            # 同一句可能同时命中多条套路（例如「加客服领任务+垫付返款」），
            # 按套路去重，各取该句最高分，不再限制「一句只留一条」。
            per_sentence: dict[int, float] = {}
            scores = self.provider.similarity_all(sentence)
            threshold = self.threshold
            for doc_index, score in enumerate(scores):
                if score < threshold:
                    continue
                owner = self._doc_owner[doc_index]
                if score > per_sentence.get(owner, 0.0):
                    per_sentence[owner] = score
            for owner, score in per_sentence.items():
                pattern = self.patterns[owner]
                current = best.get(pattern.pattern_id)
                if current is None or score > current.score:
                    best[pattern.pattern_id] = PatternMatch(pattern=pattern, sentence=sentence, score=score)
        ranked = sorted(best.values(), key=lambda m: m.score, reverse=True)
        return ranked[:top_k]
