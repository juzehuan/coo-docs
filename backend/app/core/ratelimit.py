"""进程内接口限流（规格书第五章「接口限流与登录失败锁定」）。

按客户端 IP 的滑动窗口计数：
- 登录接口：60 次 / 分钟；暴力破解的主闸是账号级失败锁定（5 次锁 30 分钟），
  此处阈值放宽以容纳整厂共用一个出口 IP 时的换班集中登录。
- 其余接口：1200 次 / 分钟。第 77 轮实测了真实会话的速率，替换掉原来"数倍余量"
  这个未经验证的说法：**静置 2.6 次/分钟/标签页**（通知轮询 2 + 身份复核 1），
  **密集浏览约 41 次/分钟**（连续点菜单的上限，真实用户远达不到）。
  按整厂 20 人共用一个出口 IP 折算：静置 52 次/分钟（余量 23 倍），
  极端情况下全员连续点击约 820 次/分钟（余量 1.5 倍）。
  也就是说日常余量充足，但"全厂同时密集操作"并非遥不可及——
  若将来并发用户数上调，这个阈值要跟着重算，不能沿用。
超限返回 429，并带 `Retry-After`（精确到窗口内最早一次请求的过期时刻）。

**注意整厂共用一个出口 IP 的后果**：计数是按 IP 的，因此全厂共用同一个桶——
一旦触顶，**所有人同时被拦**，包括正在审核的人。登录与其余接口是两个独立的桶
（已实测：登录桶打满时 `/health` 与业务接口照常），所以登录风暴不会波及业务。

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
                # 带上 Retry-After：429 不给这个头，客户端只能瞎猜什么时候能再试——
                # 监控会按固定间隔硬撞、脚本要么放弃要么把限流撑得更久。
                # 窗口内最早那次请求过期时即可再试，这个秒数是精确可算的。
                retry_after = max(1, int(window - (now - dq[0])) + 1)
                return JSONResponse(
                    {"detail": "请求过于频繁，请稍后再试"},
                    status_code=429,
                    headers={"Retry-After": str(retry_after)},
                )
            dq.append(now)
        return await call_next(request)
