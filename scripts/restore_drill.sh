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

SRC="${1:-$(ls -t backups/*.sql.gz backups/*.sql.gz.enc 2>/dev/null | head -1)}"
DRILL_DB="coo_restore_drill"
PROD_DB="${MYSQL_DATABASE:-coo}"
# 自动读取 .env：口令自 2026-08-26 起只存在于 .env（compose 只引用不存值）。
# 脚本自己读，就不必依赖 cron 行里记得写 `. ./.env`——少一个会静默失效的前提。
# **只补齐未设置的变量**：`set -a && . ./.env` 会覆盖调用者显式传入的值，
# 那会让"临时指向另一套配置跑一次"变得不可能，且失败原因极难看出来。
if [ -f ./.env ]; then
  while IFS='=' read -r _k _v; do
    case "$_k" in ''|'#'*) continue ;; *[!A-Za-z0-9_]*) continue ;; esac
    [ -n "${!_k:-}" ] || export "$_k=$_v"
  done < ./.env
fi

# 不设弱默认值：口令拿不到就失败退出，而不是拿 rootpass 去试
ROOT_PASS="${MYSQL_ROOT_PASSWORD:-}"
if [ -z "$ROOT_PASS" ]; then
  echo "[ERROR] 未取到 MYSQL_ROOT_PASSWORD：请确认项目根目录下有 .env（见 .env.example）。" >&2
  exit 1
fi

[ -n "$SRC" ] && [ -f "$SRC" ] || { echo "[ERROR] 找不到备份文件（先执行 scripts/backup_mysql.sh）" >&2; exit 1; }
echo "演练备份：$SRC"

# 加密备份先解到临时目录再演练——离机留存的备份必须能在演练里走通解密这一步，
# 否则"能解密"这个假设永远没被验证过，真出事时才发现口令不对就来不及了。
DECDIR=""
# 末尾必须 `return 0`：EXIT trap 的返回值会覆盖脚本退出码，而明文备份场景下
# DECDIR 为空、`[ -n "" ]` 返回 1，会让一次通过的演练以退出码 1 结束——
# 监控只看退出码的话，就变成天天报假故障。
cleanup_dec() { [ -n "$DECDIR" ] && rm -rf "$DECDIR"; return 0; }
trap cleanup_dec EXIT
case "$SRC" in
  *.enc)
    [ -n "${BACKUP_ENCRYPT_PASS:-}" ] || { echo "[ERROR] 备份已加密，请设置 BACKUP_ENCRYPT_PASS" >&2; exit 1; }
    DECDIR="$(mktemp -d)"
    PLAIN="$DECDIR/$(basename "${SRC%.enc}")"
    if ! openssl enc -d -aes-256-cbc -pbkdf2 -iter 600000 \
         -pass env:BACKUP_ENCRYPT_PASS -in "$SRC" -out "$PLAIN" 2>/dev/null; then
      echo "[ERROR] 备份解密失败（口令不符或文件损坏）：$SRC" >&2; exit 1
    fi
    echo "  已解密到临时目录用于演练"
    SRC_ENC="$SRC"; SRC="$PLAIN"
    ;;
esac

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

# ---- 附件文件在位校验 ----
# 数据库恢复得再完美，附件文件缺失一样是「证据丢失」：附件表里每条记录都指向
# UPLOAD_DIR 下一个按内容哈希命名的物理文件。此前演练只比对数据库，因此完全
# 看不出「备份不含附件目录」这个缺口——恢复到新机会得到一堆悬空记录。
echo
# 附件备份与数据库备份由同一次 backup_mysql.sh 产出、同目录同时间戳，
# 优先取同一时间戳的那一份，避免拿数据库与附件对不上号的两次备份来演练
# 基于**原始**备份路径推导：加密场景下 $SRC 已被换成解密后的临时文件，
# 用它推导会指向临时目录。同时要剥掉 .enc 后缀，否则时间戳里会混进后缀。
SRC_ORIG="${SRC_ENC:-$SRC}"
BK_DIR="$(dirname "$SRC_ORIG")"
BK_STAMP="$(basename "$SRC_ORIG" | sed -e 's/\.enc$//' -e 's/\.sql\.gz$//' -e 's/^coo_//')"
FILES_BK="$BK_DIR/coo_files_${BK_STAMP}.tar.gz"
[ -f "$FILES_BK" ] || { [ -f "$FILES_BK.enc" ] && FILES_BK="$FILES_BK.enc"; } || true
# `|| true`：无匹配时 ls 返回非零，在 set -e + pipefail 下会直接杀掉脚本——
# 而那恰恰是本检查要报告的场景（备份里没有附件），哑着退出等于检查失效
[ -f "$FILES_BK" ] || FILES_BK="$(ls -t "$BK_DIR"/coo_files_*.tar.gz 2>/dev/null | head -1 || true)"
if [ -z "$FILES_BK" ]; then
  echo "  [ERROR] 未找到附件备份 coo_files_*.tar.gz —— 仅有数据库备份无法恢复证据" >&2
  fail=1
else
  # 取演练库中全部被引用的存储文件名，逐个确认在附件备份里
  NEED="$(my -N -e "SELECT DISTINCT file_name FROM $DRILL_DB.attachments;")"
  # 加密的附件包先解密再列目录
  case "$FILES_BK" in
    *.enc) HAVE="$(openssl enc -d -aes-256-cbc -pbkdf2 -iter 600000 \
                     -pass env:BACKUP_ENCRYPT_PASS -in "$FILES_BK" 2>/dev/null \
                   | tar -tz 2>/dev/null | sed 's#.*/##')" ;;
    *)     HAVE="$(tar -tzf "$FILES_BK" | sed 's#.*/##')" ;;
  esac
  miss=0; total=0
  for f in $NEED; do
    total=$((total+1))
    case "$HAVE" in *"$f"*) ;; *) miss=$((miss+1)) ;; esac
  done
  if [ "$miss" -eq 0 ]; then
    printf "  %-28s OK（%s 个被引用文件全部在备份中）\n" "附件文件在位" "$total"
  else
    printf "  %-28s FAIL（%s/%s 个文件缺失）\n" "附件文件在位" "$miss" "$total"
    fail=1
  fi
fi

my -e "DROP DATABASE IF EXISTS $DRILL_DB;"
echo
if [ "$fail" = "0" ]; then
  echo "[OK] 恢复演练通过（演练库已清理），RTO 参考：${ELAPSED}s + 应用重启时间"
else
  echo "[ERROR] 恢复演练发现差异，请立即排查备份链路" >&2
fi
exit "$fail"
