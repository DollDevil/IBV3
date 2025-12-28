from __future__ import annotations

import discord
from discord.ext import commands
from discord import app_commands

from core.utils import now_ts, now_local
from core.isla_text import sanitize_isla_text
from utils.embed_utils import create_embed


def week_key_uk() -> str:
    t = now_local()
    iso_year, iso_week, _ = t.isocalendar()
    return f"{iso_year}-{iso_week:02d}"


class Moderation(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.icon = "https://i.imgur.com/5nsuuCV.png"

    async def _touch_weekly(self, gid: int, uid: int):
        wk = week_key_uk()
        await self.bot.db.execute(
            "INSERT OR IGNORE INTO weekly_stats(guild_id,week_key,user_id) VALUES(?,?,?)",
            (gid, wk, uid)
        )

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return
        gid = message.guild.id
        uid = message.author.id

        # ensure user row exists
        row = await self.bot.db.fetchone("SELECT user_id FROM users WHERE guild_id=? AND user_id=?", (gid, uid))
        if not row:
            start = int(self.bot.cfg.get("economy", "start_balance", default=250))
            await self.bot.db.execute(
                "INSERT INTO users(guild_id,user_id,coins,obedience,xp,lce,last_active_ts) VALUES(?,?,?,?,?,?,?)",
                (gid, uid, start, 0, 0, 0, now_ts())
            )

        await self.bot.db.execute(
            "UPDATE users SET last_active_ts=? WHERE guild_id=? AND user_id=?",
            (now_ts(), gid, uid)
        )

        await self._touch_weekly(gid, uid)
        wk = week_key_uk()
        await self.bot.db.execute(
            "UPDATE weekly_stats SET msg_count = msg_count + 1 WHERE guild_id=? AND week_key=? AND user_id=?",
            (gid, wk, uid)
        )

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction: discord.Reaction, user: discord.User | discord.Member):
        if user.bot or not reaction.message.guild:
            return
        gid = reaction.message.guild.id
        uid = user.id
        await self._touch_weekly(gid, uid)
        wk = week_key_uk()
        await self.bot.db.execute(
            "UPDATE weekly_stats SET react_count = react_count + 1 WHERE guild_id=? AND week_key=? AND user_id=?",
            (gid, wk, uid)
        )

    @app_commands.command(name="purge", description="Delete a number of messages from this channel.")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def purge(self, interaction: discord.Interaction, amount: int):
        if not interaction.channel or not isinstance(interaction.channel, discord.TextChannel):
            embed = create_embed("Use this in a text channel.", color="warning", is_dm=False, is_system=False)
            return await interaction.response.send_message(embed=embed, ephemeral=True)
        amount = max(1, min(200, amount))
        await interaction.response.defer(ephemeral=True)
        deleted = await interaction.channel.purge(limit=amount)
        embed = create_embed(f"Deleted {len(deleted)} messages.", color="success", is_dm=False, is_system=False)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="slowmode", description="Set slowmode for this channel (seconds).")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def slowmode(self, interaction: discord.Interaction, seconds: int):
        if not interaction.channel or not isinstance(interaction.channel, discord.TextChannel):
            embed = create_embed("Use this in a text channel.", color="warning", is_dm=False, is_system=False)
            return await interaction.response.send_message(embed=embed, ephemeral=True)
        seconds = max(0, min(21600, seconds))
        await interaction.channel.edit(slowmode_delay=seconds)
        embed = create_embed(f"Slowmode set to {seconds}s.", color="success", is_dm=False, is_system=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="lockdown", description="Toggle lockdown for this channel (send messages).")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def lockdown(self, interaction: discord.Interaction, enabled: bool):
        if not interaction.channel or not isinstance(interaction.channel, discord.TextChannel):
            embed = create_embed("Use this in a text channel.", color="warning", is_dm=False, is_system=False)
            return await interaction.response.send_message(embed=embed, ephemeral=True)
        ch: discord.TextChannel = interaction.channel
        overwrite = ch.overwrites_for(interaction.guild.default_role)
        overwrite.send_messages = (False if enabled else None)
        await ch.set_permissions(interaction.guild.default_role, overwrite=overwrite)
        embed = create_embed(f"Lockdown {'enabled' if enabled else 'disabled'}.", color="success", is_dm=False, is_system=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="dev_reload_personality", description="(Admin) Reload personality.json now.")
    @app_commands.checks.has_permissions(administrator=True)
    async def dev_reload_personality(self, interaction: discord.Interaction):
        if not interaction.guild:
            embed = create_embed("Server only.", color="warning", is_dm=False, is_system=False)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        if not hasattr(self.bot, "personality"):
            embed = create_embed("Personality system not initialized.", color="error", is_dm=False, is_system=False)
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        ok, msg = self.bot.personality.load()
        self.bot.personality.sanitize()
        embed = create_embed(f"Reload: {msg}", color="success" if ok else "error", is_dm=False, is_system=False)
        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Moderation(bot))
