"""
Centralized helper functions used across multiple cogs.
"""
from __future__ import annotations
import time
import discord
from core.isla_text import sanitize_isla_text

# Constants
STYLE1_DEFAULT = "https://i.imgur.com/5nsuuCV.png"
STYLE1_NEUTRAL = "https://i.imgur.com/9oUjOQQ.png"

def now_ts() -> int:
    """Get current Unix timestamp."""
    return int(time.time())

def format_time_left(seconds: int) -> str:
    """Format seconds into readable time (hours and minutes)."""
    if seconds <= 0:
        return "less than a minute"
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    if hours > 0:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"

def isla_embed(desc: str, title: str | None = None, icon: str = STYLE1_DEFAULT, thumb: str | None = None) -> discord.Embed:
    """Create a standardized Isla embed."""
    e = discord.Embed(title=title, description=sanitize_isla_text(desc))
    e.set_author(name="Isla", icon_url=icon)
    if thumb:
        e.set_thumbnail(url=thumb)
    return e

async def ensure_user_row(db, gid: int, uid: int):
    """Ensure user row exists with all required columns."""
    await db.execute(
        """
        INSERT INTO users(guild_id,user_id,coins,obedience,opted_out,safeword_on,safeword_set_ts,safeword_reason,vacation_until_ts,vacation_last_used_ts,vacation_welcomed_ts)
        VALUES(?,?,0,0,0,0,0,'',0,0,0)
        ON CONFLICT(guild_id,user_id) DO NOTHING
        """,
        (gid, uid)
    )

