"""
Message Tracker

Counts messages for event boss damage:
- All messages count (no char limit)
- 5s cooldown per user between counted messages
- Counts across all channels except spam channel
- Also refreshes VC full-strength on ANY message (spam excluded), regardless of cooldown
"""

from __future__ import annotations
import time
import discord
from discord.ext import commands
from collections import defaultdict
from utils.uk_time import uk_day_ymd
from utils.embed_utils import create_embed

MESSAGE_COOLDOWN = 5  # seconds


def now_ts() -> int:
    return int(time.time())


class MessageTracker(commands.Cog):
    """
    Counts messages for event boss damage:
    - All messages count (no char limit)
    - 5s cooldown per user between counted messages
    - Counts across all channels except spam channel
    - Also refreshes VC full-strength on ANY message (spam excluded), regardless of cooldown
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.spam_channel_id = int(bot.cfg.get("channels", "spam", default="0") or 0)

        # key=(gid,event_id,uid,day_ymd) -> msg_count since last flush
        self.live_msg = defaultdict(int)

        # cooldown state per (gid,event_id,uid) -> ts
        self.last_msg_counted_ts: dict[tuple[int, str, int], int] = {}

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if not message.guild:
            return
        if message.channel.id == self.spam_channel_id:
            return

        gid = message.guild.id
        uid = message.author.id
        now = now_ts()
        day = uk_day_ymd(now)

        # Which events are active? (holiday + seasonal can both be active)
        events_cog = self.bot.get_cog("EventSystem")
        if not events_cog:
            return
        
        active_event_ids = await events_cog.get_active_event_ids(gid)
        if not active_event_ids:
            return

        # VC refresh: any message restores voice full strength (spam excluded)
        voice = self.bot.get_cog("VoiceTracker")
        if voice:
            for eid in active_event_ids:
                voice.refresh_voice_strength(gid, eid, uid)

        # Boss message counting: apply 5s cooldown PER EVENT so overlaps stay consistent
        for eid in active_event_ids:
            key_state = (gid, eid, uid)
            last = self.last_msg_counted_ts.get(key_state, 0)
            if now - last < MESSAGE_COOLDOWN:
                continue

            self.last_msg_counted_ts[key_state] = now
            self.live_msg[(gid, eid, uid, day)] += 1

    async def flush_message_counters(self, db):
        """
        Called by scheduler every 60s.
        Writes msg_count increments into event_user_day.
        """
        now = now_ts()
        if not self.live_msg:
            return

        rows = []
        for (gid, eid, uid, day), cnt in list(self.live_msg.items()):
            if cnt <= 0:
                continue
            rows.append((gid, eid, uid, day, cnt, now))
            del self.live_msg[(gid, eid, uid, day)]

        if not rows:
            return

        await db.executemany(
            """
            INSERT INTO event_user_day (
              guild_id, event_id, user_id, day_ymd,
              msg_count, last_update_ts
            )
            VALUES (?,?,?,?,?,?)
            ON CONFLICT(guild_id,event_id,user_id,day_ymd) DO UPDATE SET
              msg_count = msg_count + excluded.msg_count,
              last_update_ts = excluded.last_update_ts
            """,
            rows
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(MessageTracker(bot))
