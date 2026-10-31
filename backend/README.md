# 后端骨架（T4 原型）

面试请等等小程序后端：FastAPI + SQLite（表结构按需求书 §5.3 设计，正式版换 MySQL/Redis 只改 `app/db.py`）。

**字段级接口契约在 [`docs/04-后端接口契约.md`](../docs/04-后端接口契约.md)，前端按它做 mock；异步状态机时序见该文档 §3.1。**

## 起服务

```bash
# 在 D:\qiuzhibilei 下
python -m pip install -r backend/requirements.txt
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
# 或
scripts\run_backend.ps1
```

接口文档：<http://127.0.0.1:8000/docs>

## 目录

| 文件 | 作用 |
| --- | --- |
| `app/main.py` | 应用入口、统一错误封套、request_id、/health、线程池生命周期 |
| `app/config.py` | 配置（额度、价格、上限、密钥、线程数、平台凭据），全部可用环境变量覆盖 |
| `app/db.py` | SQLite 表结构 + 轻量迁移（users/quota_ledger/analysis_tasks/reports/ad_rewards/orders/memberships/feedback） |
| `app/quota.py` | 额度流水：预扣/退回/正式扣、广告奖励、对账 |
| `app/worker.py` | 后台分析执行器（ThreadPoolExecutor；pending→running→done/failed，失败退次数） |
| `app/security.py` | token 签发校验、支付回调签名、脱敏 |
| `app/engine_runner.py` | 调用识别引擎、错误码翻译 |
| `app/platform/` | 平台适配层：抖音/微信 code2session、支付参数、回调验签、广告位；没凭据走 Mock 并标 `mock` |
| `app/routers/*.py` | 17 个基础端点（含 /plans、/analysis/upload、套路库 2 个）+ 求助广场 12 个（开关控制） |
| `app/community/` | 社区隐私打码 + 敏感词/模型两层审核 |
| `sql/community.sql` | 求助广场 6 张表 DDL（MySQL 兼容） |
| `app/patterns_seed.py` | 套路库三表种子（lexicon/patterns_v1.json 灌库） |
| `tests/` | 实现级 pytest 单测（额度三段式/幂等/状态机）；契约测试在测试者的 `tests/` |

## 开发登录通道（B 关口联调）



没有正式 AppID 时，用 scripts\run_backend.ps1 起服务（自动设 `QBL_DEV_MODE=1`），然后 `POST /auth/login {"platform":"toutiao","code":"mock"}` 直接换真 token；`code=mock:<x>` 或 `X-Debug-User` 头可切换不同开发账号。响应带 `dev_login=true` / `platform_mode=dev`。**生产部署不设 `QBL_DEV_MODE`（默认 0），此时 code=mock 返回 403。**



## CORS



只放本机来源：`^https?://(localhost|127\.0\.0\.1)(:\d{1,5})?$`，不开 `*`。



## 报告 v2（R1）

`reports` 表存 v2 报告 JSON（overall / dimensions / findings / prompt_version / pattern_db_version），
字段见 [`docs/04-识别引擎设计.md`](../docs/04-识别引擎设计.md) §二。旧 v1（risk_level/risks/verdict）作废，不做兼容。

## 异步分析（D5）

`POST /analysis` 立即返回 `{task_id, status:pending, poll_after_ms}`，分析在后台线程池跑；前端轮询 `GET /analysis/{id}`：
`pending → running → done|failed`。超过 30 秒仍未结束 → `background_mode=true`（前端转「后台处理中」），服务端继续跑不取消。失败自动退次数。

换 Celery/Redis 时只改 `app/worker.py`，接口形状不变。

## 环境变量

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `QBL_DB_PATH` | `var/backend/qbl.db` | SQLite 路径 |
| `QBL_UPLOAD_DIR` | `var/uploads` | 截图临时目录（正式版换 OSS） |
| `QBL_REPORT_DIR` | `var/reports` | 引擎报告落库目录 |
| `QBL_ENGINE_MODEL` | `mock` | `mock` / `deepseek` |
| `QBL_TOKEN_SECRET` / `QBL_PAY_SECRET` / `QBL_ADMIN_TOKEN` | dev 占位 | **生产必须替换**，走安全卡片注入 |
| `QBL_FREE_QUOTA` / `QBL_AD_DAILY_CAP` / `QBL_MEMBER_DAILY_QUOTA` | 3 / 5 / 20 | 额度参数 |
| `QBL_WORKER_THREADS` | 4 | 后台分析线程数 |
| `QBL_POLL_AFTER_MS` | 1500 | 建议轮询间隔 |
| `QBL_BACKGROUND_AFTER_SECONDS` | 30 | 超时转后台阈值 |
| `QBL_FAKE_ENGINE_DELAY_MS` | 0 | **仅测试**：给引擎加人为延迟，验证 running 与转后台语义 |
| `QBL_FEATURE_COMMUNITY` | `0` | 求助广场开关，`1` 才开放 `/community/*`（默认关，资质核实前不开） |
| `QBL_COMMUNITY_NEW_ACCOUNT_HOURS` / `QBL_COMMUNITY_REPORT_HIDE_THRESHOLD` | 24 / 3 | 新号限制时长、举报隐藏阈值 |
| `QBL_DEV_MODE` | `0` | `1` 时开放 code=mock 开发登录（run_backend.ps1 会设 1，**生产必须 0**） |

| `QBL_MAX_ORDER_AMOUNT_FEN` | 30000 | 单笔支付上限（分） |

| `QBL_UPLOAD_TTL_HOURS` | 24 | 上传图片有效期 |

| `QBL_TT_APPID` / `QBL_TT_SECRET` / `QBL_TT_AD_UNIT_ID` | 空 | 抖音平台凭据/广告位，配了才走真实 code2session |
| `QBL_WX_APPID` / `QBL_WX_SECRET` / `QBL_WX_AD_UNIT_ID` | 空 | 微信平台凭据/广告位（二期） |

## 自测

```bash
python scripts/backend_smoke.py    # 60 项：12 端点 + 异步状态机 + 并发 + 越权/幂等/验签/对账
python -m pytest backend/tests -q  # 20 项实现级单测：额度三段式、幂等、状态机
```

## 现在还不是生产实现的地方

- 登录：适配层壳已就位，**没有平台凭据时走 Mock**（响应 `platform_mode=mock`）；配了凭据即走真实 code2session；
- 支付：`pay_params` 一律 `mock:true`，抖音虚拟支付/微信支付的下单与验签算法未接；
- 异步：进程内线程池（多实例部署前必须换 Celery/Redis）；
- SQLite、本地文件、进程内限流（真实要 MySQL/Redis/OSS）。
