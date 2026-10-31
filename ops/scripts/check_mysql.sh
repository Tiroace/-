#!/usr/bin/env bash
# MySQL 就绪自检：容器健康 + 能连 + 库在 + 字符集对
# 用法（ops/ 目录）：./scripts/check_mysql.sh
set -euo pipefail

echo "[check] 容器状态"
docker compose ps mysql

echo "[check] 连通性 + 版本 + 字符集"
docker compose exec -T mysql sh -c '
  mysql -uroot -p"$MYSQL_ROOT_PASSWORD" -e "
    SELECT VERSION() AS version;
    SHOW VARIABLES LIKE \"character_set_server\";
    SHOW VARIABLES LIKE \"collation_server\";
    SHOW DATABASES LIKE \"$MYSQL_DATABASE\";
  "' 2>/dev/null

echo "[check] 业务账号可用"
docker compose exec -T mysql sh -c '
  mysql -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" "$MYSQL_DATABASE" -e "SELECT 1 AS ok;"' 2>/dev/null

echo "[check] 通过"
