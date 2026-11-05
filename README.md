# 面试请等等

## 两个版本说明

本仓库一套代码出两个版本，靠构建开关区分；两版共用同一套界面，**发布和提审的规矩不同**。

| 版本 | 首页是什么样 | 怎么构建 | 能不能提审 |
| --- | --- | --- | --- |
| **规则版**（提审用） | **粘贴卡**：用户粘贴招聘文字，全部在手机上跑；不调服务器、不调云托管、不调云 OCR、不调 DeepSeek | `npm run build:rules` | ✅ 提审用这一版 |
| **AI 版**（内部测试） | **上传卡**：选截图直发 `deepseek-flash` 识图，一次完成认字+判断 | `npm run build:deepseek`（必须注入 `VITE_DEEPSEEK_KEY`，不落代码） | ❌ 不得提审，只用于开发版/体验版内部测试 |

- **上传版本时按版本打标签**：`v1.0.7-rules`、`v1.0.7-ai`；以后每次上传照此递增（`v1.0.8-rules` / `v1.0.8-ai`）。
- **Release 里不得附任何构建包**：仓库是公开的，AI 版包里含密钥。
- 规则版构建器会主动清掉 `VITE_DEEPSEEK_KEY`（vite 直连会报错退出）；提交前 `git grep -n "sk-"` 必须无输出。

---

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

# 双版本构建（双版本令第三节：一套代码出两个包）
node <pnpm.mjs> run build:rules          # 规则版 1.0.7（默认，提审用这一版）
node <pnpm.mjs> run build:rules:review   # 规则版提审包（额外去掉广场 tab）
node <pnpm.mjs> run build:deepseek       # 识图版（需 VITE_DEEPSEEK_KEY，只能内部测试，不得提审）
```

**引擎开关说明**

- 开关是 `VITE_ENGINE`，**不设就是规则版**（`rules`）。规则版：用户粘贴招聘文字，全部在手机上检查，不发任何请求。
- 规则版构建时如果 `VITE_DEEPSEEK_KEY` 有值：`build-engine.mjs` **会先主动清掉该环境变量再构建**（产物里因此不含密钥）。
  另有第二道防线：若绕过 `build-engine` 直接调 vite 构建规则版，`vite.config.js` 会直接报错退出。
- 每次出规则版都要跑产物自检（`build:rules` 已自动带上）：产物里 `deepseek` / `api.deepseek.com` / `sk-` / `深度求索` 四个词必须全为 0，且首页与「我的」页不得出现联网调用。
- 单独复跑：`node <pnpm.mjs> run check:rules:build`；规则引擎自检：`node <pnpm.mjs> run check:rules`。

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
