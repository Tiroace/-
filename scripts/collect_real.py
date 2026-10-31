"""真实轨道测试集 · 收集台账

用途：记录每一条真实截图的来源、打码状态、标注进度，方便复核与审计。
按路线令第四节：A 公开反诈案例 / B 公开投诉平台 / C 正常岗位 / D 合成。
真实截图合规红线：打码后仅内部使用、记出处链接、不批量爬取、不绕登录。

用法：
    python scripts/collect_real.py sources    # 列出四类渠道与已收集数量
    python scripts/collect_real.py add        # 交互式/参数形式登记一条来源
    python scripts/collect_real.py status     # 收集进度
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "data" / "testset" / "real_ledger.jsonl"
IMAGE_DIR = ROOT / "data" / "testset" / "images"
OCR_DIR = ROOT / "data" / "testset" / "ocr"

SOURCE_TYPES = {
    "A": "公开反诈案例（公安/网信/人社官网、主流媒体招聘诈骗报道）",
    "B": "公开投诉平台（黑猫投诉等公开页面）",
    "C": "正常岗位招聘（公开渠道，用于测误判）",
    "D": "合成（渲染器生成，无授权要求）",
}


def load_ledger() -> list[dict]:
    if not LEDGER.is_file():
        return []
    return [json.loads(l) for l in LEDGER.read_text(encoding="utf-8").splitlines() if l.strip()]


def append(entry: dict) -> None:
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def load_index() -> list[dict]:
    p = ROOT / "data" / "testset" / "index.jsonl"
    if not p.is_file():
        return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def save_index(rows: list[dict]) -> None:
    p = ROOT / "data" / "testset" / "index.jsonl"
    p.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")


def cmd_sources() -> None:
    for k, v in SOURCE_TYPES.items():
        print(f"  {k}  {v}")
    print()
    print("采集红线（路线令第四节）：")
    print("  - 只取公开可访问内容，不批量爬取、不绕登录、不用他人账号")
    print("  - 真实截图必须打码后入库（手机号/微信/QQ/身份证/银行卡/人名/门牌号）")
    print("  - 每条记录出处链接，便于复核")
    print("  - 仅内部评测使用，不对外展示")


def cmd_status() -> None:
    rows = load_index()
    ledger = load_ledger()
    real = [r for r in rows if r.get("track") == "real"]
    synth = [r for r in rows if r.get("track") == "synthetic"]
    pending = [e for e in ledger if e.get("status") == "pending_label"]

    print(f"已入 index：real {len(real)} 条 / synthetic {len(synth)} 条（合计 {len(rows)}）")
    print(f"台账登记（待处理）：{len(pending)} 条")
    if ledger:
        by_type = Counter(e.get("source_type") for e in ledger)
        print(f"台账按渠道：{dict(by_type)}")
    print()
    print(f"目标：real ≥120、合计 300")
    print(f"缺口：real 还差 {max(0, 120 - len(real))} 条；合计还差 {max(0, 300 - len(rows))} 条")


def cmd_add() -> None:
    """登记一条待处理的真实来源。

    用法：
        python scripts/collect_real.py add --type A --url "https://..." --note "内容要点"
    """
    args = sys.argv[2:]
    opts = {}
    i = 0
    while i < len(args):
        if args[i].startswith("--"):
            key = args[i][2:]
            val = args[i + 1] if i + 1 < len(args) and not args[i + 1].startswith("--") else ""
            opts[key] = val
            i += 2
        else:
            i += 1

    stype = opts.get("type", "A").upper()
    if stype not in SOURCE_TYPES:
        print(f"未知渠道类型：{stype}（可选 {list(SOURCE_TYPES)}）")
        raise SystemExit(2)

    entry = {
        "collected_at": str(date.today()),
        "source_type": stype,
        "url": opts.get("url", ""),
        "note": opts.get("note", ""),
        "status": "pending_label",
        "masked": False,
    }
    if not entry["url"]:
        print("警告：未提供 --url，真实来源必须可回查")
    append(entry)
    print(f"已登记：{stype} {entry['url'][:60]}")


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "sources":
        cmd_sources()
    elif cmd == "status":
        cmd_status()
    elif cmd == "add":
        cmd_add()
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
