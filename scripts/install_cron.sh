#!/usr/bin/env bash
# 安装/补齐 coo-docs 的三条定时任务（幂等，可单独反复执行）：
#   每日 02:00 备份、每月 1 日 03:00 恢复演练、每周日 04:00 附件内容完整性核对。
#
# 为什么从 install.sh 里抽出来（第 103 轮）：install.sh 是"全新机器一次装完"的路径，
# 会生成 .env、构建并启动服务——在一台已经在跑的机器上不能再执行它。演示机正是这样：
# 它在 install.sh 出现之前就搭好了，于是三条任务一条都没装，"每日备份"只存在于手册里。
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
warn() { echo "[WARN] $*" >&2; }
[ -f "$ROOT/.env" ] || { echo "[ERROR] $ROOT/.env 不存在：备份与演练脚本需要它里面的口令" >&2; exit 1; }
BK="$ROOT/scripts/backup_mysql.sh"
DR="$ROOT/scripts/restore_drill.sh"
# 日志目录必须先确定再拼 cron 行：非 root 部署时 /var/log 不可写，
# 若仍把路径写成 /var/log/...，cron 的输出会直接丢掉——而"备份失败"正是
# 靠这份日志和退出码被发现的，写进一个黑洞等于把告警关掉了
if [ -w /var/log ] || { touch /var/log/coo_backup.log 2>/dev/null; }; then
  LOGDIR=/var/log
else
  LOGDIR="$ROOT/logs"
  mkdir -p "$LOGDIR"
  warn "/var/log 不可写，备份日志改落 $LOGDIR"
fi
CRON_BK="0 2 * * * cd $ROOT && set -a && . ./.env && set +a && $BK >> $LOGDIR/coo_backup.log 2>&1 # coo-docs-backup"
CRON_DR="0 3 1 * * cd $ROOT && set -a && . ./.env && set +a && $DR >> $LOGDIR/coo_drill.log 2>&1 # coo-docs-drill"
# 每周日 04:00 逐个重算附件 sha256：证据文件被改动（位翻转/误覆盖/篡改）时，
# 只有这一项能发现；存在性巡检与备份演练都查不出内容错误（第 83 轮）
CRON_VF="0 4 * * 0 cd $ROOT && docker compose exec -T backend python /app/scripts/storage_check.py --verify >> $LOGDIR/coo_verify.log 2>&1 # coo-docs-verify"
# 追加而非覆盖：宿主上可能还有别的项目的任务，crontab - 会整体替换
CUR="$(crontab -l 2>/dev/null || true)"
ADD=""
echo "$CUR" | grep -q 'coo-docs-backup' || ADD="$ADD$CRON_BK"$'\n'
echo "$CUR" | grep -q 'coo-docs-drill'  || ADD="$ADD$CRON_DR"$'\n'
echo "$CUR" | grep -q 'coo-docs-verify' || ADD="$ADD$CRON_VF"$'\n'
if [ -n "$ADD" ]; then
  printf '%s\n%s' "$CUR" "$ADD" | sed '/^$/d' | crontab -
  echo "已追加定时任务（原有任务保留）："
  crontab -l | grep 'coo-docs' | sed 's/^/  /'
else
  echo "定时任务已存在，跳过。"
fi
touch "$LOGDIR/coo_backup.log" "$LOGDIR/coo_drill.log" "$LOGDIR/coo_verify.log" 2>/dev/null || true
echo "  备份日志：$LOGDIR/coo_backup.log · 演练日志：$LOGDIR/coo_drill.log"

