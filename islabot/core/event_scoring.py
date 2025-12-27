"""
Event Scoring (ES) system.
Converts user activity into Event Score with caps.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from core.utils import now_ts

UK_TZ = ZoneInfo("Europe/London")


def calculate_es(msg_count: int, vc_minutes: int, casino_wagered: int, orders_completed: int, rituals_completed: int) -> int:
    """
    Calculate Event Score from activity metrics.
    
    Rules:
    - Messages: +1 ES each (cap 30/hour)
    - VC minutes: +2 ES each (cap 60/day = 120 ES/day)
    - Casino wager: +1 ES per 200 Coins (cap 20k/day = 100 ES/day)
    - Order completion: +25 ES (uncapped)
    - Ritual completion: +120 ES (uncapped)
    """
    # Messages: 1 ES each, cap 30/hour (we apply hourly cap in aggregation)
    msg_es = min(msg_count, 30)
    
    # VC: 2 ES per minute, cap 60 minutes/day (120 ES/day)
    vc_es = min(vc_minutes, 60) * 2
    
    # Casino: 1 ES per 200 Coins, cap 20,000 Coins/day (100 ES/day)
    casino_es = min(casino_wagered // 200, 100)
    
    # Orders: 25 ES each (uncapped)
    orders_es = orders_completed * 25
    
    # Rituals: 120 ES each (uncapped)
    rituals_es = rituals_completed * 120
    
    total = msg_es + vc_es + casino_es + orders_es + rituals_es
    return total


def reset_hourly_caps(breakdown_json: str, last_reset_ts: int) -> dict:
    """
    Reset hourly caps if needed.
    Returns updated breakdown dict.
    """
    now = now_ts()
    hour_ago = now - 3600
    
    try:
        breakdown = json.loads(breakdown_json) if breakdown_json else {}
    except Exception:
        breakdown = {}
    
    # If last reset was more than an hour ago, reset hourly counters
    if last_reset_ts < hour_ago:
        breakdown["msg_count_hour"] = 0
        breakdown["last_hour_reset_ts"] = now
    
    return breakdown


def reset_daily_caps(breakdown_json: str, last_reset_ts: int) -> dict:
    """
    Reset daily caps if needed.
    Returns updated breakdown dict.
    """
    now = now_ts()
    now_dt = datetime.fromtimestamp(now, tz=UK_TZ)
    today_start = now_dt.replace(hour=0, minute=0, second=0, microsecond=0)
    today_start_ts = int(today_start.timestamp())
    
    try:
        breakdown = json.loads(breakdown_json) if breakdown_json else {}
    except Exception:
        breakdown = {}
    
    # If last reset was before today, reset daily counters
    if last_reset_ts < today_start_ts:
        breakdown["vc_minutes_today"] = 0
        breakdown["casino_wagered_today"] = 0
        breakdown["last_day_reset_ts"] = today_start_ts
    
    return breakdown


def apply_es_caps(breakdown: dict, new_msg: int, new_vc: int, new_casino: int) -> tuple[int, int, int]:
    """
    Apply caps and return capped values for ES calculation.
    Returns: (capped_msg, capped_vc_minutes, capped_casino_wagered)
    """
    # Messages: cap at 30/hour
    msg_count_hour = breakdown.get("msg_count_hour", 0)
    capped_msg = min(new_msg, max(0, 30 - msg_count_hour))
    breakdown["msg_count_hour"] = msg_count_hour + capped_msg
    
    # VC: cap at 60 minutes/day
    vc_minutes_today = breakdown.get("vc_minutes_today", 0)
    capped_vc = min(new_vc, max(0, 60 - vc_minutes_today))
    breakdown["vc_minutes_today"] = vc_minutes_today + capped_vc
    
    # Casino: cap at 20,000 Coins/day
    casino_wagered_today = breakdown.get("casino_wagered_today", 0)
    capped_casino = min(new_casino, max(0, 20000 - casino_wagered_today))
    breakdown["casino_wagered_today"] = casino_wagered_today + capped_casino
    
    return capped_msg, capped_vc, capped_casino

