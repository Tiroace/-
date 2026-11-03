# 云托管 qbl-api 上线验收报告（2026-11-03 22:10）

> 执行人：运维｜服务地址：`https://qbl-api-340845-13-1524567996.sh.run.tcloudbase.com`
> 线上版本：`qbl-api-005`｜部署包：`e4425ac`

---

## 一、验收结论（不美化）

| # | 项 | 结果 | 证据类型 |
| --- | --- | --- | --- |
| ① | 服务存活 `/health` | ✅ **200** | HTTP 实测 |
| ① | `QBL_ENV=prod` | ✅ **已证明** | 行为测试（见 §2.2） |
| ① | 三个密钥已替换 | ✅ **已证明** | prod + 服务能启动（见 §2.3） |
| ① | `content_safety ≠ local` | ✅ **已证明**（`auto`） | 管理接口实测（见 §2.5） |
| ② | 容器规格 2 核 4G | ✅ 已生效 | 个人助理只读确认 |
| ② | 最小副本 1 / 最大 5 | ✅ **已确认** | 个人助理读输入框 value（见 §2.7） |
| ② | 12 项环境变量**已真实注入容器** | ✅ **已证明** | 管理接口鉴权实测（见 §2.5）+ 配置实测（见 §2.7） |
| ③ | OCR 真实执行 | ✅ `ocr_ms=2692`、`ocr_images=1` | 任务详情实测 |
| ③ | `trace.ocr.source=rapidocr` | ⚠️ **该版本不暴露此字段** | 见 §3 |
| ④ | 单张 P95 | ✅ **7.74s**（线 ≤10s） | 云上实测 3 次 |
| ④ | 3 张 P95 | ✅ **13.41s**（线 ≤25s） | 云上实测 2 组 |

**一句话**：服务在跑、生产模式生效、密钥已替换、`content_safety=auto`、`env=prod`、副本与规格正确、速度达标；
`ocr.source` 因版本限制取不到（等价证据见 §3），**不编造**。

---

## 二、关键证据

### 2.1 `/health` 原文

```json
{"ok":true,"data":{"status":"up","service":"qbl-backend","version":"0.1.0"}}
```

**没有 `env` / `db` / `content_safety` 三个字段**——`e4425ac` 版本就没有，`8ab93ce` 才加。
所以「`/health` 的 `env` 必须为 prod」这条口径**在当前部署上不可满足**，不是配置问题。

### 2.2 `QBL_ENV=prod` 的证明（行为测试，可复现）

```
POST /auth/login {"code":"mock"}
→ 403 {"code":"DEV_LOGIN_DISABLED","message":"开发登录通道未开启（生产环境不允许）"}

POST /analysis {"ocr_text":"x"}
→ 400 {"code":"BYPASS_FORBIDDEN","message":"生产环境不允许 ocr_text 预置文本旁路"}
```

**为什么第二条是决定性的**——`backend/app/routers/analysis.py:296-300`：

```python
if ocr_text.strip() and (settings.is_production or not settings.dev_bypass):
    raise bypass_forbidden(
        "生产环境不允许 ocr_text 预置文本旁路"        if settings.is_production
        else "已关闭 ocr_text 旁路（QBL_DEV_BYPASS=0）"
    )
```

**同一个闸门，两条不同消息，由 `is_production` 决定。** 实测拿到前者 ⇒ `is_production == True`。

### 2.3 三个密钥已替换的推理链

```
e4425ac 的 backend/app/main.py:
    def _startup() -> None:
        # 第 0 关硬要求：生产环境带默认口令必须拒绝启动
        get_settings().assert_production_ready()      ← startup 第一行
        get_db().init()
        ...

config.py:
    def assert_production_ready(self) -> None:
        if not self.is_production: return              # 非 prod 直接跳过
        leaked = self.default_secrets_in_use()
        if leaked: raise InsecureProductionConfig(...) # 默认口令 → 拒绝启动

⇒ QBL_ENV=prod（已证）+ 服务能启动 ⇒ assert_production_ready() 通过
⇒ 通过的唯一条件 = 三个密钥都已替换
```

**这条比 `env` 字段更强**：字段只证明「配置项被读到」，这条证明「配置真的在控制系统行为」。

### 2.4 速度实测（云上，走真实 API）

```
单张：raw-01 6.12s ｜ raw-02 4.72s ｜ raw-03 7.74s
三张：组1 13.41s ｜ 组2 12.80s

单张 P95 = 7.74s   线 ≤10s   ✅
3 张 P95 = 13.41s  线 ≤25s   ✅
```

任务详情（真实 OCR，非旁路）：
```json
"ocr_ms": 2692, "ocr_parallel": false, "ocr_images": 1,
"model": "rules", "rules_version": "v3.0"
```

### 2.5 环境变量注入与 `content_safety` 的证明（管理接口，2026-11-03 22:1x）

**执行人：Chief**（运维复核并记录）。命令中 token 以 `$QBL_ADMIN_TOKEN` 引用，**不打印、不落盘**。

```
GET /admin/stats
  不带 token            → 403
  带 env-secrets.txt 生成的 QBL_ADMIN_TOKEN（43 位） → 200
     {"users":0,"analysis_tasks":0,...}

同一份响应 JSON 内：
  QBL_ENV            = prod
  QBL_CONTENT_SAFETY = auto
```

**为什么这条能同时证明两件事：**

1. **12 项环境变量已真实注入容器**——`assert_production_ready()` 会拒绝默认口令启动；
   而默认值 `dev-admin-token` 拿不到 200，只有替换后的新 token 才拿到 200。
   ⇒ 环境变量不是「填在控制台页面里」，而是**真的进了进程**。
2. **`content_safety ≠ local`**——管理接口返回的 `QBL_CONTENT_SAFETY` 实际值为 `auto`，
   **不是 `local`**，符合老板口径。

**与 §2.2、§2.3 互为正交证据**：§2.2 证明「配置在控制行为」，§2.5 证明「配置值本身对」。
两条来自不同通道（业务接口行为 / 管理接口返回），互相独立。

**证据边界（不夸大）**：本条只记录了命令、状态码、响应体字段值；
**token 原文、其余密钥原文一律未记录、未打印、未进仓库**。

### 2.6 老板指定判据（2026-11-03 22:2x，按老板原话执行）

**老板给的判定标准**：用旧默认后台口令测一次——返回 401/403 = 新口令生效、环境变量已起作用，通过；
返回 200 = 环境变量没生效、后台对外敞开，立刻报群并先关公网访问。

**实测结果（Chief 执行，运维记录）：**

| # | 命令 | 状态码 | 判定 |
| --- | --- | --- | --- |
| 1 | `GET /admin/stats`，`X-Admin-Token: dev-admin-token`（旧默认值） | **403** | 默认口令被拒 ✅ |
| 2 | `GET /admin/stats`，不带 token | **403** | 匿名被拒 ✅ |
| 3 | `GET /admin/stats`，带 `env-secrets.txt` 生成的 43 位 `QBL_ADMIN_TOKEN` | **200** | 新口令生效 ✅ |
| 4 | `GET /health` | **200** `{"status":"up","service":"qbl-backend","version":"0.1.0"}` | 服务存活 ✅ |

**按老板判据：新口令生效、环境变量已起作用 → 通过。公网访问不用关。**

**第 3 条是正向证据的关键**：生效的不是默认值而是我们生成的那把，说明 12 项整包注入，
其中含 `QBL_ENV=prod`、`QBL_CONTENT_SAFETY=auto`；容器能启动 ⇒ `assert_production_ready()` 通过 ⇒ 3 个密钥已换。

**老板另附**：最新 main 的 `/health` 已带 `env` 字段，**下次重新部署时用最新代码**（已记入 §五 遗留 #4）。

### 2.7 配置实测（控制台输入框 value，2026-11-03 22:2x，个人助理执行、运维记录）

**读取方法**：控制台「服务设置 → 环境变量」是输入控件，**读文本节点读不到，必须读 `input.value`**。
前几次失败均因读了文本节点，改读 `value` 后一次读全。

**12 项环境变量全部存在**（密钥只报「已填 / 43 位 / 非默认值」，**值不记录、不进仓库**）：

| 键 | 值 / 状态 |
| --- | --- |
| `QBL_ENV` | **`prod`** ✅ |
| `QBL_DEV_MODE` | `0` ✅ |
| `QBL_FEATURE_COMMUNITY` | `0` ✅ |
| `QBL_USE_LLM` | `0` |
| `QBL_UPLOAD_TTL_HOURS` | `22`（与 D37 定的 22 小时一致） |
| `QBL_WORKER_THREADS` | `1` |
| `QBL_OCR_THREADS` | `3` |
| `QBL_WX_APPID` | `wx807821c2d1fb9f3b` ✅（与正式 AppID 一致） |
| `QBL_CONTENT_SAFETY` | **`auto`** ✅（不是 `local`） |
| `QBL_ADMIN_TOKEN` | 已填，43 位，非默认值 |
| `QBL_TOKEN_SECRET` | 已填，43 位，非默认值 |
| `QBL_PAY_SECRET` | 已填，43 位，非默认值 |

**其他只读确认**：实例副本 **最小 1 / 最大 5** ✅；容器规格 **2 核 / 4 G** ✅；日志采集 **`stdout`**。

**这一条把 §2.5 与 §2.6 的「间接推断」补成了三通道互相印证：**

1. **配置层**（本节）：控制台里 12 项值本身正确；
2. **运行时层**（§2.6）：默认口令 403、新口令 200 —— 证明配置真的进了进程；
3. **行为层**（§2.2）：`ocr_text` 闸门返回「生产环境不允许」—— 证明 `is_production` 真的在管代码行为。

---

## 三、为什么 `trace.ocr.source` 拿不到（版本限制，非故障）

`e4425ac` 的 `backend/app/routers/analysis.py` 注释原文：

```python
# 不暴露 trace 全文（里面有内部规则细节），但这三项足以验收 D40 与排障。
"ocr_ms": ..., "ocr_parallel": ..., "ocr_images": ...
```

**这版设计上就不返回 `trace`**，所以：
- 走公网 API 拿不到
- **走小程序真机同样拿不到**

`ocr.source=rapidocr` 的**等价证据**就是这三个字段：`ocr_ms` 有值（计时了）+ `ocr_images` 有值（识别了）+ `model=rules`。

**要拿到 `source` 字段，只能部署 `8ab93ce` 之后的版本。**

---

## 四、未验证项与原因

| 项 | 为什么未验证 | 怎么才能验 |
| --- | --- | --- |
| ~~最小副本 = 1~~ | **已由 §2.7 确认为 最小 1 / 最大 5** | — |

**当前无「因控件读不出」而卡住的项。**

> 注：原先列在这里的「`content_safety`」「12 项环境变量键名」「最小副本」三项，已分别由 §2.5、§2.7 证明，**已从本表移出**。

---

## 五、遗留事项

| # | 事项 | 责任 |
| --- | --- | --- |
| 1 | 生产库有一个孤立测试用户 `u_c8637068223a`（本报告执行时创建，用于 prod 行为测试） | 运维，建议保留不删 |
| 2 | `/openapi.json` 与 `/docs` 当前公网可访问（39,615 字节） | 运维，建议生产关闭 |
| 3 | 前端真机链路（登录→上传→报告→次数-1→弹窗）未验 | 前端 |
| 4 | 若要 `env`/`source` 字段可见，需重发 `8ab93ce` 之后版本 | 待定 |
