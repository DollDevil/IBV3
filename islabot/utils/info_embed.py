from __future__ import annotations
import discord

STYLE1_NEUTRAL = "https://i.imgur.com/9oUjOQQ.png"
ISLA_ICON = "https://i.imgur.com/5nsuuCV.png"

def info_embed(title: str, desc: str, thumb: str | None = None) -> discord.Embed:
    """Create a standardized info embed with Isla branding."""
    e = discord.Embed(title=title, description=desc)
    e.set_author(name="Isla", icon_url=ISLA_ICON)
    e.set_thumbnail(url=thumb or STYLE1_NEUTRAL)
    return e

