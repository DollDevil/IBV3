"""
Quarterly Tax System

One event. Predictable. Inevitable. Feared.

Every 4 months, Isla collects 10% of each user's Coin balance.
No opt-out. No appeals. Safeword only suppresses humiliation, not the tax.

Warning timeline:
- 7 days before: "In one week, I collect my tax. Count your Coins carefully."
- 3 days before: "Hoarding never ends well. You still have time to make better choices."
- 24 hours before: "Tomorrow, I take ten percent. Spend them. Burn them. Or lose them."
- Execution: "I warned you. I always do."
"""

from __future__ import annotations

import time
import math
import discord
from discord.ext import commands, tasks
from utils.helpers import isla_embed, now_ts
from core.utils import fmt
from utils.embed_utils import create_embed

# Tax configuration
TAX_INTERVAL_SECONDS = 4 * 30 * 24 * 3600  # 4 months in seconds (approximate)
WARNING_7D_SECONDS = 7 * 24 * 3600
WARNING_3D_SECONDS = 3 * 24 * 3600
WARNING_24H_SECONDS = 24 * 3600
TAX_TONE_DURATION = 24 * 3600  # 24 hours of colder tone after tax

# Tax calculation
TAX_RATE = 0.10  # 10%
MIN_BALANCE_FOR_TAX = 10  # Minimum balance to lose at least 1 coin


def calculate_tax(coins: int) -> tuple[int, int]:
    """
    Calculate tax amount and new balance.
    Returns: (coins_taken, new_balance)
    """
    if coins < MIN_BALANCE_FOR_TAX:
        return (0, coins)
    
    coins_taken = max(1, math.floor(coins * TAX_RATE))
    new_balance = max(0, coins - coins_taken)
    
    return (coins_taken, new_balance)


class QuarterlyTax(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.icon = "https://i.imgur.com/5nsuuCV.png"
        self.tax_check.start()

    def cog_unload(self):
        self.tax_check.cancel()

    async def _ensure_tax_schedule(self, gid: int) -> dict:
        """Ensure tax schedule exists for guild, initialize if needed."""
        row = await self.bot.db.fetchone(
            "SELECT next_tax_ts, last_tax_ts FROM tax_schedule WHERE guild_id=?",
            (gid,)
        )
        
        if not row:
            # Initialize: first tax in 4 months from now
            next_ts = now_ts() + TAX_INTERVAL_SECONDS
            try:
                await self.bot.db.execute(
                    """
                    INSERT INTO tax_schedule(guild_id, next_tax_ts, last_tax_ts)
                    VALUES(?,?,?)
                    """,
                    (gid, next_ts, 0)
                )
            except Exception:
                # Race condition: another process may have inserted, re-fetch
                row = await self.bot.db.fetchone(
                    "SELECT next_tax_ts, last_tax_ts FROM tax_schedule WHERE guild_id=?",
                    (gid,)
                )
                if row:
                    return dict(row)
                # If still not found, return the values we tried to insert
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
            # Get all users with coins
            users = await self.bot.db.fetchall(
                "SELECT user_id, coins FROM users WHERE guild_id=? AND coins > 0",
                (gid,)
            )
            
            if not users:
                return 0, 0
            
            total_taken = 0
            user_count = 0
            tax_ts = now_ts()
            
            # Prepare batch updates for better performance and atomicity
            update_rows = []
            ledger_rows = []
            log_rows = []
            
            # Process each user
            for row in users:
                uid = int(row["user_id"])
                coins_before = int(row["coins"])
                
                if coins_before < MIN_BALANCE_FOR_TAX:
                    continue
                
                coins_taken, coins_after = calculate_tax(coins_before)
                
                if coins_taken > 0:
                    update_rows.append((coins_after, gid, uid))
                    ledger_rows.append((gid, uid, tax_ts, -coins_taken, "quarterly_tax"))
                    log_rows.append((gid, tax_ts, uid, coins_before, coins_taken, coins_after))
                    
                    total_taken += coins_taken
                    user_count += 1
            
            # Execute batch updates
            if update_rows:
                # Update user balances
                for coins_after, gid_val, uid in update_rows:
                    await self.bot.db.execute(
                        "UPDATE users SET coins=? WHERE guild_id=? AND user_id=?",
                        (coins_after, gid_val, uid)
                    )
                
                # Log to ledger (batch insert if supported, otherwise individual)
                for ledger_row in ledger_rows:
                    try:
                        await self.bot.db.execute(
                            "INSERT INTO coin_ledger(guild_id,user_id,ts,delta,reason) VALUES(?,?,?,?,?)",
                            ledger_row
                        )
                    except Exception:
                        pass  # coin_ledger might not exist or have different schema
                
                # Log to tax_log
                for log_row in log_rows:
                    await self.bot.db.execute(
                        """
                        INSERT INTO tax_log(guild_id, tax_ts, user_id, coins_before, coins_taken, coins_after)
                        VALUES(?,?,?,?,?,?)
                        """,
                        log_row
                    )
            
            # Update schedule: next tax in 4 months
            next_tax_ts = now_ts() + TAX_INTERVAL_SECONDS
            await self.bot.db.execute(
                """
                UPDATE tax_schedule
                SET last_tax_ts=?,
                    next_tax_ts=?,
                    warning_7d_sent=0,
                    warning_3d_sent=0,
                    warning_24h_sent=0,
                    tax_tone_until_ts=?
                WHERE guild_id=?
                """,
                (tax_ts, next_tax_ts, now_ts() + TAX_TONE_DURATION, gid)
            )
            
            # Send execution message (don't fail tax if this fails)
            try:
                await self._send_execution(guild, total_taken, user_count)
            except Exception as e:
                # Log error but don't fail the tax (print since we may not have bot.log)
                print(f"ERROR: Failed to send tax execution message for guild {gid}: {e}")
            
            return total_taken, user_count
        
        except Exception as e:
            # Log error and re-raise to prevent silent failures
            print(f"ERROR: Error executing tax for guild {gid}: {e}")
            raise

    @tasks.loop(minutes=60)  # Check every hour
    async def tax_check(self):
        """Check for upcoming taxes and send warnings/execute."""
        await self.bot.wait_until_ready()
        
        now = now_ts()
        
        for guild in self.bot.guilds:
            gid = guild.id
            schedule = await self._ensure_tax_schedule(gid)
            
            next_tax = int(schedule["next_tax_ts"])
            time_until = next_tax - now
            
            # Check if tax is due
            if time_until <= 0:
                # Execute tax
                await self._execute_tax(guild, gid)
                continue
            
            # Get warning flags (schedule is guaranteed to exist after _ensure_tax_schedule)
            row = await self.bot.db.fetchone(
                """
                SELECT warning_7d_sent, warning_3d_sent, warning_24h_sent
                FROM tax_schedule
                WHERE guild_id=?
                """,
                (gid,)
            )
            
            # If row doesn't exist (shouldn't happen after _ensure_tax_schedule), skip warnings
            if not row:
                continue
            
            warning_7d = int(row["warning_7d_sent"] or 0)
            warning_3d = int(row["warning_3d_sent"] or 0)
            warning_24h = int(row["warning_24h_sent"] or 0)
            
            # 7 days warning (independent check - not elif)
            if not warning_7d and time_until <= WARNING_7D_SECONDS:
                await self._send_warning(
                    guild,
                    7,
                    "In one week, I collect my tax.\nCount your Coins carefully.\n᲼᲼"
                )
                await self.bot.db.execute(
                    "UPDATE tax_schedule SET warning_7d_sent=1 WHERE guild_id=?",
                    (gid,)
                )
            
            # 3 days warning (independent check - not elif)
            if not warning_3d and time_until <= WARNING_3D_SECONDS:
                await self._send_warning(
                    guild,
                    3,
                    "Hoarding never ends well.\nYou still have time to make better choices.\n᲼᲼"
                )
                await self.bot.db.execute(
                    "UPDATE tax_schedule SET warning_3d_sent=1 WHERE guild_id=?",
                    (gid,)
                )
            
            # 24 hours warning (independent check - not elif)
            if not warning_24h and time_until <= WARNING_24H_SECONDS:
                await self._send_warning(
                    guild,
                    1,
                    "Tomorrow, I take ten percent.\nSpend them. Burn them. Or lose them.\n᲼᲼"
                )
                await self.bot.db.execute(
                    "UPDATE tax_schedule SET warning_24h_sent=1 WHERE guild_id=?",
                    (gid,)
                )

    @tax_check.before_loop
    async def before_tax_check(self):
        await self.bot.wait_until_ready()

    # Admin command to manually trigger tax (for testing/setup)
    @commands.command(name="tax_trigger", hidden=True)
    @commands.has_permissions(administrator=True)
    async def tax_trigger(self, ctx: commands.Context):
        """Manually trigger tax execution (admin only)."""
        if not ctx.guild:
            return await ctx.send("Server only.")
        
        gid = ctx.guild.id
        total, count = await self._execute_tax(ctx.guild, gid)
        await ctx.send(f"Tax executed: {fmt(total)} coins from {count} users.", delete_after=10)

    # Admin command to check tax schedule
    @commands.command(name="tax_status", hidden=True)
    @commands.has_permissions(administrator=True)
    async def tax_status(self, ctx: commands.Context):
        """Check tax schedule status (admin only)."""
        if not ctx.guild:
            return await ctx.send("Server only.")
        
        gid = ctx.guild.id
        schedule = await self._ensure_tax_schedule(gid)
        
        next_tax = int(schedule["next_tax_ts"])
        last_tax = int(schedule.get("last_tax_ts", 0) or 0)
        now = now_ts()
        
        days_until = (next_tax - now) / (24 * 3600)
        
        msg = (
            f"**Tax Schedule**\n"
            f"Next tax: {days_until:.1f} days\n"
            f"Last tax: {time.ctime(last_tax) if last_tax > 0 else 'Never'}\n"
        )
        await ctx.send(msg, delete_after=30)


async def setup(bot: commands.Bot):
    await bot.add_cog(QuarterlyTax(bot))

