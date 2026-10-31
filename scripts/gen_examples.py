"""生成 4 种 overall 的标准示例报告（red / amber / green / unknown）。

用途：前端报告页渲染基准、测试截图基准、对外示例报告（首页「示例报告」不扣次数）。
可复跑：python scripts/gen_examples.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from engine.config import default_config  # noqa: E402
from engine.pipeline import analyze  # noqa: E402
from engine.schema import validate_report  # noqa: E402

OUT = PROJECT_ROOT / "data" / "examples"

# overall → (来源说明, OCR 文本)
CASES = {
    "red": (
        "红：入职前收押金 + 服装费（data/testset/ocr/T002.txt）",
        (PROJECT_ROOT / "data" / "testset" / "ocr" / "T002.txt").read_text(encoding="utf-8"),
    ),
    "amber": (
        "黄：合同一年试用期六个月（data/testset/ocr/T012.txt）",
        (PROJECT_ROOT / "data" / "testset" / "ocr" / "T012.txt").read_text(encoding="utf-8"),
    ),
    "green": (
        "绿：正常的后端开发岗位（data/testset/ocr/T015.txt）",
        (PROJECT_ROOT / "data" / "testset" / "ocr" / "T015.txt").read_text(encoding="utf-8"),
    ),
    "unknown": (
        "灰（信息不足）：非招聘内容，模拟用户传错图",
        "周末去爬山拍了几张照片，天气不错，山顶风有点大。",
    ),
}


def main() -> int:
    cfg = default_config()
    cfg.use_dedupe = False
    cfg.report_dir = None
    OUT.mkdir(parents=True, exist_ok=True)
    index: dict = {"schema_version": "v2", "generated_by": "scripts/gen_examples.py", "items": []}

    for overall, (description, text) in CASES.items():
        result = analyze([], text, config=cfg)
        report = result.report
        if report["overall"] != overall:
            raise SystemExit(f"示例生成失败：{overall} 实际得到 {report['overall']}")
        errors = validate_report(report, final=True)
        if errors:
            raise SystemExit(f"示例 {overall} 未通过 schema：{errors}")
        path = OUT / f"report_{overall}.json"
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        index["items"].append(
            {
                "overall": overall,
                "file": f"data/examples/report_{overall}.json",
                "description": description,
                "dimensions": {d["key"]: d["level"] for d in report["dimensions"]},
                "findings": len(report["findings"]),
            }
        )
        print(f"{overall:<8} -> {path.name}（findings {len(report['findings'])}，维度 {index['items'][-1]['dimensions']}）")

    (OUT / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"索引已写入 {OUT / 'index.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
