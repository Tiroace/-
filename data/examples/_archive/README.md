# 已归档：data/examples/（旧 v2 标准示例）

**归档时间**：2026-10-31
**原因**：前端示例报告改用 `src/scripts/example-samples.json` + `src/scripts/gen-example-reports.py` 生成，
示例是**产品内容**，不能和评测资产（`data/testset/`、`eval/`）耦合同一处。
本目录的原数据是早期用测试集样例跑出来的标准报告，会随引擎/词库更新而过期，
如果还留在 `data/` 里，容易被后来的人 `load_standard()` 读回去当兜底。

**归档时的核实**（`grep -r data/examples` 全仓库）：
- 除本目录自身的 `README.md` / `index.json` 外，**没有任何代码引用**
- `src/scripts/gen-example-reports.py` 已明确注释「不再读 data/examples/」
- `scripts/gen_examples.py` 是生成器本身，只写不读

**现在的示例报告在哪**：
- 生成器：`src/scripts/gen-example-reports.py`
- 样本输入：`src/scripts/example-samples.json`（4 条，分别对应 red/amber/green/unknown）
- 产物：`src/src/common/exampleReports.js`
- 断言：`src/scripts/check-r1.mjs` 第 22 组

**要恢复**：`git mv data/examples/_archive data/examples`，但请先确认没有回退示例生成方式。
