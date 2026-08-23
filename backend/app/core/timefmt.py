"""站点时区的时间格式化。

库里所有时间都以 `datetime.utcnow()` 写入，是**不带时区的 UTC**。这在接口下发
时问题不大（前端按约定当 UTC 解析），但落到导出文件与归档清单里就成了实质问题：
一串 `2026-08-23T07:30:19` 既没有时区也没有偏移，核查方无从判断它是哪个时区的
07:30。合规证据里的时间戳必须是自解释的。

这里统一输出站点时区（settings.TIMEZONE）的时间并带上偏移，如
`2026-08-23 14:30:19+07:00`——不依赖阅读者的环境即可还原到确切时刻。
"""
import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.config import settings

logger = logging.getLogger(__name__)


def site_tz() -> ZoneInfo:
    try:
        return ZoneInfo(settings.TIMEZONE)
    except (ZoneInfoNotFoundError, ValueError):
        logger.warning("TIMEZONE=%r 无效，回退为 UTC", settings.TIMEZONE)
        return ZoneInfo("UTC")


def to_site(dt: datetime | None) -> datetime | None:
    """把库里的朴素 UTC 时间转成站点时区的带偏移时间。"""
    if dt is None:
        return None
    aware = dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
    return aware.astimezone(site_tz())


def fmt(dt: datetime | None, sep: str = " ") -> str:
    """导出与清单用：站点时区 + 显式偏移，如 `2026-08-23 14:30:19+07:00`。"""
    local = to_site(dt)
    if local is None:
        return ""
    return local.isoformat(sep=sep, timespec="seconds")


def now_str() -> str:
    """当前时刻（站点时区 + 偏移），用于清单头部。"""
    return fmt(datetime.utcnow())
