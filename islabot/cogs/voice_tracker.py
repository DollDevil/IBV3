"""
Voice Tracker

Tracks voice minutes for event boss damage.
- Credits time every 30 seconds for users in voice
- Applies AFK reduction after 60 minutes without refresh message
- DMs user once when reduction begins
- Refresh triggered by any message in any channel except spam
"""

from __future__ import annotations
import time
import discord
from discord.ext import commands, tasks
from collections import defaultdict

from utils.uk_time import uk_day_ymd

VC_REDUCE_AFTER = 3600  # 1 hour without refresh message
VC_REDUCED_MULT = 0.35  # used later in DP computation
VOICE_TICK_SECONDS = 30  # how often we credit time


def now_ts() -> int:
    return int(time.time())


def isla_embed(desc: str, title: str | None = None, icon_url: str = "https://i.imgur.com/5nsuuCV.png") -> discord.Embed:
    e = discord.Embed(title=title, description=desc)
    e.set_author(name="Isla", icon_url=icon_url)
    return e


class VoiceTracker(commands.Cog):
    """
    Tracks voice minutes for event boss damage.
    - AFK allowed
    - Reduced after 1h without a message (spam excluded)
    - User must message any channel (spam excluded) to restore full strength
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.spam_channel_id = int(bot.cfg.get("channels", "spam", fallback="0") or 0)

        # Active voice sessions: (guild_id, user_id) -> last_tick_ts
        self.in_voice: dict[tuple[int, int], int] = {}

        # Refresh timestamps: (guild_id, event_id, user_id) -> last_refresh_ts
        self.vc_last_refresh_ts: dict[tuple[int, str, int], int] = {}

        # Warned reduced state: (guild_id, event_id, user_id)
        self.vc_reduced_warned: set[tuple[int, str, int]] = set()

        # Live counters to be flushed: key=(gid,event_id,uid,day_ymd)
        self.live_vc_seconds = defaultdict(int)
        self.live_vc_reduced_seconds = defaultdict(int)

        self.tick_loop.start()

    def cog_unload(self):
        self.tick_loop.cancel()

    # ---------- Public hooks for other cogs ----------
    def refresh_voice_strength(self, guild_id: int, event_id: str, user_id: int):
        """
        Call this when user sends a message (spam excluded).
        Restores full VC damage strength immediately.
        """
        key_state = (guild_id, event_id, user_id)
        self.vc_last_refresh_ts[key_state] = now_ts()
        if key_state in self.vc_reduced_warned:
            self.vc_reduced_warned.discard(key_state)

    async def dm_vc_reduced_warning(self, guild: discord.Guild, user_id: int):
        member = guild.get_member(user_id)
        if not member:
            return
        e = isla_embed(
            "Voice Chat damage effect reduced..\n\n"
            "Send a message in any channel to go back to full damage strength.\n"
            "᲼᲼",
            title="Voice Activity"
        )
        try:
            await member.send(embed=e)
        except discord.Forbidden:
            # If DMs are closed, ignore silently (keeps server clean)
            pass

    # ---------- Voice state tracking ----------
    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member,
                                    before: discord.VoiceState,
                                    after: discord.VoiceState):
        # Ignore bots
        if member.bot:
            return

        gid = member.guild.id
        uid = member.id

        was_in = before.channel is not None
        now_in = after.channel is not None

        # Joined voice
        if not was_in and now_in:
            self.in_voice[(gid, uid)] = now_ts()

        # Left voice
        elif was_in and not now_in:
            # Credit remaining time since last tick once, then remove
            await self._credit_voice_time(member.guild, uid, final=True)
            self.in_voice.pop((gid, uid), None)

        # Switched channel: treat as still in voice
        elif was_in and now_in:
            # nothing special needed; credit loop will handle
            return

    # ---------- Periodic credit loop ----------
    @tasks.loop(seconds=VOICE_TICK_SECONDS)
    async def tick_loop(self):
        await self.bot.wait_until_ready()

        # Get active events per guild
        for guild in self.bot.guilds:
            events_cog = self.bot.get_cog("EventSystem")
            if not events_cog:
                continue
            
            active_event_ids = await events_cog.get_active_event_ids(guild.id)
            if not active_event_ids:
                continue

            # credit time for every user currently in voice in this guild
            for (gid, uid), last_tick in list(self.in_voice.items()):
                if gid != guild.id:
                    continue
                await self._credit_voice_time(guild, uid, active_event_ids=active_event_ids)

    @tick_loop.before_loop
    async def before_tick_loop(self):
        await self.bot.wait_until_ready()

    async def _credit_voice_time(self, guild: discord.Guild, user_id: int, active_event_ids: list[str] | None = None, final: bool = False):
        """
        Credits time since last tick for (guild,user).
        If final=True, credits time once using current time and does not require active_event_ids.
        """
        gid = guild.id
        key = (gid, user_id)

        last = self.in_voice.get(key)
        if not last:
            return

        now = now_ts()
        delta = now - last
        if delta <= 0:
            return

        # update last tick timestamp
        self.in_voice[key] = now

        if final and (not active_event_ids):
            events_cog = self.bot.get_cog("EventSystem")
            if events_cog:
                active_event_ids = await events_cog.get_active_event_ids(gid)

        if not active_event_ids:
            return

        day = uk_day_ymd(now)

        # apply reduced state per event
        for event_id in active_event_ids:
            state_key = (gid, event_id, user_id)
            last_refresh = self.vc_last_refresh_ts.get(state_key, 0)
            reduced = (now - last_refresh) >= VC_REDUCE_AFTER

            if reduced:
                self.live_vc_reduced_seconds[(gid, event_id, user_id, day)] += delta
                # warn once per reduced session per event
                if state_key not in self.vc_reduced_warned:
                    self.vc_reduced_warned.add(state_key)
                    await self.dm_vc_reduced_warning(guild, user_id)
            else:
                self.live_vc_seconds[(gid, event_id, user_id, day)] += delta

    # ---------- Flush interface ----------
    async def flush_voice_counters(self):
        """
        Call this from your main event flush loop (every 60s).
        Writes vc_minutes + vc_reduced_minutes into event_user_day.
        """
        now = now_ts()
        keys = set(self.live_vc_seconds.keys()) | set(self.live_vc_reduced_seconds.keys())
        if not keys:
            return

        rows = []
        for (gid, eid, uid, day) in keys:
            sec = self.live_vc_seconds.pop((gid, eid, uid, day), 0)
            rsec = self.live_vc_reduced_seconds.pop((gid, eid, uid, day), 0)
            vc_min = sec // 60
            vc_rmin = rsec // 60
            if vc_min == 0 and vc_rmin == 0:
                continue
            rows.append((gid, eid, uid, day, vc_min, vc_rmin, now))

        if not rows:
            return

        await self.bot.db.executemany(
            """
            INSERT INTO event_user_day (
              guild_id, event_id, user_id, day_ymd,
              vc_minutes, vc_reduced_minutes, last_update_ts
            )
            VALUES (?,?,?,?,?,?,?)
            ON CONFLICT(guild_id,event_id,user_id,day_ymd) DO UPDATE SET
              vc_minutes = vc_minutes + excluded.vc_minutes,
              vc_reduced_minutes = vc_reduced_minutes + excluded.vc_reduced_minutes,
              last_update_ts = excluded.last_update_ts
            """,
            rows
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(VoiceTracker(bot))
