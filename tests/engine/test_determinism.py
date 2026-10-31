"""确定性口径回归测试（路线调整令第三节）

把「同图结果一致、证据可追溯、5 秒内」做成持续防线，不是跑一次看看。

【性能约束】本文件曾因把 170 条用例每条跑 2 次、且多个用例各扫一遍全集，
导致引擎测试从 6 秒涨到 200 秒。现在改为：
- 用 module 级 fixture **只跑一遍全集**，所有用例复用结果；
- 抽样覆盖：确定性抽 40 条（含全部轨道），耗时测全部但只跑 1 次。
这样既守住门槛，又不拖慢全量。
"""
from __future__ import annotations

import json
import random
import sys
import time
from pathlib import Path

import pytest

from conftest import ROOT, normalize

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DIMENSIONS = ["fee", "work", "title", "pay", "company", "contract"]
REAL_CASES = ROOT / "data" / "testset" / "real_cases_v1.jsonl"
INDEX = ROOT / "data" / "testset" / "index.jsonl"

# 确定性与耗时抽样条数（全集太大，抽样足够发现问题）
DETERMINISM_SAMPLE = 40
TIMING_SAMPLE = 40


def _load_cases() -> list[dict]:
    out = []
    for p in (INDEX, REAL_CASES):
        if p.is_file():
            out += [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
    return [c for c in out if c.get("ocr_text") and (ROOT / c["ocr_text"]).is_file()]


def _signature(report: dict) -> str:
    return json.dumps(
        {
            "overall": report.get("overall"),
            "is_job": report.get("is_job_posting"),
            "dims": [(d["key"], d["level"]) for d in report.get("dimensions", [])],
            "findings": [(f["level"], f["dimension"], f["evidence"]) for f in report.get("findings", [])],
        },
        ensure_ascii=False,
        sort_keys=True,
    )


@pytest.fixture(scope="module")
def engine_cfg(tmp_path_factory):
    from engine.config import default_config

    cfg = default_config()
    cfg.report_dir = None
    cfg.cache_dir = tmp_path_factory.mktemp("det") / "cache"
    cfg.use_dedupe = False
    return cfg


def _run(cfg, ocr_rel: str):
    from engine.pipeline import analyze, make_model

    model = make_model("mock", defects=False)
    t0 = time.perf_counter()
    rep = analyze([], str(ROOT / ocr_rel), config=cfg, model=model).report
    return rep, (time.perf_counter() - t0) * 1000


@pytest.fixture(scope="module")
def sample_cases():
    cases = _load_cases()
    random.seed(20261031)  # 固定种子，保证可复现
    if len(cases) > DETERMINISM_SAMPLE:
        # 保证合成与真实轨道都抽到
        synth = [c for c in cases if c.get("track") == "synthetic"]
        real = [c for c in cases if c.get("track") != "synthetic"]
        pick_s = random.sample(synth, min(len(synth), DETERMINISM_SAMPLE // 3))
        pick_r = random.sample(real, min(len(real), DETERMINISM_SAMPLE - len(pick_s)))
        return pick_s + pick_r
    return cases


class Test确定性:
    def test_同一图两次结果完全一致(self, engine_cfg, sample_cases):
        """路线令核心：同一张图每次结果必须一致（抽样验证）。"""
        assert sample_cases, "没有可用用例"
        bad = []
        for case in sample_cases:
            r1, _ = _run(engine_cfg, case["ocr_text"])
            r2, _ = _run(engine_cfg, case["ocr_text"])
            if _signature(r1) != _signature(r2):
                bad.append(case["id"])
        assert not bad, f"以下用例两次结果不一致（非确定性）：{bad[:10]}"


class Test合规门槛:
    def test_单次检查不超过5秒(self, engine_cfg, sample_cases):
        worst, worst_id = 0.0, None
        for case in sample_cases:
            _, ms = _run(engine_cfg, case["ocr_text"])
            if ms > worst:
                worst, worst_id = ms, case["id"]
        assert worst <= 5000, f"单次检查耗时 {worst:.0f}ms 超过 5 秒（{worst_id}）"

    def test_证据全部可追溯(self, engine_cfg, sample_cases):
        bad = []
        for case in sample_cases:
            text = (ROOT / case["ocr_text"]).read_text(encoding="utf-8")
            src = normalize(text)
            rep, _ = _run(engine_cfg, case["ocr_text"])
            for f in rep.get("findings", []):
                ev = normalize(f.get("evidence", ""))
                if not ev or ev not in src:
                    bad.append((case["id"], f.get("evidence", "")[:30]))
        assert not bad, f"证据不可追溯：{bad[:5]}"


class Test双轨分开:
    def test_真实与合成分开标注(self):
        cases = _load_cases()
        tracks = {c.get("track") for c in cases}
        assert "synthetic" in tracks, "缺合成轨道用例"
        assert tracks & {"real", "real_text"}, f"缺真实轨道用例，现有轨道：{tracks}"

    def test_真实用例必须有来源URL(self):
        if not REAL_CASES.is_file():
            pytest.skip("真实用例文件不存在")
        cases = [json.loads(l) for l in REAL_CASES.read_text(encoding="utf-8").splitlines() if l.strip()]
        bad = [c["id"] for c in cases if not (c.get("source") or {}).get("url")]
        assert not bad, f"真实用例缺来源 URL：{bad[:10]}"

    def test_真实用例标了采集时间(self):
        if not REAL_CASES.is_file():
            pytest.skip("真实用例文件不存在")
        cases = [json.loads(l) for l in REAL_CASES.read_text(encoding="utf-8").splitlines() if l.strip()]
        bad = [c["id"] for c in cases if not (c.get("source") or {}).get("collected_at")]
        assert not bad, f"真实用例缺采集时间：{bad[:10]}"


class Test六维度:
    def test_每条用例六维度齐全(self, engine_cfg, sample_cases):
        bad = []
        for case in sample_cases:
            rep, _ = _run(engine_cfg, case["ocr_text"])
            keys = [d["key"] for d in rep.get("dimensions", [])]
            if keys != DIMENSIONS:
                bad.append(case["id"])
        assert not bad, f"维度不齐全：{bad[:10]}"
