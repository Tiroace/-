# 用确定性引擎生成 4 种 overall 的示例报告，写进前端 exampleReports.js
# 优先用 data/examples/ 的标准示例；缺的（或字段过期的）用引擎现跑补齐
# 用法：python miniprogram/scripts/gen-example-reports.py
import json
import os
import sys

ROOT = r"D:\qiuzhibilei"
sys.path.insert(0, ROOT)

from engine.pipeline import analyze  # noqa: E402

EX_DIR = os.path.join(ROOT, "data", "examples")
OUT_DIR = os.path.join(ROOT, "src", "src", "common")
OUT_FILE = os.path.join(OUT_DIR, "exampleReports.js")

TEST = os.path.join(ROOT, "data", "testset", "index.jsonl")
ORES = ["red", "amber", "green", "unknown"]


def load_standard():
    """读 data/examples/ 的标准示例，返回 {overall: report}"""
    out = {}
    for overall in ORES:
        p = os.path.join(EX_DIR, "report_%s.json" % overall)
        if not os.path.exists(p):
            continue
        with open(p, encoding="utf-8") as f:
            out[overall] = json.load(f)
    return out


def run_engine():
    """引擎现跑，按 overall 分类取样本"""
    rows = [json.loads(l) for l in open(TEST, encoding="utf-8") if l.strip()]
    picked = {}
    for r in rows:
        o = r.get("overall")
        if o in ORES and o not in picked:
            picked[o] = r
    result = {}
    for overall in ORES:
        if overall == "unknown":
            txt = "今天天气真好，我们去公园散步吧。"
        else:
            s = picked.get(overall)
            if not s:
                continue
            p = os.path.join(ROOT, s.get("ocr_text") or "")
            txt = open(p, encoding="utf-8").read() if os.path.exists(p) else ""
        if not txt:
            continue
        try:
            result[overall] = analyze(ocr_text=txt, use_dedupe=False).report
        except Exception as e:  # noqa: BLE001
            print("引擎跑失败", overall, e)
    return result


def normalize(report, overall):
    """统一成当前的 v2 字段口径：有 rules_version，没有 prompt_version"""
    r = dict(report)
    r.pop("prompt_version", None)
    if "rules_version" not in r:
        # 标准示例是旧字段，引擎当前版本号是 v2.0
        r["rules_version"] = "v2.0"
    # source 只允许 rule / pattern
    for f in r.get("findings", []):
        if f.get("source") not in ("rule", "pattern"):
            f["source"] = "rule"
    # 引擎报告本身不带 report_id（由后端分配），前端导航需要，这里补一个稳定 ID
    if not r.get("report_id"):
        r["report_id"] = "SAMPLE-" + overall.upper()
    return r


def main():
    standard = load_standard()
    print("data/examples 标准示例:", sorted(standard.keys()) or "无")

    fresh = run_engine()
    print("引擎现跑:", sorted(fresh.keys()))

    # 优先用引擎现跑的（字段最新），缺的用标准示例补
    final = {}
    for overall in ORES:
        if overall in fresh:
            final[overall] = normalize(fresh[overall], overall)
        elif overall in standard:
            final[overall] = normalize(standard[overall], overall)

    if not final:
        print("没有任何示例，退出")
        return 1

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        f.write("// 示例报告数据（由 miniprogram/scripts/gen-example-reports.py 生成，不要手改）\n")
        f.write("// 来源：确定性引擎实际跑出的 v2 报告（优先 data/examples 标准示例），与真实引擎输出同构。\n")
        f.write("// 用途：报告页 4 种 overall 形态展示与自测；内容是测试样本，不指向任何真实企业。\n")
        f.write("export const EXAMPLE_REPORTS = ")
        json.dump(final, f, ensure_ascii=False, indent=2)
        f.write(";\n\n")
        f.write("export function getExampleReport(overall) {\n")
        f.write("  return EXAMPLE_REPORTS[overall] || null;\n")
        f.write("}\n")

    for overall in ORES:
        r = final.get(overall)
        if not r:
            print("  缺", overall)
            continue
        dims = ",".join("%s=%s" % (d["key"], d["level"]) for d in r.get("dimensions", []))
        print("  %-8s overall=%s rules_version=%s findings=%d  [%s]" % (
            overall, r.get("overall"), r.get("rules_version"), len(r.get("findings", [])), dims))

    print("\n已写入:", OUT_FILE, os.path.getsize(OUT_FILE), "bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
