from __future__ import annotations
import discord
from discord.ext import commands, tasks
from discord import app_commands

from utils.isla_style import isla_embed
from utils.uk_parse import parse_when_to_ts, parse_duration_to_seconds, now_ts, human_eta

class AnnounceGroup(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.announce = app_commands.Group(name="announce", description="Announcements")
        self._register()
        self.announce_loop.start()
        self.remind_loop.start()

    def cog_unload(self):
        self.announce_loop.cancel()
        self.remind_loop.cancel()

    def _is_mod(self, m: discord.Member) -> bool:
        p = m.guild_permissions
        return p.manage_guild or p.manage_messages or p.administrator

    # /announce send
    @app_commands.command(name="send", description="Immediate announcement.")
    @app_commands.describe(message="Text to send", title="Embed title (optional)")
    async def send(self, interaction: discord.Interaction, message: str, title: str | None = None):
        if not interaction.guild or not isinstance(interaction.user, discord.Member) or not self._is_mod(interaction.user):
            return await interaction.response.send_message(embed=isla_embed("Not for you.\n᲼᲼", title="Announce"), ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        await interaction.channel.send(embed=isla_embed(message + "\n᲼᲼", title=title or "Announcement"))
        await interaction.followup.send(embed=isla_embed("Sent.\n᲼᲼", title="Announce"), ephemeral=True)

    # /announce schedule
    @app_commands.command(name="schedule", description="Schedules an announcement with repeats.")
    @app_commands.describe(
        when="Start time: 'in 10m' or 'YYYY-MM-DD HH:MM' (UK)",
        repeat="none, hourly, daily, weekly",
        interval_minutes="For repeat='hourly' you can set interval minutes (optional)",
        title="Embed title (optional)",
        message="Announcement text"
    )
    async def schedule(self, interaction: discord.Interaction, when: str, message: str, repeat: str = "none",
                       interval_minutes: int = 0, title: str | None = None):
        if not interaction.guild or not isinstance(interaction.user, discord.Member) or not self._is_mod(interaction.user):
            return await interaction.response.send_message(embed=isla_embed("Not for you.\n᲼᲼", title="Announce"), ephemeral=True)

        await interaction.response.defer(ephemeral=True)

        run_ts = parse_when_to_ts(when)
        if run_ts <= now_ts():
            return await interaction.followup.send(embed=isla_embed("Bad time.\n᲼᲼", title="Announce"), ephemeral=True)

        rep = repeat.lower().strip()
        if rep not in ("none", "hourly", "daily", "weekly"):
            rep = "none"

        interval_minutes = max(0, int(interval_minutes or 0))

        await self.bot.db.execute(
            """
            INSERT INTO announce_jobs(guild_id,channel_id,message,embed_title,repeat_rule,interval_minutes,next_run_ts,created_ts,created_by,active)
            VALUES(?,?,?,?,?,?,?,?,?,1)
            """,
            (interaction.guild_id, interaction.channel_id, message, title or "", rep, interval_minutes, run_ts, now_ts(), interaction.user.id)
        )

        e = isla_embed(
            f"Scheduled.\n\nRuns: {human_eta(run_ts)}\nRepeat: **{rep}**\n᲼᲼",
            title="Announce"
        )
        await interaction.followup.send(embed=e, ephemeral=True)

    # /remind <when> <message>
    @app_commands.command(name="remind", description="Personal reminder.")
    @app_commands.describe(when="in 10m / 2h / YYYY-MM-DD HH:MM (UK)", message="Reminder text")
    async def remind_me(self, interaction: discord.Interaction, when: str, message: str):
        await interaction.response.defer(ephemeral=True)
        if not interaction.guild_id:
            return await interaction.followup.send("Server only.", ephemeral=True)

        ts = parse_when_to_ts(when)
        if ts <= now_ts():
            return await interaction.followup.send(embed=isla_embed("Bad time.\n᲼᲼", title="Reminder"), ephemeral=True)

        await self.bot.db.execute(
            """
            INSERT INTO personal_reminders(guild_id,user_id,message,run_ts,created_ts,active)
            VALUES(?,?,?,?,?,1)
            """,
            (interaction.guild_id, interaction.user.id, message, ts, now_ts())
        )

        e = isla_embed(f"Fine.\n\nI'll remind you {human_eta(ts)}.\n᲼᲼", title="Reminder")
        await interaction.followup.send(embed=e, ephemeral=True)

    # background: announce scheduler
    @tasks.loop(seconds=10)
    async def announce_loop(self):
        await self.bot.wait_until_ready()
        now = now_ts()
        rows = await self.bot.db.fetchall(
            """
            SELECT id,guild_id,channel_id,message,embed_title,repeat_rule,interval_minutes,next_run_ts
            FROM announce_jobs
            WHERE active=1 AND next_run_ts <= ?
            ORDER BY next_run_ts ASC
            LIMIT 5
            """,
            (now,)
        )
        for r in rows:
            gid = int(r["guild_id"])
            ch_id = int(r["channel_id"])
            guild = self.bot.get_guild(gid)
            if not guild:
                continue
            ch = guild.get_channel(ch_id)
            if not isinstance(ch, discord.TextChannel):
                continue

            await ch.send(embed=isla_embed(str(r["message"]) + "\n᲼᲼", title=(str(r["embed_title"]) or "Announcement")))

            # reschedule
            rep = str(r["repeat_rule"])
            nxt = 0
            if rep == "hourly":
                mins = int(r["interval_minutes"] or 60)
                mins = 60 if mins <= 0 else mins
                nxt = now + mins * 60
            elif rep == "daily":
                nxt = now + 86400
            elif rep == "weekly":
                nxt = now + 7 * 86400

            if nxt > 0:
                await self.bot.db.execute("UPDATE announce_jobs SET next_run_ts=? WHERE id=?", (nxt, int(r["id"])))
            else:
                await self.bot.db.execute("UPDATE announce_jobs SET active=0 WHERE id=?", (int(r["id"]),))

    # background: personal reminders
    @tasks.loop(seconds=10)
    async def remind_loop(self):
        await self.bot.wait_until_ready()
        now = now_ts()
        rows = await self.bot.db.fetchall(
            """
            SELECT id,guild_id,user_id,message
            FROM personal_reminders
            WHERE active=1 AND run_ts <= ?
            ORDER BY run_ts ASC
            LIMIT 10
            """,
            (now,)
        )
        for r in rows:
            gid = int(r["guild_id"])
            uid = int(r["user_id"])
            msg = str(r["message"])
            guild = self.bot.get_guild(gid)
            if guild:
                member = guild.get_member(uid)
                if member:
                    try:
                        await member.send(embed=isla_embed(msg + "\n᲼᲼", title="Reminder"))
                    except Exception:
                        pass
            await self.bot.db.execute("UPDATE personal_reminders SET active=0 WHERE id=?", (int(r["id"]),))

    def _register(self):
        self.announce.add_command(self.send)
        self.announce.add_command(self.schedule)

async def setup(bot: commands.Bot):
    cog = AnnounceGroup(bot)
    await bot.add_cog(cog)
    try:
        bot.tree.add_command(cog.announce)
        bot.tree.add_command(cog.remind_me)
    except Exception:
        pass  # Commands already registered

