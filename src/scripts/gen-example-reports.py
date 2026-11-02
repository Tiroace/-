# 用确定性引擎生成 4 种 overall 的对外示例报告，写进前端 exampleReports.js
#
# 数据源只有一处：src/scripts/example-samples.json（固定虚构样本，见 docs/22）。
# 不再读 data/examples/、也不再读 data/testset/——示例是产品内容，不能和评测资产耦合。
#
# 任一异常都必须「打印原因 + exit 1」，禁止用旧示例补齐：
#   - 样本文件不存在 / 读不动 / 不是 JSON 对象
#   - 任一种 overall 的样本缺失或为空
#   - 引擎抛异常
#   - 引擎返回的 overall != key（防止规则变动后把红报告塞进 amber 的位置）
#   - 引擎返回的 overall 不在 {red,amber,green,unknown} 里
#
# 用法：python src/scripts/gen-example-reports.py
#
# ⚠ 重跑会整份覆盖 src/common/exampleReports.js：red 样例里手工加的 company 字段
#   （「示例（上海）科技有限公司」）会丢，「公司核实卡片·有全称」那一态就没了。
#   本脚本只透传引擎输出，不生成 company。重跑前先看
#   reports/复验记录-提审截图可截性两项改动.md §四。
import json
import os
import sys
import traceback

ROOT = r"D:\qiuzhibilei"
sys.path.insert(0, ROOT)

from engine.pipeline import analyze  # noqa: E402
from engine.prompts import RULES_VERSION  # noqa: E402

SAMPLES = os.path.join(ROOT, "src", "scripts", "example-samples.json")
OUT_DIR = os.path.join(ROOT, "src", "src", "common")
OUT_FILE = os.path.join(OUT_DIR, "exampleReports.js")

ORES = ["red", "amber", "green", "unknown"]

# 文件头注释里出现的字段名，避免生成脚本自己被 prompt_version 断言误伤
OLD_FIELD = "prompt" + "_version"


def die(msg):
    """打印失败原因并以 1 退出。绝不写文件。"""
    print("✗ 生成失败：" + msg, file=sys.stderr)
    sys.exit(1)


def load_samples():
    """只读固定样本文件；缺失/损坏/Schema 不对一律退出"""
    if not os.path.exists(SAMPLES):
        die("样本文件不存在：" + SAMPLES)
    try:
        with open(SAMPLES, encoding="utf-8") as f:
            raw = json.load(f)
    except Exception as e:  # noqa: BLE001
        die("样本文件读不动或不是合法 JSON：%s（%s）" % (SAMPLES, e))
    if not isinstance(raw, dict):
        die("样本文件顶层必须是对象（key → 样本文本）")
    # _开头的字段是说明，不算样本
    return {k: v for k, v in raw.items() if not k.startswith("_")}


def run_engine(samples):
    """按 key 逐条跑引擎；缺样本、引擎报错、overall 对不上都退出"""
    result = {}
    for overall in ORES:
        if overall not in samples:
            die("样本文件缺 key：%s（必须有 %s 四种）" % (overall, "/".join(ORES)))
        text = samples[overall]
        if not isinstance(text, str) or not text.strip():
            die("样本 %s 内容为空或不是字符串" % overall)
        try:
            rep = analyze(ocr_text=text, use_dedupe=False).report
        except Exception as e:  # noqa: BLE001
            print(traceback.format_exc(), file=sys.stderr)
            die("引擎处理样本 %s 时抛异常：%s" % (overall, e))
        got = rep.get("overall")
        if got not in ORES:
            die("引擎对样本 %s 返回了非法 overall：%r" % (overall, got))
        if got != overall:
            die(
                "样本 %s 的引擎结论是 %s，与 key 不一致（规则变动会让对外示例错位，"
                "请换样本或调整 key）" % (overall, got)
            )
        result[overall] = rep
    return result


def normalize(report, overall):
    """统一成当前字段口径：只有 rules_version（取引擎版本号），没有旧字段"""
    r = dict(report)
    r.pop(OLD_FIELD, None)
    r["rules_version"] = RULES_VERSION
    # source 只允许 rule / pattern
    for f in r.get("findings", []):
        if f.get("source") not in ("rule", "pattern"):
            f["source"] = "rule"
    # 引擎报告本身不带 report_id（由后端分配），前端导航需要，这里补一个稳定 ID
    if not r.get("report_id"):
        r["report_id"] = "SAMPLE-" + overall.upper()
    return r


def main():
    samples = load_samples()
    print("样本文件：%s（%d 条）" % (SAMPLES, len(samples)))
    fresh = run_engine(samples)

    final = {}
    for overall in ORES:
        n = normalize(fresh[overall], overall)
        # normalize 之后再确认一次，防止中途被改动
        if n.get("overall") != overall:
            die("归一化后 %s 的 overall 变成 %r" % (overall, n.get("overall")))
        final[overall] = n

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        f.write("// 示例报告数据（由 src/scripts/gen-example-reports.py 生成，不要手改）\n")
        f.write("// 来源：src/scripts/example-samples.json 的固定虚构样本，逐条跑确定性引擎得到。\n")
        f.write("// 版本号取 engine/prompts.py 的 RULES_VERSION，与真实引擎输出同构。\n")
        f.write("// 内容是虚构的，不指向任何公司。\n")
        f.write("export const EXAMPLE_REPORTS = ")
        json.dump(final, f, ensure_ascii=False, indent=2)
        f.write(";\n\n")
        f.write("export function getExampleReport(overall) {\n")
        f.write("  return EXAMPLE_REPORTS[overall] || null;\n")
        f.write("}\n")

    for overall in ORES:
        r = final[overall]
        dims = ",".join("%s=%s" % (d["key"], d["level"]) for d in r.get("dimensions", []))
        print("  %-8s overall=%-8s rules_version=%s findings=%d  [%s]" % (
            overall, r.get("overall"), r.get("rules_version"), len(r.get("findings", [])), dims))

    print("\n已写入:", OUT_FILE, os.path.getsize(OUT_FILE), "bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
