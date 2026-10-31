#!/usr/bin/env bash
# 面试请等等 · 恢复脚本（从备份恢复到 MySQL）
#
# 用法（在 ops/ 目录）：
#   ./restore.sh backup/20261031-033000/mysql.sql.gz
#   ./restore.sh backup/20261031-033000.tar.gz.gpg      # 加密包，会先解密
#
# 注意：恢复会覆盖当前库！执行前必须有：① 明确要恢复的时间点 ② 已被知会的人
set -euo pipefail

SRC="${1:?用法: ./restore.sh <备份文件>}"
WORK="$(mktemp -d)"
trap 'rm -rf "${WORK}"' EXIT

# ---------- 解密（如果是 gpg 包）----------
case "${SRC}" in
  *.gpg)
    echo "[restore] gpg 解密 ${SRC}"
    gpg --batch --yes --decrypt "${SRC}" | tar -xzf - -C "${WORK}"
    SQL="${WORK}/mysql.sql.gz"
    ;;
  *)
    SQL="${SRC}"
    ;;
esac

[[ -f "${SQL}" ]] || { echo "[restore] 找不到 ${SQL}"; exit 1; }

echo "!! 即将把 ${SQL} 恢复到当前 MySQL，10 秒内 Ctrl+C 可取消 !!"
sleep 10

echo "[restore] 恢复中 ..."
docker compose exec -T mysql sh -c \
  'exec mysql -uroot -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE"' < <(gunzip -c "${SQL}")

echo "[restore] 完成。请立刻验证："
echo "  curl -s http://127.0.0.1:8000/health"
echo "  docker compose exec -T mysql sh -c 'mysql -uroot -p\"\$MYSQL_ROOT_PASSWORD\" \"\$MYSQL_DATABASE\" -e \"SHOW TABLES;\"'"
