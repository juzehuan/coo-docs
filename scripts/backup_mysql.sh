#!/usr/bin/env bash
# MySQL 每日备份（规格书第五章：每日自动备份，云端保留 30 天）
# 用法：手动执行，或加入 crontab（见 docs/部署与运维手册.md）：
#   0 2 * * * /srv/platform/code/coo-docs/scripts/backup_mysql.sh >> /var/log/coo_backup.log 2>&1
set -euo pipefail
cd "$(dirname "$0")/.."

BACKUP_DIR="${BACKUP_DIR:-./backups}"
KEEP_DAYS="${KEEP_DAYS:-30}"
DB_USER="${MYSQL_USER:-coo}"
DB_PASS="${MYSQL_PASSWORD:-coo123456}"   # 与 docker-compose.yml 保持一致；轮换密码后同步修改
DB_NAME="${MYSQL_DATABASE:-coo}"

mkdir -p "$BACKUP_DIR"
STAMP="$(date +%F_%H%M%S)"
OUT="$BACKUP_DIR/coo_${STAMP}.sql.gz"

# 密码经 MYSQL_PWD 环境变量传入，避免特殊字符破坏 shell 引号；
# pipefail 下管道失败（容器未运行/认证失败）由 if 捕获并清理残留文件
# --no-tablespaces：业务账号没有 PROCESS 权限，不加会打印
# "Access denied ... PROCESS privilege" 错误行污染 cron 日志（InnoDB 逻辑备份不需要表空间信息）
if ! docker compose exec -T -e MYSQL_PWD="$DB_PASS" mysql \
    mysqldump -u"$DB_USER" --single-transaction --routines --triggers --no-tablespaces "$DB_NAME" \
    | gzip > "$OUT"; then
  echo "[ERROR] mysqldump 失败（容器未运行或认证失败），已删除残留文件：$OUT" >&2
  rm -f "$OUT"
  exit 1
fi

# 附加校验：正常业务库导出远大于 1KB，过小说明导出内容异常
if [ "$(stat -c%s "$OUT")" -lt 1024 ]; then
  echo "[ERROR] 备份文件异常过小：$OUT" >&2
  rm -f "$OUT"
  exit 1
fi

# 可用性自检：能解压 + 含关键表的建表语句，才算真正可用的备份。
# 光看"文件生成了"不足以说明能恢复——不可恢复的备份等于没有备份。
if ! gunzip -t "$OUT" 2>/dev/null; then
  echo "[ERROR] 备份文件损坏（gzip 校验失败）：$OUT" >&2
  rm -f "$OUT"; exit 1
fi
# 一次性取出全部建表语句再逐个比对。
# 注意不能写成 `gunzip -c ... | grep -q`：grep -q 命中即退出会让 gunzip 收到 SIGPIPE，
# 在 set -o pipefail 下整条管道被判为失败，进而把正常备份当成损坏文件删掉（假阳性比不检查更糟）。
DUMPED_TABLES="$(gunzip -c "$OUT" | grep -F 'CREATE TABLE ' || true)"
for tbl in users orders attachments audit_logs system_settings; do
  case "$DUMPED_TABLES" in
    *"CREATE TABLE \`$tbl\`"*) ;;
    *) echo "[ERROR] 备份缺少关键表 $tbl：$OUT" >&2; rm -f "$OUT"; exit 1 ;;
  esac
done

find "$BACKUP_DIR" -name 'coo_*.sql.gz' -mtime "+$KEEP_DAYS" -delete
echo "[OK] $(date '+%F %T') 备份完成：$OUT（保留 ${KEEP_DAYS} 天）"
