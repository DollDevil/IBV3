from __future__ import annotations
import discord
from core.utils import now_ts

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

