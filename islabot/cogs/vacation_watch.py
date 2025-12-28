from __future__ import annotations
import discord
from discord.ext import commands, tasks

from core.utils import now_ts
from utils.helpers import isla_embed
from utils.embed_utils import create_embed

class VacationWatch(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.spam_channel_id = int(bot.cfg.get("channels", "spam", default=0) or 0)
        self.loop.start()

    def cog_unload(self):
        self.loop.cancel()

    @tasks.loop(minutes=10)
    async def loop(self):
        await self.bot.wait_until_ready()
        now = now_ts()

        for guild in self.bot.guilds:
            gid = guild.id
            spam = guild.get_channel(self.spam_channel_id) if self.spam_channel_id else None
            if not isinstance(spam, discord.TextChannel):
                spam = None

            # ended vacations that haven't been welcomed yet
            rows = await self.bot.db.fetchall(
                """
                SELECT user_id, vacation_until_ts, vacation_welcomed_ts
                FROM users
                WHERE guild_id=?
                  AND vacation_until_ts > 0
                  AND vacation_until_ts <= ?
                  AND (vacation_welcomed_ts=0 OR vacation_welcomed_ts < vacation_until_ts)
                  AND opted_out=0
                """,
                (gid, now)
            )
            if not rows:
                continue

            for r in rows:
                uid = int(r["user_id"])
                member = guild.get_member(uid)
                if not member:
                    # user left; still mark to avoid looping forever
                    await self.bot.db.execute(
                        "UPDATE users SET vacation_welcomed_ts=? WHERE guild_id=? AND user_id=?",
                        (now, gid, uid)
                    )
                    continue

                desc = (
                    "Welcome back.\n\n"
                    "Vacation's over.\n"
                    "You're back on normal rules again.\n\n"
                    "If you're rusty, run `/start`.\n"
                    "᲼᲼"
                )
                e = isla_embed(desc, title="Back")

                sent = False
                try:
                    await member.send(embed=e)
                    sent = True
                except discord.Forbidden:
                    sent = False

                if not sent and spam:
                    await spam.send(content=f"||{member.mention}||", embed=e)

                await self.bot.db.execute(
                    "UPDATE users SET vacation_welcomed_ts=? WHERE guild_id=? AND user_id=?",
                    (now, gid, uid)
                )

    @loop.before_loop
    async def before_loop(self):
        await self.bot.wait_until_ready()

async def setup(bot: commands.Bot):
    await bot.add_cog(VacationWatch(bot))

