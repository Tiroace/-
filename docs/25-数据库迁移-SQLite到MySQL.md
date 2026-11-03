# 数据库迁移：SQLite → MySQL（代码侧已就绪，等云托管 MySQL 开通）

**状态**：代码完成、本地 SQLite 回归全绿；**MySQL 真连接未验证**（本机无驱动、无云托管 MySQL 实例），
不拿本地结果冒充云端验证。

## 一、改了什么

| 文件 | 作用 |
| --- | --- |
| `backend/app/db_adapter.py`（新） | 双引擎门面：`Database.connect()` / `transaction()` 在 SQLite 与 MySQL 间透明切换 |
| `backend/app/db.py` | 保留原类名与 SCHEMA，实现委托给适配层（业务代码零改动） |
| `backend/app/config.py` | 新增 `QBL_DB_URL` |
| `backend/app/deps.py` | `get_db()` 按 `QBL_DB_URL` 选引擎，切库时正确重建单例 |
| `scripts/migrate_to_mysql.py`（新） | 建表 + 搬数据 + 行数比对 |
| `backend/tests/test_db_adapter.py`（新） | 18 条：连接串解析、方言翻译、SQLite 回归 |

**关键设计：业务代码一行没改**。全仓库 33 个后端文件都用 `?` 占位符、`row["列名"]` 取值，
适配层统一处理：

- `?` → `%s`（并转义字面量里的 `%`）
- MySQL 返回元组 → 包成可按键访问的行（等价 `sqlite3.Row`）
- `INSERT OR IGNORE` → `INSERT IGNORE`、`INSERT OR REPLACE` → `REPLACE`
- 建表脚本 `AUTOINCREMENT` → `AUTO_INCREMENT`、去掉 MySQL 不认的 `CREATE INDEX IF NOT EXISTS`、
  `TEXT PRIMARY KEY` → `VARCHAR(64)`（MySQL 不允许 TEXT 作主键）
- 补列迁移：SQLite 查 `PRAGMA table_info`，MySQL 查 `information_schema`

## 二、怎么切

```bash
# 本地/测试（默认，不用配）
# 什么都不设 → SQLite，走 QBL_DB_PATH

# 云托管 MySQL
QBL_DB_URL="mysql://用户:口令@主机:3306/库名?charset=utf8mb4"
```

**部署前需要装驱动**：`pip install pymysql`（已写进部署手册依赖；本地跑 SQLite 回归不需要它）。

## 三、迁移步骤（云托管 MySQL 开通后）

```bash
# 1. 先只看 schema 能不能在 MySQL 建起来
python scripts/migrate_to_mysql.py --target "mysql://…" --schema-only

# 2. 建表 + 搬数据（源库默认 var/backend/qbl.db）
python scripts/migrate_to_mysql.py --source var/backend/qbl.db --target "mysql://…"

# 3. 脚本会逐表比对行数，任何一张不一致就 exit 1
```

脚本特点：按外键顺序搬（先父表后子表）、幂等（目标非空默认跳过，`--replace` 强制重搬）、
**不打印口令**（只回显 host 和库名）、单行失败会打印是哪一行而不是静默丢。

## 四、验证结果

```
pytest backend/tests            76 passed（其中 test_db_adapter.py 18 条）
engine.selftest                 76/76
migrate_to_mysql.py --schema-only（无驱动）
    → "[FAIL] 连不上目标库：…请先 pip install pymysql"，exit=2（不是抛堆栈）
```

方言翻译有硬断言：**把真实 SCHEMA 全文翻译后，验证产物里不含 `AUTOINCREMENT`、
不含 `CREATE INDEX IF NOT EXISTS`、没有 `TEXT PRIMARY KEY`** —— 这三条任一残留，MySQL 建表就会失败。

## 五、还没验证的（部署后必须补）

1. **MySQL 真建表**：上面是离线翻译校验，真实 MySQL 8 语法细节（索引长度、默认值）要连上去才知道
2. **数据搬迁实跑**：本地没有真实数据量，空库搬迁不能证明大表也没问题
3. **并发事务行为**：SQLite 用 `BEGIN IMMEDIATE`，MySQL 用 `START TRANSACTION` + InnoDB 行锁，
   额度扣减的并发正确性要在 MySQL 上重跑一遍压测（本地只验证了串行回滚）

## 六、给运维

1. 云托管建 MySQL 后，把连接串作为 `QBL_DB_URL` 环境变量注入
2. 服务启动会自己建表（`Database.init()` 在 `startup` 里跑），不用手工执行 DDL
3. 首次切换建议先跑 `--schema-only`，确认建表无误再搬数据
