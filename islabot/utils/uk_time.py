"""
UK Time Utilities

Handles GMT/BST conversion automatically using Europe/London timezone.
"""

from __future__ import annotations
from datetime import datetime
from zoneinfo import ZoneInfo

UK_TZ = ZoneInfo("Europe/London")


def uk_now() -> datetime:
    """Get current datetime in UK timezone (GMT/BST)."""
    return datetime.now(tz=UK_TZ)


def uk_day_ymd(ts: int) -> str:
    """
    Convert Unix timestamp to UK date string (YYYY-MM-DD).
    
    Args:
        ts: Unix timestamp in seconds
    
    Returns:
        Date string in YYYY-MM-DD format
    """
    dt = datetime.fromtimestamp(ts, tz=UK_TZ)
    return dt.strftime("%Y-%m-%d")


def uk_hm(ts: int) -> str:
    """
    Convert Unix timestamp to UK time string (HH:MM).
    
    Args:
        ts: Unix timestamp in seconds
    
    Returns:
        Time string in HH:MM format
    """
    dt = datetime.fromtimestamp(ts, tz=UK_TZ)
    return dt.strftime("%H:%M")


def uk_iso(ts: int) -> str:
    """
    Convert Unix timestamp to UK ISO format string.
    
    Args:
        ts: Unix timestamp in seconds
    
    Returns:
        ISO format string with timezone
    """
    dt = datetime.fromtimestamp(ts, tz=UK_TZ)
    return dt.isoformat()

