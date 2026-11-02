"""真实截图留出集的标注与校验工具（第 4 关）。

规范见 `docs/24-真实截图留出集标注规范.md`。这个工具不碰 OCR 引擎逻辑，
只负责：录入、校验字段、检查分布、报缺口。

用法：
  python scripts/annotate_screenshot.py check      # 校验 + 分布检查（最常用）
  python scripts/annotate_screenshot.py add        # 交互式加一条
  python scripts/annotate_screenshot.py stats      # 只看分布

为什么分布检查单独做：第 4 关要求「正常岗位占一半」。如果前面收的全是骗子图，
收满 60 条也凑不出这个比例，越晚发现返工越大。所以每加一条就查一次。
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "testset" / "real_screenshots_v1.jsonl"
IMAGES = ROOT / "data" / "testset" / "images"

TRACK = "real_screenshot"
DIM_KEYS = ["fee", "work", "title", "pay", "company", "contract"]
LEGAL_OVERALL = {"red", "amber", "green", "unknown"}
LEGAL_DIM = {"red", "amber", "green", "none"}
LEGAL_SOURCE = {"real_phone", "public_page"}
LEGAL_DIFFICULTY = {"easy", "medium", "hard"}

# 第 4 关门槛（规范 §三/§四）
MIN_TOTAL = 60
MIN_NORMAL_RATIO = 0.5
MIN_RED = 15
MIN_PER_STYLE = 10
MIN_DIM_NON_NONE = 8
STYLES = {"job_detail", "chat", "ad"}


def load() -> list[dict]:
    if not DATA.is_file():
        return []
    return [json.loads(x) for x in DATA.read_text(encoding="utf-8").splitlines() if x.strip()]


def validate(rows: list[dict]) -> tuple[list[str], list[str]]:
    """返回 (错误, 警告)。错误 = 必须修；警告 = 值得看一眼。"""
    errs: list[str] = []
    warns: list[str] = []
    seen: set[str] = set()

    for r in rows:
        rid = r.get("id", "<无 id>")
        if rid in seen:
            errs.append(f"{rid}: id 重复")
        seen.add(rid)

        if r.get("track") != TRACK:
            errs.append(f"{rid}: track 应为 {TRACK}，实际 {r.get('track')!r}")

        img = r.get("image")
        if not img:
            errs.append(f"{rid}: 缺 image")
        elif not (ROOT / img).is_file():
            errs.append(f"{rid}: 图片不存在 {img}")

        if r.get("masked") is not True:
            errs.append(f"{rid}: masked 未置 true（未打码的样本不许进集）")

        src = r.get("source") or {}
        st = src.get("type")
        if st not in LEGAL_SOURCE:
            errs.append(f"{rid}: source.type 应为 {LEGAL_SOURCE} 之一，实际 {st!r}")
        if st == "public_page" and not src.get("url"):
            errs.append(f"{rid}: 公开页来源必须填 source.url")
        if not src.get("collected_at"):
            errs.append(f"{rid}: 缺 source.collected_at")

        lab = r.get("label") or {}
        if lab.get("overall") not in LEGAL_OVERALL:
            errs.append(f"{rid}: label.overall 非法 {lab.get('overall')!r}")
        dims = lab.get("dimensions") or {}
        miss = [k for k in DIM_KEYS if k not in dims]
        if miss:
            errs.append(f"{rid}: dimensions 缺 {miss}")
        for k, v in dims.items():
            if k in DIM_KEYS and v not in LEGAL_DIM:
                errs.append(f"{rid}: dimensions.{k} 非法 {v!r}")
        if not (lab.get("verdict_reason") or "").strip():
            errs.append(f"{rid}: 缺 label.verdict_reason（必须一句话说清为什么）")
        elif len(lab["verdict_reason"]) > 40:
            warns.append(f"{rid}: verdict_reason 超过 40 字（{len(lab['verdict_reason'])}）")

        for k in ("annotator", "annotated_at"):
            if not r.get(k):
                errs.append(f"{rid}: 缺 {k}")
        if r.get("difficulty") not in LEGAL_DIFFICULTY:
            errs.append(f"{rid}: difficulty 非法 {r.get('difficulty')!r}")
        if not isinstance(r.get("is_normal"), bool):
            errs.append(f"{rid}: is_normal 必须是布尔值")

    return errs, warns


def check_distribution(rows: list[dict]) -> list[str]:
    """检查是否满足第 4 关的分布要求。返回未达标项（空 = 达标）。"""
    n = len(rows)
    gaps: list[str] = []
    if n < MIN_TOTAL:
        gaps.append(f"总数 {n} < {MIN_TOTAL}")

    normal = sum(1 for r in rows if r.get("is_normal") is True)
    if n:
        ratio = normal / n
        if ratio < MIN_NORMAL_RATIO:
            gaps.append(
                f"正常岗位占比 {ratio:.0%} < {MIN_NORMAL_RATIO:.0%}"
                f"（{normal}/{n}，还差 {max(0, int(MIN_TOTAL * MIN_NORMAL_RATIO) - normal)} 条正常图）"
            )

    red = sum(1 for r in rows if (r.get("label") or {}).get("overall") == "red")
    if red < MIN_RED:
        gaps.append(f"高危 red {red} < {MIN_RED}")

    styles = Counter(r.get("style") for r in rows)
    for s in STYLES:
        if styles.get(s, 0) < MIN_PER_STYLE:
            gaps.append(f"形态 {s} 只有 {styles.get(s, 0)} 条 < {MIN_PER_STYLE}")

    dim_hits = Counter()
    for r in rows:
        for k, v in ((r.get("label") or {}).get("dimensions") or {}).items():
            if k in DIM_KEYS and v not in (None, "none"):
                dim_hits[k] += 1
    for k in DIM_KEYS:
        if dim_hits.get(k, 0) < MIN_DIM_NON_NONE:
            gaps.append(f"维度 {k} 非 none 只有 {dim_hits.get(k, 0)} 次 < {MIN_DIM_NON_NONE}")

    return gaps


def stats(rows: list[dict]) -> None:
    n = len(rows)
    print(f"样本总数：{n}")
    if not n:
        print("（还没有样本。规范见 docs/24-真实截图留出集标注规范.md）")
        return
    overall = Counter((r.get("label") or {}).get("overall") for r in rows)
    print(f"结论分布：{dict(overall)}")
    normal = sum(1 for r in rows if r.get("is_normal") is True)
    print(f"正常岗位：{normal}/{n} = {normal / n:.0%}（要求 ≥{MIN_NORMAL_RATIO:.0%}）")
    print(f"形态分布：{dict(Counter(r.get('style') for r in rows))}")
    print(f"来源分布：{dict(Counter((r.get('source') or {}).get('type') for r in rows))}")
    dim_hits = Counter()
    for r in rows:
        for k, v in ((r.get("label") or {}).get("dimensions") or {}).items():
            if k in DIM_KEYS and v not in (None, "none"):
                dim_hits[k] += 1
    print(f"维度非 none 次数：{dict(dim_hits)}")


def cmd_check() -> int:
    rows = load()
    stats(rows)
    print()
    if not rows:
        print("✗ 留出集为空——第 4 关评测条件不成立，不能报数。")
        return 1
    errs, warns = validate(rows)
    gaps = check_distribution(rows)

    if errs:
        print(f"✗ 字段错误 {len(errs)} 处：")
        for e in errs[:20]:
            print("   ", e)
        if len(errs) > 20:
            print(f"    …另有 {len(errs) - 20} 处")
    if warns:
        print(f"⚠ 警告 {len(warns)} 处：")
        for w in warns[:10]:
            print("   ", w)
    if gaps:
        print(f"✗ 分布未达标 {len(gaps)} 项：")
        for g in gaps:
            print("   ", g)

    if not errs and not gaps:
        print("✓ 字段齐全、分布达标，可以进第 4 关评测：python scripts/eval_holdout.py")
        return 0
    return 1


def cmd_stats() -> int:
    stats(load())
    return 0


def cmd_add() -> int:
    rows = load()
    n = len(rows) + 1
    rid = input(f"id（回车用 RS{n:04d}）：").strip() or f"RS{n:04d}"
    img = input("图片相对路径（如 data/testset/images/RS0001.png）：").strip()
    style = input(f"形态 {sorted(STYLES)}：").strip()
    stype = input("来源类型 real_phone / public_page：").strip()
    url = ""
    if stype == "public_page":
        url = input("来源 URL：").strip()
    overall = input("结论 red/amber/green/unknown：").strip()
    dims = {}
    for k in DIM_KEYS:
        dims[k] = input(f"  维度 {k}（red/amber/green/none）：").strip() or "none"
    reason = input("一句话理由（≤40 字）：").strip()
    is_normal = input("是正常岗位吗 y/N：").strip().lower() == "y"
    difficulty = input("难度 easy/medium/hard：").strip() or "medium"
    annotator = input("标注人：").strip()
    mask = input("已打码 y/N：").strip().lower() == "y"

    import datetime

    row = {
        "id": rid,
        "track": TRACK,
        "image": img,
        "ocr_text": f"data/testset/ocr/{rid}.txt",
        "source": {
            "type": stype,
            "url": url or None,
            "collected_at": datetime.date.today().isoformat(),
        },
        "masked": mask,
        "style": style,
        "difficulty": difficulty,
        "is_normal": is_normal,
        "label": {"overall": overall, "dimensions": dims, "verdict_reason": reason},
        "annotator": annotator,
        "annotated_at": datetime.date.today().isoformat(),
    }
    rows.append(row)
    DATA.parent.mkdir(parents=True, exist_ok=True)
    with DATA.open("w", encoding="utf-8", newline="\n") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"已写入 {DATA}")
    return cmd_check()


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "check"
    if cmd == "check":
        return cmd_check()
    if cmd == "stats":
        return cmd_stats()
    if cmd == "add":
        return cmd_add()
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
