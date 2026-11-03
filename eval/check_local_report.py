"""验证前端本地报告结构能否通过 engine/schema.py 的 validate_report。

做法：把 localReport.js 的产出规则在 Python 里照抄一遍（同一套模板与优先级），
再喂给真实校验器。若前端改了字段名，这里会立刻红。
"""
import sys

sys.path.insert(0, r"D:\qiuzhibilei")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from engine.schema import validate_report

OVERALL_SUMMARY = {
    "red": "有几处不对劲，先别急着去",
    "amber": "有几处要问清楚再决定",
    "green": "截图里没看到明显风险",
    "unknown": "信息不足，再补一张截图",
}
DIM_SHORT = {"red": "有问题", "amber": "要问清", "green": "看着正常", "none": "没提到"}
KEYS = ("fee", "work", "title", "pay", "company", "contract")
RANK = {"none": 0, "green": 1, "amber": 2, "red": 3}


def build(findings, is_job):
    dims = []
    for k in KEYS:
        rel = [f["level"] for f in findings if f["dimension"] == k]
        lv = max(rel, key=lambda x: RANK[x]) if rel else "none"
        dims.append({"key": k, "level": lv, "short": DIM_SHORT[lv]})
    levels = [d["level"] for d in dims]
    if not is_job:
        overall = "unknown"
    elif "red" in levels:
        overall = "red"
    elif "amber" in levels:
        overall = "amber"
    elif "green" in levels:
        overall = "green"
    else:
        overall = "unknown"
    return {
        "is_job_posting": is_job,
        "overall": overall,
        "summary": OVERALL_SUMMARY[overall],
        "dimensions": dims,
        "findings": findings,
        "questions_to_ask": ["问一句"],
        "how_to_verify": ["核实一下"],
        "rules_version": "v3.0",
        "pattern_db_version": "2026-10-30",
    }


def finding(level, dim, title, ev, reason):
    return {"level": level, "dimension": dim, "title": title, "evidence": ev,
            "context": ev, "reason": reason, "source": "pattern",
            "pattern_id": "P-FEE-01", "rule_id": None}


cases = {
    "红（命中一条红）": build([finding("red", "fee", "入职先交押金", "先交押金300元", "正规公司不会先收钱")], True),
    "黄": build([finding("amber", "work", "生活化诱饵", "团队都是00后氛围超好", "不说清每天干什么")], True),
    "绿（命中绿灯项）": build([finding("green", "pay", "薪资写清楚", "月薪6000元", "写清了")], True),
    "unknown（不是招聘）": build([], False),
    "unknown（六维全 none）": build([], True),
}

bad = 0
for name, rep in cases.items():
    errs = validate_report(rep)
    ok = not errs
    bad += 0 if ok else 1
    print(f"{'[OK]  ' if ok else '[FAIL]'} {name}  overall={rep['overall']}  {'' if ok else errs}")

print()
print("全部通过" if bad == 0 else f"{bad} 个用例未通过")
raise SystemExit(0 if bad == 0 else 1)
