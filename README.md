# 面试请等等

求职者上传招聘截图，30 秒内拿到一份风险报告，判断这份工作「值不值得去面试」。

- 一期**不接大模型、不用云 OCR、不做生成式 AI 登记**：识别全部由确定性程序完成（本地 RapidOCR + 规则引擎 + 套路库），同一张图每次结果一致。
- 产品里不出现「AI」字样；报告只对「这条招聘信息」做风险提示，不评价公司。
- 当前阶段：D3（7 天冲刺），代码侧 A 组全绿，真实话术准确率 90.7%；上线仍差执照/AppID/ICP/律师。

## 新会话先读这三个文件

1. 本 README
2. [`docs/STATUS.md`](docs/STATUS.md)：当前进度、下一步、卡点
3. [`docs/DECISIONS.md`](docs/DECISIONS.md)：每个决定的日期、内容、原因

需求原文在 [`docs/requirements/`](docs/requirements/)，完整决策流水在 [`docs/00-项目执行计划.md`](docs/00-项目执行计划.md)。

## 仓库结构

```
backend/      后端 API（FastAPI，SQLite 原型 → MySQL 8）
engine/       识别引擎（RapidOCR → 文本规整/变形写法 → 六维规则 → 套路库匹配 → 模板化报告）
src/          小程序前端（uni-app，抖音/微信双端；内部再有一层 src/ 是 uni-app 源码约定）
rules/        规则、套路库、变形写法表、敏感词（数据文件，对应 rules_version）
tests/        测试（engine / backend / community / compliance / rebrand）
eval/         评测脚本 + 练习集/留出集划分清单（冻结）
ops/          部署脚本（docker compose）与上线方案
docs/         文档：需求原文、架构、决策、状态、合规、测试报告等
data/testset/ 测试集（synthetic / real_text 双轨，标注带出处）
reports/      测试与评测报告（证据留存）
```

## 快速开始（本机）

```powershell
# 后端
$py = "C:\Users\Administrator\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
& $py -m uvicorn backend.app.main:app --port 8000

# 识别引擎（单图/旁路文本）
& $py -m engine.cli analyze --ocr-text data/testset/ocr/T001.txt --out var/smoke/r.json
& $py -m engine.selftest
& $py scripts/backend_smoke.py

# 测试
& $py -m pytest -m smoke        # 快速冒烟
& $py -m pytest                 # 全量

# 前端（正式包必须用这个命令，内置 dev 页清理与 15 项构建后检查）
cd src
node <pnpm.mjs> run build:mp-weixin
```

小程序在微信开发者工具打开 `src/dist/build/mp-weixin`，固定端口 9420；一键脚本 `src/scripts/open_wechat_ide.ps1`。

## 提交规矩

- 小步提交：每完成一项提交一次，说明写清做了什么、对应任务（如「D2 薪资解析」）。
- `main` 受保护：功能在分支上做，测试通过才合并；里程碑打标签（如 `v0.1-D7`）。
- 提交前由 `.githooks/pre-commit` 扫描密钥；`.env`、私钥、未打码真实截图**一律不进仓库**。
- 每个数字员工每段工作结束更新 `docs/STATUS.md`。

## 规矩

- 所有文档、提示词、代码注释用中文。
- 每次交付附证据：命令输出、测试数字或截图；没有证据不算完成。
- 合规结论必须附官方来源链接；找不到来源写「待核实」，不凭印象下结论。
