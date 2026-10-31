# ARCHITECTURE

> 更新：2026-10-31。原则：**确定性优先**——一期不接大模型，同一张图每次结果必须一致。

## 一、模块

| 模块 | 路径 | 说明 |
| --- | --- | --- |
| 小程序前端 | `src/` | uni-app（Vue 3），微信为主、抖音后端保留；页面：首页、分析中、报告、会员、我的、检查记录、求助广场（开关默认关） |
| 后端 API | `backend/app/` | FastAPI；鉴权、额度流水、分析任务、报告、广告奖励、订单、社区、后台 |
| 识别引擎 | `engine/` | 纯函数库：OCR → 文本规整 → 六维规则 → 套路库匹配 → 证据校验 → 校准 → 模板化报告 |
| 规则数据 | `rules/` | `lexicon_v3.json`（规则）、`patterns_v1.json`（套路库）、`variants_v1.json`（变形写法）、`sensitive_words_v1.json`（敏感词） |
| 测试 | `tests/` | engine / backend / community / compliance / rebrand 五组，pytest 标记 `smoke` |
| 评测 | `eval/` | 评测脚本 + 练习集/留出集划分（冻结，改动需升版本） |
| 部署 | `ops/` | docker compose、上线方案、备案材料清单、成本表 |

## 二、识别链路（确定性）

```
图片/旁路文本
  → 内容安全（本地 stub / 平台接口：待接）
  → OCR（RapidOCR 本地 CPU，长边 ≤1000，参数可配；mock/sidecar 可切换）
  → 文本规整（全半角、繁简 OpenCC、中文数字）
  → 词库扫描（逐行 + 繁简两路 + 变形写法容错，证据取 OCR 原文）
  → 套路库匹配（jieba + TF-IDF 余弦，阈值 0.35 召回 / 0.5 才写 finding）
  → 招聘截图判定（<20 字或无招聘关键词 → unknown，退次数）
  → 证据校验（evidence 必须在原文，红黄绿都校验）
  → 等级校准（硬证据下限，模型/套路不得下调）
  → 组装报告（6 维度灯、overall 由规则算、灰灯补追问、模板化文案）
  → 文案红线（定性词过滤 + PII 脱敏）→ PII 硬断言 → schema 校验
```

- 报告 schema：`is_job_posting / overall / summary / dimensions[6] / findings[] / questions_to_ask / how_to_verify / rules_version / pattern_db_version`。
- `source` 只有 `rule` / `pattern`；旧 `prompt_version` 已改 `rules_version`。
- 大模型只剩插件接口，默认关闭（`QBL_USE_LLM=0`），打开前必须先完成生成式 AI 登记。

## 三、后端

- 存储：原型 SQLite（`var/backend/qbl.db`），生产按 `ops/` 上 MySQL 8 + Redis。
- 表：users、quota_ledger（额度只走流水）、analysis_tasks、reports、uploads、ad_rewards、orders、memberships、feedback、patterns 三表；社区 posts/votes/experiences/post_reports/appeals/sensitive_words。
- 关键约束：额度三段式（预扣→成功扣/失败退）；`Idempotency-Key` 幂等；越权 404；支付回调验签 + 幂等；单笔 ≤300 元；iOS 会员入口默认隐藏。
- 社区：`QBL_FEATURE_COMMUNITY=0` 时 ASGI 中间件统一 404；开启前须完成资质核实。

## 四、环境与工具链

- Windows 10；Python 3.12（DSH 运行时）；Node 24 + pnpm；微信开发者工具（HTTP 端口 9420 / 自动化 WS 端口 9422）。
- 小程序构建必须 `pnpm build:mp-weixin`（内置 dev 页剔除 + 15 项构建后检查）；直接 `uni build` 会把 dev 页打回包里。
- 性能门槛（老板拍板）：单张 ≤4 秒、3 张 ≤10 秒、3 张并行识别；最终以正式服务器实测为准。

## 五、已知约束

1. 无正式 AppID（游客模式）：真机预览、真实支付/广告、订阅消息均未验证。
2. OCR 速度受本机 CPU 限制（单图 4–5 秒）；需服务器实测与并行方案。
3. 套路库精确率偏低（本地 TF-IDF 降级方案），接云向量后重调。
4. 社区资质未核实，功能开关保持关闭。
