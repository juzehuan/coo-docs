"""请求日志中间件。

uvicorn 自带的访问日志对排障几乎没用：
- IP 恒为 nginx 容器地址，看不出是谁在操作（真实客户端在 X-Real-IP 里）；
- 没有用户身份，403/401 无法回答"是谁"；
- 没有失败原因，404 分不清"资源不存在"与"越权被故意掩盖成 404"；
- 没有时间戳，日志一旦导出或聚合就失去时间维度。

结果是用户报"我提交时报错了"，运维只能看到一堆同样的 IP 和状态码。
这里补上：时间、真实 IP、用户、方法路径、状态码、耗时、失败原因。
健康检查按 DEBUG 记录，避免每 30 秒一条把业务日志挤出可视范围。
"""
import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware

from app.core.audit import client_ip

logger = logging.getLogger("app.request")

# 这些路径正常情况下不值得逐条记录（健康检查每 30s 一次）
_QUIET_PATHS = ("/health",)


class RequestLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        started = time.perf_counter()
        response = await call_next(request)
        cost_ms = (time.perf_counter() - started) * 1000

        path = request.url.path
        # 认证依赖会把用户挂到 request.state，未认证请求则为空
        user = getattr(request.state, "log_user", None) or "-"
        line = "%s %s %s <- %s user=%s %.0fms"
        args = (request.method, path, response.status_code, client_ip(request) or "-", user, cost_ms)

        if any(path.startswith(p) for p in _QUIET_PATHS) and response.status_code < 400:
            logger.debug(line, *args)
        elif response.status_code >= 500:
            logger.error(line, *args)
        elif response.status_code >= 400:
            # 4xx 记 warning：越权尝试、校验失败、账号异常都在这一档，是排障主要线索
            logger.warning(line, *args)
        else:
            logger.info(line, *args)
        return response
