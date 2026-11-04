"""One place to ask "what time is it?" so the demo can freeze or move time.

Set LIFECIRCLE_TODAY=2026-11-03 to pin the date; POST /demo/advance moves it.
"""
import os
from datetime import date, datetime, timedelta

_offset = timedelta(0)


def _base_now() -> datetime:
    pinned = os.environ.get("LIFECIRCLE_TODAY")
    if pinned:
        d = date.fromisoformat(pinned)
        return datetime(d.year, d.month, d.day, 9, 0)
    return datetime.now().replace(microsecond=0)


def now() -> datetime:
    return _base_now() + _offset


def today() -> date:
    return now().date()


def advance(minutes: int = 0, days: int = 0) -> datetime:
    global _offset
    _offset += timedelta(minutes=minutes, days=days)
    return now()


def reset() -> None:
    global _offset
    _offset = timedelta(0)
