"""
Event Activity Tracker

Unified system for tracking event activity (messages, voice, casino, tokens, rituals)
with in-memory counters and periodic flushing to database.
Supports both holiday weeks and seasonal eras.
"""

from __future__ import annotations
from collections import defaultdict
import json
import time

import discord
from discord.ext import commands, tasks

from core.utils import now_ts
from core.boss_damage import calculate_daily_damage
from utils.uk_time import uk_day_ymd

# Constants
MESSAGE_COOLDOWN_SECONDS = 5  # 5-second cooldown for boss damage
VC_REDUCE_AFTER_SECONDS = 3600  # 60 minutes
VC_REDUCED_MULT = 0.35
FLUSH_EVERY = 60  # Flush to DB every 60 seconds
BOSS_TICK_EVERY = 30  # Update boss HP every 30 seconds


class EventActivityTracker(commands.Cog):
    """
    Tracks event activity in memory and flushes to database periodically.
    Handles message counting, voice tracking, casino, tokens, and rituals.
    """
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        
        # In-memory counters: keyed by (gid, event_id, uid, day_ymd)
        self.live_msg = defaultdict(int)
        # Note: Voice tracking is handled by VoiceTracker cog independently
        self.live_casino_wager = defaultdict(int)
        self.live_casino_net = defaultdict(int)
        self.live_tokens_spent = defaultdict(int)
        self.live_ritual_done = defaultdict(int)  # set to 1 when completed
        
        # Per-user state: keyed by (gid, event_id, uid)
        self.last_msg_counted_ts = {}  # (gid, event_id, uid) -> ts
        # Note: VC refresh tracking is handled by VoiceTracker cog
        
        # Schedulers
        self.flush_loop.start()
        self.boss_tick_loop.start()
    
    def cog_unload(self):
        self.flush_loop.cancel()
        self.boss_tick_loop.cancel()
    
    async def get_active_event_id(self, guild_id: int) -> str | None:
        """
        Get the currently active event_id for a guild.
        Priority: holiday_week > season_era
        """
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
    
    async def handle_message(self, message: discord.Message):
        """
        Handle a message for event tracking.
        Applies 5-second cooldown, excludes spam channel, refreshes VC.
        """
        if message.author.bot or not message.guild:
            return
        
        gid = message.guild.id
        uid = message.author.id
        spam_channel_id = int(self.bot.cfg.get("channels", "spam", default=0) or 0)
        
        # Exclude spam channel
        if spam_channel_id and message.channel.id == spam_channel_id:
            return
        
        event_id = await self.get_active_event_id(gid)
        if not event_id:
            return
        
        now = now_ts()
        key_state = (gid, event_id, uid)
        
            # VC refresh is handled by VoiceTracker.refresh_voice_strength()
            # (called from MessageTracker after this method)
        
        # Check cooldown for message counting
        last = self.last_msg_counted_ts.get(key_state, 0)
        if now - last < MESSAGE_COOLDOWN_SECONDS:
            return  # VC refreshed but message doesn't count
        
        # Message counts for damage
        self.last_msg_counted_ts[key_state] = now
        
        day_ymd = uk_day_ymd(now)
        key_day = (gid, event_id, uid, day_ymd)
        self.live_msg[key_day] += 1
    
    # Note: Voice tracking is now handled by VoiceTracker cog
    # VoiceTracker credits time every 30 seconds and flushes to event_user_day
    # The old add_voice_time method is no longer needed
    
    async def add_casino_activity(
        self,
        guild_id: int,
        user_id: int,
        wager: int,
        net: int
    ):
        """Add casino wager and net to event tracking."""
        event_id = await self.get_active_event_id(guild_id)
        if not event_id:
            return
        
        now = now_ts()
        day_ymd = uk_day_ymd(now)
        key_day = (guild_id, event_id, user_id, day_ymd)
        
        self.live_casino_wager[key_day] += wager
        self.live_casino_net[key_day] += net
    
    async def add_tokens_spent(
        self,
        guild_id: int,
        user_id: int,
        amount: int,
        reason: str,
        meta: dict | None = None
    ):
        """Add token spending to event tracking and ledger."""
        event_id = await self.get_active_event_id(guild_id)
        if not event_id:
            return
        
        now = now_ts()
        day_ymd = uk_day_ymd(now)
        key_day = (guild_id, event_id, user_id, day_ymd)
        
        self.live_tokens_spent[key_day] += amount
        
        # Log to ledger
        await self.bot.db.execute(
            """
            INSERT INTO event_token_ledger(guild_id, event_id, user_id, ts, delta, reason, meta_json)
            VALUES(?,?,?,?,?,?,?)
            """,
            (guild_id, event_id, user_id, now, -amount, reason, json.dumps(meta or {}))
        )
    
    async def add_token_earned(
        self,
        guild_id: int,
        user_id: int,
        amount: int,
        reason: str,
        meta: dict | None = None
    ):
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
    
    async def mark_ritual_done(
        self,
        guild_id: int,
        user_id: int
    ):
        """Mark ritual as completed for today."""
        event_id = await self.get_active_event_id(guild_id)
        if not event_id:
            return
        
        now = now_ts()
        day_ymd = uk_day_ymd(now)
        key_day = (guild_id, event_id, user_id, day_ymd)
        
        self.live_ritual_done[key_day] = 1
    
    def _compute_dp(
        self,
        msg_count: int,
        vc_minutes: int,
        vc_reduced_minutes: int,
        ritual_done: int,
        tokens_spent: int,
        casino_wager: int,
        casino_net: int
    ) -> float:
        """Compute damage points from daily stats."""
        # Voice effective minutes (reduced minutes count at 35% multiplier)
        vc_eff = vc_minutes + (vc_reduced_minutes * VC_REDUCED_MULT)
        
        # Use the unified damage calculation
        dp, _ = calculate_daily_damage(
            tokens_spent=float(tokens_spent),
            ritual_completed=ritual_done,
            casino_net=float(max(casino_net, 0)),  # Clamp to 0
            casino_wager=float(casino_wager),
            messages=float(msg_count),
            voice_effective_minutes=float(vc_eff)
        )
        return dp
    
    @tasks.loop(seconds=FLUSH_EVERY)
    async def flush_loop(self):
        """Flush in-memory counters to database every 60 seconds."""
        await self.bot.wait_until_ready()
        await self._flush_counters()
    
    @flush_loop.before_loop
    async def before_flush_loop(self):
        await self.bot.wait_until_ready()
    
    async def _flush_counters(self):
        """Flush live counters to database."""
        if not (self.live_msg or self.live_casino_wager or self.live_casino_net or 
                self.live_tokens_spent or self.live_ritual_done):
            # Flush voice counters even if nothing else to flush
            voice_tracker = self.bot.get_cog("VoiceTracker")
            if voice_tracker:
                try:
                    await voice_tracker.flush_voice_counters()
                except Exception:
                    pass
            return
        
        # Union all keys (voice tracking handled separately by VoiceTracker)
        keys = (
            set(self.live_msg.keys()) |
            set(self.live_casino_wager.keys()) |
            set(self.live_casino_net.keys()) |
            set(self.live_tokens_spent.keys()) |
            set(self.live_ritual_done.keys())
        )
        
        if not keys:
            return
        
        now = now_ts()
        rows = []
        
        for (gid, eid, uid, day) in keys:
            msg = self.live_msg.pop((gid, eid, uid, day), 0)
            wager = self.live_casino_wager.pop((gid, eid, uid, day), 0)
            net = self.live_casino_net.pop((gid, eid, uid, day), 0)
            tsp = self.live_tokens_spent.pop((gid, eid, uid, day), 0)
            ritual = self.live_ritual_done.pop((gid, eid, uid, day), 0)
            
            # Voice minutes are 0 here - VoiceTracker handles those separately
            vc_min = 0
            vc_rmin = 0
            
            if msg == 0 and wager == 0 and net == 0 and tsp == 0 and ritual == 0:
                continue
            
            rows.append((gid, eid, uid, day, msg, vc_min, vc_rmin, ritual, tsp, wager, net, now))
        
        if not rows:
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
        
        # Flush voice counters from VoiceTracker (handles its own flushing)
        voice_tracker = self.bot.get_cog("VoiceTracker")
        if voice_tracker:
            try:
                await voice_tracker.flush_voice_counters()
            except Exception:
                pass
        
        # Persist user state (message cooldown only - VC state handled by VoiceTracker)
        await self._persist_user_states()
    
    async def _persist_user_states(self):
        """Persist in-memory user state to database (message cooldown only)."""
        if not self.last_msg_counted_ts:
            return
        
        # Persist message cooldown timestamps
        # VC refresh state is handled by VoiceTracker cog
        for (gid, event_id, uid), msg_ts in self.last_msg_counted_ts.items():
            await self.bot.db.execute(
                """
                INSERT INTO event_user_state(
                  guild_id, event_id, user_id,
                  last_msg_counted_ts
                )
                VALUES(?,?,?,?)
                ON CONFLICT(guild_id,event_id,user_id) DO UPDATE SET
                  last_msg_counted_ts = excluded.last_msg_counted_ts
                """,
                (gid, event_id, uid, msg_ts)
            )
    
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
    
    async def _boss_tick(self, guild_id: int):
        """Update boss HP for all active events in a guild."""
        # Get all active events with bosses
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
            
            # Get changed rows since last tick
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
                # Still update last_tick_ts even if nothing changed
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
                
                # Update cached DP
                await self.bot.db.execute(
                    """
                    UPDATE event_user_day
                    SET dp_cached=?
                    WHERE guild_id=? AND event_id=? AND user_id=? AND day_ymd=?
                    """,
                    (new_dp, guild_id, event_id, int(r["user_id"]), str(r["day_ymd"]))
                )
            
            # Update boss HP
            hp_new = max(0, hp_cur - int(total_delta))
            
            await self.bot.db.execute(
                "UPDATE event_boss SET hp_current=?, last_tick_ts=? WHERE guild_id=? AND event_id=?",
                (hp_new, now, guild_id, event_id)
            )
            
            # Log tick
            await self.bot.db.execute(
                "INSERT INTO event_boss_tick(guild_id,event_id,ts,damage_total,meta_json) VALUES(?,?,?,?,?)",
                (guild_id, event_id, now, float(total_delta), "{}")
            )
            
            # Check milestones (80/60/40/20/0 percent thresholds)
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
        # This will be integrated with the events cog's milestone system
        pass


async def setup(bot: commands.Bot):
    await bot.add_cog(EventActivityTracker(bot))

