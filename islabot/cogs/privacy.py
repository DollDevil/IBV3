from __future__ import annotations
import json
import discord
from discord.ext import commands
from discord import app_commands
from core.utils import now_ts

class Privacy(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="optout", description="Hard leave Isla system: deletes your data and stops tracking.")
    async def optout(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("Guild only.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        gid, uid = interaction.guild.id, interaction.user.id

        # Audit first (minimal)
        await self.bot.db.audit(gid, uid, uid, "optout_requested", "{}", now_ts())

        # Delete all user data, then mark optout
        await self.bot.db.hard_delete_user(gid, uid)
        await self.bot.db.set_optout(gid, uid, True, now_ts())
        await self.bot.db.audit(gid, uid, uid, "optout_completed", "{}", now_ts())

        await interaction.followup.send(
            "You are opted out. All Isla data for you in this server has been deleted, and I will not track you.\n"
            "If you ever want back in, use /optin.",
            ephemeral=True,
        )

    @app_commands.command(name="optin", description="Re-join Isla system after opting out.")
    async def optin(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("Guild only.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        gid, uid = interaction.guild.id, interaction.user.id

        await self.bot.db.set_optout(gid, uid, False, None)
        await self.bot.db.ensure_user(gid, uid)
        await self.bot.db.audit(gid, uid, uid, "optin", "{}", now_ts())

        await interaction.followup.send("Opt-in complete. You're back in the system.", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Privacy(bot))

