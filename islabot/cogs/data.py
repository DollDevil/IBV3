"""
Data Tracking Cog
Consolidates: moderation, progression, voice_tracker, message_tracker, event_activity_tracker, voice_stats

Responsibilities:
- Collectors: on_message, on_reaction_add, on_voice_state_update
- In-memory counters: live_msg, live_vc_seconds, live_casino_wager, etc.
- Flush loops: flush_loop, boss_tick_loop, voice_tick_loop
- Commands: rank, weekly, voice, purge, slowmode, lockdown, dev_reload_personality
"""

from __future__ import annotations

import json
import math
import time
from collections import defaultdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands, tasks
from discord import app_commands

from core.utility import now_ts, now_local, fmt
from core.events import calculate_daily_damage
from core.personality import sanitize_isla_text
from utils.helpers import isla_embed as helper_isla_embed
from utils.embed_utils import create_embed
from utils.uk_time import uk_day_ymd

UK_TZ = ZoneInfo("Europe/London")

# ========================================================================
# CONSTANTS
# ========================================================================

RANKS = [
    ("Stray", 0),
    ("Worthless Pup", 500),
    ("Leashed Pup", 1000),
    ("Collared Dog", 5000),
    ("Trained Pet", 10000),
    ("Devoted Dog", 15000),
    ("Cherished Pet", 20000),
    ("Favorite Puppy", 50000),
]

MESSAGE_COOLDOWN = 5  # seconds
VC_REDUCE_AFTER = 3600  # 1 hour without refresh message
VC_REDUCED_MULT = 0.35
VOICE_TICK_SECONDS = 30  # how often we credit time
FLUSH_EVERY = 60  # Flush to DB every 60 seconds
BOSS_TICK_EVERY = 30  # Update boss HP every 30 seconds

# ========================================================================
# HELPER FUNCTIONS
# ========================================================================


def week_key_uk() -> str:
    """Get current week key in ISO format (YYYY-WW)."""
    t = now_local()
    iso_year, iso_week, _ = t.isocalendar()
    return f"{iso_year}-{iso_week:02d}"


def day_key_uk() -> str:
    """Get current day key in format (YYYY-MM-DD)."""
    t = now_local()
    return f"{t.year}-{t.month:02d}-{t.day:02d}"


def date_key_uk(ts: int) -> str:
    """Convert timestamp to UK date key (YYYY-MM-DD)."""
    return uk_day_ymd(ts)


def last_7_date_keys() -> list[str]:
    """Get list of last 7 date keys (including today) in descending order."""
    keys = []
    now = datetime.now(tz=UK_TZ)
    for i in range(7):
        dt = now - timedelta(days=i)
        keys.append(dt.strftime("%Y-%m-%d"))
    return keys


def isla_embed(desc: str, icon: str | None = None, title: str | None = None) -> discord.Embed:
    """Create an Isla-styled embed."""
    if icon:
        return helper_isla_embed(desc, icon=icon)
    e = discord.Embed(title=title, description=desc)
    e.set_author(name="Isla", icon_url="https://i.imgur.com/5nsuuCV.png")
    return e


# ========================================================================
# LEGACY HELPER CLASS (WAS computation formulas)
# ========================================================================


class WASCalculator:
    """Legacy helper for WAS (Weekly Activity Score) computation formulas."""
    
    @staticmethod
    def compute(msg_count: int, react_count: int, voice_seconds: int, casino_wagered: int) -> int:
        """Compute WAS from activity counts."""
        voice_minutes = voice_seconds // 60
        score = (
            msg_count * 3 +
            react_count * 1 +
            min(voice_minutes, 600) * 2 +
            int(math.sqrt(max(casino_wagered, 0))) * 2
        )
        return int(score)
    
    @staticmethod
    def weekly_bonus_from_was(was: int) -> int:
        """Compute weekly bonus coins from WAS score."""
        base = 200
        bonus = base + int(min(2800, math.sqrt(max(was, 0)) * 35))
        return bonus


# ========================================================================
# DATA COG
# ========================================================================


class Data(commands.Cog):
    """
    Consolidated data tracking cog:
    - Activity collectors (messages, reactions, voice)
    - In-memory counters for event tracking
    - Flush loops for persistence
    - Progression commands (rank, weekly)
    - Moderation commands (purge, slowmode, lockdown)
    """
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.icon = "https://i.imgur.com/5nsuuCV.png"
        self.spam_channel_id = int(bot.cfg.get("channels", "spam", default="0") or 0)
        
        # Legacy ensure_user cache (only call once per process lifetime per user)
        self._ensured_legacy: set[tuple[int, int]] = set()  # (guild_id, user_id)
        
        # Start balance cache (avoid repeated DB calls in commands)
        self._start_balance_done: set[tuple[str, str]] = set()  # (guild_id, user_id) as strings
        
        # Voice tracking state (in-memory counters)
        self.in_voice: dict[tuple[int, int], int] = {}  # (guild_id, user_id) -> last_tick_ts
        self.vc_last_refresh_ts: dict[tuple[int, str, int], int] = {}  # (guild_id, event_id, user_id) -> last_refresh_ts
        self.vc_reduced_warned: set[tuple[int, str, int]] = set()  # (guild_id, event_id, user_id)
        self.live_vc_seconds = defaultdict(int)  # (gid, event_id, uid, day_ymd) -> seconds
        self.live_vc_reduced_seconds = defaultdict(int)  # (gid, event_id, uid, day_ymd) -> seconds
        
        # Message tracking state (in-memory counters)
        self.live_msg = defaultdict(int)  # (gid, event_id, uid, day_ymd) -> msg_count
        self.last_msg_counted_ts: dict[tuple[int, str, int], int] = {}  # (gid, event_id, uid) -> ts
        
        # Event activity tracking state (in-memory counters)
        self.live_casino_wager = defaultdict(int)  # (gid, event_id, uid, day_ymd) -> wager
        self.live_casino_net = defaultdict(int)  # (gid, event_id, uid, day_ymd) -> net
        self.live_tokens_spent = defaultdict(int)  # (gid, event_id, uid, day_ymd) -> tokens
        self.live_ritual_done = defaultdict(int)  # (gid, event_id, uid, day_ymd) -> 1 if done
        
        # Start loops
        self.voice_tick_loop.start()
        self.flush_loop.start()
        self.boss_tick_loop.start()
    
    def cog_unload(self):
        self.voice_tick_loop.cancel()
        self.flush_loop.cancel()
        self.boss_tick_loop.cancel()
    
    # ========================================================================
    # USER MANAGEMENT
    # ========================================================================
    
    async def _ensure_user(self, gid: int, uid: int):
        """Ensure user exists in both legacy and v3 schemas (optimized)."""
        # Legacy compatibility: only call once per process lifetime per user
        legacy_key = (gid, uid)
        if legacy_key not in self._ensured_legacy:
            await self.bot.db.ensure_user(gid, uid)
            self._ensured_legacy.add(legacy_key)
        
        # V3 schema: ensure user exists (v3_track_* methods handle this, but we ensure here for safety)
        await self.bot.db.ensure_v3_user(gid, uid, join_ts=now_ts())
        
        # Grant start balance once (idempotent, cached in-memory to avoid repeated DB checks)
        start_balance_key = (str(gid), str(uid))
        if start_balance_key not in self._start_balance_done:
            start_balance = int(self.bot.cfg.get("economy", "start_balance", default=250))
            if start_balance > 0:
                await self.bot.db.v3_grant_start_balance_once(gid, uid, start_balance)
            self._start_balance_done.add(start_balance_key)
    
    # ========================================================================
    # RANK HELPERS
    # ========================================================================
    
    def rank_for_obedience(self, obedience: int) -> str:
        """Get rank name for given obedience value."""
        current = RANKS[0][0]
        for name, req in RANKS:
            if obedience >= req:
                current = name
        return current
    
    def next_rank(self, obedience: int):
        """Get next rank name and requirement."""
        for name, req in RANKS:
            if obedience < req:
                return name, req
        return None, None
    
    # ========================================================================
    # COLLECTORS: Message Tracking
    # ========================================================================
    
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Track messages and update activity."""
        if message.author.bot:
            return
        if not message.guild:
            return
        if message.channel.id == self.spam_channel_id:
            return
        
        gid = message.guild.id
        uid = message.author.id
        now = now_ts()
        date_key = date_key_uk(now)
        
        # V3: Track message (ensures user exists, updates last_seen, bumps message count)
        await self.bot.db.v3_track_message(gid, uid, date_key, now, inc=1)
        
        # Event message tracking (keep as-is for EventSystem)
        events_cog = self.bot.get_cog("EventSystem")
        if not events_cog:
            return
        
        active_event_ids = await events_cog.get_active_event_ids(gid)
        if not active_event_ids:
            return
        
        # VC refresh: any message restores voice full strength (spam excluded)
        for eid in active_event_ids:
            self.refresh_voice_strength(gid, eid, uid)
        
        # Boss message counting: apply 5s cooldown PER EVENT
        day = uk_day_ymd(now)
        for eid in active_event_ids:
            key_state = (gid, eid, uid)
            last = self.last_msg_counted_ts.get(key_state, 0)
            if now - last < MESSAGE_COOLDOWN:
                continue
            
            self.last_msg_counted_ts[key_state] = now
            self.live_msg[(gid, eid, uid, day)] += 1
    
    @commands.Cog.listener()
    async def on_reaction_add(self, reaction: discord.Reaction, user: discord.User | discord.Member):
        """Track reactions and update activity."""
        if user.bot or not reaction.message.guild:
            return
        gid = reaction.message.guild.id
        uid = user.id
        now = now_ts()
        date_key = date_key_uk(now)
        
        # V3: Track reaction (ensures user exists, updates last_seen, bumps reaction count)
        await self.bot.db.v3_track_reaction(gid, uid, date_key, now, inc=1)
    
    # ========================================================================
    # COLLECTORS: Voice Tracking
    # ========================================================================
    
    def refresh_voice_strength(self, guild_id: int, event_id: str, user_id: int):
        """Call this when user sends a message (spam excluded). Restores full VC damage strength immediately."""
        key_state = (guild_id, event_id, user_id)
        self.vc_last_refresh_ts[key_state] = now_ts()
        if key_state in self.vc_reduced_warned:
            self.vc_reduced_warned.discard(key_state)
    
    async def dm_vc_reduced_warning(self, guild: discord.Guild, user_id: int):
        """Send DM warning when voice damage is reduced."""
        member = guild.get_member(user_id)
        if not member:
            return
        e = isla_embed(
            "Voice Chat damage effect reduced..\n\nSend a message in any channel to go back to full damage strength.\n᲼᲼",
            title="Voice Activity"
        )
        try:
            await member.send(embed=e)
        except discord.Forbidden:
            pass
    
    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        """Track voice state changes."""
        if member.bot:
            return
        
        gid = member.guild.id
        uid = member.id
        
        was_in = before.channel is not None
        now_in = after.channel is not None
        
        if not was_in and now_in:
            # Start tracking voice (v3_track_voice_seconds will ensure user exists)
            self.in_voice[(gid, uid)] = now_ts()
        elif was_in and not now_in:
            await self._credit_voice_time(member.guild, uid, final=True)
            self.in_voice.pop((gid, uid), None)
    
    @tasks.loop(seconds=VOICE_TICK_SECONDS)
    async def voice_tick_loop(self):
        """Credit voice time every 30 seconds."""
        await self.bot.wait_until_ready()
        
        for guild in self.bot.guilds:
            events_cog = self.bot.get_cog("EventSystem")
            if not events_cog:
                continue
            
            active_event_ids = await events_cog.get_active_event_ids(guild.id)
            if not active_event_ids:
                continue
            
            for (gid, uid), last_tick in list(self.in_voice.items()):
                if gid != guild.id:
                    continue
                await self._credit_voice_time(guild, uid, active_event_ids=active_event_ids)
    
    @voice_tick_loop.before_loop
    async def before_voice_tick_loop(self):
        await self.bot.wait_until_ready()
    
    async def _credit_voice_time(self, guild: discord.Guild, user_id: int, active_event_ids: list[str] | None = None, final: bool = False):
        """Credit voice time to both v3 schema and event system."""
        gid = guild.id
        key = (gid, user_id)
        
        last = self.in_voice.get(key)
        if not last:
            return
        
        now = now_ts()
        delta = now - last
        if delta <= 0:
            return
        
        self.in_voice[key] = now
        date_key = date_key_uk(now)
        
        # V3: Track voice seconds (ensures user exists, updates last_seen, adds voice seconds)
        await self.bot.db.v3_track_voice_seconds(gid, user_id, date_key, now, seconds=delta)
        
        # Event system tracking (keep as-is)
        if final and (not active_event_ids):
            events_cog = self.bot.get_cog("EventSystem")
            if events_cog:
                active_event_ids = await events_cog.get_active_event_ids(gid)
        
        if not active_event_ids:
            return
        
        day = uk_day_ymd(now)
        
        for event_id in active_event_ids:
            state_key = (gid, event_id, user_id)
            last_refresh = self.vc_last_refresh_ts.get(state_key, 0)
            reduced = (now - last_refresh) >= VC_REDUCE_AFTER
            
            if reduced:
                self.live_vc_reduced_seconds[(gid, event_id, user_id, day)] += delta
                if state_key not in self.vc_reduced_warned:
                    self.vc_reduced_warned.add(state_key)
                    await self.dm_vc_reduced_warning(guild, user_id)
            else:
                self.live_vc_seconds[(gid, event_id, user_id, day)] += delta
    
    # ========================================================================
    # FLUSHERS: Persist In-Memory Counters
    # ========================================================================
    
    async def flush_voice_counters(self):
        """Flush voice counters to event_user_day table (EventSystem)."""
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
    
    async def flush_message_counters(self, db):
        """Flush message counters to event_user_day table (EventSystem)."""
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
    
    @tasks.loop(seconds=FLUSH_EVERY)
    async def flush_loop(self):
        """Flush in-memory counters to database every 60 seconds."""
        await self.bot.wait_until_ready()
        await self._flush_counters()
    
    @flush_loop.before_loop
    async def before_flush_loop(self):
        await self.bot.wait_until_ready()
    
    async def _flush_counters(self):
        """Flush live counters to event_user_day table (EventSystem)."""
        if not (self.live_msg or self.live_casino_wager or self.live_casino_net or 
                self.live_tokens_spent or self.live_ritual_done):
            await self.flush_voice_counters()
            return
        
        keys = (
            set(self.live_msg.keys()) |
            set(self.live_casino_wager.keys()) |
            set(self.live_casino_net.keys()) |
            set(self.live_tokens_spent.keys()) |
            set(self.live_ritual_done.keys())
        )
        
        if not keys:
            await self.flush_voice_counters()
            return
        
        now = now_ts()
        rows = []
        
        for (gid, eid, uid, day) in keys:
            msg = self.live_msg.pop((gid, eid, uid, day), 0)
            wager = self.live_casino_wager.pop((gid, eid, uid, day), 0)
            net = self.live_casino_net.pop((gid, eid, uid, day), 0)
            tsp = self.live_tokens_spent.pop((gid, eid, uid, day), 0)
            ritual = self.live_ritual_done.pop((gid, eid, uid, day), 0)
            
            # Voice minutes are flushed separately
            vc_min = 0
            vc_rmin = 0
            
            if msg == 0 and wager == 0 and net == 0 and tsp == 0 and ritual == 0:
                continue
            
            rows.append((gid, eid, uid, day, msg, vc_min, vc_rmin, ritual, tsp, wager, net, now))
        
        if not rows:
            await self.flush_voice_counters()
            return
        
        await self.bot.db.executemany(
            """
            INSERT INTO event_user_day (
              guild_id, event_id, user_id, day_ymd,
              msg_count, vc_minutes, vc_reduced_minutes,
              ritual_done, tokens_spent, casino_wager, casino_net,
              last_update_ts
            )
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(guild_id,event_id,user_id,day_ymd) DO UPDATE SET
              msg_count = msg_count + excluded.msg_count,
              vc_minutes = vc_minutes + excluded.vc_minutes,
              vc_reduced_minutes = vc_reduced_minutes + excluded.vc_reduced_minutes,
              ritual_done = MAX(ritual_done, excluded.ritual_done),
              tokens_spent = tokens_spent + excluded.tokens_spent,
              casino_wager = casino_wager + excluded.casino_wager,
              casino_net = casino_net + excluded.casino_net,
              last_update_ts = excluded.last_update_ts
            """,
            rows
        )
        
        await self.flush_voice_counters()
        await self._persist_user_states()
    
    async def _persist_user_states(self):
        """Persist in-memory user state to event_user_state table (batched for performance)."""
        if not self.last_msg_counted_ts:
            return
        
        rows = [(gid, event_id, uid, msg_ts) for (gid, event_id, uid), msg_ts in self.last_msg_counted_ts.items()]
        
        async with self.bot.db.transaction():
            await self.bot.db.executemany(
                """
                INSERT INTO event_user_state(
                  guild_id, event_id, user_id,
                  last_msg_counted_ts
                )
                VALUES(?,?,?,?)
                ON CONFLICT(guild_id,event_id,user_id) DO UPDATE SET
                  last_msg_counted_ts = excluded.last_msg_counted_ts
                """,
                rows,
                commit=False
            )
    
    # ========================================================================
    # FLUSHERS: Boss Tick Loop
    # ========================================================================
    
    @tasks.loop(seconds=BOSS_TICK_EVERY)
    async def boss_tick_loop(self):
        """Update boss HP every 30 seconds based on recent activity."""
        await self.bot.wait_until_ready()
        
        for guild in self.bot.guilds:
            gid = guild.id
            await self._boss_tick(gid)
    
    @boss_tick_loop.before_loop
    async def before_boss_tick_loop(self):
        await self.bot.wait_until_ready()
    
    def _compute_dp(self, msg_count: int, vc_minutes: int, vc_reduced_minutes: int, ritual_done: int, tokens_spent: int, casino_wager: int, casino_net: int) -> float:
        """Compute damage points from daily stats (EventSystem)."""
        vc_eff = vc_minutes + (vc_reduced_minutes * VC_REDUCED_MULT)
        
        dp, _ = calculate_daily_damage(
            tokens_spent=float(tokens_spent),
            ritual_completed=ritual_done,
            casino_net=float(max(casino_net, 0)),
            casino_wager=float(casino_wager),
            messages=float(msg_count),
            voice_effective_minutes=float(vc_eff)
        )
        return dp
    
    async def _boss_tick(self, guild_id: int):
        """Update boss HP for all active events in a guild."""
        events = await self.bot.db.fetchall(
            """
            SELECT e.event_id, b.hp_current, b.hp_max, b.last_tick_ts, b.last_announce_hp_bucket
            FROM events e
            JOIN event_boss b ON e.guild_id=b.guild_id AND e.event_id=b.event_id
            WHERE e.guild_id=? AND e.is_active=1
            """,
            (guild_id,)
        )
        
        for event_row in events:
            event_id = str(event_row["event_id"])
            hp_cur = int(event_row["hp_current"])
            hp_max = int(event_row["hp_max"])
            last_tick = int(event_row["last_tick_ts"] or 0)
            last_bucket = int(event_row["last_announce_hp_bucket"] or 100)
            
            now = now_ts()
            
            changed = await self.bot.db.fetchall(
                """
                SELECT user_id, day_ymd,
                       msg_count, vc_minutes, vc_reduced_minutes,
                       ritual_done, tokens_spent, casino_wager, casino_net,
                       dp_cached
                FROM event_user_day
                WHERE guild_id=? AND event_id=? AND last_update_ts > ?
                """,
                (guild_id, event_id, last_tick)
            )
            
            if not changed:
                await self.bot.db.execute(
                    "UPDATE event_boss SET last_tick_ts=? WHERE guild_id=? AND event_id=?",
                    (now, guild_id, event_id)
                )
                continue
            
            total_delta = 0.0
            
            for r in changed:
                new_dp = self._compute_dp(
                    int(r["msg_count"]),
                    int(r["vc_minutes"]),
                    int(r["vc_reduced_minutes"]),
                    int(r["ritual_done"]),
                    int(r["tokens_spent"]),
                    int(r["casino_wager"]),
                    int(r["casino_net"])
                )
                old_dp = float(r["dp_cached"] or 0.0)
                delta = max(0.0, new_dp - old_dp)
                total_delta += delta
                
                await self.bot.db.execute(
                    """
                    UPDATE event_user_day
                    SET dp_cached=?
                    WHERE guild_id=? AND event_id=? AND user_id=? AND day_ymd=?
                    """,
                    (new_dp, guild_id, event_id, int(r["user_id"]), str(r["day_ymd"]))
                )
            
            hp_new = max(0, hp_cur - int(total_delta))
            
            await self.bot.db.execute(
                "UPDATE event_boss SET hp_current=?, last_tick_ts=? WHERE guild_id=? AND event_id=?",
                (hp_new, now, guild_id, event_id)
            )
            
            await self.bot.db.execute(
                "INSERT INTO event_boss_tick(guild_id,event_id,ts,damage_total,meta_json) VALUES(?,?,?,?,?)",
                (guild_id, event_id, now, float(total_delta), "{}")
            )
            
            hp_pct = int((hp_new / max(1, hp_max)) * 100)
            buckets = [80, 60, 40, 20, 0]
            
            for bucket in buckets:
                if hp_pct <= bucket < last_bucket:
                    await self._handle_milestone(guild_id, event_id, bucket, hp_new, hp_max)
                    await self.bot.db.execute(
                        "UPDATE event_boss SET last_announce_hp_bucket=? WHERE guild_id=? AND event_id=?",
                        (bucket, guild_id, event_id)
                    )
                    break
    
    async def _handle_milestone(self, guild_id: int, event_id: str, bucket: int, hp_cur: int, hp_max: int):
        """Handle milestone reached (placeholder - integrate with events system)."""
        pass
    
    # ========================================================================
    # EVENT ACTIVITY TRACKING (External API)
    # ========================================================================
    
    async def get_active_event_id(self, guild_id: int) -> str | None:
        """Get the currently active event_id for a guild. Priority: holiday_week > season_era."""
        row = await self.bot.db.fetchone(
            """
            SELECT event_id FROM events
            WHERE guild_id=? AND is_active=1 AND event_type='holiday_week'
            ORDER BY start_ts DESC LIMIT 1
            """,
            (guild_id,)
        )
        if row:
            return str(row["event_id"])
        
        row = await self.bot.db.fetchone(
            """
            SELECT event_id FROM events
            WHERE guild_id=? AND is_active=1 AND event_type='season_era'
            ORDER BY start_ts DESC LIMIT 1
            """,
            (guild_id,)
        )
        if row:
            return str(row["event_id"])
        
        return None
    
    async def add_casino_activity(self, guild_id: int, user_id: int, wager: int, net: int):
        """Add casino wager and net to event tracking."""
        event_id = await self.get_active_event_id(guild_id)
        if not event_id:
            return
        
        now = now_ts()
        day_ymd = uk_day_ymd(now)
        key_day = (guild_id, event_id, user_id, day_ymd)
        
        self.live_casino_wager[key_day] += wager
        self.live_casino_net[key_day] += net
    
    async def add_tokens_spent(self, guild_id: int, user_id: int, amount: int, reason: str, meta: dict | None = None):
        """Add token spending to event tracking and ledger."""
        event_id = await self.get_active_event_id(guild_id)
        if not event_id:
            return
        
        now = now_ts()
        day_ymd = uk_day_ymd(now)
        key_day = (guild_id, event_id, user_id, day_ymd)
        
        self.live_tokens_spent[key_day] += amount
        
        await self.bot.db.execute(
            """
            INSERT INTO event_token_ledger(guild_id, event_id, user_id, ts, delta, reason, meta_json)
            VALUES(?,?,?,?,?,?,?)
            """,
            (guild_id, event_id, user_id, now, -amount, reason, json.dumps(meta or {}))
        )
    
    async def add_token_earned(self, guild_id: int, user_id: int, amount: int, reason: str, meta: dict | None = None):
        """Add token earning to ledger (doesn't affect damage, just audit)."""
        event_id = await self.get_active_event_id(guild_id)
        if not event_id:
            return
        
        now = now_ts()
        
        await self.bot.db.execute(
            """
            INSERT INTO event_token_ledger(guild_id, event_id, user_id, ts, delta, reason, meta_json)
            VALUES(?,?,?,?,?,?,?)
            """,
            (guild_id, event_id, user_id, now, amount, reason, json.dumps(meta or {}))
        )
    
    async def mark_ritual_done(self, guild_id: int, user_id: int):
        """Mark ritual as completed for today."""
        event_id = await self.get_active_event_id(guild_id)
        if not event_id:
            return
        
        now = now_ts()
        day_ymd = uk_day_ymd(now)
        key_day = (guild_id, event_id, user_id, day_ymd)
        
        self.live_ritual_done[key_day] = 1
    
    # ========================================================================
    # COMMANDS: Progression
    # ========================================================================
    
    @app_commands.command(name="rank", description="Show your rank ladder progress.")
    async def rank(self, interaction: discord.Interaction):
        """Show user's rank based on obedience."""
        if not interaction.guild_id:
            embed = create_embed("Use this in a server.", color="info", is_dm=False, is_system=False)
            return await interaction.response.send_message(embed=embed, ephemeral=True)
        
        gid = interaction.guild_id
        uid = interaction.user.id
        await self._ensure_user(gid, uid)
        
        # Read from v3_progression_core
        row = await self.bot.db.fetchone(
            "SELECT obedience_7d_cached FROM v3_progression_core WHERE guild_id=? AND user_id=?",
            (str(gid), str(uid))
        )
        
        if not row:
            obedience = 0
        else:
            obedience = int(row["obedience_7d_cached"] or 0)
        
        # Check if v3_ranks are configured
        ranks_check = await self.bot.db.fetchone(
            "SELECT COUNT(*) as cnt FROM v3_ranks WHERE guild_id=?", (str(gid),)
        )
        
        if not ranks_check or int(ranks_check["cnt"]) == 0:
            # Fallback to legacy RANKS
            cur_rank = self.rank_for_obedience(obedience)
            nxt_name, nxt_req = self.next_rank(obedience)
        else:
            # Use v3_ranks if available
            rank_row = await self.bot.db.fetchone(
                "SELECT rank_name FROM v3_ranks WHERE guild_id=? AND obedience_required <= ? ORDER BY obedience_required DESC LIMIT 1",
                (str(gid), obedience)
            )
            if rank_row:
                cur_rank = str(rank_row["rank_name"])
            else:
                cur_rank = "Unranked"
            
            nxt_row = await self.bot.db.fetchone(
                "SELECT rank_name, obedience_required FROM v3_ranks WHERE guild_id=? AND obedience_required > ? ORDER BY obedience_required ASC LIMIT 1",
                (str(gid), obedience)
            )
            if nxt_row:
                nxt_name = str(nxt_row["rank_name"])
                nxt_req = int(nxt_row["obedience_required"])
            else:
                nxt_name, nxt_req = None, None
        
        if nxt_name:
            need = max(0, nxt_req - obedience)
            desc = f"{interaction.user.mention}\nRank: **{cur_rank}**\nObedience: **{fmt(obedience)}**\nNext: **{nxt_name}** in **{fmt(need)}**.\n᲼᲼"
        else:
            desc = f"{interaction.user.mention}\nRank: **{cur_rank}**\nObedience: **{fmt(obedience)}**\nYou're capped.\n᲼᲼"
        
        await interaction.response.send_message(embed=isla_embed(desc, self.icon), ephemeral=True)
    
    @app_commands.command(name="weekly", description="Claim your weekly activity bonus (Coins).")
    async def weekly(self, interaction: discord.Interaction):
        """Claim weekly bonus based on 7-day WAS."""
        if not interaction.guild_id:
            embed = create_embed("Use this in a server.", color="info", is_dm=False, is_system=False)
            return await interaction.response.send_message(embed=embed, ephemeral=True)
        
        gid = interaction.guild_id
        uid = interaction.user.id
        await self._ensure_user(gid, uid)
        
        wk = week_key_uk()
        
        # Check if already claimed this week by checking v3_transactions
        last_claim = await self.bot.db.fetchone(
            "SELECT created_ts FROM v3_transactions WHERE guild_id=? AND user_id=? AND reason_code='weekly_claim' ORDER BY created_ts DESC LIMIT 1",
            (str(gid), str(uid))
        )
        
        if last_claim:
            last_claim_ts = int(last_claim["created_ts"])
            last_claim_week = week_key_uk_from_ts(last_claim_ts)
            if last_claim_week == wk:
                embed = create_embed("You already claimed this week.", color="info", is_dm=False, is_system=False)
                return await interaction.response.send_message(embed=embed, ephemeral=True)
        
        # Compute WAS from 7-day window using v3_recompute_was_7d (returns value and updates cache)
        date_keys = last_7_date_keys()
        was_7d = await self.bot.db.v3_recompute_was_7d(gid, uid, date_keys)
        
        bonus = WASCalculator.weekly_bonus_from_was(int(was_7d))
        
        # Apply coins and update weekly claim tracking (in transaction for atomicity)
        import time
        now_ts = int(time.time())
        async with self.bot.db.transaction():
            await self.bot.db.v3_apply_coins_delta(
                gid, uid, delta=bonus, counts_toward_lce=True,
                reason_code="weekly_claim", ref_type="system", commit=False
            )
            # Update weekly claim tracking
            await self.bot.db.execute(
                """INSERT INTO v3_progression_core(guild_id, user_id, weekly_claim_last_week_key, weekly_claim_last_amount, updated_at)
                   VALUES(?, ?, ?, ?, ?)
                   ON CONFLICT(guild_id, user_id) DO UPDATE SET
                     weekly_claim_last_week_key=?,
                     weekly_claim_last_amount=?,
                     updated_at=?""",
                (str(gid), str(uid), wk, bonus, now_ts, wk, bonus, now_ts),
                commit=False
            )
        
        desc = f"{interaction.user.mention}\nWeekly bonus: **{fmt(bonus)} Coins**\nWAS (7-day): **{fmt(int(was_7d))}**\n᲼᲼"
        await interaction.response.send_message(embed=isla_embed(desc, self.icon), ephemeral=True)
    
    # ========================================================================
    # COMMANDS: Voice Stats
    # ========================================================================
    
    @app_commands.command(name="voice", description="Show your voice activity today.")
    async def voice(self, interaction: discord.Interaction):
        """Show user's voice activity for today."""
        if not interaction.guild:
            embed = create_embed("Use this in a server.", color="info", is_dm=False, is_system=False)
            return await interaction.response.send_message(embed=embed, ephemeral=True)
        
        gid = interaction.guild.id
        uid = interaction.user.id
        dk = day_key_uk()
        
        # Check v3_activity_daily first
        row = await self.bot.db.fetchone(
            "SELECT voice_seconds FROM v3_activity_daily WHERE guild_id=? AND user_id=? AND date_key=?",
            (str(gid), str(uid), dk)
        )
        
        if row:
            sec = int(row["voice_seconds"] or 0)
        else:
            # Fallback to legacy table
            row = await self.bot.db.fetchone(
                "SELECT seconds FROM voice_daily WHERE guild_id=? AND user_id=? AND day_key=?",
                (gid, uid, dk)
            )
            sec = int(row["seconds"]) if row else 0
        
        mins = sec // 60
        
        await interaction.response.send_message(
            f"You've logged **{mins} minutes** in voice today.",
            ephemeral=True
        )
    
    # ========================================================================
    # COMMANDS: Moderation
    # ========================================================================
    
    @app_commands.command(name="purge", description="Delete a number of messages from this channel.")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def purge(self, interaction: discord.Interaction, amount: int):
        """Delete messages from channel."""
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
        """Set slowmode for channel."""
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
        """Toggle channel lockdown."""
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
        """Reload personality system."""
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


def week_key_uk_from_ts(ts: int) -> str:
    """Convert timestamp to week key in ISO format."""
    dt = datetime.fromtimestamp(ts, tz=UK_TZ)
    iso_year, iso_week, _ = dt.isocalendar()
    return f"{iso_year}-{iso_week:02d}"


async def setup(bot: commands.Bot):
    await bot.add_cog(Data(bot))
