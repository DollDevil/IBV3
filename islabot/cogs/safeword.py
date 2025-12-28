from __future__ import annotations
import discord
from discord.ext import commands
from discord import app_commands

from core.utils import now_ts
from utils.helpers import isla_embed, ensure_user_row
from utils.embed_utils import create_embed

class Safeword(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="safeword", description="Toggle neutral tone for IslaBot.")
    @app_commands.describe(reason="Optional reason (stored privately; you can leave blank).")
    async def safeword(self, interaction: discord.Interaction, reason: str = ""):
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild_id
        if not gid:
            embed = create_embed("Server only.", color="warning", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)

        await ensure_user_row(self.bot.db, gid, interaction.user.id)

        row = await self.bot.db.fetchone(
            "SELECT opted_out, safeword_on FROM users WHERE guild_id=? AND user_id=?",
            (gid, interaction.user.id)
        )
        if row and int(row["opted_out"] or 0) == 1:
            e = isla_embed(
                "You're opted out.\nUse `/opt-in` first if you want IslaBot again.\n᲼᲼",
                title="Safeword"
            )
            return await interaction.followup.send(embed=e, ephemeral=True)

        cur = int(row["safeword_on"] or 0) if row else 0
        new = 0 if cur else 1

        await self.bot.db.execute(
            "UPDATE users SET safeword_on=?, safeword_set_ts=?, safeword_reason=? WHERE guild_id=? AND user_id=?",
            (new, now_ts(), (reason or ""), gid, interaction.user.id)
        )

        if new == 1:
            desc = (
                "Noted.\n\n"
                "Neutral mode is on.\n"
                "You can keep using IslaBot normally.\n\n"
                "What changes:\n"
                "• No degrading language\n"
                "• No petnames\n"
                "• No flirt escalation\n"
                "• No targeted public callouts\n\n"
                "Toggle off anytime with `/safeword`.\n"
                "᲼᲼"
            )
            e = isla_embed(desc, title="Safeword On")
        else:
            desc = (
                "Okay.\n\n"
                "Neutral mode is off.\n"
                "Back to normal.\n"
                "᲼᲼"
            )
            e = isla_embed(desc, title="Safeword Off")

        await interaction.followup.send(embed=e, ephemeral=True)

    @app_commands.command(name="safeword_status", description="View what Safeword does and your current mode.")
    async def safeword_status(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild_id
        if not gid:
            embed = create_embed("Server only.", color="warning", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)

        await ensure_user_row(self.bot.db, gid, interaction.user.id)
        row = await self.bot.db.fetchone(
            "SELECT safeword_on, safeword_set_ts FROM users WHERE guild_id=? AND user_id=?",
            (gid, interaction.user.id)
        )
        on = int(row["safeword_on"] or 0) if row else 0
        since = int(row["safeword_set_ts"] or 0)

        if on:
            desc = (
                "Status: **Safeword On**\n\n"
                "Isla will stay neutral with you.\n"
                "You still have access to:\n"
                "• coins, profile, quests, orders, casino\n\n"
                "Neutral means:\n"
                "• no humiliation\n"
                "• no petnames\n"
                "• no flirt escalation\n"
                "• no targeted public callouts\n"
                "᲼᲼"
            )
        else:
            desc = (
                "Status: **Safeword Off**\n\n"
                "Isla uses normal tone with you.\n"
                "You can turn Safeword on anytime with `/safeword`.\n"
                "᲼᲼"
            )

        e = isla_embed(desc, title="Safeword")
        await interaction.followup.send(embed=e, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Safeword(bot))

