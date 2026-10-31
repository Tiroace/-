"""把「警示语/反例/正规流程」类话术生成的用例从 real_text 主集里剔除。

背景（2026-10-31 实测）：
`data/testset/real_phrases_v1.json` 里混了 7 条非招聘话术——
「入职前任何费用一律拒绝」「拒绝空白合同」「超高薪资、特殊渠道招聘大概率为骗局」
「报考人员均需通过笔试、面试、公示等环节」。这些是**反诈提示和正规流程**，
不是骗术。

`build_real_cases.py` 把它们当成招聘话术，塞进了「岗位要求」栏，于是生成出
「招聘岗位：运营助理 / 岗位要求：入职前任何费用一律拒绝」这种假广告，还把
结论标成 red。这不是引擎漏判，是语料生成错了——同一句话放进「岗位要求」栏，
引擎按骗术判红反而是对的。

处理：把这批用例从 real_text 主集移出，单独存 `real_warning_cases_v1.jsonl`，
主集只留真招聘话术。原始文件不动，保证可回溯。

用法：python scripts/split_warning_cases.py [--apply]
  不带 --apply 只打印将要移动的清单（dry run）。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PHRASES = ROOT / "data" / "testset" / "real_phrases_v1.json"
CASES = ROOT / "data" / "testset" / "real_cases_v1.jsonl"
OUT_WARNING = ROOT / "data" / "testset" / "real_warning_cases_v1.jsonl"
BACKUP = ROOT / "data" / "testset" / "real_cases_v1.jsonl.bak"

# 类别里带这些词的，是「提示/反例/正规」，不是骗术本身
NON_SCAM_MARKERS = ("反例", "警示", "正规")


def non_scam_phrases() -> dict[str, dict]:
    data = json.loads(PHRASES.read_text(encoding="utf-8"))
    items = data["phrases"] if isinstance(data, dict) else data
    return {
        p["id"]: p
        for p in items
        if any(m in (p.get("category") or "") for m in NON_SCAM_MARKERS)
    }


def main() -> int:
    apply = "--apply" in sys.argv
    bad = non_scam_phrases()
    rows = [
        json.loads(line)
        for line in CASES.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    moved, kept = [], []
    for row in rows:
        text = (ROOT / row["ocr_text"]).read_text(encoding="utf-8")
        matched = [pid for pid, p in bad.items() if p["text"] in text]
        if matched:
            row = dict(row)
            row["track"] = "warning_phrase"
            row["notes"] = (
                f"原 real_text；话术 {matched[0]} 属「{bad[matched[0]]['category']}」，"
                "是提示/反例而非骗术，故不计入 real_text 主集。"
                + (row.get("notes") or "")
            )
            moved.append(row)
        else:
            kept.append(row)

    print(f"非招聘话术：{sorted(bad)}")
    print(f"原用例 {len(rows)} 条 → 移出 {len(moved)} 条，保留 {len(kept)} 条")
    for r in moved:
        print("  -", r["id"])
    if not apply:
        print("\n（dry run，未写文件；加 --apply 执行）")
        return 0

    if not BACKUP.exists():
        BACKUP.write_text(CASES.read_text(encoding="utf-8"), encoding="utf-8")
    with CASES.open("w", encoding="utf-8", newline="\n") as fh:
        for r in kept:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    with OUT_WARNING.open("w", encoding="utf-8", newline="\n") as fh:
        for r in moved:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"\n已写入：{CASES.name}（{len(kept)} 条）、{OUT_WARNING.name}（{len(moved)} 条）")
    print(f"备份：{BACKUP.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
