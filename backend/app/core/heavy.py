"""重接口的并发闸门。

**为什么需要它**：第 79 轮压测把瓶颈定准了——不是连接池、不是 SQL，是**单进程的
CPU**。xlsx 生成是纯 CPU 活，GIL 之下一个进程只能真正跑一个。实测（审计导出，
单请求基线 1.8s）：

    并发   墙钟     旁观者的普通请求
      1    1.8s    0.3s
      5   18.9s    1.2s
     10   40.0s    1.2s
     20   全部超时  12.9s
     40   全部超时  也超时

也就是说这套部署能承受的**并发重导出大约在 5 以内**，越过之后全站对普通用户不可用。
更糟的是连接池不区分轻重请求：20 个并发导出会把 15 个连接全占光，一个只取 1 条
订单的普通请求也要等池 30 秒然后拿到 503。

**闸门的作用不是让导出变快**，而是让重活**永远不能把轻活饿死**：
超出名额的导出请求**立即**返回 429，不占连接、不排队、不烧 CPU；
留给普通请求的连接始终有 15 - MAX_CONCURRENT_HEAVY 个。

名额取 2（而不是贴着拐点的 5）：拐点处单请求已要 19 秒，那不是可接受的体感；
留 2 个既能让日常的偶发并发导出直接通过，又给普通流量留足 CPU。
可用 `MAX_CONCURRENT_EXPORT` 环境变量调整而不必改代码。
"""
import threading

from fastapi import HTTPException, status

from app.core.config import settings

# 建议的重试等待：一次典型导出的量级，够让前一个名额腾出来
RETRY_AFTER_SECONDS = 20

_sem = threading.BoundedSemaphore(max(1, settings.MAX_CONCURRENT_EXPORT))


def heavy_slot():
    """占用一个导出名额；占不到立即 429。

    用 `yield` 依赖而非在端点内手写 try/finally：6 个端点各写一遍必然漏掉一个
    （第 71/72 轮的教训）。释放放在 finally 里，异常路径同样归还名额。
    """
    if not _sem.acquire(blocking=False):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"导出任务繁忙（同时最多 {settings.MAX_CONCURRENT_EXPORT} 个），请稍后重试",
            headers={"Retry-After": str(RETRY_AFTER_SECONDS)},
        )
    try:
        yield
    finally:
        _sem.release()


def in_use() -> int:
    """当前已占用的名额数（供自检/诊断用，不参与判定）。"""
    return settings.MAX_CONCURRENT_EXPORT - _sem._value   # noqa: SLF001
