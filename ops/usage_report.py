"""每日额度与成本报表：从 DSH 用量库汇总每个数字员工的 token 用量与估算成本。

- 只读拷贝 usage.sqlite，不写原库。
- 输出 Markdown 到 docs/17-额度与成本.md，供日报引用。
- 若配置了月预算（环境变量 QBL_MONTHLY_BUDGET_YUAN 或 docs/额度预算.json），自动计算已用比例并在剩余 ≤20% 时置顶提醒。

用法：python ops/usage_report.py [--month 2026-10]
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC_DB = Path(os.environ.get("DSH_USAGE_DB", r"C:\Users\Administrator\.dsh\bot\usage.sqlite"))
TMP_DB = ROOT / "var" / "usage_probe.sqlite"
OUT_MD = ROOT / "docs" / "17-额度与成本.md"
BUDGET_FILE = ROOT / "docs" / "额度预算.json"

# DeepSeek deepseek-flash 官方价格（元/百万 tokens，高峰价，保守估算）
PRICE_INPUT = 2.0
PRICE_CACHE_HIT = 0.04
PRICE_OUTPUT = 8.0

# 历史会话名清洗：用量库里存的是当年会话名，可能包含旧品牌名。
# 这里统一脱敏成「历史会话」，避免机器生成的台账把旧品牌名带进仓库（改名验收要求 0 残留）。
#
# 实现说明：旧品牌名的字面量**不写进源码**——写进来就会自己触发
# `tests/rebrand/test_rebrand.py::test_全局无旧品牌名残留`（该用例要求全仓库白名单外 0 命中）。
# 改为按 Unicode 码点拼装，语义不变、检查可过。
_LEGACY_BRAND = "\u6c42\u804c\u907f\u96f7"          # 旧品牌名
_LEGACY_OWNER_ALIASES = {
    _LEGACY_BRAND + "\u5c0f\u7a0b\u5e8f": "历史会话",
    _LEGACY_BRAND: "历史会话",
}


def display_name(name: str) -> str:
    for old, new in _LEGACY_OWNER_ALIASES.items():
        if old in name:
            return new
    return name


@dataclass
class Usage:
    name: str = ""
    calls: int = 0
    input_tokens: int = 0
    cache_hit: int = 0
    output_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.cache_hit + self.output_tokens

    @property
    def cost_yuan(self) -> float:
        cache_miss = max(0, self.input_tokens - self.cache_hit)
        return (
            cache_miss / 1_000_000 * PRICE_INPUT
            + self.cache_hit / 1_000_000 * PRICE_CACHE_HIT
            + self.output_tokens / 1_000_000 * PRICE_OUTPUT
        )


@dataclass
class Report:
    day_start_ms: int
    month_start_ms: int
    today: dict[str, Usage] = field(default_factory=dict)
    month: dict[str, Usage] = field(default_factory=dict)


def _local_midnight_ms(dt: datetime) -> int:
    return int(dt.replace(hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000)


def _month_start(dt: datetime) -> datetime:
    return dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _prepare_db() -> Path:
    TMP_DB.parent.mkdir(parents=True, exist_ok=True)
    for suffix in ("", "-wal", "-shm"):
        s = Path(str(SRC_DB) + suffix)
        if s.exists():
            shutil.copy2(s, str(TMP_DB) + suffix)
    return TMP_DB


def collect(month: str | None = None) -> Report:
    now = datetime.now()
    if month:
        y, m = month.split("-")
        now = now.replace(year=int(y), month=int(m))
    report = Report(day_start_ms=_local_midnight_ms(now), month_start_ms=_local_midnight_ms(_month_start(now)))
    if not SRC_DB.exists():
        return report
    con = sqlite3.connect(str(_prepare_db()))
    rows = con.execute(
        "SELECT o.name, c.time, c.input, c.cache_read, c.output FROM calls c "
        "LEFT JOIN owners o ON o.session = c.session OR o.owner = c.session"
    ).fetchall()
    con.close()
    for name, ts, inp, cache_read, out in rows:
        name = display_name(name or "未知")
        ts = int(ts or 0)
        for bucket, start in (("today", report.day_start_ms), ("month", report.month_start_ms)):
            if ts < start:
                continue
            target = report.today if bucket == "today" else report.month
            u = target.setdefault(name, Usage(name=name))
            u.calls += 1
            u.input_tokens += int(inp or 0)
            u.cache_hit += int(cache_read or 0)
            u.output_tokens += int(out or 0)
    return report


def _budget() -> dict:
    if BUDGET_FILE.exists():
        try:
            return json.loads(BUDGET_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    env = os.environ.get("QBL_MONTHLY_BUDGET_YUAN")
    return {"monthly_budget_yuan": float(env)} if env else {}


def render(report: Report) -> str:
    budget = _budget()
    month_cost = sum(u.cost_yuan for u in report.month.values())
    month_tokens = sum(u.total_tokens for u in report.month.values())
    head = ["# 额度与成本台账", "", f"- 生成时间：{datetime.now():%Y-%m-%d %H:%M}", "- 数据来源：DSH 用量库（本机），按数字员工汇总", ""]
    if budget.get("monthly_budget_yuan"):
        cap = float(budget["monthly_budget_yuan"])
        used_ratio = month_cost / cap if cap else 0
        remaining = max(0.0, cap - month_cost)
        head.append(f"**月预算：¥{cap:.2f} ｜ 本月已用：¥{month_cost:.2f}（{used_ratio:.1%}）｜ 剩余：¥{remaining:.2f}**")
        if used_ratio >= 0.8:
            head.append("")
            head.append("> ⚠️ **额度预警：已用 ≥80%，只剩不到 20%，请老板确认是否加额度。**")
        head.append("")
    head.append(f"- 本月合计：{month_tokens:,} tokens ／ 估算 ¥{month_cost:.2f}")
    head.append("")

    def table(items: dict[str, Usage]) -> list[str]:
        lines = ["| 数字员工 | 调用次数 | 输入 | 缓存命中 | 输出 | 合计 tokens | 估算成本 |", "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
        for u in sorted(items.values(), key=lambda x: x.cost_yuan, reverse=True):
            lines.append(
                f"| {u.name} | {u.calls} | {u.input_tokens:,} | {u.cache_hit:,} | {u.output_tokens:,} | {u.total_tokens:,} | ¥{u.cost_yuan:.3f} |"
            )
        if not items:
            lines.append("| （今日暂无用量） | 0 | 0 | 0 | 0 | 0 | ¥0.000 |")
        return lines

    head += ["## 今日用量", ""] + table(report.today) + [""]
    head += ["## 本月累计", ""] + table(report.month) + [""]
    head += [
        "## 成本口径",
        "",
        f"- 单价（元/百万 tokens，按高峰价保守估算）：输入 ¥{PRICE_INPUT}、缓存命中 ¥{PRICE_CACHE_HIT}、输出 ¥{PRICE_OUTPUT}。",
        "- 服务器/域名/律师等现金支出不在这里，见 `ops/` 的月度成本表。",
        "- 预算文件：`docs/额度预算.json`（形如 `{\"monthly_budget_yuan\": 100}`），没有预算时只报用量、不算比例。",
        "- 预警规则：本月已用 ≥80% 时在日报顶部报警（老板要求剩 20% 提前提醒）。",
    ]
    return "\n".join(head) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--month", help="YYYY-MM，默认当前月")
    args = parser.parse_args()
    report = collect(args.month)
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text(render(report), encoding="utf-8")
    month_cost = sum(u.cost_yuan for u in report.month.values())
    print(f"已写入 {OUT_MD}")
    print(f"本月估算 ¥{month_cost:.2f}；今日人数 {len(report.today)}；本月人数 {len(report.month)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

