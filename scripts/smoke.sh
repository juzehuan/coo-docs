#!/usr/bin/env bash
# 部署后探活：健康检查 → 登录 → 带令牌取 /auth/me。
#
# 为什么需要它：preflight.sh 在部署前导入一次应用，抓得住语法与 import 错误，
# 抓不住函数体里的名字/属性错误（第 80/85/89 轮三次同类）。第 89 轮一处
# `import datetime` 遮蔽了 `from datetime import datetime`，登录接口 500 约 3 分钟，
# 而部署者先去跑自己的专项测试才发现。部署后第一件事应当是把主路径打一遍。
#
# 用法：./scripts/smoke.sh [BASE_URL]        默认 http://127.0.0.1
#   凭据：SMOKE_USER / SMOKE_PASS（缺省只做健康检查与"登录接口能回 JSON"两步）
set -u
BASE="${1:-http://127.0.0.1}"
fail() { echo "  ✗ $*"; exit 1; }

# 后端容器 healthy 之前 nginx 会回 502，最多等 60 秒
for _ in $(seq 1 30); do
  code=$(curl -s -o /dev/null -w '%{http_code}' "$BASE/health" || true)
  [ "$code" = "200" ] && break
  sleep 2
done
[ "$code" = "200" ] || fail "健康检查 $BASE/health 返回 $code"
echo "  ✓ 健康检查 200"

USER_="${SMOKE_USER:-}"; PASS_="${SMOKE_PASS:-}"
if [ -z "$USER_" ]; then
  # 没给凭据：用一个必然错误的口令，只验证登录接口本身活着（应回 401 的 JSON，而不是 500）
  code=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$BASE/api/auth/login" \
         -H 'Content-Type: application/json' -d '{"username":"__smoke__","password":"x"}')
  [ "$code" = "401" ] || fail "登录接口返回 $code（期望 401），接口可能已坏"
  echo "  ✓ 登录接口存活（401 JSON）；未提供 SMOKE_USER/SMOKE_PASS，跳过真实登录"
  exit 0
fi
body=$(curl -s -X POST "$BASE/api/auth/login" -H 'Content-Type: application/json' \
       -d "{\"username\":\"$USER_\",\"password\":\"$PASS_\"}")
tok=$(printf '%s' "$body" | python3 -c 'import sys,json; print(json.load(sys.stdin).get("access_token",""))' 2>/dev/null || true)
[ -n "$tok" ] || fail "登录失败：$(printf '%s' "$body" | head -c 200)"
echo "  ✓ 登录成功"
code=$(curl -s -o /dev/null -w '%{http_code}' "$BASE/api/auth/me" -H "Authorization: Bearer $tok")
[ "$code" = "200" ] || fail "/auth/me 返回 $code"
echo "  ✓ 带令牌 /auth/me 200"
echo "探活通过。"
