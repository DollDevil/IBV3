from __future__ import annotations
import time
from datetime import datetime
from zoneinfo import ZoneInfo

LONDON = ZoneInfo("Europe/London")

def now_ts() -> int:
    return int(time.time())

def tz(cfg) -> ZoneInfo:
    name = cfg.get("isla", "timezone", default="Europe/London")
    return ZoneInfo(name)

def now_local(cfg=None) -> datetime:
    """Get current time in London timezone. If cfg provided, uses config timezone."""
    if cfg:
        return datetime.now(tz=tz(cfg))
    return datetime.now(tz=LONDON)

def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))

def day_key(ts: int | None = None) -> int:
    if ts is None:
        ts = now_ts()
    return ts // 86400

def week_key(ts: int | None = None) -> int:
    if ts is None:
        ts = now_ts()
    return ts // (7 * 86400)

def current_season_tag(dt: datetime) -> str:
    m = dt.month
    if m in (12, 1, 2): return "winter"
    if m in (3, 4, 5): return "spring"
    if m in (6, 7, 8): return "summer"
    return "autumn"

def parse_schedule(s: str) -> tuple[str, str]:
    # "FRIDAY 20:00"
    p = s.strip().split()
    return p[0].upper(), p[1]

def fmt(n: int) -> str:
    """Format number with thousand separators."""
    return f"{n:,}"

