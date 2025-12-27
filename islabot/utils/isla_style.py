from __future__ import annotations
import discord

ISLA_ICON = "https://i.imgur.com/5nsuuCV.png"
STYLE1_NEUTRAL = "https://i.imgur.com/9oUjOQQ.png"

def isla_embed(desc: str, title: str | None = None, thumb: str | None = None) -> discord.Embed:
    e = discord.Embed(title=title, description=desc)
    e.set_author(name="Isla", icon_url=ISLA_ICON)
    e.set_thumbnail(url=thumb or STYLE1_NEUTRAL)
    return e

def fmt(n: int | float) -> str:
    try:
        return f"{int(n):,}"
    except Exception:
        return "0"

