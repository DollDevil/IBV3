from __future__ import annotations
import time
import discord
from discord.ext import commands
from discord import app_commands

from utils.uk_time import uk_day_ymd, uk_now
from utils.economy import get_wallet, add_coins, get_recent_ledger, ensure_wallet

ISLA_ICON = "https://i.imgur.com/5nsuuCV.png"
STYLE1_NEUTRAL = "https://i.imgur.com/9oUjOQQ.png"

PAY_DAILY_LIMIT = 500  # max sent per day

def now_ts() -> int:
    return int(time.time())

def fmt(n: int) -> str:
    return f"{int(n):,}"

def isla_embed(desc: str, title: str | None = None, thumb: str | None = None) -> discord.Embed:
    e = discord.Embed(title=title, description=desc)
    e.set_author(name="Isla", icon_url=ISLA_ICON)
    e.set_thumbnail(url=thumb or STYLE1_NEUTRAL)
    return e

def iso_week_key() -> str:
    d = uk_now().date()
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"

def uk_midnight_ts(day_ymd: str) -> int:
    from datetime import datetime
    from zoneinfo import ZoneInfo
    UK = ZoneInfo("Europe/London")
    dt = datetime.fromisoformat(day_ymd + "T00:00:00").replace(tzinfo=UK)
    return int(dt.timestamp())

class CoinsGroup(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

        # /coins (group)
        self.coins = app_commands.Group(name="coins", description="Coins economy")

        # /coins tax (nested group)
        self.tax = app_commands.Group(name="tax", description="Tax commands", parent=self.coins)

        self._register_commands()

    # ---------- helpers ----------
    async def _sum_sent_today(self, guild_id: int, user_id: int) -> int:
        day = uk_day_ymd(now_ts())
        row = await self.bot.db.fetchone(
            """
            SELECT COALESCE(SUM(-delta), 0) AS sent
            FROM economy_ledger
            WHERE guild_id=? AND user_id=? AND kind='pay_out' AND ts >= ?
            """,
            (guild_id, user_id, uk_midnight_ts(day))
        )
        return int(row["sent"] or 0)

    # ---------- /coins balance ----------
    @app_commands.command(name="balance", description="Coins + daily tax status + pending deductions.")
    @app_commands.describe(user="User to check (defaults to you)")
    async def balance(self, interaction: discord.Interaction, user: discord.Member | None = None):
        await interaction.response.defer(ephemeral=True)
        if not interaction.guild_id:
            return await interaction.followup.send("Server only.", ephemeral=True)

        target = user or interaction.user
        gid = interaction.guild_id
        uid = target.id

        w = await get_wallet(self.bot.db, gid, uid)

        desc = (
            f"{target.mention}\n\n"
            f"Coins: **{fmt(w.coins)}**\n"
            f"Tax debt: **{fmt(w.tax_debt)}**\n"
            "᲼᲼"
        )
        e = isla_embed(desc, title="Balance")
        e.add_field(
            name="Notes",
            value="Tax is capped so inactivity doesn't feel punishing.\nUse `/coins tax status` to see the next tick.",
            inline=False
        )
        await interaction.followup.send(embed=e, ephemeral=True)

    # ---------- /coins daily ----------
    @app_commands.command(name="daily", description="Daily Coins claim (streak-based).")
    async def daily(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild_id
        if not gid:
            return await interaction.followup.send("Server only.", ephemeral=True)

        uid = interaction.user.id
        today = uk_day_ymd(now_ts())

        await self.bot.db.execute(
            "INSERT OR IGNORE INTO economy_daily(guild_id,user_id,streak,last_claim_ymd) VALUES(?,?,0,'')",
            (gid, uid)
        )
        row = await self.bot.db.fetchone(
            "SELECT streak,last_claim_ymd FROM economy_daily WHERE guild_id=? AND user_id=?",
            (gid, uid)
        )
        streak = int(row["streak"] or 0)
        last = str(row["last_claim_ymd"] or "")

        if last == today:
            return await interaction.followup.send(embed=isla_embed("Already claimed today.\n᲼᲼", title="Daily"), ephemeral=True)

        from datetime import datetime, timedelta
        from zoneinfo import ZoneInfo
        UK = ZoneInfo("Europe/London")
        dt_today = datetime.fromisoformat(today).replace(tzinfo=UK).date()
        try:
            dt_last = datetime.fromisoformat(last).replace(tzinfo=UK).date()
        except Exception:
            dt_last = None

        if dt_last and dt_last == (dt_today - timedelta(days=1)):
            streak += 1
        else:
            streak = 1

        base = 80
        bonus = min(120, (streak - 1) * 10)
        amount = base + bonus

        await self.bot.db.execute(
            "UPDATE economy_daily SET streak=?, last_claim_ymd=? WHERE guild_id=? AND user_id=?",
            (streak, today, gid, uid)
        )
        await add_coins(self.bot.db, gid, uid, amount, kind="daily", reason=f"daily streak {streak}")

        e = isla_embed(
            f"Claimed.\n\n+**{fmt(amount)} Coins**\nStreak: **{streak}**\n᲼᲼",
            title="Daily"
        )
        await interaction.followup.send(embed=e, ephemeral=True)

    # ---------- /coins weekly ----------
    @app_commands.command(name="weekly", description="Weekly payout bonus claim (for active participation).")
    async def weekly(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild_id
        if not gid:
            return await interaction.followup.send("Server only.", ephemeral=True)

        uid = interaction.user.id
        wk = iso_week_key()

        await self.bot.db.execute(
            "INSERT OR IGNORE INTO economy_weekly(guild_id,user_id,last_claim_week) VALUES(?,?, '')",
            (gid, uid)
        )
        row = await self.bot.db.fetchone(
            "SELECT last_claim_week FROM economy_weekly WHERE guild_id=? AND user_id=?",
            (gid, uid)
        )
        last = str(row["last_claim_week"] or "")
        if last == wk:
            return await interaction.followup.send(embed=isla_embed("Already claimed this week.\n᲼᲼", title="Weekly"), ephemeral=True)

        cutoff = now_ts() - (7 * 86400)
        r = await self.bot.db.fetchone(
            """
            SELECT COALESCE(SUM(ABS(delta)), 0) AS vol
            FROM economy_ledger
            WHERE guild_id=? AND user_id=? AND ts >= ?
            """,
            (gid, uid, cutoff)
        )
        vol = int(r["vol"] or 0)
        base = 250
        bonus = min(750, vol // 2000)
        amount = base + bonus

        await self.bot.db.execute(
            "UPDATE economy_weekly SET last_claim_week=? WHERE guild_id=? AND user_id=?",
            (wk, gid, uid)
        )
        await add_coins(self.bot.db, gid, uid, amount, kind="weekly", reason=f"weekly bonus {wk}")

        e = isla_embed(f"Weekly payout.\n\n+**{fmt(amount)} Coins**\n᲼᲼", title="Weekly")
        await interaction.followup.send(embed=e, ephemeral=True)

    # ---------- /coins pay ----------
    @app_commands.command(name="pay", description="Peer-to-peer transfer (max 500 a day).")
    @app_commands.describe(user="Recipient", amount="Coins to send", reason="Optional note")
    async def pay(self, interaction: discord.Interaction, user: discord.Member, amount: int, reason: str | None = None):
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild_id
        if not gid:
            return await interaction.followup.send("Server only.", ephemeral=True)

        if user.bot:
            return await interaction.followup.send(embed=isla_embed("Not a bot.\n᲼᲼", title="Pay"), ephemeral=True)

        sender = interaction.user
        if user.id == sender.id:
            return await interaction.followup.send(embed=isla_embed("No.\n᲼᲼", title="Pay"), ephemeral=True)

        if amount <= 0:
            return await interaction.followup.send(embed=isla_embed("Use a real number.\n᲼᲼", title="Pay"), ephemeral=True)

        sent_today = await self._sum_sent_today(gid, sender.id)
        remaining = max(0, PAY_DAILY_LIMIT - sent_today)
        if amount > remaining:
            return await interaction.followup.send(
                embed=isla_embed(f"Limit.\n\nYou can still send **{fmt(remaining)} Coins** today.\n᲼᲼", title="Pay"),
                ephemeral=True
            )

        sw = await get_wallet(self.bot.db, gid, sender.id)
        if sw.coins < amount:
            return await interaction.followup.send(embed=isla_embed("You don't have enough.\n᲼᲼", title="Pay"), ephemeral=True)

        await ensure_wallet(self.bot.db, gid, user.id)
        await add_coins(self.bot.db, gid, sender.id, -amount, kind="pay_out", reason=reason or "", other_user_id=user.id)
        await add_coins(self.bot.db, gid, user.id, +amount, kind="pay_in", reason=reason or "", other_user_id=sender.id)

        e = isla_embed(
            f"Sent.\n\n{sender.mention} → {user.mention}\n**{fmt(amount)} Coins**\n᲼᲼",
            title="Pay"
        )
        if reason:
            e.add_field(name="Reason", value=reason, inline=False)
        await interaction.followup.send(embed=e, ephemeral=True)

    # ---------- /coins top ----------
    @app_commands.command(name="top", description="Leaderboard by day/week/all-time.")
    @app_commands.describe(timeframe="day, week, or all")
    async def top(self, interaction: discord.Interaction, timeframe: str):
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild_id
        if not gid:
            return await interaction.followup.send("Server only.", ephemeral=True)

        tf = timeframe.lower().strip()
        now = now_ts()

        if tf == "day":
            cutoff = now - 86400
            title = "Coins Top (24h volume)"
        elif tf == "week":
            cutoff = now - (7 * 86400)
            title = "Coins Top (7d volume)"
        else:
            cutoff = 0
            title = "Coins Top (all-time volume)"

        rows = await self.bot.db.fetchall(
            """
            SELECT user_id, COALESCE(SUM(ABS(delta)), 0) AS vol
            FROM economy_ledger
            WHERE guild_id=? AND ts >= ?
            GROUP BY user_id
            ORDER BY vol DESC
            LIMIT 10
            """,
            (gid, cutoff)
        )

        lines = []
        guild = interaction.guild
        for i, r in enumerate(rows, start=1):
            uid = int(r["user_id"])
            vol = int(r["vol"] or 0)
            m = guild.get_member(uid)
            name = m.display_name if m else f"User {uid}"
            lines.append(f"{i}) {name} — {fmt(vol)}")

        if not lines:
            lines = ["No data yet."]

        e = isla_embed("Leaderboard.\n᲼᲼", title=title)
        e.add_field(name="Top 10", value="\n".join(lines), inline=False)
        await interaction.followup.send(embed=e, ephemeral=True)

    # ---------- /coins shop ----------
    @app_commands.command(name="shop", description="Displays purchasable perks (attention, mercy, buffs, cosmetics).")
    async def shop(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        e = isla_embed(
            "Shop is open.\n\nUse `/coins buy <item>`.\n᲼᲼",
            title="Coins Shop"
        )
        e.add_field(name="Examples", value="collar_basic_red\ncollar_basic_blue\nmercy_token\ncolor_nameplate", inline=False)
        await interaction.followup.send(embed=e, ephemeral=True)

    # ---------- /coins buy ----------
    @app_commands.command(name="buy", description="Purchase a perk.")
    @app_commands.describe(item="Item ID")
    async def buy(self, interaction: discord.Interaction, item: str):
        await interaction.response.defer(ephemeral=True)
        e = isla_embed(f"Purchased.\n\nItem: **{item}**\n᲼᲼", title="Buy")
        await interaction.followup.send(embed=e, ephemeral=True)

    # ---------- /coins burn ----------
    @app_commands.command(name="burn", description="Sacrifice Coins for attention.")
    @app_commands.describe(amount="Coins to burn", message="Optional message")
    async def burn(self, interaction: discord.Interaction, amount: int, message: str | None = None):
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild_id
        if not gid:
            return await interaction.followup.send("Server only.", ephemeral=True)

        uid = interaction.user.id
        if amount <= 0:
            return await interaction.followup.send(embed=isla_embed("Use a real number.\n᲼᲼", title="Burn"), ephemeral=True)

        w = await get_wallet(self.bot.db, gid, uid)
        if w.coins < amount:
            return await interaction.followup.send(embed=isla_embed("You don't have enough.\n᲼᲼", title="Burn"), ephemeral=True)

        await add_coins(self.bot.db, gid, uid, -amount, kind="burn", reason=message or "burn")

        desc = f"Burned.\n\n-**{fmt(amount)} Coins**\n"
        if message:
            desc += f"\n\"{message}\"\n"
        desc += "᲼᲼"
        await interaction.followup.send(embed=isla_embed(desc, title="Burn"), ephemeral=True)

    # =========================
    # /coins tax status (nested)
    # =========================
    @app_commands.command(name="status", description="Shows inactivity tax rules and next tick.")
    async def tax_status(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild_id
        if not gid:
            return await interaction.followup.send("Server only.", ephemeral=True)

        uid = interaction.user.id
        w = await get_wallet(self.bot.db, gid, uid)

        e = isla_embed(
            f"Tax status.\n\n"
            f"Current debt: **{fmt(w.tax_debt)} Coins**\n"
            "Tax debt is capped.\n"
            "᲼᲼",
            title="Tax"
        )
        e.add_field(name="Next tick", value="Daily tick (UK time).", inline=False)
        e.add_field(name="Avoid it", value="Stay active or use `/vacation` properly.", inline=False)
        await interaction.followup.send(embed=e, ephemeral=True)

    # ---------- /coins history ----------
    @app_commands.command(name="history", description="Last transactions (default: you).")
    @app_commands.describe(user="User to view (defaults to you)", limit="How many (default 20)")
    async def history(self, interaction: discord.Interaction, user: discord.Member | None = None, limit: int = 20):
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild_id
        if not gid:
            return await interaction.followup.send("Server only.", ephemeral=True)

        target = user or interaction.user
        uid = target.id
        limit = max(1, min(50, int(limit)))

        rows = await get_recent_ledger(self.bot.db, gid, uid, limit=limit)
        if not rows:
            return await interaction.followup.send(embed=isla_embed("Nothing yet.\n᲼᲼", title="History"), ephemeral=True)

        lines = []
        for r in rows:
            delta = int(r["delta"])
            kind = str(r["kind"])
            reason = str(r["reason"] or "")
            ts = int(r["ts"])
            sign = "+" if delta >= 0 else ""
            t = time.strftime("%Y-%m-%d %H:%M", time.gmtime(ts))
            extra = f" — {reason}" if reason else ""
            lines.append(f"`{t}` {sign}{delta} ({kind}){extra}")

        e = isla_embed(f"{target.mention}\n᲼᲼", title="History")
        e.add_field(name=f"Last {limit}", value="\n".join(lines[:25]), inline=False)
        await interaction.followup.send(embed=e, ephemeral=True)

    # ---------- register groups + commands ----------
    def _register_commands(self):
        # /coins
        self.coins.add_command(self.balance)
        self.coins.add_command(self.daily)
        self.coins.add_command(self.weekly)
        self.coins.add_command(self.pay)
        self.coins.add_command(self.top)
        self.coins.add_command(self.shop)
        self.coins.add_command(self.buy)
        self.coins.add_command(self.burn)
        self.coins.add_command(self.history)

        # /coins tax status
        self.tax.add_command(self.tax_status)

async def setup(bot: commands.Bot):
    cog = CoinsGroup(bot)
    await bot.add_cog(cog)
    try:
        bot.tree.add_command(cog.coins)
    except Exception:
        pass  # Command already registered
