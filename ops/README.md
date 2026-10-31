# ops/ 部署与上线

> 负责人：运维（数字员工）。D7 前补齐，本文件是骨架。

## 目标形态

```
api        FastAPI（backend.app.main:app）
mysql      MySQL 8（生产；本地原型可用 SQLite）
redis      Redis（任务队列/限流，接 Celery 后启用）
ocr        RapidOCR 随 api 进程内运行（CPU）
```

## 文件

- `docker-compose.yml`：一键起 api + mysql + redis（本地验证用）。
- `Dockerfile.api`：api 镜像（待运维补）。
- `.env.example`：部署用环境变量清单（与仓库根 `.env.example` 对齐，密钥不进代码）。
- `上线方案.md`：云厂商/机型/存储/备份/监控/日志（保留 ≥6 个月）/成本表（D7 前交付）。
- `icp-备案材料清单.md`：备案材料与流程（D7 前交付）。
- `安全基线.md`：密钥管理、后台来源限制、防火墙端口、HTTPS（D7 前交付）。

## 本地一键跑通（验收 D7）

```bash
cd ops
cp .env.example .env   # 填本地值（不要提交）
docker compose up -d
docker compose ps
curl http://127.0.0.1:8000/health
```

## 不做

不购买任何云资源、不做实名认证——整理成「老板待办」（见 `上线方案.md` 末尾）。
