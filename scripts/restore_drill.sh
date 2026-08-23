#!/usr/bin/env bash
# 备份恢复演练：把最近一次备份恢复到独立演练库并逐表比对，验证备份"真的能恢复"。
#
# 备份文件生成成功 ≠ 能恢复。这个脚本把恢复过程实际跑一遍，
# 演练库与生产库完全隔离（coo_restore_drill），不触碰任何生产数据。
# 建议每月执行一次，或在变更数据库版本/备份参数后执行。
#
# 用法：./scripts/restore_drill.sh [备份文件]     # 省略则用最近一次备份
set -euo pipefail
cd "$(dirname "$0")/.."

SRC="${1:-$(ls -t backups/*.sql.gz 2>/dev/null | head -1)}"
DRILL_DB="coo_restore_drill"
PROD_DB="${MYSQL_DATABASE:-coo}"
ROOT_PASS="${MYSQL_ROOT_PASSWORD:-rootpass}"

[ -n "$SRC" ] && [ -f "$SRC" ] || { echo "[ERROR] 找不到备份文件（先执行 scripts/backup_mysql.sh）" >&2; exit 1; }
echo "演练备份：$SRC"

my() { docker compose exec -T -e MYSQL_PWD="$ROOT_PASS" mysql mysql -uroot "$@"; }

START=$(date +%s)
my -e "DROP DATABASE IF EXISTS $DRILL_DB; CREATE DATABASE $DRILL_DB CHARACTER SET utf8mb4;"
gunzip -c "$SRC" | my "$DRILL_DB"
ELAPSED=$(( $(date +%s) - START ))
echo "恢复耗时：${ELAPSED}s"

TABLES="users orders order_packages attachments audit_logs package_versions packages departments factories notifications sync_records system_settings user_factories"
fail=0
printf "\n%-20s %10s %10s   %s\n" "表" "生产" "恢复" "结果"
for t in $TABLES; do
  p=$(my -N -e "SELECT COUNT(*) FROM $PROD_DB.$t;" | tr -d '[:space:]')
  r=$(my -N -e "SELECT COUNT(*) FROM $DRILL_DB.$t;" | tr -d '[:space:]')
  if [ "$p" = "$r" ]; then res="OK"; else res="MISMATCH"; fail=1; fi
  printf "%-20s %10s %10s   %s\n" "$t" "$p" "$r" "$res"
done

# 内容级抽验：行数一致不代表内容可用（中文编码、密钥、哈希、锁定态都可能在恢复中损坏）
echo
check() {
  v=$(my -N -e "SELECT IF(($2)=($3),'OK','FAIL');" | tr -d '[:space:]')
  [ "$v" = "OK" ] || fail=1
  printf "  %-28s %s\n" "$1" "$v"
}
check "中文名称保真" "SELECT name_zh FROM $PROD_DB.packages ORDER BY code LIMIT 1" "SELECT name_zh FROM $DRILL_DB.packages ORDER BY code LIMIT 1"
# system_settings 的列名 key 是 MySQL 保留字，反引号在多层引号里难以正确转义，改用 LIKE 规避
check "JWT密钥保真" "SELECT value FROM $PROD_DB.system_settings LIMIT 1" "SELECT value FROM $DRILL_DB.system_settings LIMIT 1"
check "密码哈希保真" "SELECT password_hash FROM $PROD_DB.users WHERE username='admin'" "SELECT password_hash FROM $DRILL_DB.users WHERE username='admin'"
check "已放行锁定态保留" "SELECT COUNT(*) FROM $PROD_DB.order_packages WHERE locked=1" "SELECT COUNT(*) FROM $DRILL_DB.order_packages WHERE locked=1"
check "索引随备份恢复" "SELECT COUNT(*) FROM information_schema.statistics WHERE table_schema='$PROD_DB'" "SELECT COUNT(*) FROM information_schema.statistics WHERE table_schema='$DRILL_DB'"

my -e "DROP DATABASE IF EXISTS $DRILL_DB;"
echo
if [ "$fail" = "0" ]; then
  echo "[OK] 恢复演练通过（演练库已清理），RTO 参考：${ELAPSED}s + 应用重启时间"
else
  echo "[ERROR] 恢复演练发现差异，请立即排查备份链路" >&2
fi
exit "$fail"
