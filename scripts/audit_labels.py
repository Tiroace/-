"""标注一致性审计（只读，不修改任何数据）。

背景：产品经理发现同一句「无经验骑手、月入9000元」在两批样本里标了相反等级
（RT0067/68/69 红 vs RT0118/119/120 黄），已按 D30 统一判黄。
本脚本检查测试集是否还有别处「同文不同标」，以及空标注、非法值、划分覆盖。

【快照约定】D30 修订分两次快照，报告里两份都保留：
  - 修订前（18:21）：RT0067/68/69 仍为 red，冲突 6 组
  - 修订后（D30 落库后）：再跑一次，追加到报告末尾，不覆盖上一份
每次运行都按「本次数据快照」重新生成自己的那份，历史快照作为小节保留。

用法：python scripts/audit_labels.py
输出：reports/标注一致性审计-2026-10-31.md
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CASES = ROOT / "data" / "testset" / "real_cases_v1.jsonl"
SPLITS = ROOT / "eval" / "splits.json"
OUT = ROOT / "reports" / "标注一致性审计-2026-10-31.md"

DIM_KEYS = ["fee", "work", "title", "pay", "company", "contract"]
LEGAL_OVERALL = {"red", "amber", "green", "unknown"}
LEGAL_DIM = {"red", "amber", "green", "none"}


def normalize(text: str) -> str:
    """去空格标点全半角，只留中文/字母/数字——用于判定「同一句话」。"""
    t = unicodedata.normalize("NFKC", text)
    return "".join(ch for ch in t if unicodedata.category(ch)[0] in ("L", "N"))


def body_without_header(text: str) -> str:
    """去掉第一行（岗位名/公司名这类模板头），用来抓「只差标题一行」的近重复。"""
    lines = [ln for ln in text.splitlines() if ln.strip()]
    return normalize("\n".join(lines[1:])) if len(lines) > 1 else ""


def load_cases() -> list[dict]:
    out = []
    for line in CASES.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        row["_text"] = (ROOT / row["ocr_text"]).read_text(encoding="utf-8")
        out.append(row)
    return out


def label_key(row: dict) -> tuple:
    lab = row.get("label") or {}
    dims = lab.get("dimensions") or {}
    return (lab.get("overall"), tuple(dims.get(k) for k in DIM_KEYS))


def main() -> int:
    rows = load_cases()
    by_id = {r["id"]: r for r in rows}
    import datetime

    snap = datetime.datetime.fromtimestamp(CASES.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
    d30_pending = [
        i for i in ("RT0067", "RT0068", "RT0069")
        if by_id.get(i, {}).get("label", {}).get("overall") == "red"
    ]

    # ---------------- 1. 完全相同文本的分组
    exact = defaultdict(list)
    for r in rows:
        exact[normalize(r["_text"])].append(r)

    conflicts = []       # 正文完全相同但标注不同
    consistent = []      # 正文相同且标注相同（这是正常的 3 情景组）
    for key, group in exact.items():
        if len(group) < 2:
            continue
        keys = {label_key(g) for g in group}
        if len(keys) > 1:
            conflicts.append(group)
        else:
            consistent.append(group)

    # ---------------- 2. 近重复：去掉首行后相同
    near = defaultdict(list)
    for r in rows:
        b = body_without_header(r["_text"])
        if b:
            near[b].append(r)
    near_conflicts = []
    for key, group in near.items():
        if len(group) < 2:
            continue
        # 正文完全相同的那组已在上面算过，这里只留「首行不同」的
        bodies = {normalize(g["_text"]) for g in group}
        if len(bodies) < 2:
            continue
        if len({label_key(g) for g in group}) > 1:
            near_conflicts.append(group)

    # ---------------- 3. 空标注 / 非法值
    empty, illegal = [], []
    for r in rows:
        lab = r.get("label")
        if not isinstance(lab, dict):
            empty.append((r["id"], "label 缺失"))
            continue
        if not lab.get("overall"):
            empty.append((r["id"], "缺 overall"))
        dims = lab.get("dimensions")
        if not isinstance(dims, dict):
            empty.append((r["id"], "缺 dimensions"))
        else:
            miss = [k for k in DIM_KEYS if k not in dims]
            if miss:
                empty.append((r["id"], f"dimensions 缺 {miss}"))
        if lab.get("overall") and lab["overall"] not in LEGAL_OVERALL:
            illegal.append((r["id"], "overall", lab["overall"]))
        for k, v in (dims or {}).items():
            if k in DIM_KEYS and v not in LEGAL_DIM:
                illegal.append((r["id"], k, v))

    # ---------------- 4. 划分覆盖
    splits = json.loads(SPLITS.read_text(encoding="utf-8"))
    practice = list(splits.get("practice") or [])
    holdout = list(splits.get("holdout") or [])
    all_ids = set(by_id)
    in_p, in_h = set(practice), set(holdout)
    overlap = sorted(in_p & in_h)
    missing = sorted(all_ids - (in_p | in_h))
    extra = sorted((in_p | in_h) - all_ids)
    dup_p = sorted({i for i in practice if practice.count(i) > 1})
    dup_h = sorted({i for i in holdout if holdout.count(i) > 1})

    # 划分里的「多余 id」可能是合成轨（index.jsonl 的 S 开头），核实清楚再报
    synth_ids: set[str] = set()
    index_path = ROOT / "data" / "testset" / "index.jsonl"
    if index_path.is_file():
        for line in index_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                synth_ids.add(json.loads(line)["id"])
    extra_synth = [i for i in extra if i in synth_ids]
    extra_unknown = [i for i in extra if i not in synth_ids]

    # ---------------- 报告
    lines = []
    A = lines.append
    A("# 标注一致性审计（2026-10-31）")
    A("")
    A("- 审计对象：`data/testset/real_cases_v1.jsonl` 全部真实用例")
    A(f"- 用例总数：**{len(rows)}** 条")
    A("- 性质：**只读审计，未修改任何数据**；仅报告，不下结论")
    A(f"- 数据快照时间（文件修改时间）：`{snap}`")
    if d30_pending:
        A(f"- **快照时点：D30 修订尚未执行**（{'、'.join(d30_pending)} 仍为 red）。"
          "本审计结果对应修订前的数据；D30 执行后请重跑本脚本。")
    else:
        A("- D30 修订已生效（RT0067/68/69 已为 amber）。")
    A("- 生成脚本：`scripts/audit_labels.py`（可复跑）")
    A("")
    A("## 一、正文完全相同但标注不一致")
    A("")
    if conflicts:
        A(f"**{len(conflicts)} 组**，共涉及 "
          f"{sum(len(g) for g in conflicts)} 条用例：")
        A("")
        for group in conflicts:
            ids = [g["id"] for g in group]
            A(f"### 冲突组：{'、'.join(ids)}")
            A("")
            A("| id | overall | " + " | ".join(DIM_KEYS) + " |")
            A("| --- | --- | " + " | ".join(["---"] * len(DIM_KEYS)) + " |")
            for g in group:
                lab = g["label"]
                dims = lab.get("dimensions") or {}
                A(f"| {g['id']} | {lab.get('overall')} | "
                  + " | ".join(str(dims.get(k)) for k in DIM_KEYS) + " |")
            diff_dims = [
                k for k in DIM_KEYS
                if len({(g['label'].get('dimensions') or {}).get(k) for g in group}) > 1
            ]
            diff_overall = len({g['label'].get('overall') for g in group}) > 1
            A("")
            A(f"- 差异：overall {'不同' if diff_overall else '相同'}；"
              f"维度差异 {diff_dims or '无'}")
            A(f"- 正文首行：`{group[0]['_text'].strip().splitlines()[0]}`")
            A("")
    else:
        A("未发现正文完全相同却标注不一致的组。")
        A("")
    if consistent:
        A(f"（另有 {len(consistent)} 组正文相同且标注一致，属正常的同文复用："
          f"{', '.join('/'.join(g['id'] for g in grp) for grp in consistent[:6])}"
          f"{' …' if len(consistent) > 6 else ''}）")
        A("")

    A("## 二、近重复（只差岗位名/公司名一行）但标注不一致")
    A("")
    if near_conflicts:
        A(f"**{len(near_conflicts)} 组**：")
        A("")
        for group in near_conflicts:
            A(f"### {'、'.join(g['id'] for g in group)}")
            A("")
            A("| id | overall | 首行 |")
            A("| --- | --- | --- |")
            for g in group:
                first = g["_text"].strip().splitlines()[0] if g["_text"].strip() else ""
                A(f"| {g['id']} | {g['label'].get('overall')} | `{first}` |")
            A("")
    else:
        A("未发现「只差一行却标注不一致」的组。")
        A("")

    A("## 三、空标注与非法值")
    A("")
    A(f"- 空标注：**{len(empty)}** 处")
    for item in empty[:20]:
        A(f"  - `{item[0]}`：{item[1]}")
    A(f"- 非法值：**{len(illegal)}** 处")
    for item in illegal[:20]:
        A(f"  - `{item[0]}` 的 `{item[1]}` = `{item[2]}`")
    A("")

    A("## 四、practice / holdout 划分覆盖")
    A("")
    A(f"- 划分文件：`eval/splits.json`（version `{splits.get('version')}`，"
      f"frozen_at `{splits.get('frozen_at')}`）")
    A(f"- practice {len(practice)} 条、holdout {len(holdout)} 条，"
      f"合计 {len(practice) + len(holdout)} 条；用例总数 {len(all_ids)} 条")
    A("")
    A(f"- 未被划分覆盖：**{len(missing)}** 条 {missing[:20] if missing else '（无）'}")
    A(f"- 划分里有、数据里没有：**{len(extra)}** 条")
    if extra_synth:
        A(f"  - 其中 **{len(extra_synth)} 条是合成轨**（`index.jsonl` 的 S 开头用例，"
          f"不属于真实用例集，属正常）：{extra_synth[:5]} …")
    if extra_unknown:
        A(f"  - **{len(extra_unknown)} 条无法归类（需核实）**：{extra_unknown}")
    A(f"- 同时落在两组：**{len(overlap)}** 条 {overlap[:20] if overlap else '（无）'}")
    A(f"- 组内重复 id：practice {dup_p or '（无）'}、holdout {dup_h or '（无）'}")
    A("")
    A(f"**结论（覆盖）**：{len(all_ids)} 条真实用例"
      f"{'全部被划分覆盖，无遗漏、无重叠。' if not missing and not overlap and not extra_unknown else '存在上述问题，详见上表。'}")
    A("")

    A("## 五、需要产品经理拍板的标注冲突")
    A("")
    if conflicts or near_conflicts:
        A("以下冲突**只报警，不下结论**，需产品经理按 D30 口径逐组定：")
        A("")
        n = 0
        for group in conflicts + near_conflicts:
            n += 1
            ids = "、".join(g["id"] for g in group)
            first = group[0]["_text"].strip().splitlines()[0]
            A(f"{n}. `{ids}`（正文首行 `{first}`）")
        A("")
    else:
        A("无。")
        A("")
    A("---")
    A("")
    A("**说明**：本审计只做结构一致性检查，不判断标注「对不对」。"
      "同一句话在不同语境下标注不同，也可能是合理的——需产品经理确认后统一。")

    # ---------------- 落盘：每次运行保存独立快照，不覆盖历史
    #
    # 为什么不能覆盖：这份报告的价值在于「什么时候的什么结论」。D30 修订前
    # 有 6 组冲突、修订后剩 3 组，两份都必须留着；只留一份的话，后来人无法
    # 判断某个指标是基于哪版标注算的。
    OUT.parent.mkdir(parents=True, exist_ok=True)
    phase = "D30修订后" if not d30_pending else "D30修订前"
    snap_name = f"标注一致性审计-2026-10-31-{phase}.md"
    snap_path = OUT.parent / snap_name
    content = "\n".join(lines) + "\n"
    snap_path.write_text(content, encoding="utf-8")

    # 兼容旧路径：最新一次的结论也写到约定文件名，方便别人直接打开
    OUT.write_text(content, encoding="utf-8")

    # 两份快照的对照表（修订前那份已归档为固定文件名）
    before = OUT.parent / "标注一致性审计-2026-10-31-修订前18-21.md"
    rows_md = []
    if before.is_file():
        rows_md.append("| 修订前（18:21） | 6 | 见文件 | `标注一致性审计-2026-10-31-修订前18-21.md` |")
    rows_md.append(
        f"| {phase}（{snap}） | {len(conflicts)} | {len(near_conflicts)} | `{snap_name}` |"
    )
    index_path = OUT.parent / "标注一致性审计-索引.md"
    summary = [
        "# 标注一致性审计 · 快照对照",
        "",
        "每次运行 `scripts/audit_labels.py` 生成一份独立快照，**历史快照不覆盖**。",
        "",
        "| 阶段 | 正文完全相同冲突组 | 近重复冲突组 | 快照文件 |",
        "| --- | ---: | ---: | --- |",
        *rows_md,
        "",
        "> 修订前那份的「近重复冲突组」数见该文件正文第二节。",
    ]
    index_path.write_text("\n".join(summary) + "\n", encoding="utf-8")

    print(f"用例：{len(rows)} 条")
    print(f"完全同文冲突组：{len(conflicts)}")
    print(f"近重复冲突组：{len(near_conflicts)}")
    print(f"空标注：{len(empty)}；非法值：{len(illegal)}")
    print(f"划分未覆盖：{len(missing)}；多余：{len(extra)}；重叠：{len(overlap)}")
    print(f"报告：{OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
