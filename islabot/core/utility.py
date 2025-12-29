"""
Utility functions and guards.
Consolidates: utils, guards
"""

from __future__ import annotations
import time
import discord
from datetime import datetime
from zoneinfo import ZoneInfo

LONDON = ZoneInfo("Europe/London")

# ============================================================================
# UTILITY FUNCTIONS (from utils.py)
# ============================================================================

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

# ============================================================================
# GUARDS (from guards.py)
# ============================================================================

async def ensure_not_opted_out(bot, interaction: discord.Interaction) -> bool:
    """Guard: check if user is opted out. Returns False if opted out (and sends message)."""
    if not interaction.guild:
        return True
    gid, uid = interaction.guild.id, interaction.user.id
    if await bot.db.is_opted_out(gid, uid):
        await interaction.response.send_message(
            "You're opted out. Use /optin if you want to rejoin.",
            ephemeral=True
        )
        return False
    return True

async def ensure_not_safeworded(bot, interaction: discord.Interaction) -> bool:
    """
    Guard: check if user has active safeword. Returns False if safeworded (and sends message).
    Use at start of commands that should respect safeword.
    """
    if not interaction.guild:
        return True
    gid, uid = interaction.guild.id, interaction.user.id
    
    row = await bot.db.fetchone(
        "SELECT safeword_until_ts FROM users WHERE guild_id=? AND user_id=?",
        (gid, uid),
    )
    if row and row["safeword_until_ts"] and int(row["safeword_until_ts"]) > now_ts():
        await interaction.response.send_message(
            "You're paused right now.",
            ephemeral=True
        )
        return False
    return True

