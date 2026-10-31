"""引擎自测 v2：不依赖测试框架，直接 python -m engine.selftest 跑。

覆盖：词库 v2（6 维度）、套路库检索、规则命中、证据校验（红黄绿）、等级校准（规则/套路下限）、
schema v2 校验、整体结论由后端算、灰灯追问、脱敏与 PII 零泄漏、去重、模型降级、全测试集链路。
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from .adapters.models import DeepSeekModel, ModelNotConfigured
from .calibrate import calibrate
from .config import PROJECT_ROOT, default_config
from .dedupe import DedupeCache
from .evidence import verify_findings
from .lexicon import load_lexicon, scan
from .patterns import PatternLibrary
from .pipeline import AnalysisError, analyze
from .report import build_report
from .schema import computed_overall, validate_report
from .textnorm import (
    DIMENSION_KEYS,
    context_containing,
    evidence_in_text,
    filter_banned_words,
    find_pii,
    mask_pii,
    normalize,
)

PASS = 0
FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name}" + (f" —— {detail}" if detail else ""))


def section(title: str) -> None:
    print(f"\n== {title} ==")


def read_sample(sample_id: str) -> str:
    return (PROJECT_ROOT / "data" / "testset" / "ocr" / f"{sample_id}.txt").read_text(encoding="utf-8")


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    cfg = default_config()
    lexicon = load_lexicon(cfg.lexicon_path)
    patterns = PatternLibrary(cfg.patterns_path, threshold=cfg.pattern_threshold)

    section("1. 词库 v2（6 维度）")
    check("词库版本为 3.x（六维规则 v1 起）", lexicon.version.startswith("3."), lexicon.version)
    check("规则数 ≥ 50（26 条基础 + 24 条六维规则 v1）", len(lexicon.rules) >= 50, str(len(lexicon.rules)))
    six_rules = [r for r in lexicon.rules if r.rule_id.startswith(("R-INSIDER", "R-NAMED", "R-REMOTE", "R-TRIAL", "R-FEE-MULTI", "R-CAR", "R-CLAUSE", "R-IMPERSON", "R-BAIT", "R-DISCRIM-0"))]
    check("六维规则 v1 已入库（≥24 条）", len(six_rules) >= 24, str(len(six_rules)))
    check("每条规则都有 4–8 字标题与合法维度", all(4 <= len(r.title) <= 8 and r.dimension in DIMENSION_KEYS for r in lexicon.rules))
    check("每条规则都有合法 dimension", all(r.dimension in DIMENSION_KEYS for r in lexicon.rules))
    check("每条规则都有 4–8 字标题", all(4 <= len(r.title) <= 8 for r in lexicon.rules),
          str([r.title for r in lexicon.rules if not 4 <= len(r.title) <= 8]))
    check("有绿色（正面证据）规则", any(r.level == "green" for r in lexicon.rules))

    section("2. 套路库（检索）")
    check("套路库加载 ≥ 20 条", patterns.count >= 20, str(patterns.count))
    t001 = read_sample("T001")
    hits = patterns.match(t001, top_k=5)
    ids = {m.pattern.pattern_id for m in hits}
    check("T001 命中刷单/垫付套路", "P-FEE-05" in ids, str(sorted(ids)))
    check("命中句子来自原文", all(normalize(m.sentence) in normalize(t001) for m in hits))
    check("正常岗位 T015 不明显误命中套路", not any(m.score > 0.6 for m in patterns.match(read_sample("T015"))))

    section("3. 规则初筛（维度归属）")
    hits002 = scan(read_sample("T002"), lexicon)
    check("T002 押金命中 fee 维度", any(h.rule_id == "R-DEPOSIT-01" and h.dimension == "fee" for h in hits002))
    check("押金规则为硬证据", any(h.rule_id == "R-DEPOSIT-01" and h.hard for h in hits002))
    check("否定词不误报（无需缴纳押金）", not scan("本岗位无需缴纳押金，欢迎投递", lexicon))

    section("4. 证据校验（红黄绿都要原文）")
    kept, dropped = verify_findings(
        [
            {"level": "red", "dimension": "fee", "title": "先交押金", "evidence": "需交押金 300 元",
             "context": "入职须知：需交押金 300 元", "reason": "x", "source": "rule", "pattern_id": None, "rule_id": "R-DEPOSIT-01"},
            {"level": "green", "dimension": "company", "title": "编造的绿灯", "evidence": "入职当天发 2000 元安家费",
             "context": "入职当天发 2000 元安家费", "reason": "y", "source": "llm", "pattern_id": None, "rule_id": None},
        ],
        read_sample("T002"),
    )
    check("原文里有的证据保留", len(kept) == 1)
    check("编造的绿证据也被删", len(dropped) == 1 and dropped[0].finding["level"] == "green")

    section("5. 等级校准（规则/套路下限，D-01）")
    downgraded = [{"level": "amber", "dimension": "fee", "title": "先交押金", "evidence": hits002[0].evidence,
                   "context": hits002[0].evidence, "reason": "x", "source": "rule", "pattern_id": None, "rule_id": hits002[0].rule_id}]
    cal = calibrate(downgraded, hits002, [])
    check("模型把硬证据判轻，被拉回 red", cal.findings[0]["level"] == "red", str(cal.findings[0]["level"]))
    check("校准留痕", any(a["kind"] == "raise" for a in cal.adjustments))
    pattern_floor = [{"level": "green", "dimension": "fee", "title": "先交押金", "evidence": "x",
                      "context": "x", "reason": "x", "source": "pattern", "pattern_id": "P-FEE-01", "rule_id": None}]
    match = patterns.by_id("P-FEE-01")
    from .patterns import PatternMatch

    cal2 = calibrate(pattern_floor, [], [PatternMatch(pattern=match, sentence="x", score=0.9)])
    check("红灯套路不得被模型下调", cal2.findings[0]["level"] == "red", str(cal2.findings[0]["level"]))
    cal3 = calibrate([], hits002, [])
    check("模型漏报硬证据，按规则兜底补一条", any(f["source"] == "rule" for f in cal3.findings))

    # D-02：source=llm 但引用了真规则 / 证据能对上真规则，同样受词库下限保护
    llm_rule = [{"level": "green", "dimension": "fee", "title": "先交押金", "evidence": hits002[0].evidence,
                 "context": hits002[0].evidence, "reason": "x", "source": "llm", "pattern_id": None,
                 "rule_id": hits002[0].rule_id}]
    cal_d02a = calibrate(llm_rule, hits002, [])
    check("D-02：llm 引用规则也不得判轻（按 rule_id）", cal_d02a.findings[0]["level"] == "red", cal_d02a.findings[0]["level"])
    llm_no_id = [{"level": "green", "dimension": "fee", "title": "先交押金", "evidence": hits002[0].evidence,
                  "context": hits002[0].evidence, "reason": "x", "source": "llm", "pattern_id": None, "rule_id": None}]
    cal_d02b = calibrate(llm_no_id, hits002, [])
    check("D-02：llm 没写 rule_id 但证据对上规则，也按规则下限", cal_d02b.findings[0]["level"] == "red", cal_d02b.findings[0]["level"])

    section("6. schema v2 校验")
    good, _ = build_report(
        {"questions_to_ask": ["薪资结构是怎样的？"], "how_to_verify": ["查企业信用信息公示系统"]},
        [{"level": "red", "dimension": "fee", "title": "先交押金", "evidence": "交押金 300 元",
          "context": "入职须知：交押金 300 元", "reason": "收费", "source": "rule", "pattern_id": None, "rule_id": "R-DEPOSIT-01"}],
        True,
        "v2.0",
        "2026-10-30",
    )
    check("合法 v2 报告通过", not validate_report(good, final=True), str(validate_report(good, final=True))[:200])
    check("dimensions 固定 6 项且顺序固定", [d["key"] for d in good["dimensions"]] == list(DIMENSION_KEYS))
    missing = dict(good)
    missing.pop("overall")
    check("缺字段被拒", any("缺少字段" in e for e in validate_report(missing, final=True)))
    bad_dim = json.loads(json.dumps(good))
    bad_dim["dimensions"] = bad_dim["dimensions"][:5]
    check("维度不足 6 项被拒", any("dimensions" in e for e in validate_report(bad_dim, final=True)))
    bad_title = json.loads(json.dumps(good))
    bad_title["findings"][0]["title"] = "太短了"
    check("finding 标题不足 4 字被拒", any("title" in e for e in validate_report(bad_title, final=False)))
    bad_ctx = json.loads(json.dumps(good))
    bad_ctx["findings"][0]["context"] = "这段话说的是别的东西"
    check("context 不含 evidence 被拒", any("context" in e for e in validate_report(bad_ctx, final=False)))
    check("overall 由维度规则算出（有红→red）", computed_overall(good["dimensions"], good["findings"], True) == "red")
    check("没有发现时 overall=unknown", computed_overall(
        [{"key": k, "level": "none"} for k in DIMENSION_KEYS], [], True) == "unknown")

    section("7. 报告链路（红/绿/灰灯/追问）")
    red = analyze([], read_sample("T002"), config=cfg, use_dedupe=False)
    check("T002 overall=red 且 fee=red",
          red.report["overall"] == "red" and {d["key"]: d["level"] for d in red.report["dimensions"]}["fee"] == "red",
          red.report["overall"])
    grey = analyze([], read_sample("T015"), config=cfg, use_dedupe=False)
    check("正常岗位 T015 overall=green", grey.report["overall"] == "green", grey.report["overall"])
    amber = analyze([], read_sample("T012"), config=cfg, use_dedupe=False)
    check("T012 试用期超限 → contract=amber", {d["key"]: d["level"] for d in amber.report["dimensions"]}["contract"] == "amber")
    check("灰灯自动补追问", any("没提到" in q for q in grey.report["questions_to_ask"]), str(grey.report["questions_to_ask"]))
    check("每条 finding 的 context 包含 evidence", all(
        normalize(f["evidence"]) in normalize(f["context"]) for f in red.report["findings"]))
    check("每条 finding 带来源标签", all(f["source"] in ("rule", "pattern", "llm") for f in red.report["findings"]))

    section("8. 脱敏与 PII 零泄漏")
    mask_text = "招聘仓库理货员\n入职需交押金 300 元，联系人 13800000000\n工作地点：城北物流园"
    masked = analyze([], mask_text, config=cfg, use_dedupe=False)
    out_json = json.dumps(masked.report, ensure_ascii=False)
    check("evidence 里手机号已打码", "13800000000" not in out_json and "138****0000" in out_json)
    check("输出层 PII 零泄漏（全 JSON 扫描）", find_pii(out_json) == [], str(find_pii(out_json)))
    raw_trace = masked.trace.get("evidence_raw") or []
    check("trace 保留脱敏前原文（供评测/复核）", any("13800000000" in str(i.get("evidence")) for i in raw_trace), str(raw_trace))
    masked_phone = mask_pii("联系我 13812345678，身份证 110101199001011234")
    check("手机号/身份证脱敏", "13812345678" not in masked_phone and "110101199001011234" not in masked_phone)
    filtered, banned = filter_banned_words("这就是一家骗子公司，简直是黑心企业")
    check("定性词被替换", "骗子" not in filtered and "黑心" not in filtered)

    section("9. 整句与切句")
    ctx = context_containing(read_sample("T001"), "首次垫付 100 元")
    check("context 是包含证据的原文片段", "首次垫付 100 元" in ctx and len(ctx) <= 160, ctx)

    section("10. 24 小时去重")
    with tempfile.TemporaryDirectory() as tmp:
        cfg_dedupe = default_config()
        cfg_dedupe.cache_dir = Path(tmp)
        cfg_dedupe.report_dir = None
        text = read_sample("T001")
        first = analyze([], text, config=cfg_dedupe)
        second = analyze([], text, config=cfg_dedupe)
        check("第一次未命中缓存", first.trace["dedupe_hit"] is False)
        check("24 小时内重复上传命中缓存", second.trace["dedupe_hit"] is True)
        check("命中缓存返回同一份报告", second.report == first.report)
        check("缓存文件已落盘", bool(list(Path(tmp).glob("*.json"))))
        check("超过 TTL 视为过期", DedupeCache(tmp, ttl_hours=0).get(list(Path(tmp).glob("*.json"))[0].stem) is None)

    section("11. 模型插件（默认关闭）")
    from .adapters.models import ModelRequest

    try:
        DeepSeekModel(api_key="").generate(ModelRequest(ocr_text="招聘", rule_hits=[]))
        check("无 key 调 DeepSeek 抛 ModelNotConfigured", False)
    except ModelNotConfigured:
        check("无 key 调 DeepSeek 抛 ModelNotConfigured", True)

    default_run = analyze([], read_sample("T001"), config=cfg, use_dedupe=False)
    check("默认走确定性规则引擎（不依赖大模型）", default_run.trace.get("engine_mode") == "rules")

    cfg_llm = default_config()
    cfg_llm.use_llm = True
    cfg_llm.use_dedupe = False
    cfg_llm.report_dir = None
    try:
        analyze([], read_sample("T001"), config=cfg_llm, model=DeepSeekModel(api_key=""), use_dedupe=False)
        check("插件打开后遇模型未配置按失败处理", False)
    except AnalysisError as exc:
        check("插件打开后遇模型未配置按失败处理（可退次数）", exc.code == "MODEL_FAILED", exc.code)

    section("12. 全测试集链路（20 条）")
    cfg_eval = default_config()
    cfg_eval.use_dedupe = False
    cfg_eval.report_dir = None
    rows = [line for line in (cfg_eval.testset_dir / "index.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    ok_schema = ok_trace = ok_pii = ok_dims = 0
    for line in rows:
        row = json.loads(line)
        text = (PROJECT_ROOT / row["ocr_text"]).read_text(encoding="utf-8")
        res = analyze([], text, config=cfg_eval)
        if not validate_report(res.report, final=True):
            ok_schema += 1
        raw = res.trace.get("evidence_raw") or []
        if all(evidence_in_text(str(i.get("evidence")), text) for i in raw):
            ok_trace += 1
        if not find_pii(json.dumps(res.report, ensure_ascii=False)):
            ok_pii += 1
        if [d["key"] for d in res.report["dimensions"]] == list(DIMENSION_KEYS):
            ok_dims += 1
    check("20 条样例全部通过 v2 schema", ok_schema == len(rows), f"{ok_schema}/{len(rows)}")
    check("20 条样例证据全部可追溯（脱敏前）", ok_trace == len(rows), f"{ok_trace}/{len(rows)}")
    check("20 条样例输出层 PII 零泄漏", ok_pii == len(rows), f"{ok_pii}/{len(rows)}")
    check("20 条样例都是 6 维度齐全", ok_dims == len(rows), f"{ok_dims}/{len(rows)}")

    section("13. 六维规则 v1（真实话术回归，防退步）")
    real_cases = PROJECT_ROOT / "data" / "testset" / "real_cases_v1.jsonl"
    if real_cases.is_file():
        rows = [json.loads(line) for line in real_cases.read_text(encoding="utf-8").splitlines() if line.strip()]
        sample = rows[:60]  # 抽样跑，保证 selftest 秒级
        cfg_real = default_config()
        cfg_real.use_dedupe = False
        cfg_real.report_dir = None
        correct = 0
        for row in sample:
            text = (PROJECT_ROOT / row["ocr_text"]).read_text(encoding="utf-8")
            result = analyze([], text, config=cfg_real)
            if result.report["overall"] == row["label"]["overall"]:
                correct += 1
        acc = correct / len(sample)
        check(f"真实话术整体准确率 ≥70%（抽样 {len(sample)} 条）", acc >= 0.70, f"{acc:.1%}")
        probes = {
            "保录直签": "招聘岗位：行政专员\n岗位要求：打着「国企内推」「保录直签」等旗号",
            "分批次收介绍费": "招聘岗位：运营助理\n岗位要求：分批次收取高额就业介绍费用",
            "无薪试岗": "招聘岗位：客服\n岗位要求：以岗前培训考核、适应性试岗为名，设置3至7天无薪试岗期",
            "单位点名": "招聘岗位：运营助理\n岗位要求：可在国家电网、部队文职、三甲医院等单位安排工作",
            "异地引流": "招聘岗位：市场专员\n岗位要求：以「已招满」为由，诱导求职者前往省外务工",
        }
        expected_dim = {"保录直签": "title", "分批次收介绍费": "fee", "无薪试岗": "contract", "单位点名": "title", "异地引流": "work"}
        for name, text in probes.items():
            result = analyze([], text, config=cfg_real)
            dims = {d["key"]: d["level"] for d in result.report["dimensions"]}
            check(f"真实话术可识别：{name}", result.report["overall"] == "red" and dims.get(expected_dim[name]) == "red", f"{result.report['overall']} {dims}")
        first = analyze([], probes["保录直签"], config=cfg_real).report
        second = analyze([], probes["保录直签"], config=cfg_real).report
        check("同一文本两次报告完全一致（确定性）", first == second)
    else:
        check("真实话术用例存在", False, str(real_cases))

    section("14. 反例回归（正规国企公告 / 大厂外包 / 外地招工不能误判）")
    neg_path = PROJECT_ROOT / "rules" / "rule_negatives_v1.json"
    if neg_path.is_file():
        neg_cfg = default_config()
        neg_cfg.use_dedupe = False
        neg_cfg.report_dir = None
        neg_cases = json.loads(neg_path.read_text(encoding="utf-8"))["cases"]
        for case in neg_cases:
            report = analyze([], case["text"], config=neg_cfg).report
            fired = {f["rule_id"] for f in report["findings"] if f.get("rule_id")}
            forbidden = sorted(fired & set(case["forbid_rules"]))
            check(
                f"反例不被误判：{case['id']}",
                not forbidden and report["overall"] in case["expect_overall"],
                f"{report['overall']} {forbidden}",
            )
    else:
        check("反例语料存在", False, str(neg_path))

    print(f"\n结果：{PASS} 项通过，{FAIL} 项失败")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
