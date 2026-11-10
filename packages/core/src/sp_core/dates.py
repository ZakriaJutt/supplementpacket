"""Date helpers. The only place calendar arithmetic is done (R-03).

Exact calendar arithmetic on ``datetime.date``; no holiday calendar is applied in B1
(weekends only), which is recorded in verification-report-fixing.md.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

__all__ = ["business_days_between", "days_between", "pilot_day_date", "pilot_day_end"]


def business_days_between(start: date, end: date) -> int:
    """Business days after ``start`` up to and including ``end`` (Mon-Fri).

    Sent on a Friday, aged on the next Wednesday: Mon, Tue, Wed = 3 (UT-16).
    """
    if end <= start:
        return 0
    days = 0
    current = start
    while current < end:
        current += timedelta(days=1)
        if current.weekday() < 5:
            days += 1
    return days


def days_between(start: date, end: date) -> int:
    """Calendar days from ``start`` to ``end``."""
    return (end - start).days


def pilot_day_date(start_date: date, day_number: int) -> date:
    """Pilot day 1 is ``start_date``; day n is ``start_date + (n - 1)`` days."""
    if day_number < 1:
        raise ValueError("pilot days start at 1")
    return start_date + timedelta(days=day_number - 1)


def pilot_day_end(start_date: date, day_number: int, timezone: str) -> datetime:
    """The instant 23:59:59.999999 local time at the end of pilot day ``day_number``."""
    local_day = pilot_day_date(start_date, day_number)
    return datetime.combine(local_day, time.max, tzinfo=ZoneInfo(timezone))
