# 云托管环境 ID 到手后的切换清单

> 提交人：运维｜时间：2026-11-03
> 用途：**环境 ID 一拿到，照这张单子一次切完，不用现场再查代码。**
> 关联：`ops/云托管部署手册.md`、`ops/第2关部署前检查表.md`

---

## 0. 环境 ID 是什么、在哪拿

**云托管控制台 → 左上角环境切换处 / 环境设置**，形如 `prod-xxxxxxx`（不是 `wx` 开头的 AppID）。

| 字段 | 例子 | 用在哪 |
| --- | --- | --- |
| **环境 ID** | `prod-1a2b3c` | 前端 `VITE_CLOUD_ENV`、`wx.cloud.init({env})` |
| **服务名** | `qbl-api` | 前端 `VITE_CLOUD_SERVICE`、请求头 `X-WX-SERVICE` |
| 默认公网域名 | `qbl-api-xxx.ap-shanghai.run.tcloudbase.com` | 后台调试用（小程序走内网不需要） |

> **服务名是我们自己建的**，建议就叫 `qbl-api`（见部署手册 §3 推荐配置）。

---

## 1. 三处要填的配置（已确认代码读哪里）

### 1.1 前端：构建时注入两个环境变量

前端已预留内网调用通道（`f9a93fb`），代码读的是构建期常量：

```powershell
# 在 src 目录下构建前设置
$env:VITE_CLOUD_ENV = "prod-xxxxxx"    # ← 环境 ID
$env:VITE_CLOUD_SERVICE = "qbl-api"    # ← 服务名
node <pnpm.mjs> run build:mp-weixin
```

对应源码（**已逐个核实**）：

| 文件 | 内容 |
| --- | --- |
| `src/src/common/config.js:16-23` | `CLOUD_ENV` / `CLOUD_SERVICE` / `hasCloudBackend()`，从构建期常量 `__QBL_CLOUD_ENV__` / `__QBL_CLOUD_SERVICE__` 读 |
| `src/src/services/transport.js:12,45-51` | 走 `callContainer({ env: CLOUD_ENV, service: CLOUD_SERVICE, ... })` |
| `src/src/platform/index.js` | `wx.cloud.callContainer` 的平台封装 |

> ⚠️ 注意：**不是 `services/api.js`**（那里只有一句注释指向 transport.js）。
> 我第一版清单写错了这个位置，已核对后更正。

**未配这两个变量时行为与旧版一致**（`hasCloudBackend()` 返回 false，退回原通道），
所以填错不会静默坏掉，但也不会用上云托管——**必须按 §2 的 V2 验证确认真的走内网了**。

### 1.2 后端：环境变量（云托管控制台填，不进代码）

| 变量 | 值 |
| --- | --- |
| `QBL_ENV` | `prod` |
| `QBL_WX_APPID` | `wx807821c2d1fb9f3b`（已确认） |
| `QBL_WX_SECRET` | **AppSecret，走安全卡片，控制台填** |
| `QBL_UPLOAD_TTL_HOURS` | `22` |
| `QBL_OCR_THREADS` | `3`（开发者实测 3 线程最优） |
| `QBL_FEATURE_COMMUNITY` | `0` |
| `QBL_USE_LLM` | `0` |
| `QBL_ADMIN_TOKEN` / `QBL_TOKEN_SECRET` / `QBL_PAY_SECRET` | 随机 32 位，控制台填 |

> 完整清单见 `ops/云托管-配置选定清单.md` §4。

### 1.3 小程序后台：不需要配「服务器域名」

走 `callContainer` 内网调用**不用配服务器域名**（官方原文）。这是云托管相对自建服务器省下的一步。
**但基础库最低版本要设 ≥ 2.23.0**：小程序后台 → 设置 → 功能设置 → 基础库最低版本。

---

## 2. 切换后必须验证的三件事

| # | 验证 | 怎么验 | 通过标准 |
| --- | --- | --- | --- |
| V1 | 后端起来了 | `curl https://<默认域名>/health` | `{"ok":true,...}` |
| V2 | **小程序真的走内网调用了** | 真机打开页面看能否出报告 | 能出报告；开发者工具 Network 里没有 `request` 到公网域名 |
| V3 | **并行确实生效** | 查任务详情的 `ocr_parallel` 字段 | `true`，且 `ocr_images=3` |

**V2 最容易假通过**：如果前端 `VITE_CLOUD_ENV` 没设或设错，`hasCloudBackend()` 返回 false，
会**退回旧的 mock/公网通道**，页面照样能跑，但根本没走云托管。**所以必须看 Network 或查后端日志确认。**

---

## 3. 环境 ID 到手后的执行顺序

```
1. 确认云托管已开通且已付款（老板回答）
2. 拿到环境 ID + 确认服务名（默认 qbl-api）
3. 生成部署包            python ops/scripts/make_cloudrun_pkg.py
4. 控制台建服务 → 规格 4核8G → 最小副本 1 → 日志路径 /app/var/log → 填环境变量
5. 上传发布，等构建完成
6. V1 健康检查
7. 云上跑 D40 验收        cd /app && python eval/eval_api_e2e.py
8. 判定（检查表 §4 的判定表）
9. 前端设置 VITE_CLOUD_ENV 重新构建 → V2/V3 验证
10. 冷启动实测 → 记录
11. 出部署记录，更新 STATUS，群内回报
```

---

## 4. 待确认项（不影响开始，但部署时要问）

| 项 | 为什么重要 |
| --- | --- |
| 云托管**付费主体**是不是老板本人小程序绑定的腾讯云账号 | 官方：一个微信账号绑定一个腾讯云账号，绑错要销毁所有环境才能换 |
| 是否已有其他小程序占用同一个腾讯云账号 | 同上，会用「资源复用」而非新建 |

> 这两条我在部署第一步会确认，避免建完环境发现绑错账号。

---

## 5. 现在卡的只有一样

**环境 ID。** 有了它，上面 11 步一天内能走完。
没有它，我只能待命——包已经打好（7.74MB / 101 文件），配置位置全部确认过。
