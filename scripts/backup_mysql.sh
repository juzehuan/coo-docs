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

# ---- 附件文件 ----
# 只备份数据库是不够的：附件表里的记录指向 UPLOAD_DIR 下按内容哈希命名的物理
# 文件，仅凭数据库在新机恢复出来的是一堆指向不存在文件的记录——storage_check
# 会逐条报「证据丢失，需人工恢复」。而本系统的全部价值就在证据完整。
# NAS 上虽有第二副本，但归档路径用的是「原文件名」而非内容哈希，重建 uploads/
# 需要逐个重算 sha256 并改名，没有现成脚本，不能当作恢复手段。
#
# 文件按内容哈希命名、内容不可变（只增不改），因此这里用 tar 全量打包即可；
# 数据量大到全量不划算时，可改为对同一目录做增量 rsync——不可变意味着增量安全。
UPLOAD_DIR="${UPLOAD_DIR:-./data/uploads}"
FILES_OUT="$BACKUP_DIR/coo_files_${STAMP}.tar.gz"
if [ -d "$UPLOAD_DIR" ]; then
  if ! tar -czf "$FILES_OUT" -C "$(dirname "$UPLOAD_DIR")" "$(basename "$UPLOAD_DIR")"; then
    echo "[ERROR] 附件目录打包失败：$UPLOAD_DIR" >&2
    rm -f "$FILES_OUT"; exit 1
  fi
  if ! tar -tzf "$FILES_OUT" >/dev/null 2>&1; then
    echo "[ERROR] 附件备份损坏（tar 校验失败）：$FILES_OUT" >&2
    rm -f "$FILES_OUT"; exit 1
  fi
  FILE_CNT="$(tar -tzf "$FILES_OUT" | grep -vc '/$' || true)"
  echo "[OK] 附件备份完成：$FILES_OUT（$FILE_CNT 个文件，$(du -h "$FILES_OUT" | cut -f1)）"
else
  # 目录不存在通常意味着路径配错或挂载没起来——静默跳过会让人以为备份是完整的
  echo "[ERROR] 附件目录不存在：$UPLOAD_DIR（如路径不同请设 UPLOAD_DIR 环境变量）" >&2
  exit 1
fi

find "$BACKUP_DIR" -name 'coo_*.sql.gz' -mtime "+$KEEP_DAYS" -delete
find "$BACKUP_DIR" -name 'coo_files_*.tar.gz' -mtime "+$KEEP_DAYS" -delete
echo "[OK] $(date '+%F %T') 备份完成：$OUT + $FILES_OUT（保留 ${KEEP_DAYS} 天）"
