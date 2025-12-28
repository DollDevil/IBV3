"""
Event Scheduler

Single heartbeat for:
- flushing message + voice counters
- updating boss HP using dp_cached deltas
- milestone announcements + optional spotlight snapshots
"""

from __future__ import annotations
import time
import math
import discord
from discord.ext import commands, tasks
from utils.uk_time import uk_day_ymd, uk_hm
from utils.embed_utils import create_embed

# Boss tick timing
FLUSH_EVERY_SECONDS = 60
BOSS_TICK_EVERY_SECONDS = 30

# VC reduced multiplier must match VoiceTracker
VC_REDUCED_MULT = 0.35

# DP log scaling params (no caps)
k_TS = 25.0
k_CN = 10_000.0
k_CW = 20_000.0
k_M = 20.0
k_V = 30.0


def now_ts() -> int:
    return int(time.time())


def g(x: float, k: float) -> float:
    return math.log(1.0 + (x / k))


def compute_dp(msg_count: int, vc_minutes: int, vc_reduced_minutes: int,
               ritual_done: int, tokens_spent: int, casino_wager: int, casino_net: int) -> float:
    V_eff = float(vc_minutes) + (float(vc_reduced_minutes) * VC_REDUCED_MULT)
    CN_pos = max(int(casino_net), 0)

    return (
        260.0 * g(tokens_spent, k_TS) +
        160.0 * (1 if ritual_done else 0) +
        110.0 * g(CN_pos, k_CN) +
        95.0 * g(casino_wager, k_CW) +
        80.0 * g(msg_count, k_M) +
        80.0 * g(V_eff, k_V)
    )


def isla_embed(desc: str, title: str | None = None, icon_url: str = "https://i.imgur.com/5nsuuCV.png") -> discord.Embed:
    e = discord.Embed(title=title, description=desc)
    e.set_author(name="Isla", icon_url=icon_url)
    return e


class EventsManager:
    """
    Minimal manager wrapper so scheduler can query active events.
    If you already have bot.events, you can remove this and use yours.
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def get_active_event_ids(self, guild_id: int) -> list[str]:
        rows = await self.bot.db.fetchall(
            "SELECT event_id FROM events WHERE guild_id=? AND is_active=1",
            (guild_id,)
        )
        return [str(r["event_id"]) for r in rows]


class EventScheduler(commands.Cog):
    """
    Single heartbeat for:
    - flushing message + voice counters
    - updating boss HP using dp_cached deltas
    - milestone announcements + optional spotlight snapshots
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        if not hasattr(bot, "events"):
            bot.events = EventsManager(bot)  # fallback
        self.orders_channel_id = int(bot.cfg.get("channels", "orders", default="0") or 0)
        self.spotlight_channel_id = int(bot.cfg.get("channels", "spotlight", default="0") or 0)

        self.flush_loop.start()
        self.boss_loop.start()

    def cog_unload(self):
        self.flush_loop.cancel()
        self.boss_loop.cancel()

    # -------------------------
    # Flush: messages + voice
    # -------------------------
    @tasks.loop(seconds=FLUSH_EVERY_SECONDS)
    async def flush_loop(self):
        await self.bot.wait_until_ready()

        msg = self.bot.get_cog("MessageTracker")
        vc = self.bot.get_cog("VoiceTracker")

        if msg:
            await msg.flush_message_counters(self.bot.db)
        if vc:
            await vc.flush_voice_counters()

    @flush_loop.before_loop
    async def before_flush_loop(self):
        await self.bot.wait_until_ready()

    # -------------------------
    # Boss: rolling update
    # -------------------------
    @tasks.loop(seconds=BOSS_TICK_EVERY_SECONDS)
    async def boss_loop(self):
        await self.bot.wait_until_ready()
        now = now_ts()

        for guild in self.bot.guilds:
            gid = guild.id
            # Use bot.events if available, otherwise fall back to EventSystem cog
            if hasattr(self.bot, "events"):
                active_event_ids = await self.bot.events.get_active_event_ids(gid)
            else:
                events_cog = self.bot.get_cog("EventSystem")
                if not events_cog:
                    continue
                active_event_ids = await events_cog.get_active_event_ids(gid)
            
            if not active_event_ids:
                continue

            for event_id in active_event_ids:
                await self._boss_tick_for_event(guild, gid, event_id, now)

    @boss_loop.before_loop
    async def before_boss_loop(self):
        await self.bot.wait_until_ready()

    async def _boss_tick_for_event(self, guild: discord.Guild, gid: int, event_id: str, now: int):
        boss = await self.bot.db.fetchone(
            "SELECT boss_name, hp_current, hp_max, last_tick_ts, last_announce_hp_bucket FROM event_boss WHERE guild_id=? AND event_id=?",
            (gid, event_id)
        )
        if not boss:
            return

        last_tick = int(boss["last_tick_ts"] or 0)

        # Only consider rows updated since last tick
        rows = await self.bot.db.fetchall(
            """
            SELECT user_id, day_ymd,
                   msg_count, vc_minutes, vc_reduced_minutes,
                   ritual_done, tokens_spent, casino_wager, casino_net,
                   dp_cached
            FROM event_user_day
            WHERE guild_id=? AND event_id=? AND last_update_ts > ?
            """,
            (gid, event_id, last_tick)
        )

        if not rows:
            await self.bot.db.execute(
                "UPDATE event_boss SET last_tick_ts=? WHERE guild_id=? AND event_id=?",
                (now, gid, event_id)
            )
            return

        total_delta = 0.0
        # Update dp_cached only for changed rows
        for r in rows:
            new_dp = compute_dp(
                int(r["msg_count"] or 0),
                int(r["vc_minutes"] or 0),
                int(r["vc_reduced_minutes"] or 0),
                int(r["ritual_done"] or 0),
                int(r["tokens_spent"] or 0),
                int(r["casino_wager"] or 0),
                int(r["casino_net"] or 0),
            )
            old_dp = float(r["dp_cached"] or 0.0)
            delta = new_dp - old_dp
            if delta > 0:
                total_delta += delta

            await self.bot.db.execute(
                """
                UPDATE event_user_day
                SET dp_cached=?
                WHERE guild_id=? AND event_id=? AND user_id=? AND day_ymd=?
                """,
                (new_dp, gid, event_id, int(r["user_id"]), str(r["day_ymd"]))
            )

        hp_cur = int(boss["hp_current"])
        hp_new = max(0, hp_cur - int(total_delta))

        await self.bot.db.execute(
            "UPDATE event_boss SET hp_current=?, last_tick_ts=? WHERE guild_id=? AND event_id=?",
            (hp_new, now, gid, event_id)
        )

        # Milestone announcement checks (80/60/40/20/0)
        await self._maybe_milestone_post(guild, gid, event_id, boss["boss_name"], int(boss["hp_max"]), hp_new, int(boss["last_announce_hp_bucket"]))

    async def _maybe_milestone_post(self, guild: discord.Guild, gid: int, event_id: str, boss_name: str, hp_max: int, hp_cur: int, last_bucket: int):
        if hp_max <= 0:
            return
        hp_percent = int((hp_cur / hp_max) * 100)

        # milestone buckets in descending order
        buckets = [80, 60, 40, 20, 0]
        hit_bucket = None
        for b in buckets:
            if hp_percent <= b:
                hit_bucket = b
        if hit_bucket is None:
            return

        # Only announce when crossing into a new bucket
        if hit_bucket >= last_bucket:
            return

        await self.bot.db.execute(
            "UPDATE event_boss SET last_announce_hp_bucket=? WHERE guild_id=? AND event_id=?",
            (hit_bucket, gid, event_id)
        )

        orders = guild.get_channel(self.orders_channel_id) if self.orders_channel_id else None
        if not isinstance(orders, discord.TextChannel):
            return

        # Minimal, non-spammy milestone post
        title = "Milestone"
        desc = (
            "Good.\n\n"
            f"{boss_name} is at **{hit_bucket}%**.\n"
            "Keep going.\n"
            "᲼᲼"
        )
        await orders.send(embed=isla_embed(desc, title=title))


async def setup(bot: commands.Bot):
    await bot.add_cog(EventScheduler(bot))

