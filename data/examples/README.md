# 标准示例报告（4 种整体结论）

R3 补齐的基准数据：**red / amber / green / unknown** 各 1 份 v2 报告，作为前端渲染、测试截图与首页「示例报告」的基准，避免各处用引擎临时跑出来的版本互相对不上。

| 文件 | overall | 来源 | 用途 |
| --- | --- | --- | --- |
| `report_red.json` | red | 入职前收押金 + 服装费（T002） | 报告页红灯态、高危提示、110/96110 区块 |
| `report_amber.json` | amber | 合同一年但试用期六个月（T012） | 报告页黄灯态、追问清单 |
| `report_green.json` | green | 正常的后端开发岗位（T015） | 报告页绿灯态、绿的发现（公司/薪资写得清楚） |
| `report_unknown.json` | unknown | 非招聘内容（传错图） | 「信息不足，再补一张截图」态 |
| `index.json` | — | 四份文件的索引（overall、维度灯、findings 数量） | 前端/测试按索引取 |

- 结构：`docs/04-识别引擎设计.md` §二 的 v2 schema，四份都通过 `engine.schema.validate_report(final=True)`。
- 生成：`python scripts/gen_examples.py`（可复跑；改引擎或词库后重新生成，避免示例过期）。
- 首页「示例报告」入口用这些文件、**不扣次数**（前端内置/静态资源，不走 `/analysis`）。
- 测试截图的四种 overall 就按这四份跑，不要临时构造。
