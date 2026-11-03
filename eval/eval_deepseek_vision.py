"""DeepSeek 识图 vs 旧规则引擎：对照测试脚本（改造令第四节）。

读：D:\\程序上线资料准备\\面试请等等-测试答案表.xlsx 的「答案表」页（跳过「示例」开头的行）
截图：D:\\程序上线资料准备\\测试截图\\<文件名>
写：D:\\程序上线资料准备\\测试结果.xlsx（每张一行）
   答案表只读，脚本永不写回。

用法：
    python eval/eval_deepseek_vision.py                # 思考开、关各跑一遍
    python eval/eval_deepseek_vision.py --mode off     # 只跑关思考
    python eval/eval_deepseek_vision.py --limit 3      # 先拿 3 张试跑

提示词来自 rules/prompt_v1.txt（与小程序同一份），编号白名单来自 rules/patterns_v1.json，
校验规则与前端 judge.js 完全一致：编号须在白名单、证据须在模型抄录的 text 里逐字找到。
"""
from __future__ import annotations

import base64
import io
import json
import re
import statistics
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _console import safe_console  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
KEY_FILE = Path(r"D:\程序上线资料准备\deepseek-key.txt")
XLSX = Path(r"D:\程序上线资料准备\面试请等等-测试答案表.xlsx")
SHOT_DIR = Path(r"D:\程序上线资料准备\测试截图")
OUT = Path(r"D:\程序上线资料准备\测试结果.xlsx")
PROMPT_FILE = ROOT / "rules" / "prompt_v1.txt"
PATTERNS_FILE = ROOT / "rules" / "patterns_v1.json"

API_URL = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-flash"
MAX_SIDE = 1600
JPEG_Q = 80
TIMEOUT = 90

# DeepSeek 官网定价（元 / 百万 token）。用前请核对官网，脚本把用到的价格打印出来。
PRICE_INPUT = 2.0
PRICE_OUTPUT = 3.0


def load_key() -> str:
    if not KEY_FILE.is_file():
        raise SystemExit(f"找不到密钥文件：{KEY_FILE}")
    return KEY_FILE.read_text(encoding="utf-8").strip()


def load_patterns() -> dict[str, dict]:
    data = json.loads(PATTERNS_FILE.read_text(encoding="utf-8"))
    return {p["pattern_id"]: p for p in (data.get("patterns") or [])}


def red_yellow_green(hits: list[dict], patterns: dict[str, dict], is_job: bool) -> str:
    """与前端 localReport 同一套规则：任一红→红；否则有黄→黄；否则绿；不是招聘→unknown。"""
    if not is_job:
        return "unknown"
    levels = []
    for h in hits:
        p = patterns.get(h["pattern_id"]) or {}
        lv = str(p.get("level") or "").lower()
        levels.append("red" if lv in ("high", "red") else ("green" if lv == "green" else "amber"))
    if "red" in levels:
        return "red"
    if "amber" in levels:
        return "amber"
    return "green"


def validate_hits(raw: dict, text: str, patterns: dict[str, dict]) -> tuple[list[dict], list[dict]]:
    """返回 (通过的命中, 被丢弃的命中)。规则与 src/src/services/judge.js 完全一致。"""
    norm = lambda s: re.sub(r"\s+", "", str(s or ""))  # noqa: E731
    body = norm(text)
    kept, dropped, seen = [], [], set()
    for h in (raw.get("hits") or []) if isinstance(raw, dict) else []:
        if not isinstance(h, dict):
            continue
        pid, ev = h.get("pattern_id"), h.get("evidence")
        if pid not in patterns:
            dropped.append({**h, "why": "编号不在白名单（模型编造）"})
            continue
        if not ev or not body or norm(ev) not in body:
            dropped.append({**h, "why": "证据在抄录文字里找不到"})
            continue
        if pid in seen:
            dropped.append({**h, "why": "重复编号"})
            continue
        seen.add(pid)
        kept.append(h)
    return kept, dropped


def to_base64(path: Path) -> tuple[str, int]:
    from PIL import Image

    im = Image.open(path).convert("RGB")
    scale = min(1.0, MAX_SIDE / max(im.size))
    if scale < 1.0:
        im = im.resize((int(im.width * scale), int(im.height * scale)))
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=JPEG_Q)
    raw = buf.getvalue()
    return base64.b64encode(raw).decode(), len(raw)


def call_deepseek(key: str, prompt: str, b64: str, *, thinking_off: bool) -> dict:
    body = {
        "model": MODEL,
        "temperature": 0,
        "max_tokens": 2000,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": [
                {"type": "text", "text": "请识别并判断这张招聘截图。"},
                {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + b64}},
            ]},
        ],
    }
    if thinking_off:
        body["thinking"] = {"type": "disabled"}
    req = urllib.request.Request(
        API_URL,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + key},
    )
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return {"error": f"HTTP {exc.code}", "elapsed": time.perf_counter() - t0}
    elapsed = time.perf_counter() - t0
    content = ((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "{}"
    try:
        raw = json.loads(content)
    except json.JSONDecodeError:
        return {"error": "BAD_JSON", "elapsed": elapsed, "usage": data.get("usage") or {}}
    return {"raw": raw, "usage": data.get("usage") or {}, "elapsed": elapsed}


def cost_of(usage: dict) -> float:
    pin = int(usage.get("prompt_tokens") or 0)
    pout = int(usage.get("completion_tokens") or 0)
    return pin / 1e6 * PRICE_INPUT + pout / 1e6 * PRICE_OUTPUT


def run_legacy(image: Path) -> dict:
    """对照组：RapidOCR + 规则引擎（服务器现在跑的同一套）。"""
    from engine.adapters.ocr import make_ocr_adapter
    from engine.config import default_config
    from engine.pipeline import analyze

    cfg = default_config()
    cfg.use_dedupe = False
    cfg.report_dir = None
    t0 = time.perf_counter()
    try:
        ocr = make_ocr_adapter(getattr(cfg, "ocr_backend", "rapidocr"))
        text = ocr.extract([image]).text
        rep = analyze([str(image)], text, config=cfg).report
    except Exception as exc:  # 单张失败不影响整批
        return {"error": f"{type(exc).__name__}", "elapsed": time.perf_counter() - t0}
    return {
        "overall": rep.get("overall"),
        "hits": [f.get("pattern_id") or f.get("rule_id") for f in (rep.get("findings") or [])],
        "text_len": len(re.sub(r"\s", "", text or "")),
        "elapsed": time.perf_counter() - t0,
    }


def read_cases() -> list[dict]:
    if not XLSX.is_file():
        raise SystemExit(f"找不到答案表：{XLSX}")
    wb = openpyxl.load_workbook(XLSX, data_only=True)
    ws = wb["答案表"] if "答案表" in wb.sheetnames else wb[wb.sheetnames[0]]
    rows = list(ws.iter_rows(min_row=2, values_only=True))
    cases, skipped = [], []
    for row in rows:
        if not row or not row[0]:
            continue
        no = str(row[0]).strip()
        if no.startswith("示例"):
            continue
        fname = (row[1] or "").strip() if len(row) > 1 else ""
        if not fname:
            skipped.append(no)
            continue
        cases.append({
            "no": no,
            "file": fname,
            "boss": str(row[2] or "").strip(),
            "desc": str(row[3] or "").strip(),
            "boss_patterns": str(row[4] or "").strip(),
            "note": str(row[5] or "").strip() if len(row) > 5 else "",
        })
    if skipped:
        print(f"注意：{len(skipped)} 行没有文件名，跳过：{skipped[:5]}")
    return cases


def norm_level(s: str) -> str:
    m = {"红": "red", "黄": "amber", "绿": "green", "红黄": "red", "不确定": ""}
    return m.get(str(s or "").strip(), "")


def stats(rows: list[dict], judge_key: str, detail_key: str) -> dict:
    """抓坑率 / 冤枉率 / 完全一致 / 平均耗时 / 平均花费。"""
    catches = catch_hits = 0
    green_total = false_red = 0
    agree = 0
    lat, costs = [], []
    for r in rows:
        boss = norm_level(r.get("boss") or "")
        got = r.get(judge_key) or ""
        if boss in ("red", "amber"):
            catches += 1
            if got in ("red", "amber"):
                catch_hits += 1
        if boss == "green":
            green_total += 1
            if got == "red":
                false_red += 1
        if boss and got and boss == got:
            agree += 1
        d = r.get(detail_key) or {}
        if d.get("elapsed"):
            lat.append(d["elapsed"])
        if d.get("cost") is not None:
            costs.append(d["cost"])
    total = len([r for r in rows if norm_level(r.get("boss") or "")])
    return {
        "n": total,
        "catch": (catch_hits, catches),
        "false_red": (false_red, green_total),
        "agree": (agree, total),
        "latency": statistics.mean(lat) if lat else 0,
        "cost": statistics.mean(costs) if costs else 0,
    }


def pct(a: int, b: int) -> str:
    return f"{a}/{b} = {a / b * 100:.0f}%" if b else "0/0"


def main() -> int:
    safe_console()
    key = load_key()
    prompt = PROMPT_FILE.read_text(encoding="utf-8")
    patterns = load_patterns()
    cases = read_cases()
    if not cases:
        print("答案表里没有有效行（T01… 都没有文件名）。请老板先填答案表和放截图。")
        return 2
    if "--limit" in sys.argv:
        cases = cases[: int(sys.argv[sys.argv.index("--limit") + 1])]
    modes = [True, False] if "--mode" not in sys.argv else [sys.argv[sys.argv.index("--mode") + 1] != "on"]

    print(f"用例 {len(cases)} 张；套路库 {len(patterns)} 条；提示词 {len(prompt)} 字")
    print(f"计价：输入 {PRICE_INPUT} 元/百万 token，输出 {PRICE_OUTPUT} 元/百万 token（请与官网核对）\n")

    rows = []
    for c in cases:
        img = SHOT_DIR / c["file"]
        if not img.is_file():
            print(f"  跳过 {c['no']}：截图不存在 {img}")
            continue
        b64, raw_len = to_base64(img)
        rec = {"no": c["no"], "file": c["file"], "boss": c["boss"], "desc": c["desc"],
               "boss_patterns": c["boss_patterns"]}
        for mode_name, off in (("off", True), ("on", False)):
            if off not in modes:
                continue
            r = call_deepseek(key, prompt, b64, thinking_off=off)
            if "error" in r:
                rec[f"ds_{mode_name}"] = {"error": r["error"]}
                continue
            raw = r["raw"]
            text = str(raw.get("text") or "")
            kept, dropped = validate_hits(raw, text, patterns)
            rec[f"ds_{mode_name}"] = {
                "overall": red_yellow_green(kept, patterns, raw.get("is_job_posting") is not False
                                            and len(re.sub(r"\s", "", text)) >= 20),
                "hits": [h["pattern_id"] for h in kept],
                "dropped": [d.get("pattern_id") for d in dropped],
                "evidence": [h["evidence"] for h in kept],
                "text_len": len(re.sub(r"\s", "", text)),
                "elapsed": r["elapsed"],
                "cost": cost_of(r["usage"]),
                "usage": r["usage"],
            }
        rec["legacy"] = run_legacy(img)
        rows.append(rec)
        print(f"  {c['no']} 老板={c['boss'] or '?'} "
              f"关思考={rec.get('ds_off', {}).get('overall', '?')} "
              f"开思考={rec.get('ds_on', {}).get('overall', '?')} "
              f"旧规则={rec.get('legacy', {}).get('overall', '?')}")

    # ---------- 写 xlsx ----------
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "逐张结果"
    header = ["编号", "截图", "老板判断", "老板描述的坑", "老板填的套路",
              "关思考-模型判断", "关思考-命中套路", "关思考-证据原文", "关思考-字数", "关思考-耗时s",
              "开思考-模型判断", "开思考-命中套路", "开思考-耗时s",
              "旧规则判断", "旧规则命中", "旧规则-耗时s", "关思考-花费元", "是否一致(关思考)", "备注"]
    ws.append(header)
    for c in ws[1]:
        c.font = Font(bold=True)
        c.fill = PatternFill("solid", fgColor="E8EEF7")
    for r in rows:
        off = r.get("ds_off") or {}
        on = r.get("ds_on") or {}
        lg = r.get("legacy") or {}
        boss = norm_level(r.get("boss") or "")
        agree = ""
        if boss:
            agree = "一致" if boss == off.get("overall") else "不一致"
        ws.append([
            r["no"], r["file"], r.get("boss", ""), r.get("desc", ""), r.get("boss_patterns", ""),
            off.get("overall", off.get("error", "")), "、".join(off.get("hits") or []),
            " ｜ ".join(off.get("evidence") or []), off.get("text_len", ""),
            round(off["elapsed"], 2) if off.get("elapsed") else "",
            on.get("overall", on.get("error", "")), "、".join(on.get("hits") or []),
            round(on["elapsed"], 2) if on.get("elapsed") else "",
            lg.get("overall", lg.get("error", "")), "、".join(str(x) for x in (lg.get("hits") or []) if x),
            round(lg["elapsed"], 2) if lg.get("elapsed") else "",
            round(off.get("cost") or 0, 6), agree, r.get("note", ""),
        ])
    for col, width in zip("ABCDEFGHIJKLMNOPQRS", [8, 22, 10, 26, 18, 12, 20, 40, 8, 9, 12, 20, 9, 10, 24, 9, 10, 10, 16]):
        ws.column_dimensions[col].width = width
    for row in ws.iter_rows(min_row=2):
        for c in row:
            c.alignment = Alignment(vertical="top", wrap_text=True)

    # ---------- 汇总页 ----------
    s = wb.create_sheet("汇总")
    s.append(["指标", "关思考", "开思考", "旧规则引擎"])
    for c in s[1]:
        c.font = Font(bold=True)
        c.fill = PatternFill("solid", fgColor="E8EEF7")
    so = stats(rows, "ds_off", "ds_off")
    sn = stats(rows, "ds_on", "ds_on")
    sl = {"catch": (0, 0), "false_red": (0, 0), "agree": (0, 0), "latency": 0, "cost": 0}
    # 旧规则的手工统计
    c_hit = c_all = f_hit = f_all = a_all = 0
    lat_l = []
    for r in rows:
        boss = norm_level(r.get("boss") or "")
        got = (r.get("legacy") or {}).get("overall")
        if boss in ("red", "amber"):
            c_all += 1
            c_hit += 1 if got in ("red", "amber") else 0
        if boss == "green":
            f_all += 1
            f_hit += 1 if got == "red" else 0
        if boss and got:
            a_all += 1 if boss == got else 0
        if (r.get("legacy") or {}).get("elapsed"):
            lat_l.append(r["legacy"]["elapsed"])
    total = so["n"]
    s.append(["有坑的截图抓到了", pct(*so["catch"]), pct(*sn["catch"]), pct(c_hit, c_all)])
    s.append(["正常截图误判成红", pct(*so["false_red"]), pct(*sn["false_red"]), pct(f_hit, f_all)])
    s.append(["与老板完全一致", pct(*so["agree"]), pct(*sn["agree"]), pct(a_all, total)])
    s.append(["平均耗时(s)", round(so["latency"], 2), round(sn["latency"], 2),
              round(statistics.mean(lat_l), 2) if lat_l else 0])
    s.append(["平均每次花费(元)", round(so["cost"], 6), round(sn["cost"], 6), "0（本地推理）"])
    s.append([])
    s.append(["计价口径", f"输入 {PRICE_INPUT} 元/百万 token", f"输出 {PRICE_OUTPUT} 元/百万 token", "—"])
    s.append(["通过标准", "抓坑明显多于规则引擎、正常误判≤2、平均≤10 秒", "同左", "—"])
    for col, width in zip("ABCD", [24, 34, 34, 22]):
        s.column_dimensions[col].width = width

    wb.save(OUT)
    print(f"\n已写出：{OUT}")

    print("\n=== 汇总 ===")
    print(f"抓坑率  关思考 {pct(*so['catch'])}　开思考 {pct(*sn['catch'])}　旧规则 {pct(c_hit, c_all)}")
    print(f"冤枉红  关思考 {pct(*so['false_red'])}　开思考 {pct(*sn['false_red'])}　旧规则 {pct(f_hit, f_all)}")
    print(f"完全一致 关思考 {pct(*so['agree'])}　开思考 {pct(*sn['agree'])}　旧规则 {pct(a_all, total)}")
    print(f"平均耗时 关思考 {so['latency']:.2f}s　开思考 {sn['latency']:.2f}s　"
          f"旧规则 {(statistics.mean(lat_l) if lat_l else 0):.2f}s")
    print(f"平均花费 关思考 {so['cost']:.6f} 元　开思考 {sn['cost']:.6f} 元")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
