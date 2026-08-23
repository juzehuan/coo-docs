"""超期判断（F-03「待我处理超期标红」）。

due_date 在模型中是宽松文本（如 2026-10-15），此处解析 YYYY-MM-DD / YYYY/M/D
等常见写法；解析失败或未填视为不超期。已放行（released）不再计超期。
"今天"按站点时区（settings.TIMEZONE）计算，而非容器 UTC 时钟。
"""
import datetime
import re
from zoneinfo import ZoneInfo

from app.constants import VersionStatus
from app.core.config import settings

_DATE_RE = re.compile(r"^\s*(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})")


def parse_due(s: str | None) -> datetime.date | None:
    if not s:
        return None
    m = _DATE_RE.match(str(s))
    if not m:
        return None
    try:
        return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def _today() -> datetime.date:
    try:
        return datetime.datetime.now(ZoneInfo(settings.TIMEZONE)).date()
    except Exception:
        return datetime.date.today()


def is_overdue(due_date: str | None, status: str | None = None) -> bool:
    if status == VersionStatus.RELEASED:
        return False
    d = parse_due(due_date)
    return d is not None and _today() > d
