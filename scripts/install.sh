#!/usr/bin/env bash
# coo-docs 首次部署。目标是让「装完即是正确状态」，而不是留一份要人逐条照做的清单。
#
# 做四件事：
#   1. 生成随机口令写入 .env（数据库、对象存储、备份加密）
#   2. 构建并启动服务
#   3. 追加每日备份与每月恢复演练的 crontab
#   4. 自检并打印 admin 初始口令
#
# 可重复运行：已存在的 .env 不会被覆盖，已装过的 crontab 不会重复追加。
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"

say()  { printf '\n\033[1m== %s\033[0m\n' "$*"; }
warn() { printf '\033[33m[WARN] %s\033[0m\n' "$*" >&2; }
die()  { printf '\033[31m[ERROR] %s\033[0m\n' "$*" >&2; exit 1; }

# 口令只用字母数字：MYSQL_PASSWORD 会被拼进 DATABASE_URL，
# 其中的 @ : / ? # 会被当成 URL 分隔符，后端会连不上库且报错难懂
genpw() { LC_ALL=C tr -dc 'A-Za-z0-9' < /dev/urandom | head -c "${1:-32}"; }

command -v docker >/dev/null || die "未找到 docker"
docker compose version >/dev/null 2>&1 || die "未找到 docker compose（v2）"

say "1/4 生成配置"
if [ -f .env ]; then
  warn ".env 已存在，保持不变。"
  warn "（若要轮换口令，请勿直接改这里：库已初始化后改 .env 只会让后端连不上，"
  warn "  正确步骤见《部署与运维手册》§11.3）"
else
  # 库已经初始化过、却没有 .env —— 这时生成新口令会让后端连不上已有的库
  # 只看**本项目**的卷：grep 'mysql_data' 会匹配同一台机器上其他项目的同名卷，
  # 在一台干净的客户机上也可能误判中止（本机就有别的项目命中）
  PROJECT="${COMPOSE_PROJECT_NAME:-$(basename "$ROOT" | tr '[:upper:]' '[:lower:]' | tr -cd 'a-z0-9_-')}"
  if docker volume ls -q 2>/dev/null | grep -qx "${PROJECT}_mysql_data"; then
    warn "检测到已存在的 mysql_data 数据卷，但没有 .env。"
    warn "新生成的口令**不会**改掉库里的既有口令，服务会起不来。"
    die  "请先从原部署取回 .env，或确认可以丢弃该卷后执行 docker compose down -v 再重来。"
  fi
  umask 077
  cat > .env <<EOF
# 由 scripts/install.sh 于 $(date '+%Y-%m-%d %H:%M:%S %Z') 生成。
# 口令仅在数据库首次初始化时生效；库建好后改这里不会改掉库里的口令。
MYSQL_ROOT_PASSWORD=$(genpw 32)
MYSQL_DATABASE=coo
MYSQL_USER=coo
MYSQL_PASSWORD=$(genpw 32)

MINIO_ROOT_USER=coo$(genpw 8)
MINIO_ROOT_PASSWORD=$(genpw 40)
S3_ENDPOINT_URL=http://minio:9000
S3_BUCKET=coo-nas
S3_REGION=us-east-1

TIMEZONE=${TIMEZONE:-Asia/Bangkok}
CORS_ORIGINS=${CORS_ORIGINS:-http://localhost}

BACKUP_ENCRYPT_PASS=$(genpw 40)
EOF
  chmod 600 .env
  echo "已生成 .env（权限 600，已被 .gitignore 忽略）"
  [ -n "${TIMEZONE:-}" ] || warn "时区取了默认值 Asia/Bangkok，如客户不在此时区请改 .env 的 TIMEZONE 后重启"
fi

say "2/4 构建并启动服务"
docker compose up -d --build

say "3/4 安装定时任务"
"$ROOT/scripts/install_cron.sh"

say "4/4 自检"
# 端口从 compose 的实际映射里取，不写死：override 或改过端口时写死的 8000 会误报失败
HP="$(docker compose port backend 8000 2>/dev/null | tail -1)"
HP="${HP:-127.0.0.1:8000}"
for i in $(seq 1 30); do
  if curl -fsS "http://${HP}/health" >/dev/null 2>&1; then break; fi
  sleep 3
done
HEALTH="$(curl -fsS "http://${HP}/health" 2>/dev/null || echo '')"
[ -n "$HEALTH" ] || die "服务未在 90 秒内就绪，请查看 docker compose logs backend"
echo "  http://${HP}/health -> $HEALTH"

# admin 初始口令只在首次启动时打印一次
PWLINE="$(docker compose logs backend 2>/dev/null | grep -i -m1 'admin.*密码\|初始密码' || true)"

cat <<EOF

────────────────────────────────────────────────────────────
部署完成。请立刻处理下面两件事，它们**没有**被自动化掉：

1. 管理员初始口令
$( [ -n "$PWLINE" ] && echo "   $PWLINE" || echo "   未在日志中找到（可能不是首次启动）：docker compose logs backend | grep -i 密码" )
   登录后立即改成自己的口令。

2. 备份加密口令保管
   .env 里的 BACKUP_ENCRYPT_PASS 是解开备份的唯一钥匙。
   请复制到密码管理器或其他与本机分离的地方——
   它和备份放在同一台机器上，等于没有加密；丢了则备份永久打不开。

仍需人工决定的事项见 docs/上线待办与风险记录.md「交付时人工确认」一节。
────────────────────────────────────────────────────────────
EOF
