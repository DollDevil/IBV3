from __future__ import annotations

import json
import random
import math
import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from core.utility import now_ts, fmt
from core.personality import sanitize_isla_text
from core.events import (
    SEASONAL_CONFIGS, get_seasonal_config,
    SEASONAL_TONE_POOLS, get_seasonal_tone,
    HOLIDAY_CONFIGS, get_holiday_config, get_all_holidays, parse_holiday_date,
    calculate_daily_damage, calculate_global_scale, calculate_boss_hp_from_users,
    calculate_expected_daily_damage, calculate_voice_effective_minutes,
    g_log_scale, K_TS, K_CN, K_CW, K_M, K_V
)
from utils.uk_time import uk_day_ymd, uk_hm
from utils.uk_parse import parse_when_to_ts, human_eta
from utils.isla_style import isla_embed as isla_embed_util
from utils.economy import ensure_wallet, get_wallet, add_coins
from utils.embed_utils import create_embed

UK_TZ = ZoneInfo("Europe/London")

# ---------------------------------------------------------
# Thumbnail style keys (placeholders; you fill URLs later)
# ---------------------------------------------------------
THUMB_KEYS = {
    "THUMB_NEUTRAL",
    "THUMB_SMIRK_DOMINANT",
    "THUMB_INTRIGUED",
    "THUMB_DISPLEASED",
    "THUMB_LAUGHING",
    "BOSS_START__DOMINANT",
    "BOSS_PHASE2__INTRIGUED",
    "BOSS_PHASE3__DISPLEASED",
    "BOSS_FINAL__INTENSE",
    "BOSS_KILL__LAUGHING",
    "QUESTBOARD_DAILY__NEUTRAL",
    "QUESTBOARD_WEEKLY__SMIRK",
    "QUESTBOARD_ELITE__INTRIGUED",
    "SEASON_LAUNCH__DOMINANT",
    "SEASON_MID__NEUTRAL",
    "SEASON_DROP__INTRIGUED",
    "SEASON_FINALE__INTENSE",
    "SEASON_AWARDS__SMIRK",
    "HOLIDAY_LAUNCH__THEMED_DOMINANT",
    "HOLIDAY_MID__THEMED_INTRIGUED",
    "HOLIDAY_BOSS__THEMED_INTENSE",
    "HOLIDAY_FINALE__THEMED_LAUGHING",
    "DROP_REVEAL__INTRIGUED",
    "DROP_LAST_CALL__DISPLEASED",
    "DROP_SOLD_OUT__LAUGHING",
}


def uk_now() -> datetime:
    return datetime.now(tz=UK_TZ)


def day_key_uk(dt: datetime | None = None) -> str:
    dt = dt or uk_now()
    return f"{dt.year:04d}-{dt.month:02d}-{dt.day:02d}"


def clamp(n: int, a: int, b: int) -> int:
    return max(a, min(b, n))


# ---------------------------------------------------------
# Event config defaults
# ---------------------------------------------------------
DEFAULT_CHANNEL_KEYS = ["orders", "spam", "casino", "spotlight"]

DEFAULT_THUMBS = {k: "" for k in THUMB_KEYS}  # user will fill URLs later

DEFAULT_BOSS_CAPS = {
    # score caps per user
    "msg_per_hour": 30,
    "vc_minutes_per_day": 60,
    "wager_coins_per_day": 20000,   # wager counted toward boss ES up to this amount/day
}

DEFAULT_SCORE_WEIGHTS = {
    "msg": 1,            # 1 ES per msg
    "vc_min": 2,         # 2 ES per VC minute
    "wager_per": 200,    # 1 ES per 200 wagered coins
    "order_complete": 25,
    "ritual_complete": 120,
}


def hp_bar(current: int, maximum: int, width: int = 14) -> str:
    maximum = max(1, maximum)
    filled = int(round(width * (current / maximum)))
    filled = clamp(filled, 0, width)
    return "█" * filled + "░" * (width - filled)

# DP (Damage Points) calculation helpers (from event_group/event_scheduler)
VC_REDUCED_MULT = 0.35
k_TS = 25.0
k_CN = 10_000.0
k_CW = 20_000.0
k_M = 20.0
k_V = 30.0

def g_dp(x: float, k: float) -> float:
    """Log scaling function for DP calculation."""
    return math.log(1.0 + (x / k))

def compute_dp(msg_count: int, vc_minutes: int, vc_reduced_minutes: int,
               ritual_done: int, tokens_spent: int, casino_wager: int, casino_net: int) -> float:
    """Compute Damage Points using logarithmic scaling."""
    V_eff = float(vc_minutes) + (float(vc_reduced_minutes) * VC_REDUCED_MULT)
    CN_pos = max(int(casino_net), 0)
    return (
        260.0 * g_dp(tokens_spent, k_TS) +
        160.0 * (1 if ritual_done else 0) +
        110.0 * g_dp(CN_pos, k_CN) +
        95.0 * g_dp(casino_wager, k_CW) +
        80.0 * g_dp(msg_count, k_M) +
        80.0 * g_dp(V_eff, k_V)
    )

def fmt_int(n: int | float) -> str:
    """Format integer with commas."""
    try:
        return f"{int(n):,}"
    except Exception:
        return "0"


# ---------------------------------------------------------
# EventSystem Cog
# ---------------------------------------------------------
class EventSystem(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.icon = "https://i.imgur.com/5nsuuCV.png"  # default author icon
        
        # Initialize command groups
        self.event = app_commands.Group(name="event", description="Event commands")
        self.calendar = app_commands.Group(name="calendar", description="Server calendar events")
        self._register_command_groups()
        
        # Start task loops
        self.tick_events.start()
        self.tick_boss.start()
        self.tick_quest_refresh.start()
        self.tick_seasonal_finale.start()
        self.tick_holiday_weeks.start()
        self.flush_loop.start()
        self.boss_dp_loop.start()
        
        # Scheduler config
        self.orders_channel_id = int(bot.cfg.get("channels", "orders", default="0") or 0)
        self.spotlight_channel_id = int(bot.cfg.get("channels", "spotlight", default="0") or 0)
    
    async def get_active_event_ids(self, guild_id: int) -> list[str]:
        """
        Get list of active event IDs for a guild.
        Returns both holiday_week and season_era events if active.
        If you want "holiday overlaps season," keep both active simultaneously.
        """
        rows = await self.bot.db.fetchall(
            "SELECT event_id FROM events WHERE guild_id=? AND is_active=1",
            (guild_id,)
        )
        return [str(r["event_id"]) for r in rows]

    def cog_unload(self):
        self.tick_events.cancel()
        self.tick_boss.cancel()
        self.tick_quest_refresh.cancel()
        self.tick_seasonal_finale.cancel()
        self.tick_holiday_weeks.cancel()
        self.flush_loop.cancel()
        self.boss_dp_loop.cancel()
    
    def _register_command_groups(self):
        """Register /event and /calendar group commands."""
        # /event group commands
        self.event.command(name="info", description="View current event info.")(self._cmd_event_info)
        self.event.command(name="boss", description="View the current event boss.")(self._cmd_event_boss)
        self.event.command(name="progress", description="View boss progress and your contribution today.")(self._cmd_event_progress)
        self.event.command(name="leaderboard", description="View event leaderboards.")(self._cmd_event_leaderboard)
        self.event.command(name="ritual", description="View today's ritual info.")(self._cmd_event_ritual)
        self.event.command(name="shop", description="View the event shop info.")(self._cmd_event_shop)
        
        # /calendar group commands
        self.calendar.command(name="create", description="Interactive event wizard.")(self._cmd_calendar_create)
        self.calendar.command(name="list", description="Upcoming events.")(self._cmd_calendar_list)
        self.calendar.command(name="join", description="Join event and get role.")(self._cmd_calendar_join)
        self.calendar.command(name="leave", description="Leave an event.")(self._cmd_calendar_leave)

    # -------------------------
    # Config getters
    # -------------------------
    def ch_id(self, key: str) -> int:
        return int(self.bot.cfg.get("channels", key, default=0) or 0)

    def get_channel(self, guild: discord.Guild, key: str) -> discord.TextChannel | None:
        cid = self.ch_id(key)
        ch = guild.get_channel(cid) if cid else None
        return ch if isinstance(ch, discord.TextChannel) else None

    # -------------------------
    # DB helpers
    # -------------------------
    async def _next_event_id(self, gid: int) -> int:
        row = await self.bot.db.fetchone("SELECT value FROM event_system_state WHERE guild_id=? AND key='event_seq'", (gid,))
        if not row:
            await self.bot.db.execute("INSERT INTO event_system_state(guild_id,key,value) VALUES(?,?,?)", (gid, "event_seq", "2000"))
            return 2000
        n = int(row["value"]) + 1
        await self.bot.db.execute("UPDATE event_system_state SET value=? WHERE guild_id=? AND key='event_seq'", (str(n), gid))
        return n

    async def _next_quest_id(self, gid: int) -> int:
        row = await self.bot.db.fetchone("SELECT value FROM event_system_state WHERE guild_id=? AND key='quest_seq'", (gid,))
        if not row:
            await self.bot.db.execute("INSERT INTO event_system_state(guild_id,key,value) VALUES(?,?,?)", (gid, "quest_seq", "3000"))
            return 3000
        n = int(row["value"]) + 1
        await self.bot.db.execute("UPDATE event_system_state SET value=? WHERE guild_id=? AND key='quest_seq'", (str(n), gid))
        return n

    async def _state_get(self, gid: int, eid: int, key: str, default: str = "") -> str:
        row = await self.bot.db.fetchone(
            "SELECT value FROM event_state WHERE guild_id=? AND event_id=? AND key=?",
            (gid, eid, key)
        )
        return str(row["value"]) if row else default

    async def _state_set(self, gid: int, eid: int, key: str, value: str):
        await self.bot.db.execute(
            """
            INSERT INTO event_state(guild_id,event_id,key,value,updated_ts)
            VALUES(?,?,?,?,?)
            ON CONFLICT(guild_id,event_id,key)
            DO UPDATE SET value=excluded.value, updated_ts=excluded.updated_ts
            """,
            (gid, eid, key, str(value), now_ts())
        )

    async def _active_wrapper(self, gid: int) -> dict | None:
        # wrapper = season or holiday_week, prefer holiday if active
        row = await self.bot.db.fetchone(
            "SELECT * FROM events WHERE guild_id=? AND status='active' AND type IN ('holiday_week','season') "
            "ORDER BY CASE WHEN type='holiday_week' THEN 0 ELSE 1 END, start_ts DESC LIMIT 1",
            (gid,)
        )
        return dict(row) if row else None

    async def _active_boss(self, gid: int) -> dict | None:
        row = await self.bot.db.fetchone(
            "SELECT * FROM events WHERE guild_id=? AND status='active' AND type='boss' ORDER BY start_ts DESC LIMIT 1",
            (gid,)
        )
        return dict(row) if row else None

    # -------------------------
    # Thumbnail selection
    # -------------------------
    def _thumb(self, config: dict, key: str) -> str:
        thumbs = (config or {}).get("thumbs", {}) if isinstance(config, dict) else {}
        url = thumbs.get(key) or thumbs.get("THUMB_NEUTRAL") or ""
        return url

    def _embed(self, title: str | None, desc: str, thumb_url: str = "", color: discord.Color | None = None) -> discord.Embed:
        e = discord.Embed(title=title, description=sanitize_isla_text(desc), color=color or discord.Color.dark_grey())
        e.set_author(name="Isla", icon_url=self.icon)
        if thumb_url:
            e.set_thumbnail(url=thumb_url)
        return e

    # -------------------------
    # Channel enforcement
    # -------------------------
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # Allow read-only commands anywhere (they're ephemeral)
        allow_anywhere = {"event", "season", "tokens", "quests", "quest_progress", "boss_leaderboard", "event_progress"}
        if interaction.command and interaction.command.name in allow_anywhere:
            return True

        # Everything else should be used in #spam (claim/reroll/etc.)
        spam_id = self.ch_id("spam")
        if spam_id and interaction.channel_id != spam_id:
            try:
                embed = create_embed(f"Use <#{spam_id}> for that.", color="info", is_dm=False, is_system=False)
                await interaction.response.send_message(embed=embed, ephemeral=True)
            except Exception:
                pass
            return False
        return True

    # -------------------------
    # Quest helpers
    # -------------------------
    async def _get_or_create_quest_run(self, gid: int, quest_id: int, user_id: int) -> dict:
        run = await self.bot.db.fetchone(
            "SELECT * FROM quest_runs WHERE guild_id=? AND quest_id=? AND user_id=?",
            (gid, quest_id, user_id)
        )
        if run:
            return dict(run)

        await self.bot.db.execute(
            "INSERT INTO quest_runs(guild_id,quest_id,user_id,status,progress_json,started_ts) VALUES(?,?,?,?,?,?)",
            (gid, quest_id, user_id, "active", "{}", now_ts())
        )
        run = await self.bot.db.fetchone(
            "SELECT * FROM quest_runs WHERE guild_id=? AND quest_id=? AND user_id=?",
            (gid, quest_id, user_id)
        )
        return dict(run)

    async def _quest_check_completion(self, gid: int, user_id: int, requirement: dict, start_ts: int, end_ts: int) -> tuple[bool, str]:
        rtype = requirement.get("type")

        if rtype == "messages":
            # Try to use channel history for message counting
            channel_id = int(requirement.get("channel_id", 0) or 0)
            if channel_id:
                channel = self.bot.get_channel(channel_id)
                if isinstance(channel, discord.TextChannel):
                    try:
                        from datetime import datetime
                        after_dt = datetime.fromtimestamp(start_ts, tz=UK_TZ)
                        got = 0
                        async for msg in channel.history(limit=500, after=after_dt):
                            if msg.author.id == user_id and not msg.author.bot:
                                msg_ts = int(msg.created_at.timestamp())
                                if start_ts <= msg_ts <= end_ts:
                                    got += 1
                        count = int(requirement.get("count", 1))
                        return (got >= count, f"{got}/{count} messages")
                    except Exception:
                        pass
            return False, "Message tracking not available."

        if rtype == "vc_minutes":
            vt = self.bot.get_cog("Data")
            if not vt:
                return False, "Voice tracking not available."
            need = int(requirement.get("minutes", 5))
            try:
                got = await vt.minutes_in_range(gid, user_id, start_ts, end_ts)
            except Exception:
                # fallback: approximate from voice_events
                rows = await self.bot.db.fetchall(
                    """
                    SELECT SUM(seconds) as total_seconds FROM voice_events
                    WHERE guild_id=? AND user_id=? AND end_ts >= ? AND start_ts <= ?
                    """,
                    (gid, user_id, start_ts, end_ts)
                )
                total_seconds = sum(int(r["total_seconds"] or 0) for r in rows)
                got = total_seconds // 60
            return (got >= need, f"{got}/{need} VC minutes")

        if rtype == "casino_rounds":
            cc = self.bot.get_cog("CasinoCore")
            if not cc:
                return False, "Casino tracking not available."
            need = int(requirement.get("count", 1))
            try:
                stats = await cc.get_window_summary(gid, start_ts)
                # Count rounds from msg_memory directly
                ctx = f"casino_rounds:{gid}"
                row = await self.bot.db.fetchone("SELECT hash FROM msg_memory WHERE guild_id=? AND context=?", (gid, ctx))
                got = 0
                if row:
                    try:
                        data = json.loads(row["hash"]) or []
                        for ev in data:
                            ts = int(ev.get("ts", 0))
                            if start_ts <= ts <= end_ts:
                                ev_uid = int(ev.get("uid", 0))
                                wager = int(ev.get("wager", 0))
                                if ev_uid == user_id and wager > 0:
                                    got += 1
                    except Exception:
                        pass
                return (got >= need, f"{got}/{need} rounds")
            except Exception:
                return False, "Casino tracking error."

        if rtype == "casino_wager":
            cc = self.bot.get_cog("CasinoCore")
            if not cc:
                return False, "Casino tracking not available."
            need = int(requirement.get("coins", 1))
            try:
                ctx = f"casino_rounds:{gid}"
                row = await self.bot.db.fetchone("SELECT hash FROM msg_memory WHERE guild_id=? AND context=?", (gid, ctx))
                got = 0
                if row:
                    try:
                        data = json.loads(row["hash"]) or []
                        for ev in data:
                            ts = int(ev.get("ts", 0))
                            if start_ts <= ts <= end_ts:
                                ev_uid = int(ev.get("uid", 0))
                                if ev_uid == user_id:
                                    wager = int(ev.get("wager", 0))
                                    got += wager
                    except Exception:
                        pass
                return (got >= need, f"{got}/{need} wagered Coins")
            except Exception:
                return False, "Casino tracking error."

        if rtype == "manual":
            return False, "Manual proof required."

        return False, "Unknown requirement."

    async def _add_tokens(self, gid: int, user_id: int, scope_event_id: int, tokens: int):
        if tokens <= 0:
            return
        await self.bot.db.execute(
            """
            INSERT INTO token_balances(guild_id,user_id,scope_event_id,tokens,updated_ts)
            VALUES(?,?,?,?,?)
            ON CONFLICT(guild_id,user_id,scope_event_id)
            DO UPDATE SET tokens=tokens+excluded.tokens, updated_ts=excluded.updated_ts
            """,
            (gid, user_id, scope_event_id, int(tokens), now_ts())
        )

    async def _add_profile_rewards(self, gid: int, user_id: int, coins: int, obedience: int):
        # assumes you store coins/obedience in users table
        if coins:
            await self.bot.db.execute("UPDATE users SET coins=coins+? WHERE guild_id=? AND user_id=?", (int(coins), gid, user_id))
        if obedience:
            await self.bot.db.execute("UPDATE users SET obedience=obedience+? WHERE guild_id=? AND user_id=?", (int(obedience), gid, user_id))

    async def _token_scope_for_wrapper(self, gid: int) -> int:
        wrapper = await self._active_wrapper(gid)
        return int(wrapper["event_id"]) if wrapper else 0

    async def _get_user_tokens(self, gid: int, user_id: int, event_id: int) -> int:
        """Get user's token balance for an event."""
        row = await self.bot.db.fetchone(
            "SELECT tokens FROM token_balances WHERE guild_id=? AND user_id=? AND scope_event_id=?",
            (gid, user_id, event_id)
        )
        return int(row["tokens"]) if row else 0

    # =========================================================
    #  A) PUBLIC COMMANDS
    # =========================================================
    # Note: /event group commands are now in section D) below
    # @app_commands.command(name="event", description="View the current active season/holiday, boss fight, and questboard.")
    async def _event_legacy(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild_id
        if not gid:
            embed = create_embed("Use this in a server.", color="info", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)

        wrapper = await self._active_wrapper(gid)
        boss = await self._active_boss(gid)

        lines = []
        if wrapper:
            cfg = json.loads(wrapper["config_json"])
            end = int(wrapper["end_ts"])
            left_h = max(0, (end - now_ts()) // 3600)
            lines.append(f"Wrapper: **{wrapper['name']}** ({wrapper['type']}) • ends in **{left_h}h**")
        else:
            lines.append("Wrapper: **None**")

        if boss:
            cfg = json.loads(boss["config_json"])
            hp = int(await self._state_get(gid, boss["event_id"], "hp_current", "0"))
            hpmax = int(await self._state_get(gid, boss["event_id"], "hp_max", "1"))
            pct = int(round((hp / max(1, hpmax)) * 100))
            lines.append(f"Boss: **{boss['name']}** • HP **{pct}%** `{hp_bar(hp, hpmax)}`")
        else:
            lines.append("Boss: **None**")

        e = self._embed(
            title=None,
            desc="\n".join(lines) + "\n᲼᲼",
            thumb_url=self.icon
        )
        await interaction.followup.send(embed=e, ephemeral=True)

    @app_commands.command(name="boss_leaderboard", description="Top contributors for the current boss fight.")
    async def boss_leaderboard(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild_id
        if not gid:
            embed = create_embed("Use this in a server.", color="info", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)

        boss = await self._active_boss(gid)
        if not boss:
            embed = create_embed("No active boss fight.", color="info", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)

        eid = int(boss["event_id"])
        rows = await self.bot.db.fetchall(
            "SELECT user_id, score_total FROM event_contrib WHERE guild_id=? AND event_id=? ORDER BY score_total DESC LIMIT 10",
            (gid, eid)
        )
        if not rows:
            embed = create_embed("No contributions yet.", color="info", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)

        desc = []
        for i, r in enumerate(rows, start=1):
            desc.append(f"**{i}.** <@{int(r['user_id'])}> — **{fmt(int(r['score_total']))} ES**")
        e = self._embed(None, "\n".join(desc) + "\n᲼᲼", thumb_url=self.icon)
        await interaction.followup.send(embed=e, ephemeral=True)

    @app_commands.command(name="event_progress", description="Your personal progress in the active boss/event.")
    async def event_progress(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild_id
        if not gid:
            embed = create_embed("Use this in a server.", color="info", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)

        boss = await self._active_boss(gid)
        if not boss:
            embed = create_embed("No active boss fight.", color="info", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)

        eid = int(boss["event_id"])
        row = await self.bot.db.fetchone(
            "SELECT score_total, breakdown_json FROM event_contrib WHERE guild_id=? AND event_id=? AND user_id=?",
            (gid, eid, interaction.user.id)
        )
        if not row:
            embed = create_embed("No contribution recorded yet.", color="info", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)

        breakdown = json.loads(row["breakdown_json"] or "{}")
        desc = (
            f"{interaction.user.mention}\n"
            f"Score: **{fmt(int(row['score_total']))} ES**\n"
            f"Messages: **{fmt(int(breakdown.get('msg',0)))}**\n"
            f"VC minutes: **{fmt(int(breakdown.get('vc',0)))}**\n"
            f"Wager ES: **{fmt(int(breakdown.get('wager_es',0)))}**\n"
            f"Orders: **{fmt(int(breakdown.get('orders',0)))}**\n"
            f"Rituals: **{fmt(int(breakdown.get('rituals',0)))}**\n"
            "᲼᲼"
        )
        e = self._embed(None, desc, thumb_url=self.icon)
        await interaction.followup.send(embed=e, ephemeral=True)

    @app_commands.command(name="event_claim", description="Claim unlocked event milestone rewards.")
    async def event_claim(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild_id
        if not gid:
            embed = create_embed("Use this in a server.", color="info", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)

        boss = await self._active_boss(gid)
        if not boss:
            embed = create_embed("No active boss fight.", color="info", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)

        eid = int(boss["event_id"])
        cfg = json.loads(boss["config_json"])
        unlocked = json.loads(await self._state_get(gid, eid, "milestones_unlocked", "{}") or "{}")
        milestones = cfg.get("milestones", [])

        claimable = []
        for m in milestones:
            key = str(m.get("key"))
            if key in unlocked:
                claimable.append(m)

        if not claimable:
            embed = create_embed("Nothing unlocked yet.", color="info", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)

        claimed_any = False
        total_tokens = 0

        # token scope: wrapper (season/holiday) if configured else 0 (no tokens)
        scope_id = int(cfg.get("wrapper_scope_event_id") or 0)
        if scope_id <= 0:
            # if no wrapper, still allow token bank under boss itself
            scope_id = eid

        for m in claimable:
            ckey = str(m.get("key"))
            # already claimed?
            row = await self.bot.db.fetchone(
                "SELECT 1 FROM event_claims WHERE guild_id=? AND event_id=? AND user_id=? AND claim_key=?",
                (gid, eid, interaction.user.id, ckey)
            )
            if row:
                continue

            reward = m.get("reward", {})
            tokens = int(reward.get("tokens", 0))
            if tokens > 0:
                total_tokens += tokens

            await self.bot.db.execute(
                "INSERT INTO event_claims(guild_id,event_id,user_id,claim_key,claimed_ts) VALUES(?,?,?,?,?)",
                (gid, eid, interaction.user.id, ckey, now_ts())
            )
            claimed_any = True

        if not claimed_any:
            embed = create_embed("You've already claimed everything you can.", color="info", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)

        if total_tokens > 0:
            await self.bot.db.execute(
                """
                INSERT INTO token_balances(guild_id,user_id,scope_event_id,tokens,updated_ts)
                VALUES(?,?,?,?,?)
                ON CONFLICT(guild_id,user_id,scope_event_id)
                DO UPDATE SET tokens=tokens+excluded.tokens, updated_ts=excluded.updated_ts
                """,
                (gid, interaction.user.id, scope_id, total_tokens, now_ts())
            )
            # Forward token earning to EventActivityTracker (for ledger audit)
            tracker = self.bot.get_cog("Data")
            if tracker:
                try:
                    # Find the active event_id (could be wrapper or boss)
                    event_row = await self.bot.db.fetchone(
                        "SELECT event_id FROM events WHERE guild_id=? AND (event_id=? OR event_id LIKE ?) AND is_active=1 LIMIT 1",
                        (gid, scope_id, f"{scope_id}%")
                    )
                    if event_row:
                        event_id_str = str(event_row["event_id"])
                        await tracker.add_token_earned(gid, interaction.user.id, total_tokens, "milestone_claim", {"event_id": eid})
                except Exception:
                    pass

        desc = (
            f"{interaction.user.mention}\n"
            f"Claimed: **{fmt(total_tokens)} Tokens**\n"
            "᲼᲼"
        )
        await interaction.followup.send(embed=self._embed(None, desc, thumb_url=self.icon), ephemeral=True)

    @app_commands.command(name="tokens", description="View your current event token balance.")
    async def tokens(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild_id
        if not gid:
            embed = create_embed("Use this in a server.", color="info", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)

        wrapper = await self._active_wrapper(gid)
        if not wrapper:
            embed = create_embed("No active season or holiday tokens right now.", color="info", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)

        scope_id = int(wrapper["event_id"])
        bal = await self._get_user_tokens(gid, interaction.user.id, scope_id)

        cfg = json.loads(wrapper["config_json"])
        token_name = str(cfg.get("token_name") or "Tokens")

        desc = f"{interaction.user.mention}\n{wrapper['name']}\nBalance: **{fmt(bal)} {token_name}**\n᲼᲼"
        e = self._embed(None, desc, thumb_url=self._thumb(cfg, "THUMB_NEUTRAL"))
        await interaction.followup.send(embed=e, ephemeral=True)

    @app_commands.command(name="season", description="View the current season/holiday wrapper.")
    async def season(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild_id
        if not gid:
            embed = create_embed("Use this in a server.", color="info", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)

        wrapper = await self._active_wrapper(gid)
        if not wrapper:
            embed = create_embed("No active season/holiday right now.", color="info", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)

        cfg = json.loads(wrapper["config_json"])
        end = int(wrapper["end_ts"])
        left_days = max(0, (end - now_ts()) // 86400)
        token_name = str(cfg.get("token_name") or "Tokens")

        desc = (
            f"Wrapper: **{wrapper['name']}** ({wrapper['type']})\n"
            f"Ends in: **{left_days} days**\n"
            f"Token: **{token_name}**\n"
            "᲼᲼"
        )
        thumb_key = "HOLIDAY_LAUNCH__THEMED_DOMINANT" if wrapper["type"] == "holiday_week" else "SEASON_MID__NEUTRAL"
        e = self._embed(None, desc, thumb_url=self._thumb(cfg, thumb_key))
        await interaction.followup.send(embed=e, ephemeral=True)

    @app_commands.command(name="event_boss", description="View the current event boss status (standalone).")
    async def event_boss_standalone(self, interaction: discord.Interaction):
        """Standalone /event_boss command (for backward compatibility)."""
        await interaction.response.defer(ephemeral=True)
        if not interaction.guild_id:
            embed = create_embed("Server only.", color="warning", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)
        
        gid = interaction.guild_id
        event_id = await self._pick_active_event_for_dp(gid)
        if not event_id:
            return await interaction.followup.send(
                embed=self._embed("No active event boss right now.\n᲼᲼", "Boss", thumb_url=self.icon),
                ephemeral=True
            )
        
        meta = await self.bot.db.fetchone(
            "SELECT name, event_type, token_name FROM events WHERE guild_id=? AND event_id=?",
            (gid, event_id)
        )
        boss = await self.bot.db.fetchone(
            "SELECT boss_name, hp_current, hp_max FROM event_boss WHERE guild_id=? AND event_id=?",
            (gid, event_id)
        )
        if not boss:
            return await interaction.followup.send(
                embed=self._embed("No boss is attached to the current event.\n᲼᲼", "Boss", thumb_url=self.icon),
                ephemeral=True
            )
        
        boss_name = str(boss["boss_name"])
        hp_cur = int(boss["hp_current"])
        hp_max = max(1, int(boss["hp_max"]))
        hp_pct = max(0, min(100, int((hp_cur / hp_max) * 100)))
        
        today = uk_day_ymd(now_ts())
        top_today = await self.bot.db.fetchall(
            "SELECT user_id, dp_cached AS pts FROM event_user_day WHERE guild_id=? AND event_id=? AND day_ymd=? ORDER BY pts DESC LIMIT 3",
            (gid, event_id, today)
        )
        top_overall = await self.bot.db.fetchall(
            "SELECT user_id, SUM(dp_cached) AS pts FROM event_user_day WHERE guild_id=? AND event_id=? GROUP BY user_id ORDER BY pts DESC LIMIT 10",
            (gid, event_id)
        )
        
        recent_damage = None
        try:
            cutoff = now_ts() - (6 * 3600)
            r = await self.bot.db.fetchone(
                "SELECT COALESCE(SUM(damage_total), 0) AS dmg FROM event_boss_tick WHERE guild_id=? AND event_id=? AND ts >= ?",
                (gid, event_id, cutoff)
            )
            recent_damage = int(float(r["dmg"] or 0))
        except Exception:
            recent_damage = None
        
        def line_for(uid: int, pts: float) -> str:
            m = interaction.guild.get_member(int(uid))
            name = m.display_name if m else f"User {uid}"
            return f"{name} — {fmt_int(pts)}"
        
        today_lines = [f"{i}) {line_for(int(r['user_id']), float(r['pts'] or 0))}" for i, r in enumerate(top_today, start=1)]
        overall_lines = [f"{i}) {line_for(int(r['user_id']), float(r['pts'] or 0))}" for i, r in enumerate(top_overall, start=1)]
        if not today_lines:
            today_lines = ["No data yet."]
        if not overall_lines:
            overall_lines = ["No data yet."]
        
        event_name = str(meta["name"]) if meta else "Event"
        event_type = str(meta["event_type"]) if meta else "event"
        token_name = str(meta["token_name"]) if meta else "Tokens"
        
        desc = f"**{boss_name}**\nHP: **{fmt_int(hp_cur)} / {fmt_int(hp_max)}** (**{hp_pct}%**)\n"
        if recent_damage is not None:
            desc += f"Recent damage (6h): **{fmt_int(recent_damage)}**\n"
        desc += "᲼᲼"
        
        e = self._embed(desc, f"{event_name} Boss", thumb_url=self.icon)
        e.add_field(name="Top Damage Today", value="\n".join(today_lines), inline=False)
        e.add_field(name="Top Damage Overall", value="\n".join(overall_lines[:10]), inline=False)
        e.add_field(name="Event", value=f"{event_type}\nToken: {token_name}", inline=True)
        e.set_footer(text="Use /event to see more event options.")
        await interaction.followup.send(embed=e, ephemeral=True)
    
    async def _pick_active_event_for_dp(self, gid: int) -> str | None:
        """Pick active event ID for DP system."""
        rows = await self.bot.db.fetchall(
            "SELECT event_id, event_type FROM events WHERE guild_id=? AND is_active=1",
            (gid,)
        )
        if not rows:
            return None
        for r in rows:
            if str(r["event_type"]) == "holiday_week":
                return str(r["event_id"])
        for r in rows:
            if str(r["event_type"]) == "season_era":
                return str(r["event_id"])
        return str(rows[0]["event_id"]) if rows else None
    
    @app_commands.command(name="season_shop", description="View the season shop (token store).")
    async def season_shop(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild_id
        if not gid:
            embed = create_embed("Use this in a server.", color="info", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)

        wrapper = await self._active_wrapper(gid)
        if not wrapper:
            embed = create_embed("No active season/holiday shop right now.", color="info", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)

        cfg = json.loads(wrapper["config_json"])
        items = cfg.get("season_shop_items") or []  # you fill later

        if not items:
            # Placeholder only; you can wire to your real store
            desc = (
                "Season shop is not configured yet.\n"
                "Add `season_shop_items` to wrapper config_json.\n"
                "᲼᲼"
            )
            e = self._embed(None, desc, thumb_url=self._thumb(cfg, "SEASON_DROP__INTRIGUED"))
            return await interaction.followup.send(embed=e, ephemeral=True)

        # items expected format:
        # [{"id":"frost_collar_blue","name":"Frost Collar (Blue)","cost_tokens":120,"rarity":"basic","note":"..."}]
        lines = []
        for it in items[:15]:
            lines.append(f"• `{it.get('id')}` **{it.get('name')}** — **{fmt(int(it.get('cost_tokens',0)))} Tokens**")

        e = self._embed(None, "\n".join(lines) + "\n᲼᲼", thumb_url=self._thumb(cfg, "SEASON_DROP__INTRIGUED"))
        await interaction.followup.send(embed=e, ephemeral=True)

    @app_commands.command(name="quests", description="View quests (daily/weekly/elite).")
    @app_commands.describe(tier="daily, weekly, elite, or all")
    async def quests(self, interaction: discord.Interaction, tier: str = "all"):
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild_id
        if not gid:
            embed = create_embed("Use this in a server.", color="info", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)

        tier = tier.lower().strip()
        if tier not in {"daily", "weekly", "elite", "all"}:
            tier = "all"

        wrapper = await self._active_wrapper(gid)
        event_filter = ""
        params = [gid]

        # Prefer wrapper-scoped quests if wrapper exists, else show global
        if wrapper:
            event_filter = "AND event_id=?"
            params.append(int(wrapper["event_id"]))
        else:
            event_filter = "AND event_id IS NULL"

        tier_filter = ""
        if tier != "all":
            tier_filter = "AND tier=?"
            params.append(tier)

        rows = await self.bot.db.fetchall(
            f"SELECT quest_id,tier,name,description,end_ts FROM quests "
            f"WHERE guild_id=? AND active=1 {event_filter} {tier_filter} "
            f"ORDER BY CASE tier WHEN 'daily' THEN 0 WHEN 'weekly' THEN 1 ELSE 2 END, quest_id ASC LIMIT 20",
            tuple(params)
        )
        if not rows:
            embed = create_embed("No quests available right now.", color="info", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)

        lines = []
        for r in rows:
            qid = int(r["quest_id"])
            end = int(r["end_ts"])
            left_h = max(0, (end - now_ts()) // 3600)
            lines.append(f"`{qid}` **{r['tier'].upper()}** — {r['name']} • ends in **{left_h}h**")

        cfg = json.loads(wrapper["config_json"]) if wrapper else {"thumbs": {}}
        thumb_key = "QUESTBOARD_DAILY__NEUTRAL" if tier in ("daily","all") else ("QUESTBOARD_WEEKLY__SMIRK" if tier=="weekly" else "QUESTBOARD_ELITE__INTRIGUED")
        e = self._embed(None, "\n".join(lines) + "\n᲼᲼", thumb_url=self._thumb(cfg, thumb_key))
        await interaction.followup.send(embed=e, ephemeral=True)

    @app_commands.command(name="quest_progress", description="Check your progress on a quest.")
    @app_commands.describe(quest_id="Quest ID")
    async def quest_progress(self, interaction: discord.Interaction, quest_id: int):
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild_id
        if not gid:
            embed = create_embed("Use this in a server.", color="info", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)

        q = await self.bot.db.fetchone("SELECT * FROM quests WHERE guild_id=? AND quest_id=? AND active=1", (gid, quest_id))
        if not q:
            embed = create_embed("Quest not found.", color="info", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)

        q = dict(q)
        run = await self._get_or_create_quest_run(gid, quest_id, interaction.user.id)
        if run["status"] in ("claimed",):
            embed = create_embed("You already claimed this quest.", color="info", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)

        req = json.loads(q["requirement_json"])
        ok, detail = await self._quest_check_completion(
            gid, interaction.user.id, req, int(q["start_ts"]), int(q["end_ts"])
        )
        left_m = max(0, (int(q["end_ts"]) - now_ts()) // 60)

        desc = (
            f"{interaction.user.mention}\n"
            f"Quest: **{q['name']}**\n"
            f"Progress: **{detail}**\n"
            f"Time left: **{left_m} minutes**\n"
            "᲼᲼"
        )
        wrapper = await self._active_wrapper(gid)
        cfg = json.loads(wrapper["config_json"]) if wrapper else {"thumbs": {}}
        thumb_key = "QUESTBOARD_ELITE__INTRIGUED" if q["tier"] == "elite" else ("QUESTBOARD_WEEKLY__SMIRK" if q["tier"] == "weekly" else "QUESTBOARD_DAILY__NEUTRAL")
        e = self._embed(None, desc, thumb_url=self._thumb(cfg, thumb_key))
        await interaction.followup.send(embed=e, ephemeral=True)

    @app_commands.command(name="quest_claim", description="Claim a quest reward if complete.")
    @app_commands.describe(quest_id="Quest ID")
    async def quest_claim(self, interaction: discord.Interaction, quest_id: int):
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild_id
        if not gid:
            embed = create_embed("Use this in a server.", color="info", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)

        q = await self.bot.db.fetchone("SELECT * FROM quests WHERE guild_id=? AND quest_id=? AND active=1", (gid, quest_id))
        if not q:
            embed = create_embed("Quest not found.", color="info", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)
        q = dict(q)

        run = await self._get_or_create_quest_run(gid, quest_id, interaction.user.id)
        if run["status"] == "claimed":
            embed = create_embed("Already claimed.", color="info", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)

        # Check completion
        req = json.loads(q["requirement_json"])
        ok, detail = await self._quest_check_completion(gid, interaction.user.id, req, int(q["start_ts"]), int(q["end_ts"]))
        if not ok:
            # manual quests route to inbox (optional)
            if req.get("type") == "manual":
                embed = create_embed("This quest requires manual proof.", color="info", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)
            embed = create_embed(f"Not complete yet: {detail}", color="info", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)

        # rewards
        reward = json.loads(q["reward_json"] or "{}")
        tokens = int(reward.get("tokens", 0))
        coins = int(reward.get("coins", 0))
        obedience = int(reward.get("obedience", 0))

        # token scope = active wrapper if exists else quest event_id else 0
        wrapper_scope = await self._token_scope_for_wrapper(gid)
        scope_event_id = wrapper_scope or int(q.get("event_id") or 0) or 0
        if scope_event_id == 0:
            # fallback: just store under quest's own id space
            scope_event_id = 999999  # global bucket

        await self._add_tokens(gid, interaction.user.id, scope_event_id, tokens)
        await self._add_profile_rewards(gid, interaction.user.id, coins, obedience)

        await self.bot.db.execute(
            "UPDATE quest_runs SET status='claimed', completed_ts=?, claimed_ts=? WHERE guild_id=? AND quest_id=? AND user_id=?",
            (now_ts(), now_ts(), gid, quest_id, interaction.user.id)
        )

        desc = (
            f"{interaction.user.mention}\n"
            f"Claimed: **{q['name']}**\n"
            f"Reward: **{fmt(tokens)} Tokens** • **{fmt(coins)} Coins** • **{fmt(obedience)} Obedience**\n"
            "᲼᲼"
        )
        wrapper = await self._active_wrapper(gid)
        cfg = json.loads(wrapper["config_json"]) if wrapper else {"thumbs": {}}
        e = self._embed(None, desc, thumb_url=self._thumb(cfg, "THUMB_INTRIGUED"))
        await interaction.followup.send(embed=e, ephemeral=True)

    @app_commands.command(name="quest_reroll", description="Reroll one daily quest (costs Tokens or Coins).")
    async def quest_reroll(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild_id
        if not gid:
            embed = create_embed("Use this in a server.", color="info", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)

        wrapper = await self._active_wrapper(gid)
        if not wrapper:
            embed = create_embed("No active season/holiday to reroll quests in.", color="info", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)

        scope_id = int(wrapper["event_id"])
        cfg = json.loads(wrapper["config_json"])
        reroll_cost_tokens = int(cfg.get("reroll_cost_tokens", 5))
        reroll_cost_coins = int(cfg.get("reroll_cost_coins", 1000))

        # Find active daily quests in this wrapper
        dailies = await self.bot.db.fetchall(
            "SELECT quest_id,name FROM quests WHERE guild_id=? AND active=1 AND tier='daily' AND event_id=?",
            (gid, scope_id)
        )
        if not dailies or len(dailies) < 2:
            embed = create_embed("Not enough daily quests to reroll.", color="info", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)

        # Find a daily quest the user hasn't already claimed/rerolled
        # Pick the first eligible as "current"
        current = None
        for q in dailies:
            run = await self.bot.db.fetchone(
                "SELECT status FROM quest_runs WHERE guild_id=? AND quest_id=? AND user_id=?",
                (gid, int(q["quest_id"]), interaction.user.id)
            )
            if not run or run["status"] != "claimed":
                current = int(q["quest_id"])
                break
        if current is None:
            embed = create_embed("You've already cleared today's dailies.", color="info", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)

        # Pay cost: tokens preferred, else coins
        tokens_have = await self._get_user_tokens(gid, interaction.user.id, scope_id)
        paid = ""
        if tokens_have >= reroll_cost_tokens and reroll_cost_tokens > 0:
            await self.bot.db.execute(
                "UPDATE token_balances SET tokens=tokens-?, updated_ts=? WHERE guild_id=? AND user_id=? AND scope_event_id=?",
                (reroll_cost_tokens, now_ts(), gid, interaction.user.id, scope_id)
            )
            # Forward token spending to EventActivityTracker
            tracker = self.bot.get_cog("Data")
            if tracker:
                try:
                    event_row = await self.bot.db.fetchone(
                        "SELECT event_id FROM events WHERE guild_id=? AND (event_id=? OR event_id LIKE ?) AND is_active=1 LIMIT 1",
                        (gid, scope_id, f"{scope_id}%")
                    )
                    if event_row:
                        await tracker.add_tokens_spent(gid, interaction.user.id, reroll_cost_tokens, "quest_reroll", {"quest_id": current})
                except Exception:
                    pass
            paid = f"{reroll_cost_tokens} Tokens"
        else:
            # coins fallback
            row = await self.bot.db.fetchone("SELECT coins FROM users WHERE guild_id=? AND user_id=?", (gid, interaction.user.id))
            coins_have = int(row["coins"]) if row else 0
            if coins_have < reroll_cost_coins:
                return await interaction.followup.send(
                    f"Need **{reroll_cost_tokens} Tokens** or **{reroll_cost_coins} Coins** to reroll.",
                    ephemeral=True
                )
            await self.bot.db.execute("UPDATE users SET coins=coins-? WHERE guild_id=? AND user_id=?", (reroll_cost_coins, gid, interaction.user.id))
            paid = f"{reroll_cost_coins} Coins"

        # Mark current as claimed with reroll tag
        await self._get_or_create_quest_run(gid, current, interaction.user.id)
        await self.bot.db.execute(
            "UPDATE quest_runs SET status='claimed', progress_json=?, claimed_ts=? WHERE guild_id=? AND quest_id=? AND user_id=?",
            (json.dumps({"rerolled": True}), now_ts(), gid, current, interaction.user.id)
        )

        # Choose a different daily quest
        other_ids = [int(q["quest_id"]) for q in dailies if int(q["quest_id"]) != current]
        new_id = random.choice(other_ids)

        new_q = await self.bot.db.fetchone("SELECT * FROM quests WHERE guild_id=? AND quest_id=?", (gid, new_id))
        new_q = dict(new_q)

        # Create run entry (active)
        await self._get_or_create_quest_run(gid, new_id, interaction.user.id)

        desc = (
            f"{interaction.user.mention}\n"
            f"Rerolled a daily quest.\n"
            f"Paid: **{paid}**\n\n"
            f"New quest: **{new_q['name']}**\n"
            f"{new_q['description']}\n"
            "᲼᲼"
        )
        e = self._embed(None, desc, thumb_url=self._thumb(cfg, "QUESTBOARD_DAILY__NEUTRAL"))
        await interaction.followup.send(embed=e, ephemeral=True)

    # =========================================================
    #  B) STAFF COMMANDS (minimal skeleton)
    # =========================================================
    
    @app_commands.command(name="event_start_holiday", description="(Staff) Manually start a holiday week event.")
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.describe(holiday_id="Holiday ID: valentines_week, easter_week, midsummer_week, harvest_week, halloween_week, christmas_week", start_date="Start date (YYYY-MM-DD, optional)", hp_max="Boss HP (default: 15000)")
    async def event_start_holiday(self, interaction: discord.Interaction, holiday_id: str, start_date: str | None = None, hp_max: int = 15000):
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild_id
        if not gid or not interaction.guild:
            embed = create_embed("Use this in a server.", color="info", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)

        holiday_id = holiday_id.lower().strip()
        config = get_holiday_config(holiday_id)
        if not config:
            embed = create_embed(f"Invalid holiday ID. Use: valentines_week, easter_week, midsummer_week, harvest_week, halloween_week, christmas_week", color="info", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)

        # Check for existing active wrapper
        existing = await self._active_wrapper(gid)
        if existing and existing.get("type") == "holiday_week":
            embed = create_embed(f"A holiday week is already active: {existing['name']}", color="info", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)

        # Calculate dates
        if start_date:
            try:
                start_dt = datetime.strptime(start_date, "%Y-%m-%d")
                start_dt = start_dt.replace(hour=0, minute=0, second=0, tzinfo=UK_TZ)
            except ValueError:
                embed = create_embed("Invalid date format. Use YYYY-MM-DD", color="info", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            start_dt = uk_now().replace(hour=0, minute=0, second=0)

        duration_days = config.get("duration_days", 7)
        end_dt = start_dt + timedelta(days=duration_days)
        start_ts = int(start_dt.timestamp())
        end_ts = int(end_dt.timestamp())

        # Create holiday week wrapper event
        eid = await self._next_event_id(gid)
        holiday_config = {
            "id": config["id"],
            "channels": {k: self.ch_id(k) for k in DEFAULT_CHANNEL_KEYS},
            "thumbs": dict(DEFAULT_THUMBS),
            "token_name": config.get("token_name", "Tokens"),
            "theme": config.get("theme", ""),
            "duration_days": duration_days,
            "climax_day": config.get("climax_day", ""),
            "boss_name": config.get("boss_name", ""),
            "ritual_name": config.get("ritual_name", ""),
            "damage_weights": config.get("damage_weights", {}),
            "milestones": config.get("milestones", []),
            "easter_egg": config.get("easter_egg", {}),
            "special_roles": config.get("special_roles", []),
            "shop_items": config.get("shop_items", []),
            "isla_voice_start": config.get("isla_voice_start", {}),
        }

        await self.bot.db.execute(
            "INSERT INTO events(guild_id,event_id,type,parent_event_id,name,start_ts,end_ts,status,config_json,created_ts) "
            "VALUES(?,?,?,?,?,?,?,?,?,?)",
            (gid, eid, "holiday_week", None, config["name"], start_ts, end_ts, "active", json.dumps(holiday_config), now_ts())
        )

        # Start boss fight
        await self._start_holiday_boss(interaction.guild, eid, holiday_config, config, hp_max)

        # Announce holiday week start
        orders_ch = self.get_channel(interaction.guild, "orders")
        if orders_ch:
            thumb = self._thumb(holiday_config, "HOLIDAY_LAUNCH__THEMED_DOMINANT")
            desc = (
                f"**{config['name']}** has begun.\n"
                f"Duration: **{duration_days} days**\n"
                f"Climax: **{config.get('climax_day', 'Day 7')}**\n"
                f"Check progress with /event.\n"
                "᲼᲼"
            )
            e = self._embed("Holiday Week Started", desc, thumb_url=thumb)
            await orders_ch.send(embed=e)

        embed = create_embed(f"Holiday week **{config['name']}** started.", color="info", is_dm=False, is_system=False)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="event_start_season", description="(Staff) Start a seasonal event (spring/summer/autumn/winter).")
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.describe(season="Season name: spring, summer, autumn, or winter", start_date="Start date (YYYY-MM-DD, optional)", hp_max="Boss HP for finale (default: 20000)")
    async def event_start_season(self, interaction: discord.Interaction, season: str, start_date: str | None = None, hp_max: int = 20000):
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild_id
        if not gid or not interaction.guild:
            embed = create_embed("Use this in a server.", color="info", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)

        season = season.lower().strip()
        config = get_seasonal_config(season)
        if not config:
            embed = create_embed(f"Invalid season. Use: spring, summer, autumn, or winter.", color="info", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)

        # Check for existing active season
        existing = await self._active_wrapper(gid)
        if existing:
            embed = create_embed(f"A season/holiday is already active: {existing['name']}", color="info", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)

        # Calculate dates
        from datetime import datetime
        from utils.embed_utils import create_embed
        if start_date:
            try:
                start_dt = datetime.strptime(start_date, "%Y-%m-%d")
                start_dt = start_dt.replace(hour=0, minute=0, second=0, tzinfo=UK_TZ)
            except ValueError:
                embed = create_embed("Invalid date format. Use YYYY-MM-DD", color="info", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            start_dt = uk_now().replace(hour=0, minute=0, second=0)

        duration_days = config["duration_weeks"] * 7
        end_dt = start_dt + timedelta(days=duration_days)
        start_ts = int(start_dt.timestamp())
        end_ts = int(end_dt.timestamp())

        # Create season wrapper event
        eid = await self._next_event_id(gid)
        season_config = {
            "channels": {k: self.ch_id(k) for k in DEFAULT_CHANNEL_KEYS},
            "thumbs": dict(DEFAULT_THUMBS),
            "token_name": config.get("token_name", "Tokens"),
            "theme": config.get("theme", ""),
            "aesthetic": config.get("aesthetic", {}),
            "duration_weeks": config["duration_weeks"],
            "finale_week": config["finale_week"],
            "finale_name": config["finale_name"],
            "boss_name": config["boss_name"],
            "damage_weights": config["damage_weights"],
            "milestones": config["milestones"],
            "easter_eggs": config["easter_eggs"],
            "weekly_ritual": config.get("weekly_ritual", {}),
        }

        await self.bot.db.execute(
            "INSERT INTO events(guild_id,event_id,type,parent_event_id,name,start_ts,end_ts,status,config_json,created_ts) "
            "VALUES(?,?,?,?,?,?,?,?,?,?)",
            (gid, eid, "season", None, config["name"], start_ts, end_ts, "active", json.dumps(season_config), now_ts())
        )

        # Announce season start
        orders_ch = self.get_channel(interaction.guild, "orders")
        if orders_ch:
            thumb = self._thumb(season_config, "SEASON_LAUNCH__DOMINANT")
            desc = (
                f"**{config['name']}** has begun.\n"
                f"Duration: **{config['duration_weeks']} weeks**\n"
                f"Finale: Week {config['finale_week']} - **{config['finale_name']}**\n"
                f"Check progress with /season.\n"
                "᲼᲼"
            )
            e = self._embed("Season Started", desc, thumb_url=thumb)
            await orders_ch.send(embed=e)

        embed = create_embed(f"Season **{config['name']}** started. Finale will trigger automatically in week {config['finale_week']}.", color="info", is_dm=False, is_system=False)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="event_start_boss", description="(Staff) Start a boss fight event.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def event_start_boss(self, interaction: discord.Interaction, name: str, hours: int = 48, hp_max: int = 20000):
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild_id
        if not gid or not interaction.guild:
            embed = create_embed("Use this in a server.", color="info", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)

        # prevent double boss
        existing = await self._active_boss(gid)
        if existing:
            embed = create_embed("A boss fight is already active.", color="info", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)

        eid = await self._next_event_id(gid)
        start = now_ts()
        end = start + int(hours) * 3600

        wrapper = await self._active_wrapper(gid)
        parent_id = int(wrapper["event_id"]) if wrapper else None

        config = {
            "channels": {k: self.ch_id(k) for k in DEFAULT_CHANNEL_KEYS},
            "thumbs": dict(DEFAULT_THUMBS),
            "caps": dict(DEFAULT_BOSS_CAPS),
            "weights": dict(DEFAULT_SCORE_WEIGHTS),
            "milestones": [
                {"pct": 90, "key": "milestone_90", "reward": {"tokens": 5}},
                {"pct": 75, "key": "milestone_75", "reward": {"tokens": 8}},
                {"pct": 50, "key": "milestone_50", "reward": {"tokens": 12}},
                {"pct": 25, "key": "milestone_25", "reward": {"tokens": 15}},
                {"pct": 0,  "key": "boss_kill_pack", "reward": {"tokens": 20}},
            ],
            "wrapper_scope_event_id": parent_id or 0,  # token scope
        }

        await self.bot.db.execute(
            "INSERT INTO events(guild_id,event_id,type,parent_event_id,name,start_ts,end_ts,status,config_json,created_ts) "
            "VALUES(?,?,?,?,?,?,?,?,?,?)",
            (gid, eid, "boss", parent_id, name, start, end, "active", json.dumps(config), now_ts())
        )

        await self._state_set(gid, eid, "hp_max", str(int(hp_max)))
        await self._state_set(gid, eid, "hp_current", str(int(hp_max)))
        await self._state_set(gid, eid, "phase", "1")
        await self._state_set(gid, eid, "milestones_unlocked", json.dumps({}))  # map key->bool
        await self._state_set(gid, eid, "last_calc_ts", str(start))

        # Post clean announcement in #orders (no pings)
        orders_ch = self.get_channel(interaction.guild, "orders")
        if orders_ch:
            thumb = self._thumb(config, "BOSS_START__DOMINANT")
            desc = (
                "Boss fight online.\n"
                f"Health: **100%** `{hp_bar(hp_max, hp_max)}`\n"
                "Contribute by being active.\n"
                "Check progress with /event.\n"
                "᲼᲼"
            )
            e = self._embed("Boss Fight", desc, thumb_url=thumb)
            await orders_ch.send(embed=e)

        embed = create_embed(f"Boss started: `{eid}`", color="info", is_dm=False, is_system=False)
        await interaction.followup.send(embed=embed, ephemeral=True)

    # =========================================================
    #  Scheduler 1: Activate scheduled events, end expired
    # =========================================================
    @tasks.loop(seconds=30)
    async def tick_events(self):
        await self.bot.wait_until_ready()
        now = now_ts()

        for guild in self.bot.guilds:
            gid = guild.id

            # activate scheduled events
            sched = await self.bot.db.fetchall(
                "SELECT event_id,config_json,type,name FROM events WHERE guild_id=? AND status='scheduled' AND start_ts<=? LIMIT 25",
                (gid, now)
            )
            for r in sched:
                await self.bot.db.execute(
                    "UPDATE events SET status='active' WHERE guild_id=? AND event_id=?",
                    (gid, int(r["event_id"]))
                )
                # optionally announce in #orders (keep minimal)

            # end active events past end_ts
            expired = await self.bot.db.fetchall(
                "SELECT event_id,type,config_json,name FROM events WHERE guild_id=? AND status='active' AND end_ts<=? LIMIT 25",
                (gid, now)
            )
            for r in expired:
                await self._end_event(gid, int(r["event_id"]), r["type"], json.loads(r["config_json"]), r["name"], guild)

    async def _end_event(self, gid: int, eid: int, etype: str, cfg: dict, name: str, guild: discord.Guild):
        await self.bot.db.execute("UPDATE events SET status='ended' WHERE guild_id=? AND event_id=?", (gid, eid))

        # Boss end recap (if boss ended without kill)
        if etype == "boss":
            hp = int(await self._state_get(gid, eid, "hp_current", "0"))
            hpmax = int(await self._state_get(gid, eid, "hp_max", "1"))
            pct = int(round((hp / max(1, hpmax)) * 100))

            orders_ch = self.get_channel(guild, "orders")
            if orders_ch:
                thumb = self._thumb(cfg, "THUMB_NEUTRAL")
                desc = (
                    f"Boss fight ended.\n"
                    f"Final HP: **{pct}%** `{hp_bar(hp, hpmax)}`\n"
                    "I expected more.\n"
                    "᲼᲼"
                )
                e = self._embed("Boss End", desc, thumb_url=thumb)
                await orders_ch.send(embed=e)

    # =========================================================
    #  Scheduler 2: Boss tick (compute score deltas + reduce HP + unlock milestones)
    # =========================================================
    @tasks.loop(hours=24)
    async def tick_seasonal_finale(self):
        """Check for seasonal events that need finale bosses started."""
        await self.bot.wait_until_ready()
        
        for guild in self.bot.guilds:
            gid = guild.id
            # Find active seasonal events
            rows = await self.bot.db.fetchall(
                "SELECT * FROM events WHERE guild_id=? AND type='season' AND status='active'",
                (gid,)
            )
            for row in rows:
                season_event = dict(row)
                await self._auto_start_seasonal_finale(guild, season_event)

    @tasks.loop(hours=6)  # Check every 6 hours for holiday week starts
    async def tick_holiday_weeks(self):
        """Auto-start holiday weeks based on calendar dates."""
        await self.bot.wait_until_ready()
        
        now = uk_now()
        current_year = now.year
        
        for guild in self.bot.guilds:
            gid = guild.id
            
            # Check each holiday config for auto-start
            for holiday_id, holiday_cfg in get_all_holidays().items():
                try:
                    # Parse start date
                    date_range = holiday_cfg.get("date_range", ())
                    if not date_range:
                        continue
                    
                    start_date_str = date_range[0]
                    year, month, day = parse_holiday_date(start_date_str, current_year)
                    start_dt = datetime(year, month, day, 0, 0, 0, tzinfo=UK_TZ)
                    
                    # Check if we're within 12 hours of start (or already past but not started)
                    time_until_start = (start_dt - now).total_seconds()
                    if -43200 <= time_until_start <= 43200:  # Within 12 hours before/after
                        # Check if event already exists or is active
                        existing = await self.bot.db.fetchone(
                            "SELECT event_id, status FROM events WHERE guild_id=? AND type='holiday_week' AND config_json LIKE ?",
                            (gid, f'%"id":"{holiday_id}"%')
                        )
                        
                        if not existing or existing["status"] != "active":
                            # Check if already scheduled
                            if not existing:
                                await self._auto_start_holiday_week(guild, holiday_cfg, start_dt)
                except Exception as e:
                    # Skip invalid dates or parse errors
                    continue

    @tasks.loop(minutes=2)
    async def tick_boss(self):
        await self.bot.wait_until_ready()

        for guild in self.bot.guilds:
            gid = guild.id
            boss = await self._active_boss(gid)
            if not boss:
                continue

            eid = int(boss["event_id"])
            cfg = json.loads(boss["config_json"])
            # Only talk in #orders during awake hours (12–15) + max 2/day
            # But calculation runs always.

            await self._boss_calculate(guild, eid, cfg)

    # =========================================================
    #  Scheduler 3: Quest refresh tick (daily/weekly inside awake window)
    # =========================================================
    @tasks.loop(minutes=5)
    async def tick_quest_refresh(self):
        await self.bot.wait_until_ready()
        t = uk_now()
        # refresh in awake window only: 12:00–15:00
        if not (12 <= t.hour < 15):
            return

        for guild in self.bot.guilds:
            gid = guild.id
            wrapper = await self._active_wrapper(gid)
            if not wrapper:
                continue

            # Daily refresh guard
            dk = day_key_uk(t)
            last = await self.bot.db.fetchone("SELECT value FROM event_system_state WHERE guild_id=? AND key='daily_quest_refresh'", (gid,))
            if last and last["value"] == dk:
                continue

            await self._refresh_daily_quests(guild, wrapper)
            await self.bot.db.execute(
                "INSERT INTO event_system_state(guild_id,key,value) VALUES(?,?,?) "
                "ON CONFLICT(guild_id,key) DO UPDATE SET value=excluded.value",
                (gid, "daily_quest_refresh", dk)
            )

    # =========================================================
    #  Quest generation (basic but functional)
    # =========================================================
    async def _refresh_daily_quests(self, guild: discord.Guild, wrapper: dict):
        gid = guild.id
        scope_event_id = int(wrapper["event_id"])
        start = now_ts()
        end = start + 24 * 3600

        # deactivate previous daily quests for this wrapper
        await self.bot.db.execute(
            "UPDATE quests SET active=0 WHERE guild_id=? AND tier='daily' AND event_id=?",
            (gid, scope_event_id)
        )

        spam_id = self.ch_id("spam")
        casino_id = self.ch_id("casino")

        # Create 6 dailies: 3 chat, 1 vc, 2 casino (if casino exists)
        templates = [
            ("daily", "Say something", "Send 10 messages in #spam.", {"type":"messages","count":10,"channel_id":spam_id}, {"tokens":3,"coins":150,"obedience":3}),
            ("daily", "Keep it moving", "Send 15 messages in #spam.", {"type":"messages","count":15,"channel_id":spam_id}, {"tokens":4,"coins":200,"obedience":4}),
            ("daily", "No lurking", "Send 8 messages in #spam.", {"type":"messages","count":8,"channel_id":spam_id}, {"tokens":2,"coins":120,"obedience":2}),
            ("daily", "Voice presence", "Spend 15 minutes in voice.", {"type":"vc_minutes","minutes":15}, {"tokens":4,"coins":180,"obedience":4}),
            ("daily", "Casino warmup", "Play 5 casino rounds.", {"type":"casino_rounds","count":5}, {"tokens":4,"coins":0,"obedience":3}),
            ("daily", "Wager", "Wager 2000 Coins total.", {"type":"casino_wager","coins":2000}, {"tokens":5,"coins":0,"obedience":4}),
        ]

        for tier, name, desc, req, reward in templates:
            qid = await self._next_quest_id(gid)
            await self.bot.db.execute(
                "INSERT INTO quests(guild_id,quest_id,event_id,tier,name,description,requirement_json,reward_json,start_ts,end_ts,max_completions_per_user,active) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,1)",
                (gid, qid, scope_event_id, tier, name, desc, json.dumps(req), json.dumps(reward), start, end, 1)
            )

        # One clean note in #orders (no ping)
        orders = self.get_channel(guild, "orders")
        if orders:
            cfg = json.loads(wrapper["config_json"])
            thumb = self._thumb(cfg, "QUESTBOARD_DAILY__NEUTRAL")
            e = self._embed(
                None,
                "Daily quests refreshed.\nCheck them with /quests.\n᲼᲼",
                thumb_url=thumb
            )
            await orders.send(embed=e)

    async def _boss_calculate_legacy(self, guild: discord.Guild, eid: int, cfg: dict):
        """Legacy boss calculation - kept for backward compatibility."""
        # This method maintains the old ES-based calculation
        # New holiday weeks should use _boss_calculate_new_daily instead
        await self._boss_calculate(guild, eid, cfg)
    
    async def _boss_calculate(self, guild: discord.Guild, eid: int, cfg: dict):
        gid = guild.id
        now = now_ts()

        last_calc = int(await self._state_get(gid, eid, "last_calc_ts", str(now - 120)))
        if last_calc >= now:
            return

        caps = cfg.get("caps", DEFAULT_BOSS_CAPS)
        weights = cfg.get("weights", DEFAULT_SCORE_WEIGHTS)

        # compute window
        start = last_calc
        end = now

        # Pull activity from your tracker cogs (must exist)
        mt = self.bot.get_cog("Data")
        vt = self.bot.get_cog("Data")
        cc = self.bot.get_cog("CasinoCore")
        oc = self.bot.get_cog("Orders")  # optional: only if you log completions

        # If trackers missing, do nothing (but don't crash)
        if not (mt or vt or cc or oc):
            await self._state_set(gid, eid, "last_calc_ts", str(now))
            return

        # We need per-user deltas in this window.
        msg_by_user = {}
        vc_by_user = {}
        wager_by_user = {}
        orders_by_user = {}
        rituals_by_user = {}

        # Messages: query msg_memory or approximate from weekly_stats
        # Simplified: use voice_events-style query if available, else approximate
        # For now, we'll use a simplified approach that queries voice_events directly
        # and approximates messages from moderation tracking

        # Voice minutes from VoiceTracker
        vc_by_user = {}
        if vt:
            try:
                vc_by_user = await vt.window_minutes(gid, start, end)
            except Exception:
                # fallback: query voice_events directly
                vc_rows = await self.bot.db.fetchall(
                    """
                    SELECT user_id, SUM(seconds) as total_seconds
                    FROM voice_events
                    WHERE guild_id=? AND end_ts >= ? AND start_ts <= ?
                    GROUP BY user_id
                    """,
                    (gid, start, end)
                )
                vc_by_user = {int(r["user_id"]): int(r["total_seconds"] or 0) // 60 for r in vc_rows}

        # Casino wagered from msg_memory (CasinoCore pattern)
        if cc:
            try:
                st = await cc.get_window_summary(gid, start)
                wager_by_user = {int(k): int(v) for k, v in (st.get("wager_by_user") or {}).items()}
            except Exception:
                wager_by_user = {}

        # Messages from MessageTracker
        if mt:
            try:
                msg_by_user = await mt.window_counts(gid, start, end)
            except Exception:
                msg_by_user = {}

        # Orders/Rituals: use Orders cog methods if available
        if oc:
            try:
                orders_by_user = await oc.window_order_completions(gid, start, end)
                rituals_by_user = await oc.window_ritual_completions(gid, start, end)
            except Exception:
                # fallback: query order_completion_log directly
                order_rows = await self.bot.db.fetchall(
                    """
                    SELECT user_id, COUNT(*) as cnt
                    FROM order_completion_log
                    WHERE guild_id=? AND kind='order' AND ts>=? AND ts<?
                    GROUP BY user_id
                    """,
                    (gid, start, end)
                )
                orders_by_user = {int(r["user_id"]): int(r["cnt"] or 0) for r in order_rows}
                
                ritual_rows = await self.bot.db.fetchall(
                    """
                    SELECT user_id, COUNT(*) as cnt
                    FROM order_completion_log
                    WHERE guild_id=? AND kind='ritual' AND ts>=? AND ts<?
                    GROUP BY user_id
                    """,
                    (gid, start, end)
                )
                rituals_by_user = {int(r["user_id"]): int(r["cnt"] or 0) for r in ritual_rows}

        # Union all users touched
        touched = set(msg_by_user.keys()) | set(vc_by_user.keys()) | set(wager_by_user.keys()) | set(orders_by_user.keys()) | set(rituals_by_user.keys())
        if not touched:
            await self._state_set(gid, eid, "last_calc_ts", str(now))
            return

        # Per-user cap windows: msg/hour, vc/day, wager/day
        # We'll store cap buckets in event_contrib.caps_json
        # keys: msg_bucket_{YYYY-MM-DD-HH}, vc_bucket_{YYYY-MM-DD}, wager_bucket_{YYYY-MM-DD}
        dt = datetime.fromtimestamp(end, tz=UK_TZ)
        hour_key = f"{dt.year:04d}-{dt.month:02d}-{dt.day:02d}-{dt.hour:02d}"
        day_key = f"{dt.year:04d}-{dt.month:02d}-{dt.day:02d}"

        total_es = 0

        for uid in touched:
            uid = int(uid)

            # load / init contrib row
            await self.bot.db.execute(
                "INSERT OR IGNORE INTO event_contrib(guild_id,event_id,user_id,score_total,breakdown_json,caps_json,last_update_ts) "
                "VALUES(?,?,?,?,?,?,?)",
                (gid, eid, uid, 0, "{}", "{}", 0)
            )
            row = await self.bot.db.fetchone(
                "SELECT breakdown_json,caps_json,score_total FROM event_contrib WHERE guild_id=? AND event_id=? AND user_id=?",
                (gid, eid, uid)
            )

            breakdown = json.loads(row["breakdown_json"] or "{}")
            capb = json.loads(row["caps_json"] or "{}")
            score_total = int(row["score_total"] or 0)

            # Apply caps
            msg_cap_key = f"msg_bucket_{hour_key}"
            vc_cap_key = f"vc_bucket_{day_key}"
            wager_cap_key = f"wager_bucket_{day_key}"

            msg_used = int(capb.get(msg_cap_key, 0))
            vc_used = int(capb.get(vc_cap_key, 0))
            wager_used = int(capb.get(wager_cap_key, 0))

            msg_raw = int(msg_by_user.get(uid, 0))
            vc_raw = int(vc_by_user.get(uid, 0))
            wager_raw = int(wager_by_user.get(uid, 0))
            orders_raw = int(orders_by_user.get(uid, 0))
            rituals_raw = int(rituals_by_user.get(uid, 0))

            # message cap per hour (skip for now since we don't have msg tracking)
            msg_allow = max(0, int(caps["msg_per_hour"]) - msg_used)
            msg_counted = min(msg_raw, msg_allow)

            # vc cap per day
            vc_allow = max(0, int(caps["vc_minutes_per_day"]) - vc_used)
            vc_counted = min(vc_raw, vc_allow)

            # wager cap per day (coins)
            wager_allow = max(0, int(caps["wager_coins_per_day"]) - wager_used)
            wager_counted = min(wager_raw, wager_allow)

            # Convert to ES
            es_msg = msg_counted * int(weights["msg"])
            es_vc = vc_counted * int(weights["vc_min"])
            es_wager = int(wager_counted // int(weights["wager_per"]))
            es_orders = orders_raw * int(weights["order_complete"])
            es_rituals = rituals_raw * int(weights["ritual_complete"])

            user_es = es_msg + es_vc + es_wager + es_orders + es_rituals
            if user_es <= 0:
                continue

            # Update cap usage
            capb[msg_cap_key] = msg_used + msg_counted
            capb[vc_cap_key] = vc_used + vc_counted
            capb[wager_cap_key] = wager_used + wager_counted

            # Update breakdown totals (lifetime in boss event)
            breakdown["msg"] = int(breakdown.get("msg", 0)) + msg_counted
            breakdown["vc"] = int(breakdown.get("vc", 0)) + vc_counted
            breakdown["wager_es"] = int(breakdown.get("wager_es", 0)) + es_wager
            breakdown["orders"] = int(breakdown.get("orders", 0)) + orders_raw
            breakdown["rituals"] = int(breakdown.get("rituals", 0)) + rituals_raw

            score_total += user_es
            total_es += user_es

            await self.bot.db.execute(
                "UPDATE event_contrib SET score_total=?, breakdown_json=?, caps_json=?, last_update_ts=? "
                "WHERE guild_id=? AND event_id=? AND user_id=?",
                (score_total, json.dumps(breakdown), json.dumps(capb), now, gid, eid, uid)
            )

        if total_es <= 0:
            await self._state_set(gid, eid, "last_calc_ts", str(now))
            return

        # Reduce HP by total ES (tuneable)
        hp_max = int(await self._state_get(gid, eid, "hp_max", "1"))
        hp_cur = int(await self._state_get(gid, eid, "hp_current", str(hp_max)))

        new_hp = max(0, hp_cur - total_es)
        await self._state_set(gid, eid, "hp_current", str(new_hp))
        await self._state_set(gid, eid, "last_calc_ts", str(now))

        # Update phase and unlock milestones
        await self._boss_update_phase_and_milestones(guild, eid, cfg, hp_max, new_hp, total_es)

    async def _boss_update_phase_and_milestones(self, guild: discord.Guild, eid: int, cfg: dict, hp_max: int, hp_cur: int, delta_es: int):
        gid = guild.id
        pct = int(round((hp_cur / max(1, hp_max)) * 100))

        # Phase logic
        if pct > 75:
            phase = 1
            thumb_key = "BOSS_START__DOMINANT"
        elif pct > 50:
            phase = 2
            thumb_key = "BOSS_PHASE2__INTRIGUED"
        elif pct > 25:
            phase = 3
            thumb_key = "BOSS_PHASE3__DISPLEASED"
        else:
            phase = 4
            thumb_key = "BOSS_FINAL__INTENSE"

        await self._state_set(gid, eid, "phase", str(phase))

        # Unlock milestones
        unlocked_raw = await self._state_get(gid, eid, "milestones_unlocked", "{}")
        unlocked = json.loads(unlocked_raw or "{}")

        milestones = cfg.get("milestones", [])
        newly = []
        for m in milestones:
            mpct = int(m.get("pct", 0))
            key = str(m.get("key"))
            if key in unlocked:
                continue
            if pct <= mpct:
                unlocked[key] = True
                newly.append(m)

        if newly:
            await self._state_set(gid, eid, "milestones_unlocked", json.dumps(unlocked))
            # Process seasonal milestone rewards and announce
            for m in newly:
                await self._process_seasonal_milestone_reward(guild, eid, m, cfg)
                # Announce milestone with seasonal tone
                await self._announce_seasonal_milestone(guild, eid, m, cfg)

        # If boss killed, end event and Spotlight winners
        if hp_cur <= 0:
            await self._boss_finish(guild, eid, cfg)
            return

        # Minimal #orders update policy: only in awake hours + max 2/day
        t = uk_now()
        if not (12 <= t.hour < 15):
            return

        orders_ch = self.get_channel(guild, "orders")
        if not orders_ch:
            return

        # Rate guard: max 2 updates/day per boss
        dk = day_key_uk(t)
        posted_key = f"boss_updates_{dk}"
        posted = int(await self._state_get(gid, eid, posted_key, "0"))
        if posted >= 2:
            return

        # Only post if something meaningful happened: milestone unlocked or big delta
        big_hit = delta_es >= max(300, hp_max // 50)  # tune
        if not newly and not big_hit:
            return

        await self._state_set(gid, eid, posted_key, str(posted + 1))

        # Create a clean "thinking out loud" update (no pings)
        thumb = self._thumb(cfg, thumb_key)
        lines = [
            f"Status check.\nHP: **{pct}%** `{hp_bar(hp_cur, hp_max)}`\n᲼᲼"
        ]
        if newly:
            # Keep it short
            lines.append("Something just unlocked.\nCheck /event_claim.\n᲼᲼")

        e = self._embed(None, "".join(lines), thumb_url=thumb)
        await orders_ch.send(embed=e)

    async def _boss_finish(self, guild: discord.Guild, eid: int, cfg: dict):
        gid = guild.id

        # End boss event
        await self.bot.db.execute("UPDATE events SET status='ended' WHERE guild_id=? AND event_id=?", (gid, eid))

        # Orders recap (no pings)
        orders_ch = self.get_channel(guild, "orders")
        if orders_ch:
            thumb = self._thumb(cfg, "BOSS_KILL__LAUGHING")
            e = self._embed(
                "Boss Down",
                "Boss defeated.\nI watched every bit of it.\nCheck #spotlight.\n᲼᲼",
                thumb_url=thumb
            )
            await orders_ch.send(embed=e)

        # Check if this is a seasonal finale boss
        parent_row = await self.bot.db.fetchone(
            "SELECT type, config_json FROM events WHERE guild_id=? AND event_id=(SELECT parent_event_id FROM events WHERE guild_id=? AND event_id=?)",
            (gid, gid, eid)
        )
        is_seasonal = parent_row and parent_row["type"] == "season"
        
        # Spotlight winners (user-only pings, never @everyone)
        spotlight = self.get_channel(guild, "spotlight")
        if spotlight:
            rows = await self.bot.db.fetchall(
                "SELECT user_id, score_total FROM event_contrib WHERE guild_id=? AND event_id=? ORDER BY score_total DESC LIMIT 3",
                (gid, eid)
            )
            if rows:
                pings = " ".join([f"<@{int(r['user_id'])}>" for r in rows])  # user pings only
                lines = []
                for i, r in enumerate(rows, start=1):
                    lines.append(f"**{i}.** <@{int(r['user_id'])}> — **{fmt(int(r['score_total']))} ES**")
                thumb = self._thumb(cfg, "BOSS_KILL__LAUGHING")
                
                # Use seasonal victory tone if applicable
                desc = "Top 3 finishers.\n" + "\n".join(lines)
                if is_seasonal and parent_row:
                    season_cfg = json.loads(parent_row["config_json"])
                    season_name = season_cfg.get("theme", "season")
                    # Get server stage for tone
                    stage = 2  # Default, you may want to calculate per-user
                    victory_line = get_seasonal_tone(season_name, "victory", stage) or get_seasonal_tone(season_name, f"{season_name}_victory", stage)
                    if victory_line:
                        desc = victory_line + "\n\n" + desc
                
                # Spotlight post is a system message (sent to channel, includes author)
                e = self._embed(None, desc + "\n᲼᲼", thumb_url=thumb)
                # _embed already includes author, so this is correct for system messages
                await spotlight.send(content=pings, embed=e)

        # Process seasonal finale victory rewards (badges, roles, private DMs)
        if is_seasonal and parent_row:
            season_cfg = json.loads(parent_row["config_json"])
            milestone_0 = next((m for m in season_cfg.get("milestones", []) if m.get("pct") == 0), None)
            if milestone_0:
                await self._process_seasonal_milestone_reward(guild, eid, milestone_0, season_cfg, is_finale=True)


    # =========================================================
    #  C) SEASONAL EVENT HELPERS
    # =========================================================
    
    async def _convert_seasonal_damage_weights_to_es(self, damage_weights: dict) -> dict:
        """Convert seasonal damage_weights to ES weights format.
        
        Seasonal config specifies damage directly:
        - 1 message = 10 dmg → msg weight = 10
        - 1 VC minute = 2 dmg → vc_min weight = 2  
        - 100 wagered coins = 20 dmg → wager_per = 100/20 = 5 (coins per ES/dmg)
        - 1 order = 40 dmg → order_complete = 40
        - 1 ritual = 40 dmg → ritual_complete = 40
        
        Example: wager_coins = 0.2 means 100 coins = 20 dmg
        So 5 coins = 1 dmg, meaning wager_per = 5
        """
        # Seasonal config: "wager_coins": 0.2 means 100 coins wagered = 20 dmg
        # Calculation: 100 coins * 0.2 = 20 dmg
        # Therefore: 1 dmg requires 100/20 = 5 coins
        # ES system uses wager_per = coins per ES (where ES = dmg)
        # So: wager_per = 5
        wager_coins_ratio = damage_weights.get("wager_coins", 0.2)
        dmg_from_100_coins = 100 * wager_coins_ratio  # e.g., 100 * 0.2 = 20
        wager_per = int(100 / max(1, dmg_from_100_coins))  # e.g., 100 / 20 = 5
        
        return {
            "msg": int(damage_weights.get("messages", 10)),
            "vc_min": int(damage_weights.get("vc_minutes", 2)),
            "wager_per": wager_per,
            "order_complete": int(damage_weights.get("orders", 40)),
            "ritual_complete": int(damage_weights.get("rituals", 40)),
        }

    async def _process_seasonal_milestone_reward(self, guild: discord.Guild, boss_eid: int, milestone: dict, season_cfg: dict, is_finale: bool = False):
        """Process seasonal milestone rewards (roles, badges, DMs, boosts, etc.)."""
        gid = guild.id
        rewards = milestone.get("rewards", {})
        milestone_key = milestone.get("key", "")
        
        # Get top participants for role/badge/DM rewards
        top_users = []
        if rewards.get("role") or rewards.get("badge") or rewards.get("private_dm"):
            limit = max(
                rewards.get("role", {}).get("top", 0),
                rewards.get("badge", {}).get("top", 0),
                rewards.get("private_dm", {}).get("top", 0),
                rewards.get("badge", {}).get("all") and 999 or 0,
            )
            if limit > 0:
                rows = await self.bot.db.fetchall(
                    "SELECT user_id, score_total FROM event_contrib WHERE guild_id=? AND event_id=? ORDER BY score_total DESC LIMIT ?",
                    (gid, boss_eid, limit)
                )
                top_users = [int(r["user_id"]) for r in rows]

        # Roles
        if "role" in rewards:
            role_info = rewards["role"]
            role_name = role_info.get("name", "")
            if role_name and top_users:
                # Create or get role
                role = discord.utils.get(guild.roles, name=role_name)
                if not role:
                    try:
                        role = await guild.create_role(name=role_name, mentionable=True)
                    except Exception:
                        pass
                if role:
                    count = role_info.get("count", len(top_users))
                    is_random = role_info.get("random", False)
                    users_to_role = top_users[:count] if not is_random else random.sample(top_users, min(count, len(top_users)))
                    for uid in users_to_role:
                        member = guild.get_member(uid)
                        if member and role not in member.roles:
                            try:
                                await member.add_roles(role)
                            except Exception:
                                pass

        # Badges (shop items - you'll need to integrate with shop system)
        # This is a placeholder - actual badge granting should integrate with your shop/inventory system
        if "badge" in rewards:
            badge_info = rewards["badge"]
            badge_name = badge_info.get("name", "")
            if badge_name:
                # TODO: Grant badge via shop/inventory system
                pass

        # Private DM sequences
        if "private_dm" in rewards:
            dm_info = rewards["private_dm"]
            dm_name = dm_info.get("name", "")
            top_count = dm_info.get("top", 10)
            if dm_name and top_users:
                season_name = season_cfg.get("theme", "")
                # Map DM names to tone pool keys
                dm_key_map = {
                    "Isla's Private Bloom": "private_bloom_dm",
                    "Isla's Private Inferno": "private_inferno_dm",
                    "Isla's Private Fall": "private_fall_dm",
                    "Isla's Private Thaw": "private_thaw_dm",
                }
                tone_key = dm_key_map.get(dm_name, "")
                if tone_key:
                    for uid in top_users[:top_count]:
                        member = guild.get_member(uid)
                        if member:
                            stage = 4  # Private DMs are stage 4 only
                            lines = SEASONAL_TONE_POOLS.get(tone_key, {}).get(stage, [])
                            if lines:
                                try:
                                    line = random.choice(lines)
                                    from utils.embed_utils import create_embed
                                    embed = create_embed(sanitize_isla_text(line), color="system", is_dm=True, is_system=False)
                                    await member.send(embed=embed)
                                except Exception:
                                    pass

        # Token boosts, shop discounts, etc. are handled via event state or config
        # These would need integration with the respective systems (casino, shop, etc.)

    async def _auto_start_seasonal_finale(self, guild: discord.Guild, season_event: dict):
        """Auto-start seasonal finale boss fight during finale week."""
        gid = guild.id
        season_cfg = json.loads(season_event["config_json"])
        finale_week = season_cfg.get("finale_week", 6)
        
        # Calculate current week
        start_ts = int(season_event["start_ts"])
        now = now_ts()
        elapsed_days = (now - start_ts) // 86400
        current_week = (elapsed_days // 7) + 1
        
        if current_week != finale_week:
            return
        
        # Check if finale boss already exists
        existing = await self._active_boss(gid)
        if existing:
            return
        
        # Start finale boss
        boss_name = season_cfg.get("boss_name", "Finale Boss")
        finale_name = season_cfg.get("finale_name", "Finale")
        hp_max = 20000  # Default, can be configured
        
        eid = await self._next_event_id(gid)
        start = now
        end = start + (7 * 86400)  # 7 days
        
        # Convert seasonal damage weights to ES weights
        damage_weights = season_cfg.get("damage_weights", {})
        es_weights = await self._convert_seasonal_damage_weights_to_es(damage_weights)
        
        boss_config = {
            "channels": season_cfg.get("channels", {k: self.ch_id(k) for k in DEFAULT_CHANNEL_KEYS}),
            "thumbs": season_cfg.get("thumbs", dict(DEFAULT_THUMBS)),
            "caps": dict(DEFAULT_BOSS_CAPS),
            "weights": es_weights,
            "milestones": season_cfg.get("milestones", []),
            "wrapper_scope_event_id": int(season_event["event_id"]),
            "season_theme": season_cfg.get("theme", ""),
        }
        
        await self.bot.db.execute(
            "INSERT INTO events(guild_id,event_id,type,parent_event_id,name,start_ts,end_ts,status,config_json,created_ts) "
            "VALUES(?,?,?,?,?,?,?,?,?,?)",
            (gid, eid, "boss", int(season_event["event_id"]), boss_name, start, end, "active", json.dumps(boss_config), now_ts())
        )
        
        await self._state_set(gid, eid, "hp_max", str(hp_max))
        await self._state_set(gid, eid, "hp_current", str(hp_max))
        await self._state_set(gid, eid, "phase", "1")
        await self._state_set(gid, eid, "milestones_unlocked", json.dumps({}))
        await self._state_set(gid, eid, "last_calc_ts", str(start))
        
        # Announce finale start with seasonal tone
        orders_ch = self.get_channel(guild, "orders")
        if orders_ch:
            season_theme = season_cfg.get("theme", "")
            stage = 2  # Default server stage
            thumb_key = f"{season_theme}_finale_start" if season_theme else "BOSS_START__DOMINANT"
            start_line = get_seasonal_tone(season_theme, "finale_start", stage) or get_seasonal_tone(season_theme, f"{season_theme}_finale_start", stage)
            thumb = self._thumb(boss_config, thumb_key)
            desc = (
                f"{start_line or f'{finale_name} started.'}\n"
                f"Boss: **{boss_name}**\n"
                f"Health: **100%** `{hp_bar(hp_max, hp_max)}`\n"
                "Contribute by being active.\n"
                "Check progress with /event.\n"
                "᲼᲼"
            )
            e = self._embed(finale_name, desc, thumb_url=thumb)
            await orders_ch.send(embed=e)

    async def _auto_start_holiday_week(self, guild: discord.Guild, holiday_cfg: dict, start_dt: datetime):
        """Auto-start a holiday week event."""
        gid = guild.id
        
        # Check for existing active wrapper
        existing = await self._active_wrapper(gid)
        if existing and existing.get("type") == "holiday_week":
            return  # Already have a holiday week active
        
        # Calculate end date
        duration_days = holiday_cfg.get("duration_days", 7)
        end_dt = start_dt + timedelta(days=duration_days)
        start_ts = int(start_dt.timestamp())
        end_ts = int(end_dt.timestamp())
        
        # Create holiday week wrapper event
        eid = await self._next_event_id(gid)
        holiday_config = {
            "id": holiday_cfg["id"],
            "channels": {k: self.ch_id(k) for k in DEFAULT_CHANNEL_KEYS},
            "thumbs": dict(DEFAULT_THUMBS),
            "token_name": holiday_cfg.get("token_name", "Tokens"),
            "theme": holiday_cfg.get("theme", ""),
            "duration_days": duration_days,
            "climax_day": holiday_cfg.get("climax_day", ""),
            "boss_name": holiday_cfg.get("boss_name", ""),
            "ritual_name": holiday_cfg.get("ritual_name", ""),
            "damage_weights": holiday_cfg.get("damage_weights", {}),
            "milestones": holiday_cfg.get("milestones", []),
            "easter_egg": holiday_cfg.get("easter_egg", {}),
            "special_roles": holiday_cfg.get("special_roles", []),
            "shop_items": holiday_cfg.get("shop_items", []),
            "isla_voice_start": holiday_cfg.get("isla_voice_start", {}),
        }
        
        await self.bot.db.execute(
            "INSERT INTO events(guild_id,event_id,type,parent_event_id,name,start_ts,end_ts,status,config_json,created_ts) "
            "VALUES(?,?,?,?,?,?,?,?,?,?)",
            (gid, eid, "holiday_week", None, holiday_cfg["name"], start_ts, end_ts, "active", json.dumps(holiday_config), now_ts())
        )
        
        # Start boss fight immediately for holiday weeks
        await self._start_holiday_boss(guild, eid, holiday_config, holiday_cfg)
        
        # Announce holiday week start
        orders_ch = self.get_channel(guild, "orders")
        if orders_ch:
            thumb = self._thumb(holiday_config, "HOLIDAY_LAUNCH__THEMED_DOMINANT")
            desc = (
                f"**{holiday_cfg['name']}** has begun.\n"
                f"Duration: **{duration_days} days**\n"
                f"Climax: **{holiday_cfg.get('climax_day', 'Day 7')}**\n"
                f"Check progress with /event.\n"
                "᲼᲼"
            )
            e = self._embed("Holiday Week Started", desc, thumb_url=thumb)
            await orders_ch.send(embed=e)

    async def _start_holiday_boss(self, guild: discord.Guild, parent_eid: int, holiday_config: dict, holiday_cfg: dict, hp_max: int = 15000):
        """Start the boss fight for a holiday week."""
        gid = guild.id
        boss_name = holiday_cfg.get("boss_name", "Holiday Boss")
        
        boss_eid = await self._next_event_id(gid)
        start = now_ts()
        end = start + (7 * 86400)  # 7 days
        
        # Convert damage weights to ES weights
        damage_weights = holiday_config.get("damage_weights", {})
        es_weights = await self._convert_seasonal_damage_weights_to_es(damage_weights)
        
        boss_config = {
            "channels": holiday_config.get("channels", {k: self.ch_id(k) for k in DEFAULT_CHANNEL_KEYS}),
            "thumbs": holiday_config.get("thumbs", dict(DEFAULT_THUMBS)),
            "caps": dict(DEFAULT_BOSS_CAPS),
            "weights": es_weights,
            "milestones": holiday_config.get("milestones", []),
            "wrapper_scope_event_id": parent_eid,
            "holiday_theme": holiday_config.get("theme", ""),
        }
        
        await self.bot.db.execute(
            "INSERT INTO events(guild_id,event_id,type,parent_event_id,name,start_ts,end_ts,status,config_json,created_ts) "
            "VALUES(?,?,?,?,?,?,?,?,?,?)",
            (gid, boss_eid, "boss", parent_eid, boss_name, start, end, "active", json.dumps(boss_config), now_ts())
        )
        
        await self._state_set(gid, boss_eid, "hp_max", str(hp_max))
        await self._state_set(gid, boss_eid, "hp_current", str(hp_max))
        await self._state_set(gid, boss_eid, "phase", "1")
        await self._state_set(gid, boss_eid, "milestones_unlocked", json.dumps({}))
        await self._state_set(gid, boss_eid, "last_calc_ts", str(start))
        
        # Announce boss start in #orders
        orders_ch = self.get_channel(guild, "orders")
        if orders_ch:
            thumb = self._thumb(boss_config, "HOLIDAY_BOSS__THEMED_INTENSE")
            desc = (
                f"Boss fight: **{boss_name}**\n"
                f"Health: **100%** `{hp_bar(hp_max, hp_max)}`\n"
                "Contribute by being active.\n"
                "Check progress with /event boss.\n"
                "᲼᲼"
            )
            e = self._embed("Boss Fight Started", desc, thumb_url=thumb)
            await orders_ch.send(embed=e)

    async def _announce_seasonal_milestone(self, guild: discord.Guild, boss_eid: int, milestone: dict, boss_cfg: dict):
        """Announce seasonal milestone unlock with appropriate tone."""
        gid = guild.id
        
        # Check if this boss has a seasonal parent
        parent_row = await self.bot.db.fetchone(
            "SELECT type, config_json FROM events WHERE guild_id=? AND event_id=(SELECT parent_event_id FROM events WHERE guild_id=? AND event_id=?)",
            (gid, gid, boss_eid)
        )
        if not parent_row or parent_row["type"] != "season":
            return
        
        season_cfg = json.loads(parent_row["config_json"])
        season_theme = season_cfg.get("theme", "")
        if not season_theme:
            return
        
        spotlight = self.get_channel(guild, "spotlight")
        if not spotlight:
            return
        
        # Get milestone tone
        stage = 2  # Default server stage
        milestone_line = get_seasonal_tone(season_theme, "milestone", stage) or get_seasonal_tone(season_theme, f"{season_theme}_milestone", stage)
        milestone_name = milestone.get("name", "Milestone")
        
        desc = milestone_line or f"**{milestone_name}** unlocked." if milestone_line else f"**{milestone_name}** unlocked."
        desc += f"\nCheck /event_claim to claim rewards.\n᲼᲼"
        
        thumb = self._thumb(boss_cfg, "THUMB_INTRIGUED")
        e = self._embed(None, desc, thumb_url=thumb)
        await spotlight.send(embed=e)
    
    # =========================================================
    #  D) /event GROUP COMMANDS (from event_group.py)
    # =========================================================
    
    async def _get_active_events(self, gid: int) -> list[dict]:
        """Get list of active events (for DP system)."""
        return await self.bot.db.fetchall(
            "SELECT event_id, event_type, name, token_name, start_ts, end_ts, climax_ts FROM events WHERE guild_id=? AND is_active=1",
            (gid,)
        )
    
    async def _pick_current_event(self, gid: int) -> dict | None:
        """Pick current event (priority: holiday_week > season_era > others)."""
        rows = await self._get_active_events(gid)
        if not rows:
            return None
        for r in rows:
            if str(r["event_type"]) == "holiday_week":
                return dict(r)
        for r in rows:
            if str(r["event_type"]) == "season_era":
                return dict(r)
        return dict(rows[0]) if rows else None
    
    async def _cmd_event_info(self, interaction: discord.Interaction):
        """/event info - View current event info."""
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild_id
        if not gid:
            embed = create_embed("Server only.", color="warning", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)
        
        ev = await self._pick_current_event(gid)
        if not ev:
            return await interaction.followup.send(embed=self._embed("No event going on right now.\n᲼᲼", None, thumb_url=self.icon), ephemeral=True)
        
        desc = (
            "Hey.\n\n"
            f"Current event:\n**{ev['name']}**\n\n"
            f"Type: **{ev['event_type']}**\n"
            f"Token: **{ev['token_name']}**\n"
            "᲼᲼"
        )
        e = self._embed(desc, "Event Info", thumb_url=self.icon)
        e.add_field(
            name="Commands",
            value=("• `/event boss`\n• `/event progress`\n• `/event leaderboard`\n• `/event ritual`\n• `/event shop`\n"),
            inline=False
        )
        e.set_footer(text="If this looks empty, it means people haven't moved yet.")
        await interaction.followup.send(embed=e, ephemeral=True)
    
    async def _cmd_event_boss(self, interaction: discord.Interaction):
        """/event boss - View the current event boss."""
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild_id
        if not gid:
            embed = create_embed("Server only.", color="warning", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)
        
        ev = await self._pick_current_event(gid)
        if not ev:
            return await interaction.followup.send(embed=self._embed("No event going on right now.\n᲼᲼", None, thumb_url=self.icon), ephemeral=True)
        
        event_id = str(ev["event_id"])
        boss = await self.bot.db.fetchone(
            "SELECT boss_name, hp_current, hp_max FROM event_boss WHERE guild_id=? AND event_id=?",
            (gid, event_id)
        )
        if not boss:
            return await interaction.followup.send(embed=self._embed("No boss is attached to the current event.\n᲼᲼", "Boss", thumb_url=self.icon), ephemeral=True)
        
        boss_name = str(boss["boss_name"])
        hp_cur = int(boss["hp_current"])
        hp_max = max(1, int(boss["hp_max"]))
        hp_pct = max(0, min(100, int((hp_cur / hp_max) * 100)))
        
        today = uk_day_ymd(now_ts())
        top_today = await self.bot.db.fetchall(
            "SELECT user_id, dp_cached AS pts FROM event_user_day WHERE guild_id=? AND event_id=? AND day_ymd=? ORDER BY pts DESC LIMIT 3",
            (gid, event_id, today)
        )
        top_overall = await self.bot.db.fetchall(
            "SELECT user_id, SUM(dp_cached) AS pts FROM event_user_day WHERE guild_id=? AND event_id=? GROUP BY user_id ORDER BY pts DESC LIMIT 10",
            (gid, event_id)
        )
        
        recent_damage = None
        try:
            cutoff = now_ts() - (6 * 3600)
            r = await self.bot.db.fetchone(
                "SELECT COALESCE(SUM(damage_total), 0) AS dmg FROM event_boss_tick WHERE guild_id=? AND event_id=? AND ts >= ?",
                (gid, event_id, cutoff)
            )
            recent_damage = int(float(r["dmg"] or 0))
        except Exception:
            recent_damage = None
        
        def line_for(uid: int, pts: float) -> str:
            m = interaction.guild.get_member(int(uid))
            name = m.display_name if m else f"User {uid}"
            return f"{name} — {fmt_int(pts)}"
        
        today_lines = [f"{i}) {line_for(int(r['user_id']), float(r['pts'] or 0))}" for i, r in enumerate(top_today, start=1)]
        overall_lines = [f"{i}) {line_for(int(r['user_id']), float(r['pts'] or 0))}" for i, r in enumerate(top_overall, start=1)]
        if not today_lines:
            today_lines = ["No data yet."]
        if not overall_lines:
            overall_lines = ["No data yet."]
        
        desc = f"**{boss_name}**\nHP: **{fmt_int(hp_cur)} / {fmt_int(hp_max)}** (**{hp_pct}%**)\n"
        if recent_damage is not None:
            desc += f"Recent damage (6h): **{fmt_int(recent_damage)}**\n"
        desc += "᲼᲼"
        
        e = self._embed(desc, f"{ev['name']} Boss", thumb_url=self.icon)
        e.add_field(name="Top Damage Today", value="\n".join(today_lines), inline=False)
        e.add_field(name="Top Damage Overall", value="\n".join(overall_lines[:10]), inline=False)
        e.set_footer(text="Use /event leaderboard for the full ranking.")
        await interaction.followup.send(embed=e, ephemeral=True)
    
    async def _cmd_event_progress(self, interaction: discord.Interaction):
        """/event progress - View boss progress and your contribution today."""
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild_id
        uid = interaction.user.id
        if not gid:
            embed = create_embed("Server only.", color="warning", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)
        
        ev = await self._pick_current_event(gid)
        if not ev:
            return await interaction.followup.send(embed=self._embed("No event going on right now.\n᲼᲼", None, thumb_url=self.icon), ephemeral=True)
        
        event_id = str(ev["event_id"])
        today = uk_day_ymd(now_ts())
        
        boss = await self.bot.db.fetchone(
            "SELECT boss_name, hp_current, hp_max FROM event_boss WHERE guild_id=? AND event_id=?",
            (gid, event_id)
        )
        me = await self.bot.db.fetchone(
            "SELECT msg_count, vc_minutes, vc_reduced_minutes, ritual_done, tokens_spent, casino_wager, casino_net, dp_cached FROM event_user_day WHERE guild_id=? AND event_id=? AND user_id=? AND day_ymd=?",
            (gid, event_id, uid, today)
        )
        
        desc = "Progress check.\n᲼᲼"
        e = self._embed(desc, "Event Progress", thumb_url=self.icon)
        
        if boss:
            hp_cur = int(boss["hp_current"])
            hp_max = max(1, int(boss["hp_max"]))
            hp_pct = max(0, min(100, int((hp_cur / hp_max) * 100)))
            e.add_field(
                name="Boss",
                value=f"{boss['boss_name']}\nHP: {fmt_int(hp_cur)}/{fmt_int(hp_max)} ({hp_pct}%)",
                inline=False
            )
        
        if me:
            approx = compute_dp(
                int(me["msg_count"] or 0),
                int(me["vc_minutes"] or 0),
                int(me["vc_reduced_minutes"] or 0),
                int(me["ritual_done"] or 0),
                int(me["tokens_spent"] or 0),
                int(me["casino_wager"] or 0),
                int(me["casino_net"] or 0),
            )
            e.add_field(
                name="You Today",
                value=(
                    f"Damage: **{fmt_int(approx)}**\n"
                    f"Messages: {fmt_int(me['msg_count'] or 0)}\n"
                    f"Voice: {fmt_int(me['vc_minutes'] or 0)}m (+{fmt_int(me['vc_reduced_minutes'] or 0)}m reduced)\n"
                    f"Ritual: {'Done' if int(me['ritual_done'] or 0) else 'Not yet'}\n"
                    f"Tokens spent: {fmt_int(me['tokens_spent'] or 0)}\n"
                ),
                inline=False
            )
        else:
            e.add_field(name="You Today", value="No activity recorded yet.\nSay something or hop in voice.\n᲼᲼", inline=False)
        
        await interaction.followup.send(embed=e, ephemeral=True)
    
    async def _cmd_event_leaderboard(self, interaction: discord.Interaction):
        """/event leaderboard - View event leaderboards."""
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild_id
        if not gid:
            embed = create_embed("Server only.", color="warning", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)
        
        ev = await self._pick_current_event(gid)
        if not ev:
            return await interaction.followup.send(embed=self._embed("No event going on right now.\n᲼᲼", None, thumb_url=self.icon), ephemeral=True)
        
        event_id = str(ev["event_id"])
        today = uk_day_ymd(now_ts())
        
        top_overall = await self.bot.db.fetchall(
            "SELECT user_id, SUM(dp_cached) AS pts FROM event_user_day WHERE guild_id=? AND event_id=? GROUP BY user_id ORDER BY pts DESC LIMIT 10",
            (gid, event_id)
        )
        top_today = await self.bot.db.fetchall(
            "SELECT user_id, dp_cached AS pts FROM event_user_day WHERE guild_id=? AND event_id=? AND day_ymd=? ORDER BY pts DESC LIMIT 10",
            (gid, event_id, today)
        )
        
        def line_for(rank: int, uid: int, pts: float) -> str:
            m = interaction.guild.get_member(uid)
            name = m.display_name if m else f"User {uid}"
            return f"{rank}) {name} — {fmt_int(pts)}"
        
        overall_lines = [line_for(i, int(r["user_id"]), float(r["pts"] or 0)) for i, r in enumerate(top_overall, start=1)]
        today_lines = [line_for(i, int(r["user_id"]), float(r["pts"] or 0)) for i, r in enumerate(top_today, start=1)]
        
        if not overall_lines:
            overall_lines = ["No data yet."]
        if not today_lines:
            today_lines = ["No data yet."]
        
        e = self._embed("Here's the ranking.\n᲼᲼", f"{ev['name']} Leaderboard", thumb_url=self.icon)
        e.add_field(name="Top Overall", value="\n".join(overall_lines), inline=False)
        e.add_field(name="Top Today", value="\n".join(today_lines), inline=False)
        await interaction.followup.send(embed=e, ephemeral=True)
    
    async def _cmd_event_ritual(self, interaction: discord.Interaction):
        """/event ritual - View today's ritual info."""
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild_id
        if not gid:
            embed = create_embed("Server only.", color="warning", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)
        
        ev = await self._pick_current_event(gid)
        if not ev:
            return await interaction.followup.send(embed=self._embed("No event going on right now.\n᲼᲼", None, thumb_url=self.icon), ephemeral=True)
        
        e = self._embed(
            "Ritual is available.\n\nIf you have a ritual task posted, complete it once today.\nThen come back and check `/event progress`.\n᲼᲼",
            "Ritual",
            thumb_url=self.icon
        )
        await interaction.followup.send(embed=e, ephemeral=True)
    
    async def _cmd_event_shop(self, interaction: discord.Interaction):
        """/event shop - View the event shop info."""
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild_id
        if not gid:
            embed = create_embed("Server only.", color="warning", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)
        
        ev = await self._pick_current_event(gid)
        if not ev:
            return await interaction.followup.send(embed=self._embed("No event going on right now.\n᲼᲼", None, thumb_url=self.icon), ephemeral=True)
        
        e = self._embed("Event shop is open while the event is active.\n\nSpend event tokens on limited items.\n᲼᲼", "Event Shop", thumb_url=self.icon)
        await interaction.followup.send(embed=e, ephemeral=True)
    
    # =========================================================
    #  E) DP SYSTEM TASK LOOPS (from event_scheduler.py)
    # =========================================================
    
    @tasks.loop(seconds=60)
    async def flush_loop(self):
        """Flush message and voice counters."""
        await self.bot.wait_until_ready()
        data_cog = self.bot.get_cog("Data")
        if data_cog:
            try:
                await data_cog.flush_message_counters(self.bot.db)
                await data_cog.flush_voice_counters()
            except Exception:
                pass
    
    @flush_loop.before_loop
    async def before_flush_loop(self):
        await self.bot.wait_until_ready()
    
    @tasks.loop(seconds=30)
    async def boss_dp_loop(self):
        """Boss tick loop using DP calculation."""
        await self.bot.wait_until_ready()
        now = now_ts()
        
        for guild in self.bot.guilds:
            gid = guild.id
            active_event_ids = await self.get_active_event_ids(gid)
            if not active_event_ids:
                continue
            
            for event_id in active_event_ids:
                await self._boss_tick_for_event(guild, gid, event_id, now)
    
    @boss_dp_loop.before_loop
    async def before_boss_dp_loop(self):
        await self.bot.wait_until_ready()
    
    async def _boss_tick_for_event(self, guild: discord.Guild, gid: int, event_id: str, now: int):
        """Process boss tick for DP system."""
        boss = await self.bot.db.fetchone(
            "SELECT boss_name, hp_current, hp_max, last_tick_ts, last_announce_hp_bucket FROM event_boss WHERE guild_id=? AND event_id=?",
            (gid, event_id)
        )
        if not boss:
            return
        
        last_tick = int(boss["last_tick_ts"] or 0)
        rows = await self.bot.db.fetchall(
            "SELECT user_id, day_ymd, msg_count, vc_minutes, vc_reduced_minutes, ritual_done, tokens_spent, casino_wager, casino_net, dp_cached FROM event_user_day WHERE guild_id=? AND event_id=? AND last_update_ts > ?",
            (gid, event_id, last_tick)
        )
        
        if not rows:
            await self.bot.db.execute("UPDATE event_boss SET last_tick_ts=? WHERE guild_id=? AND event_id=?", (now, gid, event_id))
            return
        
        total_delta = 0.0
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
                "UPDATE event_user_day SET dp_cached=? WHERE guild_id=? AND event_id=? AND user_id=? AND day_ymd=?",
                (new_dp, gid, event_id, int(r["user_id"]), str(r["day_ymd"]))
            )
        
        hp_cur = int(boss["hp_current"])
        hp_new = max(0, hp_cur - int(total_delta))
        
        await self.bot.db.execute(
            "UPDATE event_boss SET hp_current=?, last_tick_ts=? WHERE guild_id=? AND event_id=?",
            (hp_new, now, gid, event_id)
        )
        
        await self._maybe_milestone_post(guild, gid, event_id, boss["boss_name"], int(boss["hp_max"]), hp_new, int(boss["last_announce_hp_bucket"]))
    
    async def _maybe_milestone_post(self, guild: discord.Guild, gid: int, event_id: str, boss_name: str, hp_max: int, hp_cur: int, last_bucket: int):
        """Announce milestone when crossing HP thresholds."""
        if hp_max <= 0:
            return
        hp_percent = int((hp_cur / hp_max) * 100)
        
        buckets = [80, 60, 40, 20, 0]
        hit_bucket = None
        for b in buckets:
            if hp_percent <= b:
                hit_bucket = b
        if hit_bucket is None:
            return
        
        if hit_bucket >= last_bucket:
            return
        
        await self.bot.db.execute(
            "UPDATE event_boss SET last_announce_hp_bucket=? WHERE guild_id=? AND event_id=?",
            (hit_bucket, gid, event_id)
        )
        
        orders = guild.get_channel(self.orders_channel_id) if self.orders_channel_id else None
        if not isinstance(orders, discord.TextChannel):
            return
        
        desc = f"Good.\n\n{boss_name} is at **{hit_bucket}%**.\nKeep going.\n᲼᲼"
        await orders.send(embed=self._embed(desc, "Milestone", thumb_url=self.icon))
    
    # =========================================================
    #  F) /calendar GROUP COMMANDS (from custom_events_group.py)
    # =========================================================
    
    def _is_mod(self, m: discord.Member) -> bool:
        """Check if member is a mod."""
        p = m.guild_permissions
        return p.manage_guild or p.manage_events or p.administrator
    
    async def _cmd_calendar_create(self, interaction: discord.Interaction):
        """/calendar create - Interactive event wizard."""
        if not interaction.guild_id or not interaction.guild:
            embed = create_embed("Server only.", color="warning", is_dm=False, is_system=False)
            return await interaction.response.send_message(embed=embed, ephemeral=True)
        if not isinstance(interaction.user, discord.Member) or not self._is_mod(interaction.user):
            return await interaction.response.send_message(embed=self._embed("Not for you.\n᲼᲼", "Event", thumb_url=self.icon), ephemeral=True)
        
        await interaction.response.send_modal(EventCreateModal(self.bot, interaction.channel_id))
    
    async def _cmd_calendar_list(self, interaction: discord.Interaction):
        """/calendar list - Upcoming events."""
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild_id
        if not gid:
            embed = create_embed("Server only.", color="warning", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)
        
        rows = await self.bot.db.fetchall(
            "SELECT event_id,title,start_ts,entry_cost FROM events_custom WHERE guild_id=? AND active=1 AND start_ts >= ? ORDER BY start_ts ASC LIMIT 10",
            (gid, now_ts())
        )
        if not rows:
            return await interaction.followup.send(embed=self._embed("No upcoming events.\n᲼᲼", "Events", thumb_url=self.icon), ephemeral=True)
        
        lines = []
        for r in rows:
            lines.append(f"**#{r['event_id']}** {r['title']} — <t:{int(r['start_ts'])}:R> — {fmt(int(r['entry_cost']))} Coins")
        
        e = self._embed("Upcoming.\n᲼᲼", "Events", thumb_url=self.icon)
        e.add_field(name="List", value="\n".join(lines), inline=False)
        e.set_footer(text="Join with /calendar join <event_id>")
        await interaction.followup.send(embed=e, ephemeral=True)
    
    async def _cmd_calendar_join(self, interaction: discord.Interaction, event_id: int):
        """/calendar join - Join event and get role."""
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild_id
        if not gid or not interaction.guild:
            embed = create_embed("Server only.", color="warning", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)
        
        ev = await self.bot.db.fetchone(
            "SELECT title,start_ts,channel_id,role_id,entry_cost,active FROM events_custom WHERE guild_id=? AND event_id=?",
            (gid, int(event_id))
        )
        if not ev or int(ev["active"]) != 1:
            return await interaction.followup.send(embed=self._embed("No such event.\n᲼᲼", "Event", thumb_url=self.icon), ephemeral=True)
        
        existing = await self.bot.db.fetchone(
            "SELECT 1 FROM events_custom_participants WHERE guild_id=? AND event_id=? AND user_id=?",
            (gid, int(event_id), interaction.user.id)
        )
        if existing:
            return await interaction.followup.send(embed=self._embed("You're already in.\n᲼᲼", "Event", thumb_url=self.icon), ephemeral=True)
        
        entry = int(ev["entry_cost"] or 0)
        if entry > 0:
            await ensure_wallet(self.bot.db, gid, interaction.user.id)
            w = await get_wallet(self.bot.db, gid, interaction.user.id)
            if w.coins < entry:
                return await interaction.followup.send(embed=self._embed("You can't cover the entry cost.\n᲼᲼", "Event", thumb_url=self.icon), ephemeral=True)
            await add_coins(self.bot.db, gid, interaction.user.id, -entry, kind="event_entry", reason=f"event #{event_id}")
        
        await self.bot.db.execute(
            "INSERT INTO events_custom_participants(guild_id,event_id,user_id,joined_ts) VALUES(?,?,?,?)",
            (gid, int(event_id), interaction.user.id, now_ts())
        )
        
        role_id = int(ev["role_id"] or 0)
        if role_id:
            role = interaction.guild.get_role(role_id)
            if role:
                try:
                    await interaction.user.add_roles(role, reason="event join")
                except Exception:
                    pass
        
        e = self._embed(
            f"Joined.\n\nEvent **#{event_id}** — {ev['title']}\nStarts: <t:{int(ev['start_ts'])}:R>\n᲼᲼",
            "Event",
            thumb_url=self.icon
        )
        await interaction.followup.send(embed=e, ephemeral=True)
    
    async def _cmd_calendar_leave(self, interaction: discord.Interaction, event_id: int):
        """/calendar leave - Leave an event."""
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild_id
        if not gid or not interaction.guild:
            embed = create_embed("Server only.", color="warning", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)
        
        ev = await self.bot.db.fetchone(
            "SELECT role_id,active FROM events_custom WHERE guild_id=? AND event_id=?",
            (gid, int(event_id))
        )
        if not ev or int(ev["active"]) != 1:
            return await interaction.followup.send(embed=self._embed("No such event.\n᲼᲼", "Event", thumb_url=self.icon), ephemeral=True)
        
        await self.bot.db.execute(
            "DELETE FROM events_custom_participants WHERE guild_id=? AND event_id=? AND user_id=?",
            (gid, int(event_id), interaction.user.id)
        )
        
        role_id = int(ev["role_id"] or 0)
        if role_id:
            role = interaction.guild.get_role(role_id)
            if role:
                try:
                    await interaction.user.remove_roles(role, reason="event leave")
                except Exception:
                    pass
        
        e = self._embed("Removed.\n᲼᲼", "Event", thumb_url=self.icon)
        await interaction.followup.send(embed=e, ephemeral=True)


# EventCreateModal for /calendar create
class EventCreateModal(discord.ui.Modal, title="Create Event"):
    title_in = discord.ui.TextInput(label="Title", max_length=80)
    start_in = discord.ui.TextInput(label="Start (UK): 'in 2h' or 'YYYY-MM-DD HH:MM'", max_length=32)
    desc_in = discord.ui.TextInput(label="Description", style=discord.TextStyle.long, required=False, max_length=1000)
    entry_in = discord.ui.TextInput(label="Entry Cost (Coins)", default="0", max_length=10)
    role_in = discord.ui.TextInput(label="Role ID (optional)", required=False, max_length=24)
    
    def __init__(self, bot: commands.Bot, channel_id: int):
        super().__init__()
        self.bot = bot
        self.channel_id = channel_id
    
    async def on_submit(self, interaction: discord.Interaction):
        gid = interaction.guild_id
        if not gid:
            embed = create_embed("Server only.", color="warning", is_dm=False, is_system=False)
            return await interaction.response.send_message(embed=embed, ephemeral=True)
        
        start_ts = parse_when_to_ts(str(self.start_in.value))
        if start_ts <= now_ts():
            return await interaction.response.send_message(embed=isla_embed_util("Bad start time.\n᲼᲼", title="Event Create"), ephemeral=True)
        
        try:
            entry_cost = max(0, int(str(self.entry_in.value).strip()))
        except Exception:
            entry_cost = 0
        
        role_id = 0
        if str(self.role_in.value).strip():
            try:
                role_id = int(str(self.role_in.value).strip())
            except Exception:
                role_id = 0
        
        await self.bot.db.execute(
            "INSERT INTO events_custom(guild_id,title,description,start_ts,end_ts,channel_id,role_id,entry_cost,reward_coins,max_slots,created_by,created_ts,active) VALUES(?,?,?,?,0,?,?,?,?,0,?,?,1)",
            (gid, str(self.title_in.value), str(self.desc_in.value or ""), int(start_ts), int(self.channel_id), int(role_id), int(entry_cost), 0, int(interaction.user.id), now_ts())
        )
        
        row = await self.bot.db.fetchone("SELECT MAX(event_id) AS eid FROM events_custom WHERE guild_id=?", (gid,))
        eid = int(row["eid"] or 0)
        
        e = isla_embed_util(
            f"Event created.\n\n**#{eid}** — {self.title_in.value}\nStarts: {human_eta(start_ts)}\nEntry: **{fmt(entry_cost)} Coins**\n᲼᲼",
            title="Event"
        )
        await interaction.response.send_message(embed=e, ephemeral=True)


async def setup(bot: commands.Bot):
    cog = EventSystem(bot)
    await bot.add_cog(cog)
    
    # Register command groups with conflict handling
    bot.tree.remove_command("event", guild=None)
    bot.tree.remove_command("calendar", guild=None)
    try:
        bot.tree.add_command(cog.event, override=True)
        bot.tree.add_command(cog.calendar, override=True)
    except Exception:
        pass
