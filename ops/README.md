# ops/ 部署与上线

> 负责人：运维（数字员工）。
> **⚠️ 2026-11-03 路线变更（D38）：个人主体上线，不买服务器和域名，改用微信云托管。**
> **现行方案：** [`微信云托管评估.md`](微信云托管评估.md)（评估结论）、[`云托管部署手册.md`](云托管部署手册.md)（部署步骤）
> 下表中标「已作废」的属自建 ECS 旧路线，保留留痕；将来迁回自有服务器仍可参考。

## 文件

| 文件 | 用途 | 状态 |
| --- | --- | --- |
| **`微信云托管评估.md`** | **D38 现行**：可行性、月费、性能风险 | ✅ 现行 |
| **`云托管部署手册.md`** | **D38 现行**：部署步骤、规格、坑 | ✅ 现行 |
| `Dockerfile.cloudrun` | **D38 现行**：云托管镜像（放根目录改名 Dockerfile） | ✅ 现行 |
| `上线方案.md` | 云厂商选型、机型、数据库、存储、备份、监控、日志、成本表 | ⚠️ 已作废（D38） |
| `部署硬检查清单.md` | 逐条打勾的部署验收 | ⚠️ 已作废（D38） |
| `icp-备案材料清单.md` | 备案材料与流程 | ⚠️ 域名 ICP 作废；**小程序备案仍要做** |
| `evidence/` | 部署证据归档 | ✅ 骨架 |
| `安全基线.md` | 密钥、后台来源限制、防火墙端口、HTTPS | ✅ 仍适用（密钥部分） |
| `docker-compose.yml` | 一键起 api + mysql + redis | ⚠️ 备选（非现行） |
| `Dockerfile.api` | api 镜像（非 root、可选 OCR） | ⚠️ 备选（非现行） |
| `.env.example` | 部署用环境变量清单（真值不进仓库） | ✅ |
| `local_up.py` | 本机无 Docker 时的一键启动 | ✅ 本机实测跑通 |
| `backup.sh` / `restore.sh` | 生产备份/恢复（MySQL + Redis） | ⚠️ 备选 |
| `backup_local.py` | SQLite 备份/恢复/校验 | ✅ 本机实测跑通 |
| `scripts/check_mysql.sh` | MySQL 就绪自检 | ✅ |
| `mysql-init/00-init.sql` | MySQL 首次初始化脚本 | ✅ |

**部署顺序（D38）**：先读 `微信云托管评估.md` 确认性能口径，再照 `云托管部署手册.md` 执行。

目标形态：

```
api        FastAPI（backend.app.main:app）
mysql      MySQL 8.4 LTS（生产；原型期后端仍走 SQLite，D2 决定）
redis      Redis 7.4（任务队列/限流，接 Celery 后启用）
ocr        RapidOCR 随 api 进程内运行（CPU）
```

---

## 一、本地一键跑通

### 方式 A：docker compose（有 Docker 引擎的机器）

```bash
cd ops
cp .env.example .env          # 填本地值；.env 已被 .gitignore 忽略
docker compose up -d --build
docker compose ps
curl http://127.0.0.1:8000/health
```

停止 / 查看日志：

```bash
docker compose down            # 停止（保留数据卷）
docker compose down -v         # 停止并删除数据卷（**会丢数据**）
docker compose logs -f api
```

### 方式 B：本机没有 Docker 引擎时（当前开发机就是）

> **环境事实**：本机 Windows 的 `Microsoft-Windows-Subsystem-Linux`、`VirtualMachinePlatform`、`Microsoft-Hyper-V-All` **三项全部为 Disabled**，`HypervisorPresent=False`，Docker Desktop 的 Linux 引擎无法启动（`docker info` 报 500 / 管道不存在）。完整探测记录见 [`var/docker-probe.txt`](../var/docker-probe.txt)。开启这些功能需要重启机器，等于中断全组工作，所以**不擅自开启**，改走下面这条等价路径。

```powershell
cd D:\qiuzhibilei
$py = "C:\Users\<你的运行环境>\python.exe"   # 本机在 README「快速开始」里

& $py ops\local_up.py up       # 起 api（后台）+ 自动健康检查
& $py ops\local_up.py status
& $py ops\local_up.py logs
& $py ops\local_up.py down
```

- 默认端口 **8010**（避开队伍里正在用的 8000，脚本不会去杀别人的进程）。
- 环境变量：`QBL_LOCAL_PORT` / `QBL_LOCAL_DB` / `QBL_LOCAL_LOG_DIR`。
- 只管理自己拉起的进程（PID 记在 `var/local/api.pid`）。

---

## 二、数据迁移

原型期（SQLite）与生产（MySQL 8）之间是**单层替换**：`backend/app/db.py` 封装了全部 SQL，换库只改这一层。迁移步骤（切生产时执行）：

```bash
# 1) 先备份
cd ops && ./backup.sh

# 2) 建表：把 backend/sql/community.sql 与 app/db.py 里的 CREATE TABLE 转成 MySQL DDL
#    （注意：SQLite 的 TEXT/INTEGER 与 MySQL 的 VARCHAR/BIGINT 类型映射、utf8mb4 排序规则）

# 3) 灌数据：导出 SQLite 为 CSV → LOAD DATA 或 Python 脚本逐行写
# 4) 校验：逐表比对行数 + 抽样比对关键字段
# 5) 切 env：QBL_DB_PATH 改为 MySQL 连接串（等 db.py 支持后）
```

> **这条迁移是开发任务，不是运维能单方面完成的**：`db.py` 目前写死 `sqlite3`，需要开发者改这一层。运维提供库、备份与恢复手段。

---

## 三、备份 / 恢复

### 3.1 生产（docker compose）

```bash
cd ops
./backup.sh --encrypt                    # 加密备份到 ./backup/<时间戳>.tar.gz.gpg
./restore.sh backup/20261031-033000.tar.gz.gpg   # 恢复（有 10 秒反悔期）
```

- 保留 30 天；加密密钥（gpg 公钥）由老板保管。
- 上传 OSS（示例）：

```bash
ossutil cp backup/20261031-033000.tar.gz.gpg \
  oss://<备份Bucket>/db/2026/10/31/ --meta x-oss-storage-class:IA
```

### 3.2 本机（SQLite，已实测）

```bash
python ops/backup_local.py backup
python ops/backup_local.py verify  var/backup/qbl-<时间戳>.db.gz
python ops/backup_local.py restore var/backup/qbl-<时间戳>.db.gz --db var/backup/drill.db
```

---

## 四、本地验证记录（2026-10-31，命令输出原文）

### 4.1 环境探测

```
$ docker --version
Docker version 29.8.2, build 7fc2dff
$ docker compose version
Docker Compose version v5.5.1

$ docker info
failed to connect to the docker API at npipe:////./pipe/dockerDesktopLinuxEngine
→ Server: request returned 500 Internal Server Error

$ Microsoft-Windows-Subsystem-Linux = Disabled
$ VirtualMachinePlatform          = Disabled
$ Microsoft-Hyper-V-All           = Disabled
$ (Get-CimInstance Win32_ComputerSystem).HypervisorPresent
False
```

### 4.2 compose 配置校验（不需要引擎）

```
$ cd ops && docker compose config --quiet
exit=0        ← 配置语法与变量展开均合法
$ docker compose config
name: ops
services:
  api:   build.context: D:\qiuzhibilei / dockerfile: ops/Dockerfile.api
  mysql: image mysql:8.4, --character-set-server=utf8mb4
  redis: image redis:7.4, --appendonly yes
exit=0
```

### 4.3 本机一键启动（方式 B）实测

```
$ python ops/local_up.py up
[up] api 启动中 pid=23500 port=8010
[up] 健康检查通过：GET http://127.0.0.1:8010/health -> {"ok":true,"data":{"status":"up","service":"qbl-backend","version":"0.1.0"}}

$ python ops/local_up.py status
[status] pid=23500 存活=True 端口=8010
[status] GET /health -> status=200 body={"ok":true,"data":{"status":"up","service":"qbl-backend","version":"0.1.0"}}
```

启动日志（自动建表 + 灌种子）：

```
INFO: Started server process [23500]
2026-10-31 20:08:18,331 INFO 套路库已灌种子：50 条
2026-10-31 20:08:18,399 INFO 敏感词已灌种子：132 条
2026-10-31 20:08:18,404 INFO 数据库就绪：D:\qiuzhibilei\var\local\qbl.db
INFO: Application startup complete.
INFO:     127.0.0.1:61144 - "GET /health HTTP/1.1" 200 OK
```

数据库自检：

```
19 张表（含 sqlite_sequence）
ad_rewards, analysis_tasks, appeals, experiences, feedback, memberships, orders,
pattern_examples, pattern_hits, patterns, post_reports, posts, quota_ledger,
reports, sensitive_words, uploads, users, votes
patterns 50 / sensitive_words 132
```

### 4.4 后台鉴权实测（安全基线 §6 自查项）

```
$ Invoke-WebRequest http://127.0.0.1:8010/admin/stats   （不带 X-Admin-Token）
code=403
日志：127.0.0.1:61226 - "GET /admin/stats HTTP/1.1" 403 Forbidden
```

### 4.5 备份 + 恢复演练（SQLite）

```
$ python ops/backup_local.py backup
[backup] 源库：var/local/qbl.db（266240 字节，18 张表）
[backup] 产物：var/backup/qbl-20261031-201550.db.gz（25259 字节）
[backup] sha256：a943b5cd3909d001fe0df4a2fcb6f0834759796a37e0f7c9b181a052e172e01a

$ python ops/backup_local.py verify var/backup/qbl-20261031-201550.db.gz
[verify] integrity_check：ok
[verify] 表数量：18
[verify] sha256：a943b5cd3909d001fe0df4a2fcb6f0834759796a37e0f7c9b181a052e172e01a

$ python ops/backup_local.py restore var/backup/qbl-20261031-201550.db.gz --db var/backup/drill-restore.db
[restore] 已恢复：var/backup/qbl-20261031-201550.db.gz -> var/backup/drill-restore.db（18 张表）
```

> 注意：「源库 18 张表」是 `_tables()` 排除了 `sqlite_sequence` 后的计数，前面 sqlite 直接查是 19 张（含该系统表）。两个数不矛盾。

---

## 五、可选本地 OCR

`Dockerfile.api` 默认不装 OCR（镜像小）。要跑真 OCR：

```bash
docker build -f ops/Dockerfile.api --build-arg INSTALL_OCR=1 -t qbl-api:ocr .
```

会额外装 `rapidocr`、`onnxruntime`、`opencv-python-headless` 和 `libgl1/libglib2.0-0`。机型按 `上线方案.md` §2 选。

---

## 六、不做

不购买任何云资源、不做实名认证——整理成「老板待办」（见 `上线方案.md` §8、`icp-备案材料清单.md` §6）。
