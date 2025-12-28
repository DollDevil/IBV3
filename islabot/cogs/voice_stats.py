from __future__ import annotations
import discord
from discord.ext import commands
from discord import app_commands

from core.utils import now_local
from utils.embed_utils import create_embed


def day_key_uk() -> str:
    t = now_local()
    return f"{t.year}-{t.month:02d}-{t.day:02d}"


class VoiceStats(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="voice", description="Show your voice activity today.")
    async def voice(self, interaction: discord.Interaction):
        if not interaction.guild:
            embed = create_embed("Use this in a server.", color="info", is_dm=False, is_system=False)
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        gid = interaction.guild.id
        uid = interaction.user.id
        dk = day_key_uk()

        row = await self.bot.db.fetchone(
            "SELECT seconds FROM voice_daily WHERE guild_id=? AND user_id=? AND day_key=?",
            (gid, uid, dk)
        )
        sec = int(row["seconds"]) if row else 0
        mins = sec // 60

        await interaction.response.send_message(
            f"You've logged **{mins} minutes** in voice today.",
            ephemeral=True
        )

async def setup(bot: commands.Bot):
    await bot.add_cog(VoiceStats(bot))

