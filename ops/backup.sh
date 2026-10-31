#!/usr/bin/env bash
# 面试请等等 · 备份脚本（MySQL + Redis + 数据卷）
#
# 用法（在 ops/ 目录，服务器上执行）：
#   ./backup.sh              # 备份到 ./backup/<时间戳>/
#   ./backup.sh --encrypt    # 备份并用 gpg 加密（生产必须加，密钥由老板保管）
#
# 保留策略：本地保留 30 天，加密包再上传 OSS（上传命令见 ops/README.md）
# 前置：docker compose 服务已在运行
set -euo pipefail

STAMP="$(date +%Y%m%d-%H%M%S)"
OUT_DIR="${BACKUP_DIR:-./backup}/${STAMP}"
ENCRYPT=0
[[ "${1:-}" == "--encrypt" ]] && ENCRYPT=1

mkdir -p "${OUT_DIR}"

echo "[backup] 开始 ${STAMP} -> ${OUT_DIR}"

# ---------- MySQL：逻辑备份（--single-transaction 不锁表）----------
echo "[backup] mysqldump ..."
docker compose exec -T mysql sh -c \
  'exec mysqldump --single-transaction --quick --routines --triggers \
   -uroot -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE"' \
  | gzip > "${OUT_DIR}/mysql.sql.gz"
echo "[backup] MySQL 备份完成：$(du -h "${OUT_DIR}/mysql.sql.gz" | cut -f1)"

# ---------- Redis：先落盘，再拷 AOF/RDB ----------
echo "[backup] redis BGSAVE ..."
docker compose exec -T redis sh -c 'redis-cli --no-auth-warning ${REDIS_PASSWORD:+-a "$REDIS_PASSWORD"} BGSAVE' || true
sleep 2
docker compose cp redis:/data/appendonlydir "${OUT_DIR}/redis-appendonlydir" 2>/dev/null \
  || echo "[backup] 跳过 Redis AOF（可能未启用）"

# ---------- 一致性说明 ----------
# 截图不做备份：OSS 上按 24 小时生命周期自动删除，属合规要求（见 ops/上线方案.md §3.3）
cat > "${OUT_DIR}/README.txt" <<EOF
备份时间：${STAMP}
包含：mysql.sql.gz（MySQL 逻辑备份）、redis-appendonlydir（如启用 AOF）
不包含：用户截图（按合规要求 24 小时自动删除，不留存备份）
恢复方法：见 ops/README.md「备份 / 恢复」
EOF

# ---------- 加密 ----------
if [[ "${ENCRYPT}" == "1" ]]; then
  echo "[backup] gpg 加密 ..."
  tar -czf - -C "${OUT_DIR}" . | gpg --batch --yes --encrypt \
    --recipient "${BACKUP_GPG_RECIPIENT:?未设置 BACKUP_GPG_RECIPIENT}" \
    --output "${OUT_DIR}.tar.gz.gpg"
  rm -rf "${OUT_DIR}"
  echo "[backup] 加密包：${OUT_DIR}.tar.gz.gpg（明文目录已删）"
fi

# ---------- 清理 30 天前的本地备份 ----------
find "${BACKUP_DIR:-./backup}" -maxdepth 1 -mtime +30 -name '20*' -exec rm -rf {} + 2>/dev/null || true

echo "[backup] 完成"
