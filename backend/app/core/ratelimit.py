"""进程内接口限流（规格书第五章「接口限流与登录失败锁定」）。

按客户端 IP 的滑动窗口计数：
- 登录接口：60 次 / 分钟；暴力破解的主闸是账号级失败锁定（5 次锁 30 分钟），
  此处阈值放宽以容纳整厂共用一个出口 IP 时的换班集中登录。
- 其余接口：1200 次 / 分钟（约 20 并发用户 + 通知轮询的数倍余量，仅拦异常流量）。
超限返回 429。

内存回收：不能只回收空队列——一次性来源的 IP 队列里会永远留着过期时间戳。
每约 60 秒做一次全表清扫，删除"最新一次请求已超出窗口"的键，保证长期有界。
单进程 uvicorn 部署内存计数即可；多实例部署需换共享存储（如 Redis）。
"""
import threading
import time
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.core.audit import client_ip

LOGIN_LIMIT = (60, 60.0)      # (次数, 窗口秒)
GLOBAL_LIMIT = (1200, 60.0)
_SWEEP_INTERVAL = 60.0
_MAX_WINDOW = max(LOGIN_LIMIT[1], GLOBAL_LIMIT[1])


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self._hits: dict[tuple, deque] = defaultdict(deque)
        self._lock = threading.Lock()
        self._last_sweep = time.monotonic()

    def _sweep(self, now: float) -> None:
        """删除最新时间戳已过期的键（调用方需持有 self._lock）。"""
        stale = [k for k, dq in self._hits.items() if not dq or now - dq[-1] > _MAX_WINDOW]
        for k in stale:
            self._hits.pop(k, None)
        self._last_sweep = now

    async def dispatch(self, request, call_next):
        path = request.url.path
        is_login = path.startswith("/api/auth/login")
        limit, window = LOGIN_LIMIT if is_login else GLOBAL_LIMIT
        key = (client_ip(request) or "unknown", "login" if is_login else "global")
        now = time.monotonic()
        with self._lock:
            if now - self._last_sweep > _SWEEP_INTERVAL:
                self._sweep(now)
            dq = self._hits[key]
            while dq and now - dq[0] > window:
                dq.popleft()
            if len(dq) >= limit:
                return JSONResponse({"detail": "请求过于频繁，请稍后再试"}, status_code=429)
            dq.append(now)
        return await call_next(request)
