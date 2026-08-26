"""NAS 自动同步调度：每天 NAS_SYNC_TIME（HH:MM）触发一次 run_sync(run_type="auto")。

此前 NAS_SYNC_TIME 只是配置项，代码中无任何调度器引用，自动归档从不执行（F-06 落空），
附件只能靠人工点手动同步。单进程 uvicorn 部署用后台守护线程实现；
注意：多进程/多实例部署时每个进程都会各自调度，届时应改用外部 cron 并关闭此调度器。

**第 59 轮修正的静默失效**（上线以来自动同步实际一次也没跑成）：

原判据是「距下次触发还有多久 <= 60 秒」，用 `_seconds_until()` 反推是否到点。
但 `_seconds_until` 在 `target <= now` 时会把目标推到第二天并返回约 86400，
而 `time.sleep()` 保证在截止时刻**当时或之后**才醒——于是醒来那一刻必然落在
`target <= now` 一侧，判定为「还差 86400 秒」，**直接跳过当天的同步**。
实测：醒来提前 100ms → 返回 0.1 → 执行；偏 0ms / 1ms / 50ms / 500ms / 2s →
全部返回约 86400 → 跳过。也就是每天都跳过，而 sleep 不会提前醒。
运行态吻合：`sync_records` 中 run_type='auto' 总共只有 1 条（属偶然），
其余 51 次全是手动。**这是完全静默的失效**：不报错、界面不告警、
`/nas/status` 仍显示「上次同步成功」，而它守的正是核查证据的异地副本。

现判据改为「今天的计划时刻已到，且今天还没跑过」（见 `_due`），不再做时间差反推。

第二处隐患一并修掉：原「今天跑过没有」记在进程内存的 `last_run` 里，
**重启即丢**——在计划时刻前后重启就可能同日跑两次。改为查 `sync_records`，
状态随数据库走，重启不影响。

副作用（有意为之）：判据不再要求「刚好落在计划时刻的 60 秒窗口内」，
因此服务若在 01:00 之后才启动、当天又没跑过，会在下一次醒来（最多 1 小时内）
补跑一次。run_sync 只处理 nas_synced=False 的附件，补跑是幂等且廉价的，
这让「昨晚机器没开」这类情况能自愈，而不是静默地少一天副本。
"""
import datetime
import logging
import threading
import time
from zoneinfo import ZoneInfo

from app.core.config import settings
from app.core import nas_config

logger = logging.getLogger("app.scheduler")

# 分段等待的上限：管理员在界面改小同步时间后，本进程最多 1 小时内就能按新值重算，
# 不必等到原来的时刻才醒
MAX_SLEEP_SECONDS = 3600.0


def _tz() -> ZoneInfo:
    try:
        return ZoneInfo(settings.TIMEZONE)
    except Exception:
        logger.warning("TIMEZONE=%r 无效，回退为 UTC", settings.TIMEZONE)
        return ZoneInfo("UTC")


def _parse_hhmm(hhmm: str) -> tuple[int, int]:
    try:
        hour, minute = (int(x) for x in hhmm.strip().split(":"))
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError
    except ValueError:
        logger.warning("同步时间 %r 格式非法（应为 HH:MM），回退为 01:00", hhmm)
        return 1, 0
    return hour, minute


def _target_for(day: datetime.date, hhmm: str, tz) -> datetime.datetime:
    """给定日期的计划触发时刻（带时区）。"""
    hour, minute = _parse_hhmm(hhmm)
    return datetime.datetime.combine(day, datetime.time(hour, minute), tzinfo=tz)


def _seconds_until(hhmm: str) -> float:
    """距下一次触发的秒数。按站点时区（TIMEZONE）计算，而非容器 UTC 时钟。

    只用来决定「睡多久」——这个用法是对的。**不要**再用它反推「是否到点」，
    那正是本模块修掉的那个 bug：sleep 醒来时它恒为约 86400。
    """
    now = datetime.datetime.now(_tz())
    target = _target_for(now.date(), hhmm, now.tzinfo)
    if target <= now:
        target += datetime.timedelta(days=1)
    return (target - now).total_seconds()


def _due(now: datetime.datetime, hhmm: str, last_auto: datetime.date | None) -> bool:
    """此刻是否应当执行同步。

    纯函数，不读时钟也不读库——调度的正确性全部集中在这里，可用注入的时刻直接验证。
    """
    if last_auto == now.date():
        return False          # 今天已经跑过
    return now >= _target_for(now.date(), hhmm, now.tzinfo)


def _last_auto_date() -> datetime.date | None:
    """最近一次自动同步的日期（站点时区）；查不到或出错时返回 None。

    出错时返回 None 意味着「当作今天还没跑过」——宁可多跑一次幂等的同步，
    也不要因为一次查询失败而静默地跳过当天的归档。
    """
    from app.db import SessionLocal
    from app.models import SyncRecord
    db = SessionLocal()
    try:
        rec = (db.query(SyncRecord)
               .filter(SyncRecord.run_type == "auto")
               .order_by(SyncRecord.started_at.desc()).first())
        if rec is None or rec.started_at is None:
            return None
        # started_at 以 naive UTC 存储，需先贴上 UTC 再换算到站点时区，
        # 否则曼谷 00:30 的记录会被算成前一天
        return (rec.started_at.replace(tzinfo=datetime.timezone.utc)
                .astimezone(_tz()).date())
    except Exception:
        logger.exception("读取上次自动同步时间失败，本轮按「今天未跑过」处理")
        return None
    finally:
        db.close()


def _run_once() -> None:
    from app.db import SessionLocal
    from app.services.nas_sync import SyncBusy, run_sync
    db = SessionLocal()
    try:
        rec = run_sync(db, run_type="auto")
        logger.info("NAS 自动同步完成：status=%s total=%s success=%s failed=%s",
                    rec.status, rec.total, rec.success, rec.failed)
    except SyncBusy:
        # 手动同步正在跑：本次自动同步跳过即可，待同步内容不会丢，
        # 那次手动同步会一并处理
        logger.info("NAS 自动同步跳过：已有同步任务在进行中")
    finally:
        db.close()


def _loop() -> None:
    while True:
        # 每轮重新读取配置：管理员在界面改同步时间或关闭自动同步后，
        # 下一次等待即按新值计算，不需要重启服务
        cfg = nas_config.get_config()
        time.sleep(min(_seconds_until(cfg["sync_time"]), MAX_SLEEP_SECONDS))
        cfg = nas_config.get_config()
        if not cfg["auto_sync"]:
            continue
        if not _due(datetime.datetime.now(_tz()), cfg["sync_time"], _last_auto_date()):
            continue
        try:
            _run_once()
        except Exception:
            logger.exception("NAS 自动同步失败，将于明日计划时间重试")


def start_nas_sync_scheduler() -> None:
    threading.Thread(target=_loop, name="nas-sync-scheduler", daemon=True).start()
    logger.info("NAS 自动同步调度已启动：每日 %s", nas_config.get_config()["sync_time"])
