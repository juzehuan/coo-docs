"""单实例选举：判断本进程是否为"主进程"。

**用途**：NAS 定时同步与异步导出 worker 都是"全系统只该跑一份"的后台线程。
单进程部署下这不成问题；一旦有人加了 `--workers`，每个进程都会各起一份——
当日同步会被跑 N 遍、同一批导出作业会被 N 个 worker 争抢。

**顺带把一个更危险的隐患变成响亮的告警**：`core/snowflake.py` 的 worker_id 是
固定常量（3），每个进程各有自己的序列号，同一毫秒会**生成完全相同的 ID**。
第 81 轮实测：两个实例各生成 2000 个 ID，**重复 19 个**——后果是订单/附件/
审计日志的主键冲突，而且是间歇性的、最难排查的那种。
直接 `--workers 4` 首先踩的就是它。

因此这里不只是选举，还负责在检测到多进程时**把未满足的前置条件逐条喊出来**，
而不是让系统安静地跑在一个会产生重复主键的配置上。
完整清单见《上线待办与风险记录》P3「多进程/多实例部署的前置清单」。

实现用 MySQL 的 `GET_LOCK()` 命名锁：数据库本就是必需依赖，不必为此引入 Redis；
锁按连接持有，进程崩溃时连接断开会自动释放，不会留下需要人工清理的死锁。
"""
import logging

from sqlalchemy import text

logger = logging.getLogger("app.singleton")

LOCK_NAME = "coo_app_primary"

_conn = None          # 持锁的专用连接，必须与进程同生命周期
_is_primary: bool | None = None


def _acquire() -> bool:
    global _conn
    from app.db import engine

    if not engine.url.get_backend_name().startswith("mysql"):
        # SQLite（本地开发）没有 GET_LOCK，也不会多进程部署，直接视为主进程
        return True
    conn = engine.connect()
    try:
        got = conn.execute(text("SELECT GET_LOCK(:n, 0)"), {"n": LOCK_NAME}).scalar()
        if got == 1:
            _conn = conn          # 故意不关闭：连接一关，锁就释放了
            return True
        conn.close()
        return False
    except Exception:  # noqa: BLE001
        conn.close()
        # 拿不准时按"是主进程"处理：宁可多跑一次幂等的同步，
        # 也不要因为一次查询失败让定时归档整个停摆（第 76 轮的取向）
        logger.exception("单实例选举失败，按主进程处理")
        return True


def is_primary() -> bool:
    """本进程是否为主进程。首次调用时选举，之后复用结果。"""
    global _is_primary
    if _is_primary is None:
        _is_primary = _acquire()
        if not _is_primary:
            _warn_multiprocess()
    return _is_primary


def _warn_multiprocess() -> None:
    logger.error(
        "检测到本机已有另一个应用进程在运行（多进程部署）。"
        "本进程将**不启动** NAS 定时同步与导出 worker，避免同一份工作被跑多遍。")
    logger.error(
        "但多进程部署还有未满足的前置条件，请勿在生产使用："
        "①雪花 ID 的 worker_id 是固定常量，多进程会产生**重复主键**"
        "（实测两进程各 2000 个 ID 重复 19 个）；"
        "②附件去重/回收互斥是进程内锁，跨进程失效会导致**证据丢失**；"
        "③NAS 同步互斥同上；④导出并发闸门会变成 N 倍名额；"
        "⑤接口限流阈值会变成 N 倍；⑥NAS 配置缓存只在改动的那个进程失效。"
        "详见《上线待办与风险记录》P3「多进程/多实例部署的前置清单」。")
