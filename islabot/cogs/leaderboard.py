from __future__ import annotations

import discord
from discord.ext import commands
from discord import app_commands

from core.utils import day_key, now_ts
from core.embedder import isla_embed

class Leaderboard(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # simple anti-spam: count only 1 msg per user per 30s
        self._last_counted: dict[tuple[int, int], int] = {}

    @commands.Cog.listener("on_message")
    async def on_message(self, msg: discord.Message):
        if msg.author.bot or not msg.guild:
            return

        gid, uid = msg.guild.id, msg.author.id
        await self.bot.db.ensure_user(gid, uid)

        # Safeword: do not "engage", but we can still passively count activity if desired.
        # If you prefer: disable counting while safeworded.
        u = await self.bot.db.fetchone(
            "SELECT safeword_until_ts FROM users WHERE guild_id=? AND user_id=?",
            (gid, uid),
        )
        if u and u["safeword_until_ts"] and int(u["safeword_until_ts"]) > now_ts():
            return

        key = (gid, uid)
        now = now_ts()
        last = self._last_counted.get(key, 0)
        if now - last < 30:
            return
        self._last_counted[key] = now

        dk = day_key()
        await self.bot.db.execute(
            """INSERT INTO spotlight(guild_id,user_id,day_key,msg_count,coins_earned,coins_burned)
               VALUES(?,?,?,?,?,?)
               ON CONFLICT(guild_id,user_id,day_key)
               DO UPDATE SET msg_count=msg_count+1""",
            (gid, uid, dk, 1, 0, 0),
        )

    async def log_coins_earned(self, gid: int, uid: int, amount: int):
        if amount <= 0:
            return
        dk = day_key()
        await self.bot.db.execute(
            """INSERT INTO spotlight(guild_id,user_id,day_key,msg_count,coins_earned,coins_burned)
               VALUES(?,?,?,?,?,?)
               ON CONFLICT(guild_id,user_id,day_key)
               DO UPDATE SET coins_earned=coins_earned+?""",
            (gid, uid, dk, 0, amount, 0, amount),
        )

    async def log_coins_burned(self, gid: int, uid: int, amount: int):
        if amount <= 0:
            return
        dk = day_key()
        await self.bot.db.execute(
            """INSERT INTO spotlight(guild_id,user_id,day_key,msg_count,coins_earned,coins_burned)
               VALUES(?,?,?,?,?,?)
               ON CONFLICT(guild_id,user_id,day_key)
               DO UPDATE SET coins_burned=coins_burned+?""",
            (gid, uid, dk, 0, 0, amount, amount),
        )

    @app_commands.command(name="spotlight", description="Show today's spotlight leaderboard (activity + coins).")
    async def spotlight(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("Guild only.", ephemeral=True)
            return
        await interaction.response.defer()
        gid = interaction.guild.id
        dk = day_key()

        rows = await self.bot.db.fetchall(
            """SELECT user_id,msg_count,coins_earned,coins_burned
               FROM spotlight
               WHERE guild_id=? AND day_key=?
               ORDER BY (coins_earned + coins_burned*2 + msg_count*2) DESC
               LIMIT 10""",
            (gid, dk),
        )
        if not rows:
            await interaction.followup.send("No spotlight data yet today.")
            return

        lines = []
        for i, r in enumerate(rows, start=1):
            uid = int(r["user_id"])
            score = int(r["coins_earned"]) + int(r["coins_burned"]) * 2 + int(r["msg_count"]) * 2
            lines.append(
                f"**{i}.** <@{uid}> — score **{score}** "
                f"(msgs {int(r['msg_count'])}, +{int(r['coins_earned'])}, burned {int(r['coins_burned'])})"
            )

        e = isla_embed("Spotlight (Today)", "\n".join(lines), color=0x03A9F4)
        await interaction.followup.send(embed=e)

async def setup(bot: commands.Bot):
    await bot.add_cog(Leaderboard(bot))

