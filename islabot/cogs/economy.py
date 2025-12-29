from __future__ import annotations

import json
import math
import time
import discord
from discord.ext import commands, tasks
from discord import app_commands

from core.utility import now_ts, fmt
from utils.helpers import isla_embed, now_ts as now_ts_helper, ensure_user_row
from utils.embed_utils import create_embed
from utils.uk_time import uk_day_ymd, uk_now
from utils.economy import get_wallet, add_coins, get_recent_ledger, ensure_wallet

ISLA_ICON = "https://i.imgur.com/5nsuuCV.png"
STYLE1_NEUTRAL = "https://i.imgur.com/9oUjOQQ.png"

# Tax configuration (from quarterly_tax.py)
TAX_INTERVAL_SECONDS = 4 * 30 * 24 * 3600  # 4 months
WARNING_7D_SECONDS = 7 * 24 * 3600
WARNING_3D_SECONDS = 3 * 24 * 3600
WARNING_24H_SECONDS = 24 * 3600
TAX_TONE_DURATION = 24 * 3600
TAX_RATE = 0.10  # 10%
MIN_BALANCE_FOR_TAX = 10

# Pay daily limit (from coins_group.py)
PAY_DAILY_LIMIT = 500

# Shop defaults (from shop.py)
DEFAULT_COLLARS_BASE = [
    ("collar_base_black", "Basic Collar Black", 150),
    ("collar_base_red", "Basic Collar Red", 250),
    ("collar_base_white", "Basic Collar White", 250),
    ("collar_base_blue", "Basic Collar Blue", 350),
    ("collar_base_pink", "Basic Collar Pink", 350),
    ("collar_base_green", "Basic Collar Green", 450),
    ("collar_base_purple", "Basic Collar Purple", 450),
]

DEFAULT_COLLARS_PREMIUM = [
    ("collar_premium_goldtrim", "Premium Collar Gold Trim", 7000),
    ("collar_premium_neon", "Premium Collar Neon", 12000),
    ("collar_premium_leather", "Premium Collar Leather", 15000),
]

DEFAULT_COLLARS_PRESTIGE = [
    ("collar_prestige_obsidian", "Prestige Collar Obsidian", 65000),
    ("collar_prestige_crowned", "Prestige Collar Crowned", 95000),
]

DEFAULT_LIMITED = [
    ("collar_limited_winter_silver", "Limited Winter Collar Silver", "limited", 18000, {"season": "winter"}),
    ("collar_limited_valentine_rose", "Limited Valentine Collar Rose", "limited", 22000, {"season": "valentine"})
]

# Helper functions
def calculate_tax(coins: int) -> tuple[int, int]:
    """Calculate tax amount and new balance. Returns: (coins_taken, new_balance)"""
    if coins < MIN_BALANCE_FOR_TAX:
        return (0, coins)
    coins_taken = max(1, math.floor(coins * TAX_RATE))
    new_balance = max(0, coins - coins_taken)
    return (coins_taken, new_balance)

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

# ============================================================================
# MAIN ECONOMY COG CLASS
# ============================================================================

class Economy(commands.Cog):
    """Consolidated Economy cog: Coins, shop, tax, and all economy-related commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.icon = ISLA_ICON
        
        # Setup coins group (from coins_group.py)
        self.coins = app_commands.Group(name="coins", description="Coins economy")
        self.tax_group = app_commands.Group(name="tax", description="Tax commands", parent=self.coins)
        
        # Start tax check task
        self.tax_check.start()
        
        # Register commands
        self._register_commands()

    def cog_unload(self):
        self.tax_check.cancel()
    
    def _register_commands(self):
        """Register all commands to their groups."""
        # /coins commands
        self.coins.add_command(self.balance)
        self.coins.add_command(self.daily)
        self.coins.add_command(self.weekly)
        self.coins.add_command(self.pay)
        self.coins.add_command(self.top)
        # shop_browse removed from coins group (use /shop_tier instead)
        self.coins.add_command(self.buy_item)
        self.coins.add_command(self.burn)
        self.coins.add_command(self.history)
        
        # /coins tax commands
        self.tax_group.add_command(self.tax_status)

    # ========================================================================
    # QUARTERLY TAX TASK (from quarterly_tax.py)
    # ========================================================================
    
    async def _ensure_tax_schedule(self, gid: int) -> dict:
        """Ensure tax schedule exists for guild."""
        row = await self.bot.db.fetchone(
            "SELECT next_tax_ts, last_tax_ts FROM tax_schedule WHERE guild_id=?",
            (gid,)
        )
        
        if not row:
            next_ts = now_ts() + TAX_INTERVAL_SECONDS
            try:
                await self.bot.db.execute(
                    "INSERT INTO tax_schedule(guild_id, next_tax_ts, last_tax_ts) VALUES(?,?,?)",
                    (gid, next_ts, 0)
                )
            except Exception:
                row = await self.bot.db.fetchone(
                    "SELECT next_tax_ts, last_tax_ts FROM tax_schedule WHERE guild_id=?",
                    (gid,)
                )
                if row:
                    return dict(row)
                return {"next_tax_ts": next_ts, "last_tax_ts": 0}
            return {"next_tax_ts": next_ts, "last_tax_ts": 0}
        
        return dict(row)

    async def _get_orders_channel(self, guild: discord.Guild) -> discord.TextChannel | None:
        """Get the orders channel for tax announcements."""
        ch_id = int(self.bot.cfg.get("channels", "orders", default="0") or 0)
        if not ch_id:
            return None
        ch = guild.get_channel(ch_id)
        return ch if isinstance(ch, discord.TextChannel) else None

    async def _send_warning(self, guild: discord.Guild, days: int, message: str):
        """Send a tax warning to the orders channel."""
        ch = await self._get_orders_channel(guild)
        if not ch:
            return
        e = isla_embed(message, title="Tax Notice", icon=self.icon)
        await ch.send(embed=e)

    async def _send_execution(self, guild: discord.Guild, total_taken: int, user_count: int):
        """Send the tax execution message."""
        ch = await self._get_orders_channel(guild)
        if not ch:
            return
        desc = (
            "I warned you.\n"
            "I always do.\n\n"
            f"**{fmt(total_taken)} Coins** collected from **{user_count}** users.\n"
            "᲼᲼"
        )
        e = isla_embed(desc, title="Tax Collected", icon=self.icon)
        await ch.send(embed=e)

    async def _execute_tax(self, guild: discord.Guild, gid: int):
        """Execute the tax: collect 10% from all users."""
        try:
            users = await self.bot.db.fetchall(
                "SELECT user_id, coins FROM users WHERE guild_id=? AND coins > 0",
                (gid,)
            )
            
            if not users:
                return 0, 0
            
            total_taken = 0
            user_count = 0
            tax_ts = now_ts()
            
            for row in users:
                uid = int(row["user_id"])
                coins_before = int(row["coins"])
                
                if coins_before < MIN_BALANCE_FOR_TAX:
                    continue
                
                coins_taken, coins_after = calculate_tax(coins_before)
                
                if coins_taken > 0:
                    await self.bot.db.execute(
                        "UPDATE users SET coins=? WHERE guild_id=? AND user_id=?",
                        (coins_after, gid, uid)
                    )
                    try:
                        await self.bot.db.execute(
                            "INSERT INTO coin_ledger(guild_id,user_id,ts,delta,reason) VALUES(?,?,?,?,?)",
                            (gid, uid, tax_ts, -coins_taken, "quarterly_tax")
                        )
                    except Exception:
                        pass
                    try:
                        await self.bot.db.execute(
                            "INSERT INTO tax_log(guild_id, tax_ts, user_id, coins_before, coins_taken, coins_after) VALUES(?,?,?,?,?,?)",
                            (gid, tax_ts, uid, coins_before, coins_taken, coins_after)
                        )
                    except Exception:
                        pass
                    
                    total_taken += coins_taken
                    user_count += 1
            
            next_tax_ts = now_ts() + TAX_INTERVAL_SECONDS
            await self.bot.db.execute(
                "UPDATE tax_schedule SET last_tax_ts=?, next_tax_ts=?, warning_7d_sent=0, warning_3d_sent=0, warning_24h_sent=0, tax_tone_until_ts=? WHERE guild_id=?",
                (tax_ts, next_tax_ts, now_ts() + TAX_TONE_DURATION, gid)
            )
            
            try:
                await self._send_execution(guild, total_taken, user_count)
            except Exception as e:
                print(f"ERROR: Failed to send tax execution message for guild {gid}: {e}")
            
            return total_taken, user_count
        except Exception as e:
            print(f"ERROR: Error executing tax for guild {gid}: {e}")
            raise

    @tasks.loop(minutes=60)
    async def tax_check(self):
        """Check for upcoming taxes and send warnings/execute."""
        await self.bot.wait_until_ready()
        now = now_ts()
        
        for guild in self.bot.guilds:
            gid = guild.id
            schedule = await self._ensure_tax_schedule(gid)
            next_tax = int(schedule["next_tax_ts"])
            time_until = next_tax - now
            
            if time_until <= 0:
                await self._execute_tax(guild, gid)
                continue
            
            row = await self.bot.db.fetchone(
                "SELECT warning_7d_sent, warning_3d_sent, warning_24h_sent FROM tax_schedule WHERE guild_id=?",
                (gid,)
            )
            if not row:
                continue
            
            warning_7d = int(row["warning_7d_sent"] or 0)
            warning_3d = int(row["warning_3d_sent"] or 0)
            warning_24h = int(row["warning_24h_sent"] or 0)
            
            if not warning_7d and time_until <= WARNING_7D_SECONDS:
                await self._send_warning(guild, 7, "In one week, I collect my tax.\nCount your Coins carefully.\n᲼᲼")
                await self.bot.db.execute("UPDATE tax_schedule SET warning_7d_sent=1 WHERE guild_id=?", (gid,))
            
            if not warning_3d and time_until <= WARNING_3D_SECONDS:
                await self._send_warning(guild, 3, "Hoarding never ends well.\nYou still have time to make better choices.\n᲼᲼")
                await self.bot.db.execute("UPDATE tax_schedule SET warning_3d_sent=1 WHERE guild_id=?", (gid,))
            
            if not warning_24h and time_until <= WARNING_24H_SECONDS:
                await self._send_warning(guild, 1, "Tomorrow, I take ten percent.\nSpend them. Burn them. Or lose them.\n᲼᲼")
                await self.bot.db.execute("UPDATE tax_schedule SET warning_24h_sent=1 WHERE guild_id=?", (gid,))

    @tax_check.before_loop
    async def before_tax_check(self):
        await self.bot.wait_until_ready()
    
    # ========================================================================
    # COINS GROUP COMMANDS (from coins_group.py - using these as primary)
    # ========================================================================
    
    @app_commands.command(name="balance", description="Coins + daily tax status + pending deductions.")
    @app_commands.describe(user="User to check (defaults to you)")
    async def balance(self, interaction: discord.Interaction, user: discord.Member | None = None):
        await interaction.response.defer(ephemeral=True)
        if not interaction.guild_id:
            embed = create_embed("Server only.", color="warning", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)

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
        e = isla_embed(desc, title="Balance", icon=self.icon)
        e.add_field(
            name="Notes",
            value="Tax is capped so inactivity doesn't feel punishing.\nUse `/coins tax status` to see the next tick.",
            inline=False
        )
        await interaction.followup.send(embed=e, ephemeral=True)

    @app_commands.command(name="daily", description="Daily Coins claim (streak-based).")
    async def daily(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild_id
        if not gid:
            embed = create_embed("Server only.", color="warning", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)

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
            return await interaction.followup.send(embed=isla_embed("Already claimed today.\n᲼᲼", title="Daily", icon=self.icon), ephemeral=True)

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
            title="Daily",
            icon=self.icon
        )
        await interaction.followup.send(embed=e, ephemeral=True)

    @app_commands.command(name="weekly", description="Weekly payout bonus claim (for active participation).")
    async def weekly(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild_id
        if not gid:
            embed = create_embed("Server only.", color="warning", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)

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
            return await interaction.followup.send(embed=isla_embed("Already claimed this week.\n᲼᲼", title="Weekly", icon=self.icon), ephemeral=True)

        cutoff = now_ts() - (7 * 86400)
        r = await self.bot.db.fetchone(
            "SELECT COALESCE(SUM(ABS(delta)), 0) AS vol FROM economy_ledger WHERE guild_id=? AND user_id=? AND ts >= ?",
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

        e = isla_embed(f"Weekly payout.\n\n+**{fmt(amount)} Coins**\n᲼᲼", title="Weekly", icon=self.icon)
        await interaction.followup.send(embed=e, ephemeral=True)

    async def _sum_sent_today(self, guild_id: int, user_id: int) -> int:
        day = uk_day_ymd(now_ts())
        row = await self.bot.db.fetchone(
            "SELECT COALESCE(SUM(-delta), 0) AS sent FROM economy_ledger WHERE guild_id=? AND user_id=? AND kind='pay_out' AND ts >= ?",
            (guild_id, user_id, uk_midnight_ts(day))
        )
        return int(row["sent"] or 0)

    @app_commands.command(name="pay", description="Peer-to-peer transfer (max 500 a day).")
    @app_commands.describe(user="Recipient", amount="Coins to send", reason="Optional note")
    async def pay(self, interaction: discord.Interaction, user: discord.Member, amount: int, reason: str | None = None):
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild_id
        if not gid:
            embed = create_embed("Server only.", color="warning", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)

        if user.bot:
            return await interaction.followup.send(embed=isla_embed("Not a bot.\n᲼᲼", title="Pay", icon=self.icon), ephemeral=True)

        sender = interaction.user
        if user.id == sender.id:
            return await interaction.followup.send(embed=isla_embed("No.\n᲼᲼", title="Pay", icon=self.icon), ephemeral=True)

        if amount <= 0:
            return await interaction.followup.send(embed=isla_embed("Use a real number.\n᲼᲼", title="Pay", icon=self.icon), ephemeral=True)

        sent_today = await self._sum_sent_today(gid, sender.id)
        remaining = max(0, PAY_DAILY_LIMIT - sent_today)
        if amount > remaining:
            return await interaction.followup.send(
                embed=isla_embed(f"Limit.\n\nYou can still send **{fmt(remaining)} Coins** today.\n᲼᲼", title="Pay", icon=self.icon),
                ephemeral=True
            )

        sw = await get_wallet(self.bot.db, gid, sender.id)
        if sw.coins < amount:
            return await interaction.followup.send(embed=isla_embed("You don't have enough.\n᲼᲼", title="Pay", icon=self.icon), ephemeral=True)

        await ensure_wallet(self.bot.db, gid, user.id)
        await add_coins(self.bot.db, gid, sender.id, -amount, kind="pay_out", reason=reason or "", other_user_id=user.id)
        await add_coins(self.bot.db, gid, user.id, +amount, kind="pay_in", reason=reason or "", other_user_id=sender.id)

        e = isla_embed(
            f"Sent.\n\n{sender.mention} → {user.mention}\n**{fmt(amount)} Coins**\n᲼᲼",
            title="Pay",
            icon=self.icon
        )
        if reason:
            e.add_field(name="Reason", value=reason, inline=False)
        await interaction.followup.send(embed=e, ephemeral=True)

    @app_commands.command(name="top", description="Leaderboard by day/week/all-time.")
    @app_commands.describe(timeframe="day, week, or all")
    async def top(self, interaction: discord.Interaction, timeframe: str):
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild_id
        if not gid:
            embed = create_embed("Server only.", color="warning", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)

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
            "SELECT user_id, COALESCE(SUM(ABS(delta)), 0) AS vol FROM economy_ledger WHERE guild_id=? AND ts >= ? GROUP BY user_id ORDER BY vol DESC LIMIT 10",
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

        e = isla_embed("Leaderboard.\n᲼᲼", title=title, icon=self.icon)
        e.add_field(name="Top 10", value="\n".join(lines), inline=False)
        await interaction.followup.send(embed=e, ephemeral=True)

    @app_commands.command(name="shop_info", description="Displays purchasable perks (attention, mercy, buffs, cosmetics).")
    async def shop_browse(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        e = isla_embed(
            "Shop is open.\n\nUse `/coins buy <item>` or `/shop tier:base`.\n᲼᲼",
            title="Coins Shop",
            icon=self.icon
        )
        e.add_field(name="Examples", value="collar_basic_red\ncollar_basic_blue\nmercy_token\ncolor_nameplate", inline=False)
        await interaction.followup.send(embed=e, ephemeral=True)

    @app_commands.command(name="buy", description="Purchase a perk or shop item.")
    @app_commands.describe(item="Item ID")
    async def buy_item(self, interaction: discord.Interaction, item: str):
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild_id
        if not gid:
            embed = create_embed("Server only.", color="warning", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)
        
        uid = interaction.user.id
        await ensure_wallet(self.bot.db, gid, uid)
        
        # Try to find in shop_items first (from shop.py)
        row = await self.bot.db.fetchone(
            "SELECT name,price,slot,active FROM shop_items WHERE guild_id=? AND item_id=?",
            (gid, item)
        )
        
        if row and int(row["active"]) == 1:
            # Shop item purchase
            price = int(row["price"])
            w = await get_wallet(self.bot.db, gid, uid)
            if w.coins < price:
                return await interaction.followup.send(embed=isla_embed("Not enough Coins.\n᲼᲼", title="Buy", icon=self.icon), ephemeral=True)
            
            await add_coins(self.bot.db, gid, uid, -price, kind="buy", reason=f"shop:{item}")
            await self.bot.db.execute(
                "INSERT INTO inventory(guild_id,user_id,item_id,qty,acquired_ts) VALUES(?,?,?,?,?) ON CONFLICT(guild_id,user_id,item_id) DO UPDATE SET qty = qty + 1",
                (gid, uid, item, 1, now_ts())
            )
            
            desc = f"{interaction.user.mention}\nPurchased **{row['name']}** for **{fmt(price)} Coins**.\n᲼᲼"
            return await interaction.followup.send(embed=isla_embed(desc, title="Buy", icon=self.icon), ephemeral=True)
        else:
            # Generic purchase (from coins_group.py)
            e = isla_embed(f"Purchased.\n\nItem: **{item}**\n᲼᲼", title="Buy", icon=self.icon)
            await interaction.followup.send(embed=e, ephemeral=True)

    @app_commands.command(name="burn", description="Sacrifice Coins for attention.")
    @app_commands.describe(amount="Coins to burn", message="Optional message")
    async def burn(self, interaction: discord.Interaction, amount: int, message: str | None = None):
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild_id
        if not gid:
            embed = create_embed("Server only.", color="warning", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)

        uid = interaction.user.id
        if amount <= 0:
            return await interaction.followup.send(embed=isla_embed("Use a real number.\n᲼᲼", title="Burn", icon=self.icon), ephemeral=True)

        w = await get_wallet(self.bot.db, gid, uid)
        if w.coins < amount:
            return await interaction.followup.send(embed=isla_embed("You don't have enough.\n᲼᲼", title="Burn", icon=self.icon), ephemeral=True)

        await add_coins(self.bot.db, gid, uid, -amount, kind="burn", reason=message or "burn")

        desc = f"Burned.\n\n-**{fmt(amount)} Coins**\n"
        if message:
            desc += f"\n\"{message}\"\n"
        desc += "᲼᲼"
        await interaction.followup.send(embed=isla_embed(desc, title="Burn", icon=self.icon), ephemeral=True)

    @app_commands.command(name="history", description="Last transactions (default: you).")
    @app_commands.describe(user="User to view (defaults to you)", limit="How many (default 20)")
    async def history(self, interaction: discord.Interaction, user: discord.Member | None = None, limit: int = 20):
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild_id
        if not gid:
            embed = create_embed("Server only.", color="warning", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)

        target = user or interaction.user
        uid = target.id
        limit = max(1, min(50, int(limit)))

        rows = await get_recent_ledger(self.bot.db, gid, uid, limit=limit)
        if not rows:
            return await interaction.followup.send(embed=isla_embed("Nothing yet.\n᲼᲼", title="History", icon=self.icon), ephemeral=True)

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

        e = isla_embed(f"{target.mention}\n᲼᲼", title="History", icon=self.icon)
        e.add_field(name=f"Last {limit}", value="\n".join(lines[:25]), inline=False)
        await interaction.followup.send(embed=e, ephemeral=True)

    @app_commands.command(name="status", description="Shows inactivity tax rules and next tick.")
    async def tax_status(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild_id
        if not gid:
            embed = create_embed("Server only.", color="warning", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)

        uid = interaction.user.id
        w = await get_wallet(self.bot.db, gid, uid)

        e = isla_embed(
            f"Tax status.\n\n"
            f"Current debt: **{fmt(w.tax_debt)} Coins**\n"
            "Tax debt is capped.\n"
            "᲼᲼",
            title="Tax",
            icon=self.icon
        )
        e.add_field(name="Next tick", value="Daily tick (UK time).", inline=False)
        e.add_field(name="Avoid it", value="Stay active or use `/vacation` properly.", inline=False)
        await interaction.followup.send(embed=e, ephemeral=True)
    
    # ========================================================================
    # SHOP COMMANDS (from shop.py)
    # ========================================================================
    
    async def seed_default_shop(self, gid: int):
        """Seed default shop items."""
        for item_id, name, price in DEFAULT_COLLARS_BASE:
            meta = {"color": item_id.split("_")[-1]}
            await self.bot.db.execute(
                "INSERT OR IGNORE INTO shop_items(guild_id,item_id,name,tier,price,slot,meta_json,active) VALUES(?,?,?,?,?,?,?,1)",
                (gid, item_id, name, "base", price, "collar", json.dumps(meta))
            )
        for item_id, name, price in DEFAULT_COLLARS_PREMIUM:
            meta = {"style": "premium"}
            await self.bot.db.execute(
                "INSERT OR IGNORE INTO shop_items(guild_id,item_id,name,tier,price,slot,meta_json,active) VALUES(?,?,?,?,?,?,?,1)",
                (gid, item_id, name, "premium", price, "collar", json.dumps(meta))
            )
        for item_id, name, price in DEFAULT_COLLARS_PRESTIGE:
            meta = {"style": "prestige"}
            await self.bot.db.execute(
                "INSERT OR IGNORE INTO shop_items(guild_id,item_id,name,tier,price,slot,meta_json,active) VALUES(?,?,?,?,?,?,?,1)",
                (gid, item_id, name, "prestige", price, "collar", json.dumps(meta))
            )
        for item_id, name, tier, price, meta in DEFAULT_LIMITED:
            await self.bot.db.execute(
                "INSERT OR IGNORE INTO shop_items(guild_id,item_id,name,tier,price,slot,meta_json,active) VALUES(?,?,?,?,?,?,?,0)",
                (gid, item_id, name, tier, int(price), "collar", json.dumps(meta))
            )
        allin_items = [
            ("badge_allin_mark", "Badge All-In Mark", "premium", 9000, "badge", {"style": "allin", "rarity": "premium"}),
            ("collar_allin_strap_black", "All-In Collar Black Strap", "premium", 14000, "collar", {"style": "allin", "color": "black"}),
            ("collar_allin_strap_red", "All-In Collar Red Strap", "premium", 16000, "collar", {"style": "allin", "color": "red"}),
            ("collar_allin_obsidian", "All-In Collar Obsidian", "prestige", 85000, "collar", {"style": "allin", "rarity": "prestige"}),
        ]
        for item_id, name, tier, price, slot, meta in allin_items:
            await self.bot.db.execute(
                "INSERT OR IGNORE INTO shop_items(guild_id,item_id,name,tier,price,slot,meta_json,active) VALUES(?,?,?,?,?,?,?,1)",
                (gid, item_id, name, tier, int(price), slot, json.dumps(meta))
            )

    @app_commands.command(name="shop_tier", description="Browse the shop by tier.")
    @app_commands.describe(tier="base|premium|prestige|limited")
    async def shop_tier(self, interaction: discord.Interaction, tier: str = "base"):
        if not interaction.guild_id:
            embed = create_embed("Use this in a server.", color="info", is_dm=False, is_system=False)
            return await interaction.response.send_message(embed=embed, ephemeral=True)
        gid = interaction.guild_id
        tier = tier.lower().strip()
        if tier not in ("base", "premium", "prestige", "limited"):
            tier = "base"

        rows = await self.bot.db.fetchall(
            "SELECT item_id,name,price,slot FROM shop_items WHERE guild_id=? AND tier=? AND active=1 ORDER BY price ASC LIMIT 25",
            (gid, tier)
        )
        if not rows:
            embed = create_embed("No items found for that tier.", color="info", is_dm=False, is_system=False)
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        lines = []
        for r in rows:
            lines.append(f"**{r['name']}** — `{r['item_id']}` — **{fmt(int(r['price']))} Coins**")
        desc = f"{interaction.user.mention}\n{tier.title()} Shop\n\n" + "\n".join(lines) + "\n᲼᲼"
        await interaction.response.send_message(embed=isla_embed(desc, title="Shop", icon=self.icon), ephemeral=True)

    @app_commands.command(name="inventory", description="View your inventory.")
    async def inventory(self, interaction: discord.Interaction):
        if not interaction.guild_id:
            embed = create_embed("Use this in a server.", color="info", is_dm=False, is_system=False)
            return await interaction.response.send_message(embed=embed, ephemeral=True)
        gid = interaction.guild_id
        uid = interaction.user.id

        rows = await self.bot.db.fetchall(
            "SELECT item_id, qty FROM inventory WHERE guild_id=? AND user_id=? ORDER BY acquired_ts DESC LIMIT 50",
            (gid, uid)
        )
        if not rows:
            embed = create_embed("Inventory is empty.", color="info", is_dm=False, is_system=False)
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        lines = [f"`{r['item_id']}` x{int(r['qty'])}" for r in rows]
        desc = f"{interaction.user.mention}\nInventory\n\n" + "\n".join(lines) + "\n᲼᲼"
        await interaction.response.send_message(embed=isla_embed(desc, title="Inventory", icon=self.icon), ephemeral=True)

    @app_commands.command(name="equip", description="Equip an item you own (e.g., collar).")
    @app_commands.describe(slot="collar", item_id="Item ID from your inventory")
    async def equip(self, interaction: discord.Interaction, slot: str, item_id: str):
        if not interaction.guild_id:
            embed = create_embed("Use this in a server.", color="info", is_dm=False, is_system=False)
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        gid = interaction.guild_id
        uid = interaction.user.id
        slot = slot.lower().strip()
        if slot not in ("collar", "badge"):
            embed = create_embed("Unsupported slot.", color="info", is_dm=False, is_system=False)
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        inv = await self.bot.db.fetchone(
            "SELECT qty FROM inventory WHERE guild_id=? AND user_id=? AND item_id=?",
            (gid, uid, item_id)
        )
        if not inv or int(inv["qty"]) <= 0:
            embed = create_embed("You don't own that item.", color="info", is_dm=False, is_system=False)
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        await self.bot.db.execute(
            "INSERT INTO equips(guild_id,user_id,slot,item_id,equipped_ts) VALUES(?,?,?,?,?) ON CONFLICT(guild_id,user_id,slot) DO UPDATE SET item_id=excluded.item_id, equipped_ts=excluded.equipped_ts",
            (gid, uid, slot, item_id, now_ts())
        )

        desc = f"{interaction.user.mention}\nEquipped `{item_id}` in **{slot}**.\n᲼᲼"
        await interaction.response.send_message(embed=isla_embed(desc, title="Equip", icon=self.icon), ephemeral=True)

    @app_commands.command(name="collars_setup", description="(Admin) Seed default collar shop items and enable collar equips.")
    @app_commands.checks.has_permissions(administrator=True)
    async def collars_setup(self, interaction: discord.Interaction):
        if not interaction.guild_id:
            embed = create_embed("Use this in a server.", color="info", is_dm=False, is_system=False)
            return await interaction.response.send_message(embed=embed, ephemeral=True)
        gid = interaction.guild_id

        await self.seed_default_shop(gid)
        await self.bot.db.execute(
            "INSERT OR IGNORE INTO guild_settings(guild_id, collars_role_enabled, collars_role_prefix, log_channel_id) VALUES(?,?,?,?)",
            (gid, 0, "Collar", int(self.bot.cfg.get("channels", "logs", default=0) or 0))
        )

        desc = "Collar shop seeded.\nUse `/shop tier:base` to browse.\nUse `/buy item_id:...` then `/equip slot:collar item_id:...`.\n᲼᲼"
        await interaction.response.send_message(embed=isla_embed(desc, title="Setup", icon=self.icon), ephemeral=True)
    
    # ========================================================================
    # ADMIN COMMANDS (from economy.py)
    # ========================================================================
    
    @app_commands.command(name="coins_add", description="(Admin) Add Coins to a user.")
    @app_commands.checks.has_permissions(administrator=True)
    async def coins_add(self, interaction: discord.Interaction, user: discord.Member, amount: int, reason: str = "admin"):
        if not interaction.guild_id:
            embed = create_embed("Use this in a server.", color="info", is_dm=False, is_system=False)
            return await interaction.response.send_message(embed=embed, ephemeral=True)
        gid = interaction.guild_id
        await add_coins(self.bot.db, gid, user.id, amount, kind="admin_add", reason=reason)
        desc = f"{user.mention} received **{fmt(amount)} Coins**.\nReason: {reason}\n᲼᲼"
        await interaction.response.send_message(embed=isla_embed(desc, title="Admin", icon=self.icon), ephemeral=True)

    @app_commands.command(name="coins_set", description="(Admin) Set a user's Coins.")
    @app_commands.checks.has_permissions(administrator=True)
    async def coins_set(self, interaction: discord.Interaction, user: discord.Member, amount: int):
        if not interaction.guild_id:
            embed = create_embed("Use this in a server.", color="info", is_dm=False, is_system=False)
            return await interaction.response.send_message(embed=embed, ephemeral=True)
        gid = interaction.guild_id
        await ensure_wallet(self.bot.db, gid, user.id)
        await self.bot.db.execute(
            "UPDATE users SET coins=? WHERE guild_id=? AND user_id=?",
            (amount, gid, user.id)
        )
        desc = f"{user.mention} now has **{fmt(amount)} Coins**.\n᲼᲼"
        await interaction.response.send_message(embed=isla_embed(desc, title="Admin", icon=self.icon), ephemeral=True)
    
    # Admin commands for tax (from quarterly_tax.py)
    @commands.command(name="tax_trigger", hidden=True)
    @commands.has_permissions(administrator=True)
    async def tax_trigger(self, ctx: commands.Context):
        """Manually trigger tax execution (admin only)."""
        if not ctx.guild:
            return await ctx.send("Server only.")
        gid = ctx.guild.id
        total, count = await self._execute_tax(ctx.guild, gid)
        await ctx.send(f"Tax executed: {fmt(total)} coins from {count} users.", delete_after=10)

    @commands.command(name="tax_status", hidden=True)
    @commands.has_permissions(administrator=True)
    async def tax_status_admin(self, ctx: commands.Context):
        """Check tax schedule status (admin only)."""
        if not ctx.guild:
            return await ctx.send("Server only.")
        gid = ctx.guild.id
        schedule = await self._ensure_tax_schedule(gid)
        next_tax = int(schedule["next_tax_ts"])
        last_tax = int(schedule.get("last_tax_ts", 0) or 0)
        now = now_ts()
        days_until = (next_tax - now) / (24 * 3600)
        msg = f"**Tax Schedule**\nNext tax: {days_until:.1f} days\nLast tax: {time.ctime(last_tax) if last_tax > 0 else 'Never'}\n"
        await ctx.send(msg, delete_after=30)


async def setup(bot: commands.Bot):
    bot.tree.remove_command("coins", guild=None)
    cog = Economy(bot)
    await bot.add_cog(cog)
    try:
        bot.tree.add_command(cog.coins, override=True)
    except Exception:
        pass  # Command already registered - ignore

