from __future__ import annotations

import discord
from discord.ext import commands
from discord import app_commands

from core.utils import now_ts
from core.embedder import isla_embed

class Tributes(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _consent_ok(self, gid: int, uid: int) -> bool:
        row = await self.bot.db.fetchone(
            "SELECT verified_18, consent_ok FROM consent WHERE guild_id=? AND user_id=?",
            (gid, uid),
        )
        return bool(row and int(row["verified_18"]) == 1 and int(row["consent_ok"]) == 1)

    @app_commands.command(name="tribute", description="Log a symbolic tribute (no payment processing).")
    async def tribute(self, interaction: discord.Interaction, amount: app_commands.Range[int, 1, 100000], note: str | None = None):
        if not interaction.guild:
            await interaction.response.send_message("Guild only.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)

        gid, uid = interaction.guild.id, interaction.user.id
        await self.bot.db.ensure_user(gid, uid)

        if not await self._consent_ok(gid, uid):
            await interaction.followup.send("You must /verify first.", ephemeral=True)
            return

        # This is ONLY a log/roleplay ledger. No external payment handling.
        await self.bot.db.execute(
            "INSERT INTO tribute_log(guild_id,user_id,amount,note,ts) VALUES(?,?,?,?,?)",
            (gid, uid, int(amount), (note or "").strip()[:200], now_ts()),
        )

        # Optional: small coin reward to reinforce engagement (tune as desired)
        reward = min(200, max(5, int(amount // 50)))
        await self.bot.db.execute(
            "UPDATE users SET coins=coins+?, lce=lce+? WHERE guild_id=? AND user_id=?",
            (reward, reward, gid, uid),
        )

        # Send a mod log entry if configured
        log_chan_id = self.bot.cfg.get("channels", "logs")
        if log_chan_id:
            ch = interaction.guild.get_channel(int(log_chan_id))
            if ch:
                e = isla_embed(
                    "Tribute Logged",
                    f"User: <@{uid}>\nAmount: **{amount}**\nRewarded Coins: **{reward}**\nNote: {note or '—'}",
                    color=0xFF4081,
                )
                try:
                    await ch.send(embed=e)
                except discord.Forbidden:
                    pass

        await interaction.followup.send(f"Logged. (+{reward} Coins)", ephemeral=True)

    @app_commands.command(name="tributes", description="(Mod) View recent tribute logs.")
    async def tributes(self, interaction: discord.Interaction, limit: app_commands.Range[int, 1, 20] = 10):
        if not interaction.guild or not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("Mods only.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)

        gid = interaction.guild.id
        rows = await self.bot.db.fetchall(
            "SELECT user_id,amount,note,ts FROM tribute_log WHERE guild_id=? ORDER BY ts DESC LIMIT ?",
            (gid, int(limit)),
        )
        if not rows:
            await interaction.followup.send("No tribute logs.", ephemeral=True)
            return

        lines = []
        for r in rows:
            lines.append(f"- <@{int(r['user_id'])}>: **{int(r['amount'])}** — {r['note'] or '—'} (<t:{int(r['ts'])}:R>)")

        await interaction.followup.send("\n".join(lines), ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Tributes(bot))

