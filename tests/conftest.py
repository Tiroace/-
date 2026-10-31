"""pytest 公共夹具与断言工具（软件测试者维护）。

跑法（在项目根目录 D:\\qiuzhibilei）：
    <python> -m pytest tests -v
其中 <python> 为本机 3.12：
    C:\\Users\\Administrator\\.dsh\\dsh-runtimes\\dsh-primary-runtime\\dependencies\\python\\python.exe
"""
from __future__ import annotations

import json
import subprocess
import sys
import unicodedata
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TESTSET_DIR = ROOT / "data" / "testset"
INDEX_PATH = TESTSET_DIR / "index.jsonl"
OCR_DIR = TESTSET_DIR / "ocr"
# 词库路径跟随引擎的默认配置，不硬编码版本号（v1→v2 改版时踩过坑：
# 测试写死 lexicon_v1.json，而引擎已切到 lexicon_v2.json，导致加载到旧词库报错）
def _resolve_lexicon_path() -> Path:
    try:
        from engine.config import default_config

        p = Path(default_config().lexicon_path)
        if p.is_file():
            return p
    except Exception:
        pass
    for candidate in ("lexicon_v2.json", "lexicon_v1.json"):
        p = ROOT / "rules" / candidate
        if p.is_file():
            return p
    return ROOT / "rules" / "lexicon_v1.json"


LEXICON_PATH = _resolve_lexicon_path()


# ---------------------------------------------------------------- 基础夹具

@pytest.fixture(scope="session")
def project_root() -> Path:
    return ROOT


@pytest.fixture(scope="session")
def index_entries() -> list[dict]:
    """读取 data/testset/index.jsonl。"""
    assert INDEX_PATH.is_file(), f"缺少测试集索引：{INDEX_PATH}"
    entries = []
    for line in INDEX_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            entries.append(json.loads(line))
    assert entries, "测试集索引为空"
    return entries


@pytest.fixture(scope="session")
def ocr_text_by_id(index_entries) -> dict[str, str]:
    """id -> OCR 原文。"""
    out: dict[str, str] = {}
    for e in index_entries:
        rel = e.get("ocr_text")
        if not rel:
            continue
        p = ROOT / rel if not Path(rel).is_absolute() else Path(rel)
        if p.is_file():
            out[e["id"]] = p.read_text(encoding="utf-8")
    return out


@pytest.fixture(scope="session")
def engine():
    """导入引擎包。导入失败直接让整组测试失败并说明原因。"""
    try:
        import engine  # noqa: F401
        from engine import pipeline, schema, calibrate, evidence, textnorm  # noqa: F401
    except Exception as exc:  # pragma: no cover
        pytest.fail(f"无法导入 engine 包：{exc!r}")
    return __import__("engine")


# ---------------------------------------------------------------- 运行链路的封装

def run_engine(ocr_text: str, *, tmp_path: Path | None = None, extra_args: list[str] | None = None):
    """在进程内跑一次 analyze（不经 CLI），返回 (report, trace)。

    只用 OCR 旁路文本，不依赖真实图片与云 OCR。
    """
    from engine.config import default_config
    from engine.pipeline import analyze, make_model

    cfg = default_config()
    if tmp_path is not None:
        cfg.report_dir = None  # 测试不落盘到 var/reports
        # 【必须隔离缓存】默认 use_dedupe=True 且 cache_dir 指向 var/cache/dedupe 全局共享，
        # 不隔离会命中历史缓存（甚至是不同代码版本写下的旧 report/trace），
        # 导致「测试读到的不是当前代码的结果」。2026-10-31 实测踩到：
        # 同一段文本 run_engine 拿不到 rule_hits，直接 analyze 却有。
        cfg.cache_dir = tmp_path / "cache"
        cfg.use_dedupe = False

    text_file = None
    if tmp_path is not None:
        tmp_path.mkdir(parents=True, exist_ok=True)
        text_file = tmp_path / "ocr.txt"
        text_file.write_text(ocr_text, encoding="utf-8")
        ocr_arg = str(text_file)
    else:
        import tempfile

        fd = tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8")
        fd.write(ocr_text)
        fd.close()
        ocr_arg = fd.name

    model = make_model("mock", defects=False)  # 契约测试用「不注入缺陷」的 mock，保证可判定
    result = analyze([], ocr_arg, config=cfg, model=model)
    return result.report, result.trace


def run_cli(args: list[str], *, timeout: int = 180):
    """以子进程方式跑 `python -m engine.cli ...`，返回 CompletedProcess（utf-8）。"""
    return subprocess.run(
        [sys.executable, "-m", "engine.cli", *args],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


# ---------------------------------------------------------------- 归一化与可追溯断言

def normalize(text: str) -> str:
    """去空白 / 去标点 / 全半角统一，用于「证据能否在 OCR 原文里找回」的判定。

    与引擎 evidence.py 的口径对齐：NFKC 归一 + 只保留中日韩/字母/数字。
    """
    if not text:
        return ""
    t = unicodedata.normalize("NFKC", text)
    return "".join(ch for ch in t if unicodedata.category(ch)[0] in ("L", "N"))


def assert_evidence_traceable(evidence: str, ocr_text: str) -> None:
    """断言 evidence 能在 OCR 原文里找到（归一化后子串匹配）。"""
    ev = normalize(evidence)
    src = normalize(ocr_text)
    assert ev, "evidence 归一化后为空，不能作为证据"
    assert ev in src, f"证据不可追溯：{evidence!r} 无法在 OCR 原文中找到"


# ---------------------------------------------------------------- 报告 v2 结构断言
#
# 【2026-10-31 v2 改版】旧 §4.3 报告（risk_level/risks/verdict）已作废，
# 由 docs/09-改版实施计划.md §二 的 v2 结构取代。
# 所有引擎用例统一改用下面的 `assert_report_v2`；v1 断言函数仅保留给
# 尚未迁移的历史用例，禁止新用例引用。

V2_DIMENSIONS = ["fee", "work", "title", "pay", "company", "contract"]
V2_OVERALL = {"red", "amber", "green", "unknown"}
V2_DIM_LEVELS = {"red", "amber", "green", "none"}
V2_FINDING_LEVELS = {"red", "amber", "green"}
V2_SOURCES = {"rule", "pattern"}  # 路线令：llm 已移除
V2_LEVEL_RANK = {"red": 3, "amber": 2, "green": 1}


def assert_report_v2(report: dict) -> None:
    """按 docs/09 §二 的报告 v2 结构独立断言一遍（不依赖引擎内部实现）。"""
    assert isinstance(report, dict), "报告必须是 JSON 对象"

    # 1) 顶层字段
    top = {
        "is_job_posting", "overall", "summary", "dimensions", "findings",
        "questions_to_ask", "how_to_verify", "rules_version", "pattern_db_version",
    }
    missing = top - set(report)
    assert not missing, f"报告 v2 缺字段：{sorted(missing)}"
    extra = set(report) - top
    assert not extra, f"报告 v2 出现未定义字段：{sorted(extra)}"

    # 2) v1 字段必须消失
    v1 = {"risk_level", "risks", "verdict", "risk_score"} & set(report)
    assert not v1, f"报告仍含 v1 字段：{sorted(v1)}"

    # 3) 基本类型
    assert isinstance(report["is_job_posting"], bool)
    assert report["overall"] in V2_OVERALL, f"overall 非法：{report['overall']}"
    assert isinstance(report["summary"], str) and report["summary"].strip()
    assert len(report["summary"]) <= 30, f"summary 超 30 字：{len(report['summary'])}"
    # 路线调整令：prompt_version → rules_version；版本号会随规则迭代上升，只校验格式
    import re as _re

    assert _re.match(r"^v\d+\.\d+$", str(report["rules_version"])), (
        f"rules_version 格式应为 vX.Y，实际 {report['rules_version']!r}"
    )
    assert isinstance(report["pattern_db_version"], str) and report["pattern_db_version"].strip(), (
        "pattern_db_version 不能为空"
    )

    # 4) 6 维度固定齐全且顺序固定
    dims = report["dimensions"]
    assert isinstance(dims, list) and len(dims) == 6, f"dimensions 必须 6 项，实际 {len(dims) if isinstance(dims, list) else 'N/A'}"
    keys = [d.get("key") for d in dims]
    assert keys == V2_DIMENSIONS, f"维度顺序/集合不符：{keys}"
    for d in dims:
        assert d.get("level") in V2_DIM_LEVELS, f"{d.get('key')}.level 非法：{d.get('level')}"
        short = d.get("short", "")
        assert isinstance(short, str) and short.strip(), f"{d['key']}.short 为空"
        assert len(short) <= 6, f"{d['key']}.short 超 6 字：{short!r}"

    # 5) findings
    findings = report["findings"]
    assert isinstance(findings, list), "findings 必须是数组"
    for i, f in enumerate(findings):
        for key in ("level", "dimension", "title", "evidence", "context", "reason", "source", "pattern_id", "rule_id"):
            assert key in f, f"findings[{i}] 缺字段 {key}"
        assert f["level"] in V2_FINDING_LEVELS, f"findings[{i}].level 非法：{f['level']}"
        assert f["dimension"] in V2_DIMENSIONS, f"findings[{i}].dimension 非法：{f['dimension']}"
        assert f["source"] in V2_SOURCES, f"findings[{i}].source 非法：{f['source']}"
        assert isinstance(f["evidence"], str) and f["evidence"].strip(), (
            f"findings[{i}] evidence 为空：没有原文支撑的发现不许展示（绿灯也一样）"
        )
        title = f.get("title", "")
        assert 4 <= len(title) <= 8, f"findings[{i}].title 应为 4–8 字：{title!r}"

    # 6) findings 按红黄绿排序
    ranks = [V2_LEVEL_RANK[f["level"]] for f in findings]
    assert ranks == sorted(ranks, reverse=True), (
        f"findings 未按红黄绿排序：{[f['level'] for f in findings]}"
    )

    # 7) overall 由灯色规则算，必须自洽
    if report["is_job_posting"] is False:
        assert report["overall"] == "unknown", "非招聘信息 overall 必须是 unknown"
    else:
        levels = {f["level"] for f in findings}
        if "red" in levels:
            expected = "red"
        elif "amber" in levels:
            expected = "amber"
        elif levels == {"green"}:
            expected = "green"
        else:
            expected = None  # 无 findings 时由引擎决定为 green 或 unknown，不硬判
        if expected is not None:
            assert report["overall"] in (expected, "unknown") or report["overall"] == expected, (
                f"overall={report['overall']} 与灯色 {sorted(levels)} 不符，按规则应为 {expected}"
            )

    # 8) 追问与核实
    for key in ("questions_to_ask", "how_to_verify"):
        v = report[key]
        assert isinstance(v, list) and v, f"{key} 不能为空"
        assert all(isinstance(x, str) and x.strip() for x in v), f"{key} 含空字符串"


# ---------------------------------------------------------------- v1 遗留（仅历史用例）

REPORT_LEVELS = {"high", "warn", "notice", "safe", "unknown"}
RISK_LEVELS = {"high", "warn", "notice"}
RISK_TYPES = {"scam", "train_loan", "bait_switch", "exaggerate", "illegal_clause"}
LEVEL_ORDER = {"notice": 1, "warn": 2, "high": 3}


def assert_report_contract(report: dict) -> None:
    """【已作废】v1 报告结构（risk_level/risks/verdict）。

    仅保留给尚未迁移的历史用例；新用例一律用 assert_report_v2。
    """
    from conftest import _assert_report_v1_legacy

    return _assert_report_v1_legacy(report)


def _assert_report_v1_legacy(report: dict) -> None:
    """不依赖引擎内部实现，按旧 §4.3 的结构独立断言一遍。"""
    assert isinstance(report, dict), "报告必须是 JSON 对象"

    # 1) 必填字段齐全
    for key in ("is_job_posting", "risk_level", "risk_score", "verdict", "summary",
                "risks", "questions_to_ask", "how_to_verify", "rules_version"):
        assert key in report, f"报告缺字段：{key}"

    # 2) 枚举与类型
    from engine.textnorm import LEVEL_TO_VERDICT

    assert isinstance(report["is_job_posting"], bool)
    assert report["risk_level"] in REPORT_LEVELS, f"risk_level 非法：{report['risk_level']}"
    assert isinstance(report["risk_score"], int) and 0 <= report["risk_score"] <= 100
    assert report["verdict"] in set(LEVEL_TO_VERDICT.values()), f"verdict 非法：{report['verdict']}"

    # 3) 结论必须与等级一致（不允许「高危但建议去」）
    assert report["verdict"] == LEVEL_TO_VERDICT[report["risk_level"]], (
        f"verdict 与 risk_level 不一致：{report['risk_level']} vs {report['verdict']}"
    )

    # 4) 风险项结构
    risks = report["risks"]
    assert isinstance(risks, list)
    assert len(risks) <= 8, "风险项最多 8 条"
    for i, r in enumerate(risks):
        for key in ("type", "level", "evidence", "reason", "rule_id"):
            assert key in r, f"risks[{i}] 缺字段 {key}"
        assert r["type"] in RISK_TYPES, f"risks[{i}].type 非法：{r['type']}"
        assert r["level"] in RISK_LEVELS, f"risks[{i}].level 非法：{r['level']}"
        assert isinstance(r["evidence"], str) and r["evidence"].strip(), (
            f"risks[{i}].evidence 为空：没有原文支撑的风险不许展示"
        )
        assert r["rule_id"], f"risks[{i}].rule_id 为空"

    # 5) 顶层等级与风险项自洽
    if report["is_job_posting"] is False:
        assert report["risk_level"] == "unknown"
        assert risks == [], "非招聘信息不应有风险项"
    else:
        assert report["risk_level"] != "unknown"
        if risks:
            computed = max(risks, key=lambda r: LEVEL_ORDER[r["level"]])["level"]
            assert report["risk_level"] == computed, (
                f"顶层等级 {report['risk_level']} 与风险项最高等级 {computed} 不一致"
            )
        else:
            assert report["risk_level"] == "safe"

    # 6) 文案长度（UI 适配）
    assert len(report["summary"]) <= 30, "summary 超过 30 字"


def highest_level(risks: list[dict]) -> str:
    if not risks:
        return "safe"
    return max(risks, key=lambda r: LEVEL_ORDER[r["level"]])["level"]
