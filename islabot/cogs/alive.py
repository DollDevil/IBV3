from __future__ import annotations
import discord
from discord.ext import commands
from core.utils import now_ts, day_key
from utils.embed_utils import create_embed

class Alive(commands.Cog):
    """Basic activity tracking and personality hot-reload."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener("on_message")
    async def on_message(self, msg: discord.Message):
        if msg.author.bot or not msg.guild:
            return
        gid, uid = msg.guild.id, msg.author.id

        # Hard opt-out means: no tracking
        if await self.bot.db.is_opted_out(gid, uid):
            return

        # Admin-applied safeword means: no tracking
        u = await self.bot.db.fetchone(
            "SELECT safeword_until_ts FROM users WHERE guild_id=? AND user_id=?",
            (gid, uid),
        )
        if u and u["safeword_until_ts"] and int(u["safeword_until_ts"]) > now_ts():
            return

        await self.bot.db.ensure_user(gid, uid)
        await self.bot.db.execute(
            "UPDATE users SET last_msg_ts=? WHERE guild_id=? AND user_id=?",
            (now_ts(), gid, uid),
        )

        dk = day_key()
        await self.bot.db.execute(
            """INSERT INTO user_activity_daily(guild_id,user_id,day_key,messages)
               VALUES(?,?,?,1)
               ON CONFLICT(guild_id,user_id,day_key) DO UPDATE SET messages=messages+1""",
            (gid, uid, dk),
        )

        # Hot-reload personality if file changed
        if hasattr(self.bot, "personality"):
            if self.bot.personality.maybe_reload():
                self.bot.personality.sanitize()

async def setup(bot: commands.Bot):
    await bot.add_cog(Alive(bot))

