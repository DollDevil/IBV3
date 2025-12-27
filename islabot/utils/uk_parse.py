from __future__ import annotations
import re
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

UK = ZoneInfo("Europe/London")

def now_ts() -> int:
    return int(time.time())

def parse_duration_to_seconds(text: str) -> int:
    s = text.strip().lower()
    m = re.fullmatch(r"(\d+)\s*([mhdw])", s)
    if not m:
        return 0
    n = int(m.group(1))
    unit = m.group(2)
    mult = {"m":60, "h":3600, "d":86400, "w":7*86400}[unit]
    return max(0, n * mult)

def parse_when_to_ts(when: str) -> int:
    """
    Accepts:
      - "in 10m", "in 2h", "in 3d"
      - "YYYY-MM-DD HH:MM" (UK time)
      - "YYYY-MM-DD" (defaults 12:00 UK)
    """
    s = when.strip()
    if s.lower().startswith("in "):
        dur = parse_duration_to_seconds(s[3:].strip())
        return now_ts() + dur if dur > 0 else 0

    # date/time formats in UK timezone
    for fmt_str in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(s, fmt_str)
            if fmt_str == "%Y-%m-%d":
                dt = dt.replace(hour=12, minute=0)
            dt = dt.replace(tzinfo=UK)
            return int(dt.timestamp())
        except Exception:
            continue
    return 0

def human_eta(ts: int) -> str:
    return f"<t:{int(ts)}:R>"

