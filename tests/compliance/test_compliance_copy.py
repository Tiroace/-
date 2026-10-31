"""合规文案测试（产品经理 05/06 两份规范转化为可执行验收）

来源：`docs/06-合规与文案/05-报告页文案模板与禁用词清单.md` §7.1 / §9
要求：「对全部页面文案 + 测试集报告输出各跑一遍，要求 0 命中」。

三组：
1. 测试集 20 条的报告输出 —— 全文扫禁用词（含 summary/risks/questions/how_to_verify）
2. 前端源码 —— 扫所有 .vue/.js 里的中文字面量
3. 结构合规 —— 报告页有 AI 标识、免责声明；高危报告有 110/96110/12333
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from conftest import ROOT, assert_report_v2

pytest.importorskip("engine", reason="需要引擎链路")

from compliance.banned_words import (  # noqa: E402
    check_ai_label_and_disclaimer,
    check_emergency_numbers,
    check_no_ai_wording,
    check_safe_wording,
    scan_banned,
)

MINIAPP_SRC = ROOT / "src" / "src"


# ---------------------------------------------------------------- 1. 报告输出

@pytest.fixture(scope="module")
def all_reports():
    """把测试集全部跑一遍，拿到 20 份真实报告。"""
    from engine.config import default_config
    from engine.pipeline import analyze, make_model

    index = [json.loads(l) for l in (ROOT / "data/testset/index.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    cfg = default_config()
    cfg.report_dir = None
    cfg.cache_dir = ROOT / "var" / "cache" / "compliance-test"
    cfg.use_dedupe = False
    model = make_model("mock", defects=False)

    reports = []
    for e in index:
        result = analyze([], str(ROOT / e["ocr_text"]), config=cfg, model=model)
        reports.append((e["id"], result.report))
    assert len(reports) >= 20, f"测试集只有 {len(reports)} 条"
    return reports


def test_报告输出零禁用词(all_reports):
    problems = []
    for rid, report in all_reports:
        blob = json.dumps(report, ensure_ascii=False)
        problems += [str(f) for f in scan_banned(blob, where=f"报告 {rid}")]
    assert not problems, "报告输出命中一级禁用词：\n" + "\n".join(problems)


def test_safe档不背书(all_reports):
    """v2：整体结论为 green 时不得出现背书式措辞。"""
    problems = []
    for rid, report in all_reports:
        problems += [
            str(f)
            for f in check_safe_wording(report["summary"], "", report["overall"])
        ]
    assert not problems, "\n".join(problems)


def test_每份报告结构合法(all_reports):
    for rid, report in all_reports:
        assert_report_v2(report)


def test_overall取值与灯色自洽(all_reports):
    """v2：4 种整体结论必须与 findings 灯色一致（不出现「有红灯却给绿灯」）。"""
    rank = {"red": 3, "amber": 2, "green": 1}
    for rid, report in all_reports:
        if not report["is_job_posting"]:
            assert report["overall"] == "unknown", f"{rid}: 非招聘应为 unknown"
            continue
        levels = {f["level"] for f in report["findings"]}
        if "red" in levels:
            assert report["overall"] == "red", f"{rid}: 有红灯但 overall={report['overall']}"
        elif "amber" in levels:
            assert report["overall"] in {"amber", "red"}, f"{rid}: 有黄灯但 overall={report['overall']}"
        elif levels == {"green"}:
            assert report["overall"] in {"green", "amber", "red", "unknown"}, f"{rid}: 灯色异常"


# ---------------------------------------------------------------- 2. 前端文案

CJK = re.compile(r"[\u4e00-\u9fff]")

# 合规文档/注释里的「反例」不算：例如产品经理文档里举例「这家公司是骗子」
# 前端源码中允许这些逻辑中必要的词（脱敏正则、禁用词自检白名单）
SOURCE_ALLOWLIST_FILES = {"bannedWords.js", "constants.js", "format.js"}


def _iter_source_files() -> list[Path]:
    if not MINIAPP_SRC.is_dir():
        return []
    out = []
    for p in MINIAPP_SRC.rglob("*"):
        if p.suffix in (".vue", ".js", ".ts", ".json") and p.is_file():
            out.append(p)
    return out


def test_前端源码零禁用词():
    problems = []
    for path in _iter_source_files():
        if path.name in SOURCE_ALLOWLIST_FILES:
            continue  # 过滤器/常量里本来就会列出禁用词
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        rel = path.relative_to(ROOT).as_posix()
        problems += [str(f) for f in scan_banned(text, where=rel)]
    assert not problems, "前端源码命中禁用词：\n" + "\n".join(problems)


def _page_text_with_imports(report_page: Path) -> str:
    """报告页正文 + 它引入的本地模块内容（常量里的文案也算报告页文案）。"""
    text = report_page.read_text(encoding="utf-8")
    for m in re.finditer(r"from\s+['\"]([^'\"]+)['\"]", text):
        spec = m.group(1)
        if spec.startswith("@/"):
            target = MINIAPP_SRC / spec[2:]
        elif spec.startswith("."):
            target = (report_page.parent / spec).resolve()
        else:
            continue
        if target.is_file():
            text += "\n" + target.read_text(encoding="utf-8")
    return text


def test_前端报告页有AI标识与免责声明():
    report_page = MINIAPP_SRC / "pages" / "report" / "index.vue"
    if not report_page.is_file():
        pytest.skip("报告页尚未创建")
    text = _page_text_with_imports(report_page)
    missing = check_ai_label_and_disclaimer(text, where="报告页")
    assert not missing, "\n".join(missing)


def test_前端报告页无AI字样():
    """路线调整令（2026-10-31）：产品中不出现「AI」字样（只查上屏文案）。

    报告页里有多处 HTML/JS 注释会提到「大模型」
    （例：`<!-- 路线调整令：一期不用大模型 -->`），那是给开发看的说明，
    不是对外文案。不剔除注释会永远误报，逼人删注释来"修复"。
    """
    report_page = MINIAPP_SRC / "pages" / "report" / "index.vue"
    if not report_page.is_file():
        pytest.skip("报告页尚未创建")
    text = _strip_comments(_page_text_with_imports(report_page))
    hits = check_no_ai_wording(text, where="报告页")
    assert not hits, "\n".join(hits)


def _all_source_text() -> str:
    if not MINIAPP_SRC.is_dir():
        return ""
    chunks = []
    for p in MINIAPP_SRC.rglob("*"):
        if p.is_file() and p.suffix in (".vue", ".js", ".json"):
            try:
                chunks.append(p.read_text(encoding="utf-8"))
            except UnicodeDecodeError:
                continue
    return "\n".join(chunks)


def _strip_comments(text: str) -> str:
    """去掉注释行，只留会渲染的文案。

    为什么必须去注释：`// 路线调整令后不使用大模型` 这类说明性注释里必然出现「大模型」，
    那是给开发者看的，不是产品文案。若不去注释，扫描会永远误报，
    结果是有人把注释删掉来「修复」——本末倒置。
    """
    keep = []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith(("//", "/*", "*", "<!--")):
            continue
        keep.append(line)
    return "\n".join(keep)


def test_前端源码无AI字样():
    """路线调整令：整个前端不出现「AI」字样（只查对外文案，不查注释）。"""
    text = _all_source_text()
    if not text:
        pytest.skip("前端源码不存在")
    hits = check_no_ai_wording(_strip_comments(text), where="前端源码")
    assert not hits, "发现 AI 字样：\n" + "\n".join(hits)


# ---------------------------------------------------------------- 发帖页审核说明
#
# 老板 2026-10-31 19:10：发帖页不许承诺时效，只留「审核通过后公开」。
# 设计稿原句是「审核通过后公开，一般几分钟内完成」，时效承诺被点名删除。
# 等异步自动审核上线后再按老板要求改回——那时这条断言要一起改。

POST_CREATE = MINIAPP_SRC / "pages" / "post-create" / "index.vue"
BUILD_POST_CREATE = (
    ROOT / "src" / "dist" / "build" / "mp-weixin" / "pages" / "post-create" / "index.wxml"
)

# 常见时效承诺写法，全部不许出现在发帖页
TIME_PROMISE_PATTERNS = ("几分钟", "分钟内完成", "秒内完成", "立即公开", "马上公开", "即时公开")


@pytest.mark.parametrize(
    "path,where",
    [(POST_CREATE, "发帖页源码"), (BUILD_POST_CREATE, "发帖页构建产物")],
    ids=["源码", "构建产物"],
)
def test_发帖页有时效承诺即失败(path: Path, where: str) -> None:
    """上屏文案不许承诺审核时效。

    同时查源码和 dist 产物：只查源码会漏掉构建时注入的文案，
    只查产物则在没有构建的环境下恒 skip。两个都查，缺哪个报哪个。
    """
    if not path.is_file():
        pytest.skip(f"{where}不存在：{path}")
    raw = path.read_text(encoding="utf-8")
    # 构建产物是 wxml，去掉标签只留文案再扫；源码同样去注释
    text = _strip_comments(raw) if where == "发帖页源码" else re.sub(r"<[^>]+>", " ", raw)
    hits = [p for p in TIME_PROMISE_PATTERNS if p in text]
    assert not hits, (
        f"{where}出现审核时效承诺 {hits}。"
        "老板要求只留「审核通过后公开」，等异步自动审核上线再改回。"
    )


def test_发帖页有审核通过后公开说明() -> None:
    """发帖页必须提示「审核通过后公开」——否则用户不知道帖子上线有门槛。"""
    if not POST_CREATE.is_file():
        pytest.skip("发帖页不存在")
    text = _strip_comments(POST_CREATE.read_text(encoding="utf-8"))
    assert "审核通过后公开" in text, "发帖页缺少「审核通过后公开」说明"


def test_时效承诺检测是否有效() -> None:
    """反向自检：确认检测逻辑能抓到真的时效承诺。

    没有这条，检测写错了（比如模式全是空串）会永远不报，测试变成摆设。
    """
    sample = "审核通过后公开，一般几分钟内完成"
    hits = [p for p in TIME_PROMISE_PATTERNS if p in sample]
    assert hits, "时效承诺检测失效：连「几分钟」这句都抓不到"


def test_前端报告页有应急号码():
    """高危报告的 110 / 96110 / 12333 可以是直接写死的，也可以经由常量引入。

    实测（2026-10-31）：报告页通过 `HELP_TIPS`（constants.js）渲染应急号码，
    直接扫 .vue 字面量会误报。所以这里按「报告页 + 它引入的本地常量文件」合并判定。
    """
    report_page = MINIAPP_SRC / "pages" / "report" / "index.vue"
    if not report_page.is_file():
        pytest.skip("报告页尚未创建")

    text = report_page.read_text(encoding="utf-8")

    # 把报告页 import 的本地模块（相对路径/别名）内容拼进来
    for m in re.finditer(r"from\s+['\"]([^'\"]+)['\"]", text):
        spec = m.group(1)
        if spec.startswith("@/"):
            target = MINIAPP_SRC / spec[2:]
        elif spec.startswith("."):
            target = (report_page.parent / spec).resolve()
        else:
            continue
        if target.is_file():
            text += "\n" + target.read_text(encoding="utf-8")

    missing = check_emergency_numbers(text, where="报告页（含常量）")
    assert not missing, "\n".join(missing)


# ---------------------------------------------------------------- 3. 扫描器自检

def test_扫描器本身有效():
    """防「测试全绿但没测到」：故意塞入禁用词，扫描器必须能抓到。"""
    bad = "这家公司是骗子公司，100% 识别准确率，最准的工具，官方认证，大家快曝光它"
    findings = scan_banned(bad, where="自检")
    caught = {f.word for f in findings}
    for word in ("骗子公司", "100%识别", "最准", "官方认证", "曝光"):
        assert word in caught, f"扫描器漏检「{word}」，当前命中：{caught}"

    assert check_safe_wording("这个工作很安全，可以去", "可以去", "safe"), "safe 背书措辞漏检"
    assert not check_safe_wording("暂未发现明显风险，可以去", "可以去", "safe")
    assert check_ai_label_and_disclaimer("这份报告由系统自动生成", "报告页"), "缺 AI 标识未检出"
    assert check_emergency_numbers("高危！请及时联系相关部门", "报告页"), "缺号码未检出"
