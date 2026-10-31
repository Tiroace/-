"""从真实话术库生成真实轨道测试用例（OCR 文本形态）

背景：
- 路线令要求真实轨道 ≥120 张。**真实截图**依赖老板手机实拍/公开图片，暂未到位。
- 但公开案例里的**真实话术**已抓取 30 条（`data/testset/real_phrases_v1.json`），
  这些是权威来源的真实文本，可以做「真实文本形态」的测试用例。

口径（必须写清楚，不能混标）：
- track = "real_text"：真实话术、权威来源，但**不是真实截图**。
- 这类**不能**算进「真实截图 ≥120」的指标，单独统计。
- 渲染成图后自动降级为 synthetic（因为图是合成的）。

用法：python scripts/build_real_cases.py
输出：data/testset/real_cases_v1.jsonl
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PHRASES = ROOT / "data" / "testset" / "real_phrases_v1.json"
OUT = ROOT / "data" / "testset" / "real_cases_v1.jsonl"
OCR_DIR = ROOT / "data" / "testset" / "ocr"

DIMENSIONS = ["fee", "work", "title", "pay", "company", "contract"]

# 情景模板：把真实话术包进一段招聘文案，模拟真实截图里话术出现的上下文
SCENARIOS = [
    {
        "name": "招聘岗位详情",
        "template": """招聘岗位：{title}
工作地点：本地
薪资待遇：面议
岗位要求：{phrase}
联系人：某女士
面试地点：市区写字楼
""",
    },
    {
        "name": "HR 聊天记录",
        "template": """HR：你好，看到你的简历了，我们这边正在招人
HR：{phrase}
HR：有意向的话尽快回复，名额不多
我：好的，我先了解一下
HR：可以先来面试看看，具体当面聊
""",
    },
    {
        "name": "招聘广告",
        "template": """【急聘】{title} 若干名
{phrase}
待遇优厚，包吃住，多劳多得
名额有限，先到先得，有意者私聊
""",
    },
]


def main() -> int:
    data = json.loads(PHRASES.read_text(encoding="utf-8"))
    phrases = data["phrases"]
    source_by_id = {s["id"]: s for s in data["sources"]}

    OCR_DIR.mkdir(parents=True, exist_ok=True)
    cases = []
    idx = 0

    for phrase in phrases:
        for scen in SCENARIOS:
            idx += 1
            cid = f"RT{idx:04d}"   # RT = real text
            title = {
                "fee": "运营助理", "work": "市场专员", "title": "储备干部",
                "pay": "销售代表", "company": "行政专员", "contract": "客服专员",
            }.get(phrase["dimension"], "运营助理")

            text = scen["template"].format(title=title, phrase=phrase["text"])
            ocr_rel = f"data/testset/ocr/{cid}.txt"
            (OCR_DIR / f"{cid}.txt").write_text(text, encoding="utf-8")

            dims = {d: "none" for d in DIMENSIONS}
            dims[phrase["dimension"]] = phrase["level"]
            overall = "red" if phrase["level"] == "red" else "amber"

            src = source_by_id.get(phrase["source"], {})
            cases.append({
                "id": cid,
                "track": "real_text",
                "image": None,
                "ocr_text": ocr_rel,
                "source": {
                    "type": "public_case",
                    "url": src.get("url", ""),
                    "collected_at": data["collected_at"],
                    "note": f"{src.get('name','')}：{phrase['category']}（话术 {phrase['id']}）",
                },
                "masked": True,
                "label": {
                    "overall": overall,
                    "dimensions": dims,
                    "expected_findings": [
                        {"dimension": phrase["dimension"], "evidence": phrase["text"]}
                    ],
                },
                "style": "job_detail" if scen["name"] == "招聘岗位详情" else ("chat" if "聊天" in scen["name"] else "mixed"),
                "difficulty": "medium",
                "notes": f"情景={scen['name']}；真实话术来源 {phrase['source']}；非真实截图",
            })

    OUT.write_text(
        "\n".join(json.dumps(c, ensure_ascii=False) for c in cases) + "\n",
        encoding="utf-8",
    )
    print(f"生成 {len(cases)} 条真实文本用例 → {OUT.relative_to(ROOT)}")
    print(f"  来源话术 {len(phrases)} 条 × {len(SCENARIOS)} 种情景")
    print("  注意：track=real_text，是真实话术但不是真实截图，不能计入「真实截图 ≥120」")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
