"""The business date: what "today" is for a rule, a publication or a repeal.

`date.today()` is the date where the process runs, and a container runs in
UTC — so for the first eight hours of every Beijing day a rule published
without a date started yesterday, and the one taking effect today was not yet
in force (review 2026-10-19, F05). Every deployment today serves UTC+8
workspaces; the zone is one setting, `ORYH_BUSINESS_TIMEZONE`, until a
workspace carries its own.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone, tzinfo
from functools import lru_cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.config import settings

# A slim image may ship without the tz database; these zones keep no DST, so
# a fixed offset is exact for them.
_FIXED = {"Asia/Shanghai": 8, "Asia/Hong_Kong": 8, "Asia/Singapore": 8, "Asia/Taipei": 8, "UTC": 0}
_OFFSET = re.compile(r"^(?:UTC)?([+-])(\d{1,2})(?::?(\d{2}))?$")


@lru_cache(maxsize=8)
def resolve_timezone(name: str) -> tzinfo:
    """An IANA name or an offset such as `+08:00`; unknown names fail loudly."""
    match = _OFFSET.match(name.strip())
    if match:
        sign, hours, minutes = match.groups()
        delta = timedelta(hours=int(hours), minutes=int(minutes or 0))
        return timezone(-delta if sign == "-" else delta)
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        if name in _FIXED:
            return timezone(timedelta(hours=_FIXED[name]))
        raise ValueError(f"unknown business timezone {name!r}") from None


def business_today() -> date:
    return datetime.now(resolve_timezone(settings.business_timezone)).date()
