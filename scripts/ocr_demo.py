"""OCR demo：一张图进去，打印行数 / 耗时 / 前几行 / 关键字段命中。

用法：
    python scripts/ocr_demo.py <图片路径> [--limit-side-len 1000] [--threads 8] [--json]

关键字段用于快速判断「这份招聘信息该被识别出来的东西有没有读到」：
岗位、公司、薪资、地点、押金/培训费/体检费（收费类）、刷单/垫付、联系方式。
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from engine.adapters.ocr import RapidOCREngine  # noqa: E402

KEYWORDS = {
    "岗位名称": ["招聘", "岗位", "职位", "工程师", "运营", "客服", "助理", "文员", "销售", "会计", "设计"],
    "公司信息": ["公司", "有限公司", "集团", "工作室"],
    "薪资": ["薪资", "月薪", "工资", "元/月", "底薪", "提成", "日结"],
    "工作地点": ["工作地点", "地址", "市区", "路", "号", "楼"],
    "收费/押金": ["押金", "保证金", "服装费", "体检费", "培训费", "收费", "缴纳", "垫付"],
    "刷单/贷款": ["刷单", "返利", "垫付", "贷款", "分期", "助学贷"],
    "联系方式": ["电话", "微信", "QQ", "手机", "联系"],
}


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    parser = argparse.ArgumentParser(description="RapidOCR demo")
    parser.add_argument("image", help="图片路径")
    parser.add_argument("--limit-side-len", type=int, default=1000)
    parser.add_argument("--threads", type=int, default=8)
    parser.add_argument("--json", action="store_true", help="输出完整 JSON（含每行坐标）")
    args = parser.parse_args()

    image = Path(args.image)
    if not image.is_file():
        print(f"[错误] 图片不存在：{image}")
        return 2

    engine = RapidOCREngine(limit_side_len=args.limit_side_len, intra_op_num_threads=args.threads)
    started = time.perf_counter()
    result = engine.extract([image])
    total = time.perf_counter() - started

    text = result.text
    print("=" * 64)
    print(f"图片：{image}")
    print(f"参数：limit_side_len={args.limit_side_len} intra_op_num_threads={args.threads}")
    print(f"行数：{len(result.lines)}    耗时：{total:.3f}s（含首次建模）")
    print(f"首图耗时：{result.meta.get('images', [{}])[0].get('seconds', '-')}s")
    print("=" * 64)
    for idx, line in enumerate(result.lines[:5], 1):
        print(f"[{idx}] {line.text}  (score={line.score:.2f})")

    print("-" * 64)
    hits = {}
    for name, words in KEYWORDS.items():
        matched = [w for w in words if w in text]
        hits[name] = matched
        flag = "✓" if matched else "✗"
        print(f"{flag} {name:<8} {('、'.join(matched)) if matched else '（未识别到）'}")

    if args.json:
        print("-" * 64)
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))

    print("-" * 64)
    hit_count = sum(1 for v in hits.values() if v)
    print(f"关键字段命中：{hit_count}/{len(KEYWORDS)}    总耗时：{total:.3f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
