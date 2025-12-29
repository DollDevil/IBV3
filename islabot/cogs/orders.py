"""
Orders Cog
Consolidates: orders, orders_group, tributes
"""

from __future__ import annotations

import json
import random
import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import timedelta, datetime
from zoneinfo import ZoneInfo

from core.utility import now_ts, now_local, fmt
from core.orders import ORDER_TONES, RITUAL_EXTRA_TONES, TONE_POOLS, PERSONAL_TEMPLATES, RITUAL_TEMPLATES, weighted_choice
from core.personality import sanitize_isla_text, isla_embed as core_isla_embed
from utils.embed_utils import create_embed
from utils.uk_time import uk_day_ymd
from utils.economy import add_coins, ensure_wallet, get_wallet

UK_TZ = ZoneInfo("Europe/London")

STYLE1_THUMBS = [
    "https://i.imgur.com/5nsuuCV.png",
    "https://i.imgur.com/8qQkq0p.png",
    "https://i.imgur.com/rcgIEtj.png",
    "https://i.imgur.com/sGDoIDA.png",
    "https://i.imgur.com/qC0MOZN.png",
]

STYLE1_NEUTRAL = "https://i.imgur.com/9oUjOQQ.png"
ISLA_ICON = "https://i.imgur.com/5nsuuCV.png"


def day_key_uk() -> str:
    t = now_local()
    return f"{t.year}-{t.month:02d}-{t.day:02d}"


def stage_from_stats(obedience: int, lce: int) -> int:
    score = obedience + (lce * 2)
    if score < 800:
        return 0
    if score < 2500:
        return 1
    if score < 8000:
        return 2
    if score < 20000:
        return 3
    return 4


def pick(pool: dict, key: str, stage: int, fallback_pool: dict | None = None) -> str:
    stage = max(0, min(4, stage))
    arr = pool.get(key, {}).get(stage) or pool.get(key, {}).get(2)
    if not arr and fallback_pool:
        arr = fallback_pool.get(key, {}).get(stage) or fallback_pool.get(key, {}).get(2)
    if not arr:
        arr = ["..."]
    return random.choice(arr)


def build_order_embed(icon_url: str, title: str, order_desc: str, coins: int, obedience: int,
                      duration: str, slots_remaining: int, max_slots: int, hint_channel: str, order_id: int) -> discord.Embed:
    e = discord.Embed(title=title, description=sanitize_isla_text(order_desc))
    e.set_author(name="Isla", icon_url=icon_url)
    e.set_thumbnail(url=random.choice(STYLE1_THUMBS))
    e.add_field(name="Reward", value=f"{coins} Coins • {obedience} Obedience", inline=False)
    e.add_field(name="Time Limit", value=duration, inline=True)
    e.add_field(name="Slots", value=f"{slots_remaining}/{max_slots}", inline=True)
    e.add_field(name="Complete In", value=hint_channel, inline=False)
    e.set_footer(text=f"Accept with /order_accept {order_id}")
    return e


def isla_embed_simple(desc: str, title: str | None = None, thumb: str | None = None) -> discord.Embed:
    """Helper for orders_group style embeds"""
    e = discord.Embed(title=title, description=desc)
    e.set_author(name="Isla", icon_url=ISLA_ICON)
    e.set_thumbnail(url=thumb or STYLE1_NEUTRAL)
    return e


async def ensure_obed(db, gid: int, uid: int):
    await db.execute(
        "INSERT OR IGNORE INTO obedience_profile(guild_id,user_id,obedience,streak_days,last_streak_ymd,mercy_uses,forgive_tokens,last_penalty_ts) VALUES(?,?,0,0,'',0,0,0)",
        (gid, uid)
    )


async def add_obed(db, gid: int, uid: int, delta: int):
    await ensure_obed(db, gid, uid)
    await db.execute(
        "UPDATE obedience_profile SET obedience = obedience + ? WHERE guild_id=? AND user_id=?",
        (int(delta), gid, uid)
    )


async def maybe_advance_streak(db, gid: int, uid: int):
    """Streak advances when user completes at least one order that day."""
    await ensure_obed(db, gid, uid)
    today = uk_day_ymd(now_ts())
    row = await db.fetchone(
        "SELECT streak_days,last_streak_ymd FROM obedience_profile WHERE guild_id=? AND user_id=?",
        (gid, uid)
    )
    streak = int(row["streak_days"] or 0)
    last = str(row["last_streak_ymd"] or "")

    if last == today:
        return streak

    # if last was yesterday, +1 else reset to 1
    dt_today = datetime.fromisoformat(today).replace(tzinfo=UK_TZ).date()
    dt_last = None
    try:
        dt_last = datetime.fromisoformat(last).replace(tzinfo=UK_TZ).date()
    except Exception:
        dt_last = None

    if dt_last and dt_last == (dt_today - timedelta(days=1)):
        streak += 1
    else:
        streak = 1

    await db.execute(
        "UPDATE obedience_profile SET streak_days=?, last_streak_ymd=? WHERE guild_id=? AND user_id=?",
        (streak, today, gid, uid)
    )
    return streak


class Orders(commands.Cog):
    """
    Consolidated Orders Cog
    Merges orders.py, orders_group.py, and tributes.py
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.icon = ISLA_ICON
        
        # /orders group for catalog-based orders
        self.orders_group = app_commands.Group(name="orders", description="Orders & streaks")
        self._register_orders_group()
        
        # Start task loops
        self.order_tick.start()
        self.ritual_scheduler.start()

    def cog_unload(self):
        self.order_tick.cancel()
        self.ritual_scheduler.cancel()

    # ------------------ channel enforcement ------------------
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Enforce spam channel for interactive commands. Staff bypass."""
        if not interaction.guild or not interaction.channel:
            return True

        # Staff bypass
        if isinstance(interaction.user, discord.Member):
            if interaction.user.guild_permissions.manage_guild or interaction.user.guild_permissions.administrator:
                return True

        # Allow /orders, /order_view, /order_personal, /allin_progress anywhere (they're ephemeral)
        if interaction.command and interaction.command.name in ("orders", "order_view", "order_personal", "allin_progress"):
            return True

        spam_id = self._spam_ch()
        if spam_id and interaction.channel_id != spam_id:
            try:
                await interaction.response.send_message(
                    f"Use <#{spam_id}> for that.",
                    ephemeral=True
                )
            except Exception:
                pass
            return False

        return True

    # ------------------ helpers ------------------
    async def _user_stage(self, gid: int, uid: int) -> int:
        row = await self.bot.db.fetchone("SELECT obedience,lce FROM users WHERE guild_id=? AND user_id=?", (gid, uid))
        obedience = int(row["obedience"]) if row else 0
        lce = int(row["lce"]) if row else 0
        return stage_from_stats(obedience, lce)

    async def _consent_ok(self, gid: int, uid: int) -> bool:
        """Check if user has consent (for tributes)"""
        row = await self.bot.db.fetchone(
            "SELECT verified_18, consent_ok FROM consent WHERE guild_id=? AND user_id=?",
            (gid, uid),
        )
        return bool(row and int(row["verified_18"]) == 1 and int(row["consent_ok"]) == 1)

    async def _next_order_id(self, gid: int) -> int:
        row = await self.bot.db.fetchone("SELECT value FROM order_system_state WHERE guild_id=? AND key='order_seq'", (gid,))
        if not row:
            await self.bot.db.execute("INSERT INTO order_system_state(guild_id,key,value) VALUES(?,?,?)", (gid, "order_seq", "1000"))
            return 1000
        n = int(row["value"])
        n += 1
        await self.bot.db.execute("UPDATE order_system_state SET value=? WHERE guild_id=? AND key='order_seq'", (str(n), gid))
        return n

    def _orders_ch(self) -> int:
        return int(self.bot.cfg.get("channels", "orders", default=0) or 0)

    def _spam_ch(self) -> int:
        return int(self.bot.cfg.get("channels", "spam", default=0) or 0)

    def _spotlight_ch(self) -> int:
        return int(self.bot.cfg.get("channels", "spotlight", default=0) or 0)

    async def _post_orders_announce(self, guild: discord.Guild, text: str, embed: discord.Embed):
        ch = guild.get_channel(self._orders_ch())
        if isinstance(ch, discord.TextChannel):
            # NO @everyone. No ping by default in #orders.
            await ch.send(content="", embed=embed)

    async def _slots_remaining(self, gid: int, order_id: int) -> tuple[int, int]:
        row = await self.bot.db.fetchone("SELECT max_slots, slots_taken FROM orders WHERE guild_id=? AND order_id=?", (gid, order_id))
        if not row:
            return (0, 0)
        max_slots = int(row["max_slots"])
        taken = int(row["slots_taken"])
        return (max(0, max_slots - taken), max_slots)

    async def _update_stats_on_complete(self, gid: int, uid: int, stage: int) -> tuple[int, bool]:
        # streak logic: one completion/day increases streak; missing a day breaks when next completes
        dk = day_key_uk()
        await self.bot.db.execute(
            "INSERT OR IGNORE INTO order_stats(guild_id,user_id,completed_total,failed_total,current_streak,best_streak,last_complete_day_key,last_action_ts)"
            " VALUES(?,?,?,?,?,?,?,?)",
            (gid, uid, 0, 0, 0, 0, "", now_ts())
        )
        s = await self.bot.db.fetchone("SELECT current_streak,best_streak,last_complete_day_key FROM order_stats WHERE guild_id=? AND user_id=?", (gid, uid))
        cur = int(s["current_streak"])
        best = int(s["best_streak"])
        last = str(s["last_complete_day_key"] or "")

        milestone = False

        if last == dk:
            # already counted today
            pass
        else:
            # if last was yesterday (UK), streak continues; else resets to 1
            t = now_local()
            yesterday = t - timedelta(days=1)
            yk = f"{yesterday.year}-{yesterday.month:02d}-{yesterday.day:02d}"
            cur = (cur + 1) if last == yk else 1
            if cur > best:
                best = cur
            await self.bot.db.execute(
                "UPDATE order_stats SET current_streak=?, best_streak=?, last_complete_day_key=?, completed_total=completed_total+1, last_action_ts=?"
                " WHERE guild_id=? AND user_id=?",
                (cur, best, dk, now_ts(), gid, uid)
            )

            # milestone trigger (7, 14, 30)
            if cur in (7, 14, 30):
                milestone = True

        return cur, milestone

    async def _apply_rewards(self, gid: int, uid: int, coins: int, obedience: int):
        await self.bot.db.execute("UPDATE users SET coins=coins+?, obedience=obedience+? WHERE guild_id=? AND user_id=?",
                                  (int(coins), int(obedience), gid, uid))

    async def _apply_failure_penalty(self, gid: int, uid: int):
        # gentle, capped (not punishing)
        # SQLite doesn't support MAX in UPDATE, so we do it in Python
        row = await self.bot.db.fetchone("SELECT obedience FROM users WHERE guild_id=? AND user_id=?", (gid, uid))
        if row:
            current = int(row["obedience"])
            new_obedience = max(0, current - 3)
            await self.bot.db.execute("UPDATE users SET obedience=? WHERE guild_id=? AND user_id=?", (new_obedience, gid, uid))
        await self.bot.db.execute(
            "INSERT OR IGNORE INTO order_stats(guild_id,user_id,completed_total,failed_total,current_streak,best_streak,last_complete_day_key,last_action_ts)"
            " VALUES(?,?,?,?,?,?,?,?)",
            (gid, uid, 0, 0, 0, 0, "", now_ts())
        )
        await self.bot.db.execute("UPDATE order_stats SET failed_total=failed_total+1, last_action_ts=? WHERE guild_id=? AND user_id=?",
                                  (now_ts(), gid, uid))

    # ------------------ requirement checks ------------------
    async def _check_completion(self, guild_id: int, user_id: int, requirement: dict, accepted_ts: int, due_ts: int) -> tuple[bool, str]:
        rtype = requirement.get("type")

        # 1) messages (count since accepted) - use channel history
        if rtype == "messages":
            count = int(requirement.get("count", 1))
            channel_id = int(requirement.get("channel_id", 0) or 0)
            if channel_id:
                channel = self.bot.get_channel(channel_id)
                if isinstance(channel, discord.TextChannel):
                    got = 0
                    try:
                        # Convert timestamp to datetime for discord.py
                        after_dt = datetime.fromtimestamp(accepted_ts, tz=UK_TZ)
                        async for msg in channel.history(limit=500, after=after_dt):
                            if msg.author.id == user_id and not msg.author.bot:
                                msg_ts = int(msg.created_at.timestamp())
                                if accepted_ts <= msg_ts <= due_ts:
                                    got += 1
                    except Exception:
                        pass
                    return (got >= count, f"{got}/{count} messages")
            return False, "Channel tracking unavailable."

        # 2) vc_minutes
        if rtype == "vc_minutes":
            need = int(requirement.get("minutes", 5))
            # Query voice_events table for time window
            rows = await self.bot.db.fetchall(
                """
                SELECT seconds FROM voice_events
                WHERE guild_id=? AND user_id=? AND end_ts >= ? AND start_ts <= ?
                """,
                (guild_id, user_id, accepted_ts, due_ts)
            )
            total_seconds = sum(int(r["seconds"]) for r in rows)
            got_minutes = total_seconds // 60
            return (got_minutes >= need, f"{got_minutes}/{need} VC minutes")

        # 3) casino_wager
        if rtype == "casino_wager":
            casino = self.bot.get_cog("CasinoCore")
            if not casino:
                return False, "Casino tracking missing."
            need = int(requirement.get("coins", 1))
            stats = await casino.get_window_summary(guild_id, accepted_ts)
            # Find user's wager from top_spenders or calculate from data
            wager_by_user = {}
            ctx = f"casino_rounds:{guild_id}"
            row = await self.bot.db.fetchone("SELECT hash FROM msg_memory WHERE guild_id=? AND context=?", (guild_id, ctx))
            if row:
                try:
                    data = json.loads(row["hash"]) or []
                    for ev in data:
                        ts = int(ev.get("ts", 0))
                        if accepted_ts <= ts <= due_ts:
                            uid = int(ev.get("uid", 0))
                            wager = int(ev.get("wager", 0))
                            if uid == user_id and wager > 0:
                                wager_by_user[uid] = wager_by_user.get(uid, 0) + wager
                except Exception:
                    pass
            got = wager_by_user.get(user_id, 0)
            return (got >= need, f"{got}/{need} wagered Coins")

        # 4) casino_rounds
        if rtype == "casino_rounds":
            casino = self.bot.get_cog("CasinoCore")
            if not casino:
                return False, "Casino tracking missing."
            need = int(requirement.get("count", 1))
            ctx = f"casino_rounds:{guild_id}"
            row = await self.bot.db.fetchone("SELECT hash FROM msg_memory WHERE guild_id=? AND context=?", (guild_id, ctx))
            got = 0
            if row:
                try:
                    data = json.loads(row["hash"]) or []
                    for ev in data:
                        ts = int(ev.get("ts", 0))
                        if accepted_ts <= ts <= due_ts:
                            uid = int(ev.get("uid", 0))
                            wager = int(ev.get("wager", 0))
                            if uid == user_id and wager > 0:
                                got += 1
                except Exception:
                    pass
            return (got >= need, f"{got}/{need} casino rounds")

        # 5) allin_required (check for at least one all-in during window)
        if rtype == "allin_required":
            ctx = f"casino_rounds:{guild_id}"
            row = await self.bot.db.fetchone("SELECT hash FROM msg_memory WHERE guild_id=? AND context=?", (guild_id, ctx))
            found_allin = False
            if row:
                try:
                    data = json.loads(row["hash"]) or []
                    for ev in data:
                        ts = int(ev.get("ts", 0))
                        if accepted_ts <= ts <= due_ts:
                            uid = int(ev.get("uid", 0))
                            meta = ev.get("meta", {})
                            if uid == user_id and meta.get("allin"):
                                found_allin = True
                                break
                except Exception:
                    pass
            return (found_allin, "All-in performed" if found_allin else "No all-in found")

        # 6) manual
        if rtype == "manual":
            return False, "Manual proof required."

        return False, "Unknown requirement."

    # ------------------ order creation (orders.py system) ------------------
    async def create_order(self, guild: discord.Guild, *, kind: str, scope: str, owner_user_id: int,
                           title: str, description: str, reward_coins: int, reward_obedience: int,
                           requirement: dict, duration_minutes: int, max_slots: int, hint_channel_id: int,
                           announce_key: str):
        gid = guild.id
        order_id = await self._next_order_id(gid)
        now = now_ts()
        due = now + int(duration_minutes) * 60

        await self.bot.db.execute(
            """
            INSERT INTO orders(guild_id,order_id,kind,scope,owner_user_id,title,description,
                               reward_coins,reward_obedience,requirement_json,hint_channel_id,
                               max_slots,slots_taken,created_ts,start_ts,due_ts,status,posted_channel_id)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (gid, order_id, kind, scope, int(owner_user_id), title, description,
             int(reward_coins), int(reward_obedience), json.dumps(requirement), int(hint_channel_id),
             int(max_slots), 0, now, now, due, "active", self._orders_ch())
        )

        # announce in #orders (clean)
        # stage for "server announcements": treat as neutral stage 1 unless you want mood-engine based
        stage = 1
        # Use merged tone pools to support ritual expansion keys
        announce_line = pick(TONE_POOLS, announce_key, stage)

        hint = f"<#{hint_channel_id}>" if hint_channel_id else "the server"
        slots_remaining, max_slots_val = await self._slots_remaining(gid, order_id)
        embed = build_order_embed(
            icon_url=self.icon,
            title="New Order",
            order_desc=f"{announce_line}\n\n{description}",
            coins=reward_coins,
            obedience=reward_obedience,
            duration=f"{duration_minutes} minutes",
            slots_remaining=slots_remaining,
            max_slots=max_slots_val,
            hint_channel=hint,
            order_id=order_id
        )
        await self._post_orders_announce(guild, "", embed)
        return order_id

    # ==================== ORDERS.PY COMMANDS (orders/order_runs tables) ====================
    
    @app_commands.command(name="order_view", description="View an order by ID.")
    @app_commands.describe(order_id="Order ID")
    async def order_view(self, interaction: discord.Interaction, order_id: int):
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild_id
        if not gid:
            embed = create_embed("Use this in a server.", color="info", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)

        r = await self.bot.db.fetchone("SELECT * FROM orders WHERE guild_id=? AND order_id=? AND status='active'", (gid, order_id))
        if not r:
            embed = create_embed("Order not found.", color="info", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)

        remaining = max(0, int(r["max_slots"]) - int(r["slots_taken"]))
        hint = f"<#{int(r['hint_channel_id'])}>" if int(r["hint_channel_id"]) else "the server"
        duration = f"{max(0, (int(r['due_ts']) - now_ts()) // 60)} minutes remaining"

        e = build_order_embed(
            icon_url=self.icon,
            title="New Order",
            order_desc=r["description"],
            coins=int(r["reward_coins"]),
            obedience=int(r["reward_obedience"]),
            duration=duration,
            slots_remaining=remaining,
            max_slots=int(r["max_slots"]),
            hint_channel=hint,
            order_id=int(r["order_id"])
        )
        await interaction.followup.send(embed=e, ephemeral=True)

    @app_commands.command(name="order_accept", description="Accept an order.")
    @app_commands.describe(order_id="Order ID")
    async def order_accept(self, interaction: discord.Interaction, order_id: int):
        await interaction.response.defer()
        gid = interaction.guild_id
        if not gid or not interaction.guild:
            embed = create_embed("Use this in a server.", color="info", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)

        order = await self.bot.db.fetchone("SELECT * FROM orders WHERE guild_id=? AND order_id=? AND status='active'", (gid, order_id))
        if not order:
            embed = create_embed("Order not found.", color="info", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)

        # personal order gate
        if order["scope"] == "user" and int(order["owner_user_id"]) != interaction.user.id:
            embed = create_embed("That order is not for you.", color="info", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)

        remaining = max(0, int(order["max_slots"]) - int(order["slots_taken"]))
        if remaining <= 0:
            embed = create_embed("No slots left.", color="info", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)

        exists = await self.bot.db.fetchone("SELECT status FROM order_runs WHERE guild_id=? AND order_id=? AND user_id=?",
                                           (gid, order_id, interaction.user.id))
        if exists:
            embed = create_embed("You already interacted with this order.", color="info", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)

        accepted = now_ts()
        due_ts = int(order["due_ts"])

        await self.bot.db.execute(
            "INSERT INTO order_runs(guild_id,order_id,user_id,accepted_ts,due_ts,status,progress_json) VALUES(?,?,?,?,?,?,?)",
            (gid, order_id, interaction.user.id, accepted, due_ts, "accepted", "{}")
        )
        await self.bot.db.execute(
            "UPDATE orders SET slots_taken=slots_taken+1 WHERE guild_id=? AND order_id=?",
            (gid, order_id)
        )

        stage = await self._user_stage(gid, interaction.user.id)
        line = pick(ORDER_TONES, "order_accepted", stage)

        # mini-embed "timer/progress"
        minutes_left = max(0, (due_ts - now_ts()) // 60)
        mini = discord.Embed(description=sanitize_isla_text(f"{interaction.user.mention}\n{line}\nTime left: **{minutes_left} minutes**\n᲼᲼"))
        mini.set_author(name="Isla", icon_url=self.icon)
        mini.set_thumbnail(url=random.choice(STYLE1_THUMBS))

        await interaction.followup.send(embed=mini)

    @app_commands.command(name="order_progress", description="Check your progress on an accepted order.")
    @app_commands.describe(order_id="Order ID")
    async def order_progress(self, interaction: discord.Interaction, order_id: int):
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild_id
        if not gid:
            embed = create_embed("Use this in a server.", color="info", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)

        order = await self.bot.db.fetchone("SELECT requirement_json FROM orders WHERE guild_id=? AND order_id=? AND status='active'", (gid, order_id))
        run = await self.bot.db.fetchone("SELECT accepted_ts,due_ts,status FROM order_runs WHERE guild_id=? AND order_id=? AND user_id=?",
                                         (gid, order_id, interaction.user.id))
        if not order or not run or run["status"] != "accepted":
            embed = create_embed("No active run found.", color="info", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)

        requirement = json.loads(order["requirement_json"])
        ok, detail = await self._check_completion(gid, interaction.user.id, requirement, int(run["accepted_ts"]), int(run["due_ts"]))
        left = max(0, (int(run["due_ts"]) - now_ts()) // 60)

        e = discord.Embed(description=sanitize_isla_text(
            f"{interaction.user.mention}\nProgress: **{detail}**\nTime left: **{left} minutes**\n᲼᲼"
        ))
        e.set_author(name="Isla", icon_url=self.icon)
        e.set_thumbnail(url=random.choice(STYLE1_THUMBS))
        await interaction.followup.send(embed=e, ephemeral=True)

    @app_commands.command(name="order_complete", description="Attempt to complete an order (auto-check).")
    @app_commands.describe(order_id="Order ID", note="Optional note for manual orders")
    async def order_complete(self, interaction: discord.Interaction, order_id: int, note: str | None = None):
        await interaction.response.defer()
        gid = interaction.guild_id
        if not gid or not interaction.guild:
            embed = create_embed("Use this in a server.", color="info", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)

        order = await self.bot.db.fetchone("SELECT * FROM orders WHERE guild_id=? AND order_id=? AND status='active'", (gid, order_id))
        run = await self.bot.db.fetchone("SELECT * FROM order_runs WHERE guild_id=? AND order_id=? AND user_id=?",
                                         (gid, order_id, interaction.user.id))
        if not order or not run or run["status"] != "accepted":
            embed = create_embed("You have not accepted this order.", color="info", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)

        if now_ts() > int(run["due_ts"]):
            # timeout -> fail
            await self.bot.db.execute("UPDATE order_runs SET status='failed' WHERE guild_id=? AND order_id=? AND user_id=?",
                                      (gid, order_id, interaction.user.id))
            await self._apply_failure_penalty(gid, interaction.user.id)

            stage = await self._user_stage(gid, interaction.user.id)
            # Use ritual tones for ritual orders
            is_ritual = order["kind"] == "ritual"
            fail_key = "ritual_failed" if is_ritual else "order_failed"
            tone_pool = RITUAL_EXTRA_TONES if is_ritual else ORDER_TONES
            line = pick(tone_pool, fail_key, stage)

            e = discord.Embed(description=sanitize_isla_text(f"{interaction.user.mention}\n{line}\n᲼᲼"))
            e.set_author(name="Isla", icon_url=self.icon)
            e.set_thumbnail(url=random.choice(STYLE1_THUMBS))
            return await interaction.followup.send(embed=e)

        requirement = json.loads(order["requirement_json"])
        ok, detail = await self._check_completion(gid, interaction.user.id, requirement, int(run["accepted_ts"]), int(run["due_ts"]))

        if requirement.get("type") == "manual":
            # Send to staff inbox channel (your "Isla inbox" system)
            inbox_id = int(self.bot.cfg.get("channels", "inbox", default=0) or 0)
            inbox = interaction.guild.get_channel(inbox_id) if inbox_id else None
            if isinstance(inbox, discord.TextChannel):
                await inbox.send(
                    content=f"Order proof request from <@{interaction.user.id}> for order `{order_id}`",
                    embed=discord.Embed(description=sanitize_isla_text(note or "No note provided."))
                )
            embed = create_embed("Proof submitted. Staff will review.", color="info", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)

        if not ok:
            embed = create_embed(f"Not complete yet: {detail}", color="info", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)

        # Success
        completed_ts = now_ts()
        await self.bot.db.execute(
            "UPDATE order_runs SET status='completed', completed_ts=? WHERE guild_id=? AND order_id=? AND user_id=?",
            (completed_ts, gid, order_id, interaction.user.id)
        )
        await self._apply_rewards(gid, interaction.user.id, int(order["reward_coins"]), int(order["reward_obedience"]))
        
        # Log completion for EventSystem (boss ES tracking)
        kind = "ritual" if order["kind"] == "ritual" else "order"
        await self.bot.db.execute(
            "INSERT OR IGNORE INTO order_completion_log(guild_id,user_id,ts,kind) VALUES(?,?,?,?)",
            (gid, interaction.user.id, completed_ts, kind)
        )
        
        # Forward ritual completion to EventActivityTracker
        if order["kind"] == "ritual":
            tracker = self.bot.get_cog("Data")
            if tracker:
                try:
                    await tracker.mark_ritual_done(gid, interaction.user.id)
                except Exception:
                    pass  # Don't break order completion if event tracking fails

        stage = await self._user_stage(gid, interaction.user.id)
        
        # Use ritual tones for ritual orders, regular tones for others
        success_key = "ritual_success" if order["kind"] == "ritual" else "order_success"
        tone_pool = RITUAL_EXTRA_TONES if order["kind"] == "ritual" else ORDER_TONES
        line = pick(tone_pool, success_key, stage)

        streak, milestone = await self._update_stats_on_complete(gid, interaction.user.id, stage)

        extra = ""
        if milestone:
            streak_key = "ritual_streak" if order["kind"] == "ritual" else "order_streak"
            extra = f"\n{pick(tone_pool, streak_key, stage)}\nStreak: **{streak}**"
            
            # Post milestone to spotlight (user-only ping, no @everyone)
            spot_id = self._spotlight_ch()
            spot = interaction.guild.get_channel(spot_id) if spot_id else None
            if isinstance(spot, discord.TextChannel):
                ping = f"<@{interaction.user.id}>"
                sline = pick(ORDER_TONES, "order_streak", stage)
                se = discord.Embed(description=sanitize_isla_text(f"{ping}\n{sline}\nStreak: **{streak}**\n᲼᲼"))
                se.set_author(name="Isla", icon_url=self.icon)
                se.set_thumbnail(url=random.choice(STYLE1_THUMBS))
                await spot.send(content=ping, embed=se)

        e = discord.Embed(description=sanitize_isla_text(
            f"{interaction.user.mention}\n{line}\nReward: **{fmt(int(order['reward_coins']))} Coins** • **{fmt(int(order['reward_obedience']))} Obedience**{extra}\n᲼᲼"
        ))
        e.set_author(name="Isla", icon_url=self.icon)
        e.set_thumbnail(url=random.choice(STYLE1_THUMBS))
        await interaction.followup.send(embed=e)

        # close server order if slots fully completed
        if int(order["slots_taken"]) >= int(order["max_slots"]):
            await self.bot.db.execute("UPDATE orders SET status='closed' WHERE guild_id=? AND order_id=?", (gid, order_id))

    @app_commands.command(name="order_abandon", description="Abandon an accepted order (penalty + cooldown).")
    @app_commands.describe(order_id="Order ID")
    async def order_abandon(self, interaction: discord.Interaction, order_id: int):
        await interaction.response.defer()
        gid = interaction.guild_id
        if not gid:
            embed = create_embed("Use this in a server.", color="info", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)

        run = await self.bot.db.fetchone("SELECT status FROM order_runs WHERE guild_id=? AND order_id=? AND user_id=?",
                                         (gid, order_id, interaction.user.id))
        if not run or run["status"] != "accepted":
            embed = create_embed("No accepted order found.", color="info", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)

        await self.bot.db.execute("UPDATE order_runs SET status='abandoned' WHERE guild_id=? AND order_id=? AND user_id=?",
                                  (gid, order_id, interaction.user.id))
        await self._apply_failure_penalty(gid, interaction.user.id)

        stage = await self._user_stage(gid, interaction.user.id)
        line = pick(ORDER_TONES, "order_abandoned", stage)

        e = discord.Embed(description=sanitize_isla_text(f"{interaction.user.mention}\n{line}\n᲼᲼"))
        e.set_author(name="Isla", icon_url=self.icon)
        e.set_thumbnail(url=random.choice(STYLE1_THUMBS))
        await interaction.followup.send(embed=e)

    # ------------------ behavior snapshot helper ------------------
    async def _behavior_snapshot_24h(self, gid: int, uid: int) -> dict:
        end = now_ts()
        start = end - 24 * 3600

        snap = {"msg": 0, "vc": 0, "wager": 0, "rounds": 0}

        # Count messages from weekly_stats or channel history (simplified: use weekly_stats if available)
        # For 24h snapshot, we'll use a simplified approach: query channel history if available
        spam_ch_id = self._spam_ch()
        if spam_ch_id:
            channel = self.bot.get_channel(spam_ch_id)
            if isinstance(channel, discord.TextChannel):
                try:
                    after_dt = datetime.fromtimestamp(start, tz=UK_TZ)
                    async for msg in channel.history(limit=500, after=after_dt):
                        if msg.author.id == uid and not msg.author.bot:
                            if start <= int(msg.created_at.timestamp()) <= end:
                                snap["msg"] += 1
                except Exception:
                    pass

        # Voice minutes from voice_events
        rows = await self.bot.db.fetchall(
            """
            SELECT seconds FROM voice_events
            WHERE guild_id=? AND user_id=? AND end_ts >= ? AND start_ts <= ?
            """,
            (gid, uid, start, end)
        )
        total_seconds = sum(int(r["seconds"]) for r in rows)
        snap["vc"] = total_seconds // 60

        # Casino stats from msg_memory
        casino = self.bot.get_cog("CasinoCore")
        if casino:
            ctx = f"casino_rounds:{gid}"
            row = await self.bot.db.fetchone("SELECT hash FROM msg_memory WHERE guild_id=? AND context=?", (gid, ctx))
            if row:
                try:
                    data = json.loads(row["hash"]) or []
                    for ev in data:
                        ts = int(ev.get("ts", 0))
                        if start <= ts <= end:
                            ev_uid = int(ev.get("uid", 0))
                            if ev_uid == uid:
                                wager = int(ev.get("wager", 0))
                                snap["wager"] += wager
                                if wager > 0:
                                    snap["rounds"] += 1
                except Exception:
                    pass

        return snap

    # ------------------ dynamic template selection ------------------
    def _pick_personal_template(self, snap: dict) -> dict:
        # Duplicate list so we can tweak weights per user
        pool = []
        for t in PERSONAL_TEMPLATES:
            t2 = dict(t)
            w = int(t2.get("weight", 1))

            # If they're quiet -> boost chat orders
            if snap["msg"] < 15 and t2["key"].startswith("chat"):
                w += 4
            # If they never VC -> boost VC
            if snap["vc"] < 10 and t2["key"].startswith("vc"):
                w += 3
            # If they haven't touched casino -> boost casino
            if snap["rounds"] < 3 and t2["key"].startswith("casino"):
                w += 2

            # If they're already very active, reduce spammy tasks and push casino/VC variety
            if snap["msg"] > 80 and t2["key"].startswith("chat"):
                w = max(1, w - 3)

            t2["weight"] = w
            pool.append(t2)

        return weighted_choice(pool)

    def _scale_params(self, snap: dict, stage: int) -> dict:
        # stage boosts difficulty slightly for higher relationship
        stage_mult = [0.9, 1.0, 1.15, 1.3, 1.5][stage]

        msg_target = int(max(6, min(35, round((10 + (snap["msg"] * 0.12)) * stage_mult))))
        vc_target = int(max(10, min(60, round((15 + (snap["vc"] * 0.15)) * stage_mult))))
        rounds_target = int(max(3, min(12, round((4 + (snap["rounds"] * 0.2)) * stage_mult))))
        wager_target = int(max(500, min(12000, round((1200 + (snap["wager"] * 0.08)) * stage_mult))))

        return {"msg": msg_target, "vc": vc_target, "rounds": rounds_target, "wager": wager_target}

    def _scale_rewards(self, base_coins: int, base_ob: int, stage: int) -> tuple[int, int]:
        # Slight scaling so high-stage feels "worth it"
        mult = [1.0, 1.05, 1.12, 1.20, 1.30][stage]
        return (int(base_coins * mult), int(base_ob * mult))

    # ------------------ personal order generator ------------------
    @app_commands.command(name="order_personal", description="Generate a personal order (if eligible).")
    async def order_personal(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild_id
        if not gid or not interaction.guild:
            embed = create_embed("Use this in a server.", color="info", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)

        # limit: 1 active personal order per user
        row = await self.bot.db.fetchone(
            "SELECT 1 FROM orders WHERE guild_id=? AND scope='user' AND owner_user_id=? AND status='active' LIMIT 1",
            (gid, interaction.user.id)
        )
        if row:
            embed = create_embed("You already have a personal order active.", color="info", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)

        stage = await self._user_stage(gid, interaction.user.id)
        opener = pick(ORDER_TONES, "personal_order", stage)

        snap = await self._behavior_snapshot_24h(gid, interaction.user.id)
        params = self._scale_params(snap, stage)
        tpl = self._pick_personal_template(snap)

        # pick duration
        dmin, dmax = tpl["duration_minutes"]
        duration = random.randint(int(dmin), int(dmax))

        # build requirement + description
        if tpl["key"].startswith("chat"):
            count = params["msg"]
            req = tpl["requirement"](self._spam_ch(), count)
            desc = f"{opener}\n\n" + random.choice(tpl["desc_variants"]).format(count=count)

        elif tpl["key"].startswith("vc"):
            minutes = params["vc"]
            req = tpl["requirement"](self._spam_ch(), minutes)
            desc = f"{opener}\n\n" + random.choice(tpl["desc_variants"]).format(minutes=minutes)

        elif tpl["key"] == "casino_rounds":
            count = params["rounds"]
            req = tpl["requirement"](self._spam_ch(), count)
            desc = f"{opener}\n\n" + random.choice(tpl["desc_variants"]).format(count=count)

        elif tpl["key"] == "casino_wager":
            coins = params["wager"]
            req = tpl["requirement"](self._spam_ch(), coins)
            desc = f"{opener}\n\n" + random.choice(tpl["desc_variants"]).format(coins=coins)

        else:
            req = tpl["requirement"](self._spam_ch(), 0)
            desc = f"{opener}\n\n" + random.choice(tpl["desc_variants"])

        base_coins, base_ob = tpl["base_reward"]
        reward_coins, reward_ob = self._scale_rewards(base_coins, base_ob, stage)

        order_id = await self.create_order(
            interaction.guild,
            kind="personal",
            scope="user",
            owner_user_id=interaction.user.id,
            title=tpl["title"],
            description=desc,
            reward_coins=reward_coins,
            reward_obedience=reward_ob,
            requirement=req,
            duration_minutes=duration,
            max_slots=1,
            hint_channel_id=self._spam_ch(),
            announce_key="order_announce"
        )
        embed = create_embed(f"Personal order created: `{order_id}`", color="info", is_dm=False, is_system=False)
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ==================== ORDERS_GROUP.PY COMMANDS (orders_catalog/orders_claims tables) ====================

    def _register_orders_group(self):
        """Register /orders group subcommands"""
        self.orders_group.add_command(self.orders_view)
        self.orders_group.add_command(self.orders_accept)
        self.orders_group.add_command(self.orders_complete)
        self.orders_group.add_command(self.orders_forfeit)
        self.orders_group.add_command(self.orders_streak)

    @app_commands.command(name="view", description="Shows available orders.")
    @app_commands.describe(type="daily, hourly, event, personal (or all)")
    async def orders_view(self, interaction: discord.Interaction, type: str = "all"):
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild_id
        if not gid:
            embed = create_embed("Server only.", color="warning", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)

        t = type.lower().strip()
        params = [gid]
        where = "guild_id=? AND is_active=1"

        if t in ("daily", "hourly", "event", "personal"):
            where += " AND order_type=?"
            params.append(t)

        rows = await self.bot.db.fetchall(
            f"""
            SELECT order_id, order_type, title, reward_coins, reward_obed, duration_seconds, max_slots
            FROM orders_catalog
            WHERE {where}
            ORDER BY order_type, order_id DESC
            LIMIT 20
            """,
            tuple(params)
        )

        if not rows:
            return await interaction.followup.send(embed=isla_embed_simple("No orders right now.\n᲼᲼", title="Orders"), ephemeral=True)

        lines = []
        for r in rows:
            oid = int(r["order_id"])
            otype = str(r["order_type"])
            title = str(r["title"])
            coins = int(r["reward_coins"])
            obed = int(r["reward_obed"])
            dur = int(r["duration_seconds"])
            lines.append(f"**#{oid}** [{otype}] {title} — {fmt(coins)} Coins • {fmt(obed)} Obed • {dur//60}m")

        e = isla_embed_simple("Pick one.\n᲼᲼", title="Orders")
        e.add_field(name="Available", value="\n".join(lines), inline=False)
        e.set_footer(text="Accept with /orders accept <order_id>")
        await interaction.followup.send(embed=e, ephemeral=True)

    @app_commands.command(name="accept", description="Accept an order (starts timer).")
    @app_commands.describe(order_id="Order ID")
    async def orders_accept(self, interaction: discord.Interaction, order_id: int):
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild_id
        uid = interaction.user.id
        if not gid:
            embed = create_embed("Server only.", color="warning", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)

        o = await self.bot.db.fetchone(
            """
            SELECT order_id, order_type, title, description, reward_coins, reward_obed, duration_seconds, max_slots, is_active
            FROM orders_catalog
            WHERE guild_id=? AND order_id=?
            """,
            (gid, int(order_id))
        )
        if not o or int(o["is_active"]) != 1:
            return await interaction.followup.send(embed=isla_embed_simple("That order isn't available.\n᲼᲼", title="Accept"), ephemeral=True)

        # slots check (if max_slots > 0)
        max_slots = int(o["max_slots"] or 0)
        if max_slots > 0:
            c = await self.bot.db.fetchone(
                "SELECT COUNT(*) AS n FROM orders_claims WHERE guild_id=? AND order_id=? AND status='active'",
                (gid, int(order_id))
            )
            if int(c["n"] or 0) >= max_slots:
                return await interaction.followup.send(embed=isla_embed_simple("No slots left.\n᲼᲼", title="Accept"), ephemeral=True)

        # already accepted?
        existing = await self.bot.db.fetchone(
            "SELECT status FROM orders_claims WHERE guild_id=? AND order_id=? AND user_id=?",
            (gid, int(order_id), uid)
        )
        if existing and str(existing["status"]) == "active":
            return await interaction.followup.send(embed=isla_embed_simple("You already accepted that.\n᲼᲼", title="Accept"), ephemeral=True)

        accepted = now_ts()
        due = accepted + int(o["duration_seconds"])

        await self.bot.db.execute(
            """
            INSERT INTO orders_claims(guild_id,order_id,user_id,status,accepted_ts,due_ts)
            VALUES(?,?,?,?,?,?)
            ON CONFLICT(guild_id,order_id,user_id) DO UPDATE SET
              status='active',
              accepted_ts=excluded.accepted_ts,
              due_ts=excluded.due_ts,
              completed_ts=0,
              proof_text='',
              proof_url='',
              penalty_coins=0,
              penalty_obed=0
            """,
            (gid, int(order_id), uid, "active", accepted, due)
        )

        e = isla_embed_simple(
            f"Accepted.\n\n"
            f"Order **#{order_id}**\n"
            f"Due: <t:{due}:R>\n"
            "᲼᲼",
            title="Orders"
        )
        e.add_field(name="Task", value=str(o["description"]), inline=False)
        e.set_footer(text="Complete with /orders complete <order_id> [proof]")
        await interaction.followup.send(embed=e, ephemeral=True)

    @app_commands.command(name="complete", description="Completes order (optional proof).")
    @app_commands.describe(order_id="Order ID", proof="Optional proof text")
    async def orders_complete(self, interaction: discord.Interaction, order_id: int, proof: str | None = None):
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild_id
        uid = interaction.user.id
        if not gid:
            embed = create_embed("Server only.", color="warning", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)

        claim = await self.bot.db.fetchone(
            """
            SELECT status, accepted_ts, due_ts
            FROM orders_claims
            WHERE guild_id=? AND order_id=? AND user_id=?
            """,
            (gid, int(order_id), uid)
        )
        if not claim or str(claim["status"]) != "active":
            return await interaction.followup.send(embed=isla_embed_simple("You don't have that order active.\n᲼᲼", title="Complete"), ephemeral=True)

        due = int(claim["due_ts"])
        if now_ts() > due:
            return await interaction.followup.send(embed=isla_embed_simple("Too late.\nThat one expired.\n᲼᲼", title="Complete"), ephemeral=True)

        o = await self.bot.db.fetchone(
            """
            SELECT reward_coins, reward_obed, title
            FROM orders_catalog
            WHERE guild_id=? AND order_id=?
            """,
            (gid, int(order_id))
        )
        if not o:
            return await interaction.followup.send(embed=isla_embed_simple("Order not found.\n᲼᲼", title="Complete"), ephemeral=True)

        # attachment proof (optional)
        proof_url = ""
        if interaction.attachments:
            proof_url = interaction.attachments[0].url

        await self.bot.db.execute(
            """
            UPDATE orders_claims
            SET status='completed', completed_ts=?, proof_text=?, proof_url=?
            WHERE guild_id=? AND order_id=? AND user_id=?
            """,
            (now_ts(), proof or "", proof_url, gid, int(order_id), uid)
        )

        coins = int(o["reward_coins"])
        obed = int(o["reward_obed"])

        await ensure_wallet(self.bot.db, gid, uid)
        if coins:
            await add_coins(self.bot.db, gid, uid, coins, kind="order_reward", reason=f"order #{order_id}")

        if obed:
            await add_obed(self.bot.db, gid, uid, obed)

        streak = await maybe_advance_streak(self.bot.db, gid, uid)

        e = isla_embed_simple(
            f"Completed.\n\n"
            f"+**{fmt(coins)} Coins**\n"
            f"+**{fmt(obed)} Obedience**\n"
            f"Streak: **{streak}**\n"
            "᲼᲼",
            title="Orders"
        )
        e.add_field(name="Order", value=f"#{order_id} — {str(o['title'])}", inline=False)
        if proof:
            e.add_field(name="Proof", value=proof[:900], inline=False)
        if proof_url:
            e.add_field(name="Attachment", value=proof_url, inline=False)
        await interaction.followup.send(embed=e, ephemeral=True)

    @app_commands.command(name="forfeit", description="Forfeit an order with penalty.")
    @app_commands.describe(order_id="Order ID")
    async def orders_forfeit(self, interaction: discord.Interaction, order_id: int):
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild_id
        uid = interaction.user.id
        if not gid:
            embed = create_embed("Server only.", color="warning", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)

        claim = await self.bot.db.fetchone(
            "SELECT status FROM orders_claims WHERE guild_id=? AND order_id=? AND user_id=?",
            (gid, int(order_id), uid)
        )
        if not claim or str(claim["status"]) != "active":
            return await interaction.followup.send(embed=isla_embed_simple("You don't have that order active.\n᲼᲼", title="Forfeit"), ephemeral=True)

        # Penalty: small, consistent sink (tune later)
        penalty_coins = 50
        penalty_obed = 10

        await ensure_wallet(self.bot.db, gid, uid)
        await add_coins(self.bot.db, gid, uid, -penalty_coins, kind="order_forfeit", reason=f"order #{order_id}")
        await add_obed(self.bot.db, gid, uid, -penalty_obed)

        await self.bot.db.execute(
            """
            UPDATE orders_claims
            SET status='forfeit', completed_ts=?, penalty_coins=?, penalty_obed=?
            WHERE guild_id=? AND order_id=? AND user_id=?
            """,
            (now_ts(), penalty_coins, penalty_obed, gid, int(order_id), uid)
        )

        await self.bot.db.execute(
            "INSERT INTO obedience_penalties(guild_id,user_id,ts,kind,coins,obed,cleared,note) VALUES(?,?,?,?,?,?,0,?)",
            (gid, uid, now_ts(), "forfeit", penalty_coins, penalty_obed, f"order #{order_id}")
        )

        e = isla_embed_simple(
            f"Forfeit logged.\n\n"
            f"-**{fmt(penalty_coins)} Coins**\n"
            f"-**{fmt(penalty_obed)} Obedience**\n"
            "᲼᲼",
            title="Orders"
        )
        await interaction.followup.send(embed=e, ephemeral=True)

    @app_commands.command(name="streak", description="Shows your current obedience streak and bonuses.")
    async def orders_streak(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild_id
        uid = interaction.user.id
        if not gid:
            embed = create_embed("Server only.", color="warning", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)

        await ensure_obed(self.bot.db, gid, uid)
        r = await self.bot.db.fetchone(
            "SELECT obedience, streak_days, last_streak_ymd, forgive_tokens FROM obedience_profile WHERE guild_id=? AND user_id=?",
            (gid, uid)
        )
        obed = int(r["obedience"] or 0)
        streak = int(r["streak_days"] or 0)
        ft = int(r["forgive_tokens"] or 0)

        # Example bonuses (tune later)
        bonus = "None"
        if streak >= 7:
            bonus = "+5% order coins"
        if streak >= 14:
            bonus = "+10% order coins"
        if streak >= 30:
            bonus = "+15% order coins"

        e = isla_embed_simple(
            f"Streak.\n\n"
            f"Obedience: **{fmt(obed)}**\n"
            f"Streak: **{streak} days**\n"
            f"Forgive tokens: **{ft}**\n"
            "᲼᲼",
            title="Streak"
        )
        e.add_field(name="Bonus", value=bonus, inline=False)
        await interaction.followup.send(embed=e, ephemeral=True)

    # ==================== STANDALONE COMMANDS (from orders_group.py) ====================

    @app_commands.command(name="obey", description="Instant micro-order: a quick task.")
    async def obey(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        micro = random.choice([
            "React to the last message you read with ✅.",
            "Send one message in #orders acknowledging you're present.",
            "Write one useful tip in any channel (except spam).",
            "Go to voice for 5 minutes. Say something once you join.",
            "Post a short progress update about your day in any channel."
        ])

        e = isla_embed_simple(
            "Quick task.\n\n"
            f"{micro}\n"
            "᲼᲼",
            title="Obey"
        )
        await interaction.followup.send(embed=e, ephemeral=True)

    @app_commands.command(name="kneel", description="A small commitment task with minor coin changes.")
    async def kneel(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild_id
        uid = interaction.user.id
        if not gid:
            embed = create_embed("Server only.", color="warning", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)

        # Non-sexual roleplay-lite: "commitment"
        task = random.choice([
            "Pick one order and accept it now.",
            "Send one constructive message in any channel.",
            "Spend 5 minutes in voice, then type one line of what you did today."
        ])

        # Minor coin change: small sink + small "focus buff" placeholder
        delta = -10
        await ensure_wallet(self.bot.db, gid, uid)
        await add_coins(self.bot.db, gid, uid, delta, kind="kneel", reason="commitment")

        e = isla_embed_simple(
            "Fine.\n\n"
            f"{task}\n\n"
            f"{delta} Coins.\n"
            "᲼᲼",
            title="Kneel"
        )
        await interaction.followup.send(embed=e, ephemeral=True)

    @app_commands.command(name="beg", description="Request mercy. Costs Coins; may reduce punishment severity.")
    @app_commands.describe(reason="Optional note")
    async def beg(self, interaction: discord.Interaction, reason: str | None = None):
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild_id
        uid = interaction.user.id
        if not gid:
            embed = create_embed("Server only.", color="warning", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)

        cost = 75
        await ensure_wallet(self.bot.db, gid, uid)
        # Check balance
        w = await get_wallet(self.bot.db, gid, uid)
        if w.coins < cost:
            return await interaction.followup.send(embed=isla_embed_simple("Not enough Coins.\n᲼᲼", title="Mercy"), ephemeral=True)

        await add_coins(self.bot.db, gid, uid, -cost, kind="mercy", reason=reason or "mercy request")

        # Store a mercy use token (consumed by your penalty engine later)
        await ensure_obed(self.bot.db, gid, uid)
        await self.bot.db.execute(
            "UPDATE obedience_profile SET mercy_uses = mercy_uses + 1 WHERE guild_id=? AND user_id=?",
            (gid, uid)
        )

        e = isla_embed_simple(
            "Mercy request logged.\n\n"
            f"-**{fmt(cost)} Coins**\n"
            "This may soften the next penalty.\n"
            "᲼᲼",
            title="Beg"
        )
        if reason:
            e.add_field(name="Reason", value=reason[:900], inline=False)
        await interaction.followup.send(embed=e, ephemeral=True)

    @app_commands.command(name="forgive", description="Forgiveness purchase or earned via streak.")
    async def forgive(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild_id
        uid = interaction.user.id
        if not gid:
            embed = create_embed("Server only.", color="warning", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)

        await ensure_obed(self.bot.db, gid, uid)
        prof = await self.bot.db.fetchone(
            "SELECT forgive_tokens FROM obedience_profile WHERE guild_id=? AND user_id=?",
            (gid, uid)
        )
        tokens = int(prof["forgive_tokens"] or 0)

        # If you have a token, use it; else charge coins
        cost = 250
        used_token = False

        if tokens > 0:
            await self.bot.db.execute(
                "UPDATE obedience_profile SET forgive_tokens = forgive_tokens - 1 WHERE guild_id=? AND user_id=?",
                (gid, uid)
            )
            used_token = True
        else:
            await ensure_wallet(self.bot.db, gid, uid)
            w = await get_wallet(self.bot.db, gid, uid)
            if w.coins < cost:
                return await interaction.followup.send(embed=isla_embed_simple("Not enough Coins.\n᲼᲼", title="Forgive"), ephemeral=True)
            await add_coins(self.bot.db, gid, uid, -cost, kind="forgive", reason="forgiveness")

        # Clear most recent uncleared penalty
        pen = await self.bot.db.fetchone(
            """
            SELECT id, kind, coins, obed, note
            FROM obedience_penalties
            WHERE guild_id=? AND user_id=? AND cleared=0
            ORDER BY ts DESC
            LIMIT 1
            """,
            (gid, uid)
        )

        if not pen:
            msg = "No penalties to clear.\n᲼᲼"
            if not used_token:
                # refund if we charged
                await add_coins(self.bot.db, gid, uid, +cost, kind="refund", reason="no penalties to forgive")
            else:
                # return token
                await self.bot.db.execute(
                    "UPDATE obedience_profile SET forgive_tokens = forgive_tokens + 1 WHERE guild_id=? AND user_id=?",
                    (gid, uid)
                )
            return await interaction.followup.send(embed=isla_embed_simple(msg, title="Forgive"), ephemeral=True)

        await self.bot.db.execute(
            "UPDATE obedience_penalties SET cleared=1 WHERE id=?",
            (int(pen["id"]),)
        )

        e = isla_embed_simple(
            "Cleared.\n\n"
            f"Penalty removed: **{pen['kind']}**\n"
            "᲼᲼",
            title="Forgive"
        )
        if used_token:
            e.add_field(name="Cost", value="1 Forgive token", inline=True)
        else:
            e.add_field(name="Cost", value=f"{fmt(cost)} Coins", inline=True)

        await interaction.followup.send(embed=e, ephemeral=True)

    # ==================== TRIBUTES COMMANDS ====================

    @app_commands.command(name="tribute", description="Log a symbolic tribute (no payment processing).")
    async def tribute(self, interaction: discord.Interaction, amount: app_commands.Range[int, 1, 100000], note: str | None = None):
        if not interaction.guild:
            embed = create_embed("Guild only.", color="warning", is_dm=False, is_system=False)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)

        gid, uid = interaction.guild.id, interaction.user.id
        await self.bot.db.ensure_user(gid, uid)

        if not await self._consent_ok(gid, uid):
            embed = create_embed("You must /verify first.", color="info", is_dm=False, is_system=False)
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        # This is ONLY a log/roleplay ledger. No external payment handling.
        await self.bot.db.execute(
            "INSERT INTO tribute_log(guild_id,user_id,amount,note,ts) VALUES(?,?,?,?,?)",
            (gid, uid, int(amount), (note or "").strip()[:200], now_ts()),
        )

        # Optional: small coin reward to reinforce engagement (tune as desired)
        reward = min(200, max(5, int(amount // 50)))
        await self.bot.db.execute(
            "UPDATE users SET coins=coins+?, lce=lce+? WHERE guild_id=? AND user_id=?",
            (reward, reward, gid, uid),
        )

        # Send a mod log entry if configured
        log_chan_id = self.bot.cfg.get("channels", "logs")
        if log_chan_id:
            ch = interaction.guild.get_channel(int(log_chan_id))
            if ch:
                e = core_isla_embed(
                    "Tribute Logged",
                    f"User: <@{uid}>\nAmount: **{amount}**\nRewarded Coins: **{reward}**\nNote: {note or '—'}",
                    color=0xFF4081,
                )
                try:
                    await ch.send(embed=e)
                except discord.Forbidden:
                    pass

        embed = create_embed(f"Logged. (+{reward} Coins)", color="info", is_dm=False, is_system=False)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="tributes", description="(Mod) View recent tribute logs.")
    async def tributes(self, interaction: discord.Interaction, limit: app_commands.Range[int, 1, 20] = 10):
        if not interaction.guild or not interaction.user.guild_permissions.manage_guild:
            embed = create_embed("Mods only.", color="info", is_dm=False, is_system=False)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)

        gid = interaction.guild.id
        rows = await self.bot.db.fetchall(
            "SELECT user_id,amount,note,ts FROM tribute_log WHERE guild_id=? ORDER BY ts DESC LIMIT ?",
            (gid, int(limit)),
        )
        if not rows:
            embed = create_embed("No tribute logs.", color="info", is_dm=False, is_system=False)
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        lines = []
        for r in rows:
            lines.append(f"- <@{int(r['user_id'])}>: **{int(r['amount'])}** — {r['note'] or '—'} (<t:{int(r['ts'])}:R>)")

        await interaction.followup.send("\n".join(lines), ephemeral=True)

    # ------------------ scheduler: reminders + expirations ------------------
    @tasks.loop(seconds=60)
    async def order_tick(self):
        await self.bot.wait_until_ready()

        for guild in self.bot.guilds:
            gid = guild.id

            # Expire overdue runs
            overdue = await self.bot.db.fetchall(
                "SELECT order_id,user_id,due_ts FROM order_runs WHERE guild_id=? AND status='accepted' AND due_ts<? LIMIT 50",
                (gid, now_ts())
            )
            for r in overdue:
                await self.bot.db.execute(
                    "UPDATE order_runs SET status='failed' WHERE guild_id=? AND order_id=? AND user_id=?",
                    (gid, int(r["order_id"]), int(r["user_id"]))
                )
                await self._apply_failure_penalty(gid, int(r["user_id"]))

            # Mid-timer reminders (only once per run)
            # Store reminder flag in progress_json: {"reminded":true}
            active_runs = await self.bot.db.fetchall(
                "SELECT order_id,user_id,accepted_ts,due_ts,progress_json FROM order_runs WHERE guild_id=? AND status='accepted' LIMIT 50",
                (gid,)
            )
            spam_ch = guild.get_channel(self._spam_ch())
            if not isinstance(spam_ch, discord.TextChannel):
                continue

            for rr in active_runs:
                try:
                    prog = json.loads(rr["progress_json"] or "{}")
                except Exception:
                    prog = {}
                if prog.get("reminded"):
                    continue

                accepted_ts = int(rr["accepted_ts"])
                due_ts = int(rr["due_ts"])
                half = accepted_ts + (due_ts - accepted_ts) // 2
                if now_ts() >= half and now_ts() < due_ts:
                    # reminder to user in #spam (ping outside embed is okay; no @everyone)
                    uid = int(rr["user_id"])
                    stage = await self._user_stage(gid, uid)
                    
                    # Use ritual reminder for ritual orders
                    order = await self.bot.db.fetchone("SELECT kind FROM orders WHERE guild_id=? AND order_id=?", (gid, int(rr["order_id"])))
                    is_ritual = order and order["kind"] == "ritual"
                    reminder_key = "ritual_reminder" if is_ritual else "order_reminder"
                    tone_pool = RITUAL_EXTRA_TONES if is_ritual else ORDER_TONES
                    line = pick(tone_pool, reminder_key, stage)

                    e = discord.Embed(description=sanitize_isla_text(f"<@{uid}>\n{line}\n᲼᲼"))
                    e.set_author(name="Isla", icon_url=self.icon)
                    e.set_thumbnail(url=random.choice(STYLE1_THUMBS))

                    await spam_ch.send(content=f"<@{uid}>", embed=e)

                    prog["reminded"] = True
                    await self.bot.db.execute(
                        "UPDATE order_runs SET progress_json=? WHERE guild_id=? AND order_id=? AND user_id=?",
                        (json.dumps(prog), gid, int(rr["order_id"]), uid)
                    )

    # ------------------ weekly ritual scheduler ------------------
    @tasks.loop(minutes=10)
    async def ritual_scheduler(self):
        await self.bot.wait_until_ready()

        for guild in self.bot.guilds:
            gid = guild.id

            # Only one active ritual at a time
            existing = await self.bot.db.fetchone(
                "SELECT 1 FROM orders WHERE guild_id=? AND kind='ritual' AND status='active' LIMIT 1",
                (gid,)
            )
            if existing:
                continue

            # Post Monday UK time between 12:00-15:00 (aligns your "awake midday")
            t = now_local()
            if t.weekday() != 0:
                continue
            if not (12 <= t.hour < 15):
                continue

            # prevent multiple posts same day
            state = await self.bot.db.fetchone(
                "SELECT value FROM order_system_state WHERE guild_id=? AND key='ritual_post_day'",
                (gid,)
            )
            dk = day_key_uk()
            if state and state["value"] == dk:
                continue

            # pick ritual
            ritual = random.choice(RITUAL_TEMPLATES)

            # build ritual params
            if ritual["key"] in ("drain_marathon",):
                coins = random.choice([15000, 20000, 25000, 30000])
                req = ritual["requirement"](coins)
                desc = random.choice(ritual["desc_variants"]).format(coins=coins)
            elif ritual["key"] in ("luck_submission",):
                count = random.choice([20, 30, 40])
                req = ritual["requirement"](count)
                desc = random.choice(ritual["desc_variants"]).format(count=count)
            else:
                count = random.choice([120, 180, 240])
                req = ritual["requirement"](self._spam_ch(), count)
                desc = random.choice(ritual["desc_variants"]).format(count=count)

            # announcement tone keys (from expansion pools)
            announce_key = ritual.get("announce_key", "ritual_announce")

            title = ritual["title"]
            base_coins, base_ob = ritual["base_reward"]
            # Rituals don't scale per-user; keep fixed rewards
            order_id = await self.create_order(
                guild,
                kind="ritual",
                scope="server",
                owner_user_id=0,
                title=title,
                description=desc,
                reward_coins=base_coins,
                reward_obedience=base_ob,
                requirement=req,
                duration_minutes=ritual["duration_minutes"],
                max_slots=ritual["slots"],
                hint_channel_id=self._spam_ch(),
                announce_key=announce_key if announce_key in TONE_POOLS else "ritual_announce"
            )

            await self.bot.db.execute(
                "INSERT INTO order_system_state(guild_id,key,value) VALUES(?,?,?) "
                "ON CONFLICT(guild_id,key) DO UPDATE SET value=excluded.value",
                (gid, "ritual_post_day", dk)
            )

    # ------------------------------------------------------------
    # Methods expected by EventSystem (boss ES tracking)
    # ------------------------------------------------------------
    async def window_order_completions(self, guild_id: int, start_ts: int, end_ts: int) -> dict[int, int]:
        """
        Returns {user_id: count} of order completions in [start_ts, end_ts).
        """
        rows = await self.bot.db.fetchall(
            """
            SELECT user_id, COUNT(*) AS c
            FROM order_completion_log
            WHERE guild_id=? AND kind='order' AND ts>=? AND ts<?
            GROUP BY user_id
            """,
            (guild_id, start_ts, end_ts)
        )
        return {int(r["user_id"]): int(r["c"] or 0) for r in rows}

    async def window_ritual_completions(self, guild_id: int, start_ts: int, end_ts: int) -> dict[int, int]:
        """
        Returns {user_id: count} of ritual completions in [start_ts, end_ts).
        """
        rows = await self.bot.db.fetchall(
            """
            SELECT user_id, COUNT(*) AS c
            FROM order_completion_log
            WHERE guild_id=? AND kind='ritual' AND ts>=? AND ts<?
            GROUP BY user_id
            """,
            (guild_id, start_ts, end_ts)
        )
        return {int(r["user_id"]): int(r["c"] or 0) for r in rows}


async def setup(bot: commands.Bot):
    # Remove command if it exists before creating cog (to avoid conflicts)
    bot.tree.remove_command("orders", guild=None)
    cog = Orders(bot)
    # Add cog - commands will be auto-registered
    try:
        await bot.add_cog(cog)
    except Exception as e:
        # If command already registered, remove it and try again
        if "CommandAlreadyRegistered" in str(e):
            bot.tree.remove_command("orders", guild=None)
            await bot.add_cog(cog)
        else:
            raise
    # Ensure command is in tree with override
    try:
        bot.tree.add_command(cog.orders_group, override=True)
    except Exception:
        pass  # Command already registered - ignore
