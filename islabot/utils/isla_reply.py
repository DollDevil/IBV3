from __future__ import annotations
import discord
from typing import Optional
from utils.consent import Consent, pick

def neutral_thumbnail() -> str:
    # Style 1 neutral / calm image
    return "https://i.imgur.com/9oUjOQQ.png"

def embed_isla(desc: str, title: str | None = None, thumb: str | None = None) -> discord.Embed:
    """Create an Isla embed with optional thumbnail."""
    e = discord.Embed(title=title, description=desc)
    e.set_author(name="Isla", icon_url="https://i.imgur.com/5nsuuCV.png")
    if thumb:
        e.set_thumbnail(url=thumb)
    return e

def msg_for(consent: Consent, pool: str, fallback: str) -> str:
    """Get message based on consent state. Uses neutral pool if safeword is on."""
    if consent.safeword_on:
        return pick(pool)
    return fallback

def thumb_for(consent: Consent, normal_thumb: str | None = None) -> str | None:
    """Get thumbnail based on consent state. Uses neutral thumbnail if safeword is on."""
    if consent.safeword_on:
        return neutral_thumbnail()
    return normal_thumb

async def get_memory_enhanced_response(
    bot,
    pool_key: str,
    stage: int,
    guild_id: Optional[int] = None,
    user_id: Optional[int] = None
) -> str:
    """Get a personality response enhanced with memory context."""
    if hasattr(bot, 'personality') and hasattr(bot, 'memory'):
        return await bot.personality.get_response_with_memory(
            pool_key, stage, guild_id, user_id
        )
    # Fallback to basic personality
    stage_key = f"stage_{min(stage, 4)}"
    pool = bot.personality.pools.get(pool_key, {})
    responses = pool.get(stage_key, pool.get("stage_0", []))
    if responses:
        import random
        return random.choice(responses)
    return ""

