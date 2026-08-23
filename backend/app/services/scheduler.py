"""NAS 自动同步调度：每天 NAS_SYNC_TIME（HH:MM）触发一次 run_sync(run_type="auto")。

此前 NAS_SYNC_TIME 只是配置项，代码中无任何调度器引用，自动归档从不执行（F-06 落空），
附件只能靠人工点手动同步。单进程 uvicorn 部署用后台守护线程实现；
注意：多进程/多实例部署时每个进程都会各自调度，届时应改用外部 cron 并关闭此调度器。
"""
import datetime
import logging
import threading
import time
from zoneinfo import ZoneInfo

from app.core.config import settings
from app.core import nas_config

logger = logging.getLogger("app.scheduler")


def _tz() -> ZoneInfo:
    try:
        return ZoneInfo(settings.TIMEZONE)
    except Exception:
        logger.warning("TIMEZONE=%r 无效，回退为 UTC", settings.TIMEZONE)
        return ZoneInfo("UTC")


def _seconds_until(hhmm: str) -> float:
    """距下一次触发的秒数。按站点时区（TIMEZONE）计算，而非容器 UTC 时钟。"""
    try:
        hour, minute = (int(x) for x in hhmm.strip().split(":"))
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError
    except ValueError:
        logger.warning("同步时间 %r 格式非法（应为 HH:MM），回退为 01:00", hhmm)
        hour, minute = 1, 0
    now = datetime.datetime.now(_tz())
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += datetime.timedelta(days=1)
    return (target - now).total_seconds()


def _loop() -> None:
    last_run: datetime.date | None = None
    while True:
        # 每轮重新读取配置：管理员在界面改同步时间或关闭自动同步后，
        # 下一次等待即按新值计算，不需要重启服务
        cfg = nas_config.get_config()
        # 单次等待不超过一小时：否则改小同步时间后，本进程仍会睡到原来的时刻才醒
        wait = min(_seconds_until(cfg["sync_time"]), 3600.0)
        time.sleep(wait)
        cfg = nas_config.get_config()
        if not cfg["auto_sync"]:
            continue
        now = datetime.datetime.now(_tz())
        if _seconds_until(cfg["sync_time"]) > 60:
            continue  # 未到计划时刻（本轮只是分段等待中的一次醒来）
        today = now.date()
        if last_run == today:
            continue  # sleep 偶发提前唤醒时防止同日双跑
        last_run = today
        try:
            from app.db import SessionLocal
            from app.services.nas_sync import run_sync
            db = SessionLocal()
            try:
                rec = run_sync(db, run_type="auto")
                logger.info("NAS 自动同步完成：status=%s total=%s success=%s failed=%s",
                            rec.status, rec.total, rec.success, rec.failed)
            finally:
                db.close()
        except Exception:
            logger.exception("NAS 自动同步失败，将于明日计划时间重试")


def start_nas_sync_scheduler() -> None:
    threading.Thread(target=_loop, name="nas-sync-scheduler", daemon=True).start()
    logger.info("NAS 自动同步调度已启动：每日 %s", nas_config.get_config()["sync_time"])
