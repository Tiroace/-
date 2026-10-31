"""测试集双轨迁移与校验工具

用途：
1. 把现有 index.jsonl 迁移到双轨格式（补 track / source.type 等字段）
2. 校验测试集是否满足双轨规范
3. 统计真实/合成数量与覆盖度

用法：
    python scripts/testset_tools.py migrate     # 迁移旧格式
    python scripts/testset_tools.py check       # 校验
    python scripts/testset_tools.py stats       # 统计
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "data" / "testset" / "index.jsonl"
OCR_DIR = ROOT / "data" / "testset" / "ocr"

DIMENSIONS = ["fee", "work", "title", "pay", "company", "contract"]
DIM_LEVELS = {"red", "amber", "green", "none"}
OVERALL = {"red", "amber", "green", "unknown"}


def load() -> list[dict]:
    if not INDEX.is_file():
        return []
    rows = []
    for line in INDEX.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def save(rows: list[dict]) -> None:
    INDEX.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )


def migrate() -> None:
    """旧格式 → 双轨格式。

    两个变更：
    1. 顶层补 track / source(对象) / style / difficulty / masked / notes
    2. 旧格式把标注放顶层（overall / dimensions / patterns），
       新规范统一收进 label 对象（label.overall / label.dimensions / label.patterns）

    按路线令：现有 20 条全部是「按公开案例仿写的构造样例」，归 synthetic 轨道。
    """
    rows = load()
    changed = 0
    for r in rows:
        touched = False

        # ---- 1. 标注收进 label ----
        if "label" not in r:
            label = {}
            if "overall" in r:
                label["overall"] = r.pop("overall")
            if "dimensions" in r:
                label["dimensions"] = r.pop("dimensions")
            if "patterns" in r:
                label["patterns"] = r.pop("patterns")
            r["label"] = label
            touched = True

        # ---- 2. 双轨字段 ----
        if "track" not in r:
            r["track"] = "synthetic"
            touched = True
        if not isinstance(r.get("source"), dict):
            old = r.get("source") or ""
            r["source"] = {
                "type": "synthetic",
                "url": None,
                "collected_at": "2026-10-31",
                "note": str(old),
            }
            touched = True
        if "style" not in r:
            r["style"] = "job_detail"
            touched = True
        if "difficulty" not in r:
            r["difficulty"] = "easy"
            touched = True
        if "masked" not in r:
            r["masked"] = True
            touched = True
        if "notes" not in r:
            r["notes"] = ""
            touched = True

        # ---- 3. id 前缀与轨道对齐 ----
        if r["track"] == "synthetic" and not r["id"].startswith("S"):
            r["legacy_id"] = r["id"]
            if r["id"].startswith("T"):
                r["id"] = "S" + r["id"][1:].zfill(4)
            else:
                r["id"] = "S" + r["id"]
            touched = True

        changed += 1 if touched else 0
    save(rows)
    print(f"迁移完成：{changed}/{len(rows)} 条被更新")


def check() -> int:
    rows = load()
    problems: list[str] = []
    ids = Counter()
    for r in rows:
        rid = r.get("id", "?")
        ids[rid] += 1

        track = r.get("track")
        if track not in ("real", "synthetic"):
            problems.append(f"{rid}: track 非法或缺失（{track}）")
            continue

        # id 前缀与轨道一致
        prefix = rid[0] if rid else "?"
        if track == "real" and prefix != "R":
            problems.append(f"{rid}: real 轨道但 id 不以 R 开头")
        if track == "synthetic" and prefix != "S":
            problems.append(f"{rid}: synthetic 轨道但 id 不以 S 开头")

        src = r.get("source")
        if not isinstance(src, dict):
            problems.append(f"{rid}: source 必须是对象")
        else:
            if not src.get("type"):
                problems.append(f"{rid}: source.type 缺失")
            if track == "real" and not src.get("url"):
                problems.append(f"{rid}: real 轨道必须有来源 url")

        if track == "real" and r.get("masked") is not True:
            problems.append(f"{rid}: real 轨道必须 masked=true（打码后入库）")

        label = r.get("label") or {}
        if label.get("overall") not in OVERALL:
            problems.append(f"{rid}: label.overall 非法（{label.get('overall')}）")
        dims = label.get("dimensions") or {}
        missing = [d for d in DIMENSIONS if d not in dims]
        if missing:
            problems.append(f"{rid}: 缺维度 {missing}")
        for d, v in dims.items():
            if d in DIMENSIONS and v not in DIM_LEVELS:
                problems.append(f"{rid}: 维度 {d} 等级非法（{v}）")

        ocr = r.get("ocr_text")
        if ocr and not (ROOT / ocr).is_file():
            problems.append(f"{rid}: OCR 文本不存在（{ocr}）")

    dup = [k for k, v in ids.items() if v > 1]
    if dup:
        problems.append(f"id 重复：{dup}")

    if problems:
        print(f"校验失败：{len(problems)} 个问题")
        for p in problems[:30]:
            print("  -", p)
        return 1
    print(f"校验通过：{len(rows)} 条全部合规")
    return 0


def stats() -> None:
    rows = load()
    by_track = Counter(r.get("track", "未标注") for r in rows)
    by_overall = Counter((r.get("label") or {}).get("overall", "?") for r in rows)
    by_style = Counter(r.get("style", "?") for r in rows)
    by_diff = Counter(r.get("difficulty", "?") for r in rows)

    print(f"总计 {len(rows)} 条")
    print(f"  轨道分布：{dict(by_track)}（目标：real≥120，合计 300）")
    print(f"  结论分布：{dict(by_overall)}")
    print(f"  样式分布：{dict(by_style)}")
    print(f"  难度分布：{dict(by_diff)}")

    real_target, total_target = 120, 300
    real_n = by_track.get("real", 0)
    print()
    print(f"缺口：real 还差 {max(0, real_target - real_n)} 条；总计还差 {max(0, total_target - len(rows))} 条")


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "stats"
    if cmd == "migrate":
        migrate()
        return 0
    if cmd == "check":
        return check()
    if cmd == "stats":
        stats()
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
