from __future__ import annotations
import time
import random
import discord
from discord.ext import commands
from discord import app_commands

from utils.uk_time import uk_day_ymd
from utils.economy import add_coins, ensure_wallet

ISLA_ICON = "https://i.imgur.com/5nsuuCV.png"
STYLE1_NEUTRAL = "https://i.imgur.com/9oUjOQQ.png"

def now_ts() -> int:
    return int(time.time())

def fmt(n: int) -> str:
    return f"{int(n):,}"

def isla_embed(desc: str, title: str | None = None, thumb: str | None = None) -> discord.Embed:
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
    """
    Streak advances when user completes at least one order that day.
    """
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
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    UK = ZoneInfo("Europe/London")
    dt_today = datetime.fromisoformat(today).replace(tzinfo=UK).date()
    dt_last = None
    try:
        dt_last = datetime.fromisoformat(last).replace(tzinfo=UK).date()
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

class OrdersGroup(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

        # /orders (group)
        self.orders = app_commands.Group(name="orders", description="Orders & streaks")

        self._register()

    # -------------------------
    # /orders view [type]
    # -------------------------
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
            return await interaction.followup.send(embed=isla_embed("No orders right now.\n᲼᲼", title="Orders"), ephemeral=True)

        lines = []
        for r in rows:
            oid = int(r["order_id"])
            otype = str(r["order_type"])
            title = str(r["title"])
            coins = int(r["reward_coins"])
            obed = int(r["reward_obed"])
            dur = int(r["duration_seconds"])
            lines.append(f"**#{oid}** [{otype}] {title} — {fmt(coins)} Coins • {fmt(obed)} Obed • {dur//60}m")

        e = isla_embed("Pick one.\n᲼᲼", title="Orders")
        e.add_field(name="Available", value="\n".join(lines), inline=False)
        e.set_footer(text="Accept with /orders accept <order_id>")
        await interaction.followup.send(embed=e, ephemeral=True)

    # -------------------------
    # /orders accept <order_id>
    # -------------------------
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
            return await interaction.followup.send(embed=isla_embed("That order isn't available.\n᲼᲼", title="Accept"), ephemeral=True)

        # slots check (if max_slots > 0)
        max_slots = int(o["max_slots"] or 0)
        if max_slots > 0:
            c = await self.bot.db.fetchone(
                "SELECT COUNT(*) AS n FROM orders_claims WHERE guild_id=? AND order_id=? AND status='active'",
                (gid, int(order_id))
            )
            if int(c["n"] or 0) >= max_slots:
                return await interaction.followup.send(embed=isla_embed("No slots left.\n᲼᲼", title="Accept"), ephemeral=True)

        # already accepted?
        existing = await self.bot.db.fetchone(
            "SELECT status FROM orders_claims WHERE guild_id=? AND order_id=? AND user_id=?",
            (gid, int(order_id), uid)
        )
        if existing and str(existing["status"]) == "active":
            return await interaction.followup.send(embed=isla_embed("You already accepted that.\n᲼᲼", title="Accept"), ephemeral=True)

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

        e = isla_embed(
            f"Accepted.\n\n"
            f"Order **#{order_id}**\n"
            f"Due: <t:{due}:R>\n"
            "᲼᲼",
            title="Orders"
        )
        e.add_field(name="Task", value=str(o["description"]), inline=False)
        e.set_footer(text="Complete with /orders complete <order_id> [proof]")
        await interaction.followup.send(embed=e, ephemeral=True)

    # -------------------------
    # /orders complete <order_id> [proof]
    # -------------------------
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
            return await interaction.followup.send(embed=isla_embed("You don't have that order active.\n᲼᲼", title="Complete"), ephemeral=True)

        due = int(claim["due_ts"])
        if now_ts() > due:
            return await interaction.followup.send(embed=isla_embed("Too late.\nThat one expired.\n᲼᲼", title="Complete"), ephemeral=True)

        o = await self.bot.db.fetchone(
            """
            SELECT reward_coins, reward_obed, title
            FROM orders_catalog
            WHERE guild_id=? AND order_id=?
            """,
            (gid, int(order_id))
        )
        if not o:
            return await interaction.followup.send(embed=isla_embed("Order not found.\n᲼᲼", title="Complete"), ephemeral=True)

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

        e = isla_embed(
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

    # -------------------------
    # /orders forfeit <order_id>
    # -------------------------
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
            return await interaction.followup.send(embed=isla_embed("You don't have that order active.\n᲼᲼", title="Forfeit"), ephemeral=True)

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

        e = isla_embed(
            f"Forfeit logged.\n\n"
            f"-**{fmt(penalty_coins)} Coins**\n"
            f"-**{fmt(penalty_obed)} Obedience**\n"
            "᲼᲼",
            title="Orders"
        )
        await interaction.followup.send(embed=e, ephemeral=True)

    # -------------------------
    # /orders streak
    # -------------------------
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

        e = isla_embed(
            f"Streak.\n\n"
            f"Obedience: **{fmt(obed)}**\n"
            f"Streak: **{streak} days**\n"
            f"Forgive tokens: **{ft}**\n"
            "᲼᲼",
            title="Streak"
        )
        e.add_field(name="Bonus", value=bonus, inline=False)
        await interaction.followup.send(embed=e, ephemeral=True)

    # -------------------------
    # /obey (micro-task generator)
    # -------------------------
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

        e = isla_embed(
            "Quick task.\n\n"
            f"{micro}\n"
            "᲼᲼",
            title="Obey"
        )
        await interaction.followup.send(embed=e, ephemeral=True)

    # -------------------------
    # /kneel (roleplay-lite commitment + tiny coin delta)
    # -------------------------
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

        e = isla_embed(
            "Fine.\n\n"
            f"{task}\n\n"
            f"{delta} Coins.\n"
            "᲼᲼",
            title="Kneel"
        )
        await interaction.followup.send(embed=e, ephemeral=True)

    # -------------------------
    # /beg [reason] (mercy request; coin sink; may reduce next penalty)
    # -------------------------
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
        from utils.economy import get_wallet
        w = await get_wallet(self.bot.db, gid, uid)
        if w.coins < cost:
            return await interaction.followup.send(embed=isla_embed("Not enough Coins.\n᲼᲼", title="Mercy"), ephemeral=True)

        await add_coins(self.bot.db, gid, uid, -cost, kind="mercy", reason=reason or "mercy request")

        # Store a mercy use token (consumed by your penalty engine later)
        await ensure_obed(self.bot.db, gid, uid)
        await self.bot.db.execute(
            "UPDATE obedience_profile SET mercy_uses = mercy_uses + 1 WHERE guild_id=? AND user_id=?",
            (gid, uid)
        )

        e = isla_embed(
            "Mercy request logged.\n\n"
            f"-**{fmt(cost)} Coins**\n"
            "This may soften the next penalty.\n"
            "᲼᲼",
            title="Beg"
        )
        if reason:
            e.add_field(name="Reason", value=reason[:900], inline=False)
        await interaction.followup.send(embed=e, ephemeral=True)

    # -------------------------
    # /forgive (coins sink, clears one recent penalty record)
    # -------------------------
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
            from utils.economy import get_wallet
            from utils.embed_utils import create_embed
            await ensure_wallet(self.bot.db, gid, uid)
            w = await get_wallet(self.bot.db, gid, uid)
            if w.coins < cost:
                return await interaction.followup.send(embed=isla_embed("Not enough Coins.\n᲼᲼", title="Forgive"), ephemeral=True)
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
            return await interaction.followup.send(embed=isla_embed(msg, title="Forgive"), ephemeral=True)

        await self.bot.db.execute(
            "UPDATE obedience_penalties SET cleared=1 WHERE id=?",
            (int(pen["id"]),)
        )

        e = isla_embed(
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

    # ---------- register ----------
    def _register(self):
        # /orders group
        self.orders.add_command(self.orders_view)
        self.orders.add_command(self.orders_accept)
        self.orders.add_command(self.orders_complete)
        self.orders.add_command(self.orders_forfeit)
        self.orders.add_command(self.orders_streak)
        # Note: /obey, /kneel, /beg, /forgive are standalone commands registered automatically via @app_commands.command decorator

async def setup(bot: commands.Bot):
    # Remove command if it exists before creating cog (to avoid conflicts)
    bot.tree.remove_command("orders", guild=None)
    cog = OrdersGroup(bot)
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
        bot.tree.add_command(cog.orders, override=True)
    except Exception:
        pass  # Command already registered - ignore

