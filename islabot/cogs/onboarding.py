from __future__ import annotations
import secrets
import discord
from discord.ext import commands
from discord import app_commands

from utils.helpers import now_ts, format_time_left, isla_embed as helper_isla_embed, ensure_user_row
from utils.embed_utils import create_embed

VACATION_MIN_DAYS = 3
VACATION_MAX_DAYS = 21
VACATION_COOLDOWN_SECONDS = 24 * 3600  # 24 hours static cooldown
TAX_LOCK_HOURS = 24

def isla_embed(desc: str, thumb: str = "", title: str | None = None) -> discord.Embed:
    return helper_isla_embed(desc, title=title, thumb=thumb)


class Onboarding(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        
        # Staff controls
        self.staff = StaffControls(self)
        # Remove command if it exists, then add it
        bot.tree.remove_command("staff", guild=None)
        try:
            bot.tree.add_command(self.staff)
        except Exception:
            pass  # Command already registered - ignore

    # -------- global helper for user flags (can be imported elsewhere) --------
    async def isla_user_flags(self, gid: int, uid: int) -> dict:
        """Get user flags: opted_out, safeword_on, vacation_until_ts."""
        row = await self.bot.db.fetchone(
            "SELECT opted_out, safeword_on, vacation_until_ts FROM users WHERE guild_id=? AND user_id=?",
            (gid, uid)
        )
        if not row:
            return {"opted_out": 0, "safeword_on": 0, "vacation_until_ts": 0}
        return {
            "opted_out": int(row["opted_out"] or 0),
            "safeword_on": int(row["safeword_on"] or 0),
            "vacation_until_ts": int(row["vacation_until_ts"] or 0),
        }

    def on_vacation(self, flags: dict) -> bool:
        """Check if user is currently on vacation."""
        return (flags.get("vacation_until_ts", 0) or 0) > now_ts()

    async def has_active_orders(self, gid: int, uid: int) -> bool:
        """Check if user has active orders (for vacation blocking)."""
        try:
            row = await self.bot.db.fetchone(
                "SELECT 1 FROM order_runs WHERE guild_id=? AND user_id=? AND status='active' LIMIT 1",
                (gid, uid)
            )
            return bool(row)
        except Exception:
            # Table might not exist, return False
            return False

    async def has_recent_tax_due(self, gid: int, uid: int) -> bool:
        """Check if user has unpaid tax due within lock window."""
        try:
            row = await self.bot.db.fetchone(
                """
                SELECT due_ts, paid_ts
                FROM tax_ledger
                WHERE guild_id=? AND user_id=?
                ORDER BY due_ts DESC LIMIT 1
                """,
                (gid, uid)
            )
            if not row:
                return False
            due_ts = int(row["due_ts"] or 0)
            paid_ts = int(row["paid_ts"] or 0)
            if paid_ts >= due_ts and due_ts > 0:
                return False
            # unpaid and due within lock window
            return (now_ts() - due_ts) <= (TAX_LOCK_HOURS * 3600)
        except Exception:
            # Table might not exist, return False
            return False

    # -------- slash commands --------
    @app_commands.command(name="opt-out", description="Stop IslaBot interactions and reset your progress.")
    async def opt_out(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild_id
        if not gid:
            embed = create_embed("Server only.", color="warning", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)

        await ensure_user_row(self.bot.db, gid, interaction.user.id)

        token = secrets.token_hex(3).upper()  # short, readable
        expires = now_ts() + 600  # 10 minutes

        await self.bot.db.execute(
            """
            INSERT INTO optout_confirm(guild_id,user_id,token,expires_ts)
            VALUES(?,?,?,?)
            ON CONFLICT(guild_id,user_id)
            DO UPDATE SET token=excluded.token, expires_ts=excluded.expires_ts
            """,
            (gid, interaction.user.id, token, expires)
        )

        desc = (
            "Read this.\n\n"
            "Opting out will remove you from IslaBot systems.\n"
            "You won't earn coins, obedience, ranks, quests, orders, tax… any of it.\n\n"
            "**It also resets your progress.**\n"
            "If you still want it, confirm with:\n"
            f"`/opt-out_confirm {token}`\n"
            "᲼᲼"
        )
        e = isla_embed(desc, title="Opt-Out Warning")
        await interaction.followup.send(embed=e, ephemeral=True)

    @app_commands.command(name="opt-out_confirm", description="Confirm opt-out with your token.")
    @app_commands.describe(token="The token shown by /opt-out")
    async def opt_out_confirm(self, interaction: discord.Interaction, token: str):
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild_id
        if not gid:
            embed = create_embed("Server only.", color="warning", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)

        row = await self.bot.db.fetchone(
            "SELECT token, expires_ts FROM optout_confirm WHERE guild_id=? AND user_id=?",
            (gid, interaction.user.id)
        )
        if not row:
            embed = create_embed("No active opt-out request. Use /opt-out first.", color="info", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)

        if now_ts() > int(row["expires_ts"]):
            embed = create_embed("That token expired. Use /opt-out again.", color="info", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)

        if token.strip().upper() != str(row["token"]).upper():
            embed = create_embed("Wrong token.", color="info", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)

        # reset + disable
        await self.bot.db.execute(
            """
            UPDATE users
            SET opted_out=1,
                safeword_on=0,
                vacation_until_ts=0,
                vacation_last_used_ts=0,
                coins=0,
                obedience=0
            WHERE guild_id=? AND user_id=?
            """,
            (gid, interaction.user.id)
        )

        # OPTIONAL: reset any extra tables you have (quests, orders, debt, tax, collars)
        # Example (commented out - uncomment and adapt as needed):
        # try:
        #     await self.bot.db.execute("DELETE FROM quest_runs WHERE guild_id=? AND user_id=?", (gid, interaction.user.id))
        #     await self.bot.db.execute("DELETE FROM order_runs WHERE guild_id=? AND user_id=?", (gid, interaction.user.id))
        #     await self.bot.db.execute("DELETE FROM equips WHERE guild_id=? AND user_id=?", (gid, interaction.user.id))
        # except Exception:
        #     pass

        await self.bot.db.execute("DELETE FROM optout_confirm WHERE guild_id=? AND user_id=?", (gid, interaction.user.id))

        e = isla_embed(
            "Okay.\nYou're opted out.\n\nIf you ever want back in, run `/opt-in`.\n᲼᲼",
            title="Opted Out"
        )
        await interaction.followup.send(embed=e, ephemeral=True)

    @app_commands.command(name="opt-in", description="Re-enable IslaBot interactions.")
    async def opt_in(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild_id
        if not gid:
            embed = create_embed("Server only.", color="warning", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)

        await ensure_user_row(self.bot.db, gid, interaction.user.id)
        await self.bot.db.execute(
            "UPDATE users SET opted_out=0 WHERE guild_id=? AND user_id=?",
            (gid, interaction.user.id)
        )
        e = isla_embed("Good.\nYou're back in.\n᲼᲼", title="Opted In")
        await interaction.followup.send(embed=e, ephemeral=True)

    @app_commands.command(name="vacation", description="Pause IslaBot penalties for a while (min 3 days).")
    @app_commands.describe(days="Vacation duration (3–21 days)")
    async def vacation(self, interaction: discord.Interaction, days: int):
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild_id
        if not gid:
            embed = create_embed("Server only.", color="warning", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)

        await ensure_user_row(self.bot.db, gid, interaction.user.id)

        row = await self.bot.db.fetchone(
            """
            SELECT vacation_until_ts, vacation_last_used_ts
            FROM users WHERE guild_id=? AND user_id=?
            """,
            (gid, interaction.user.id)
        )

        now = now_ts()
        vac_until = int(row["vacation_until_ts"] or 0) if row else 0
        last_used = int(row["vacation_last_used_ts"] or 0) if row else 0

        # Handle natural expiration: if vacation ended naturally, set last_used_ts
        if vac_until > 0 and vac_until <= now and (last_used == 0 or last_used < vac_until):
            # Vacation expired naturally, start cooldown from expiration time
            await self.bot.db.execute(
                "UPDATE users SET vacation_last_used_ts=?, vacation_until_ts=0 WHERE guild_id=? AND user_id=?",
                (vac_until, gid, interaction.user.id)
            )
            last_used = vac_until
            vac_until = 0  # Clear it so we don't think they're still on vacation

        # Already on vacation
        if vac_until > now:
            remaining = format_time_left(vac_until - now)
            return await interaction.followup.send(
                embed=isla_embed(
                    f"You're already on vacation.\nTime left: **{remaining}**\n᲼᲼",
                    title="Vacation Active"
                ),
                ephemeral=True
            )

        # Cooldown check (24h static cooldown)
        cooldown_end = last_used + VACATION_COOLDOWN_SECONDS
        if last_used > 0 and now < cooldown_end:
            left = format_time_left(cooldown_end - now)
            return await interaction.followup.send(
                embed=isla_embed(
                    f"Not yet.\n\nYou can start another vacation in **{left}**.\n᲼᲼",
                    title="Vacation Cooldown"
                ),
                ephemeral=True
            )

        # Clamp days
        days = max(VACATION_MIN_DAYS, min(days, VACATION_MAX_DAYS))

        # anti-abuse checks
        if await self.has_active_orders(gid, interaction.user.id):
            return await interaction.followup.send(
                embed=isla_embed("Finish your active orders first.\nThen you can leave.\n᲼᲼", title="Vacation Blocked"),
                ephemeral=True
            )

        if await self.has_recent_tax_due(gid, interaction.user.id):
            return await interaction.followup.send(
                embed=isla_embed(
                    "Not now.\n\nYou have tax due.\nHandle it first, then you can take time away.\n᲼᲼",
                    title="Vacation Blocked"
                ),
                ephemeral=True
            )

        until = now + (days * 86400)

        # Set vacation_until_ts, clear vacation_last_used_ts (will be set when vacation ends)
        await self.bot.db.execute(
            """
            UPDATE users
            SET vacation_until_ts=?, vacation_last_used_ts=0
            WHERE guild_id=? AND user_id=?
            """,
            (until, gid, interaction.user.id)
        )

        await interaction.followup.send(
            embed=isla_embed(
                f"Okay.\n\nVacation started.\nDuration: **{days} days**.\n\n"
                "Tax and task penalties are paused.\n"
                "You can end it early with `/vacationstop`.\n"
                "᲼᲼",
                title="Vacation Started"
            ),
            ephemeral=True
        )

    @app_commands.command(name="vacationstop", description="End your vacation early.")
    async def vacationstop(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild_id
        if not gid:
            embed = create_embed("Server only.", color="warning", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)

        await ensure_user_row(self.bot.db, gid, interaction.user.id)

        row = await self.bot.db.fetchone(
            """
            SELECT vacation_until_ts
            FROM users WHERE guild_id=? AND user_id=?
            """,
            (gid, interaction.user.id)
        )

        now = now_ts()
        vac_until = int(row["vacation_until_ts"] or 0) if row else 0

        if vac_until <= now:
            return await interaction.followup.send(
                embed=isla_embed(
                    "You're not currently on vacation.\n᲼᲼",
                    title="No Active Vacation"
                ),
                ephemeral=True
            )

        # End vacation and start 24h cooldown
        await self.bot.db.execute(
            """
            UPDATE users
            SET vacation_until_ts=0,
                vacation_last_used_ts=?
            WHERE guild_id=? AND user_id=?
            """,
            (now, gid, interaction.user.id)
        )

        await interaction.followup.send(
            embed=isla_embed(
                "Alright.\n\nYour vacation has ended early.\n\n"
                "A **24h cooldown** is now active before you can take another one.\n"
                "᲼᲼",
                title="Vacation Ended"
            ),
            ephemeral=True
        )

# -------- Staff Controls --------
def staff_check(interaction: discord.Interaction) -> bool:
    """Check if user has staff permissions."""
    if not isinstance(interaction.user, discord.Member):
        return False
    perms = interaction.user.guild_permissions
    return perms.manage_guild or perms.administrator

class StaffControls(app_commands.Group):
    def __init__(self, cog):
        super().__init__(name="staff", description="Staff controls")
        self.cog = cog

    @app_commands.command(name="vacation_set", description="Force-set a user's vacation (staff override).")
    @app_commands.describe(member="Target", days="Days (1–30)", bypass_locks="Ignore anti-abuse locks")
    async def vacation_set(self, interaction: discord.Interaction, member: discord.Member, days: int, bypass_locks: bool = True):
        if not staff_check(interaction):
            embed = create_embed("No.", color="info", is_dm=False, is_system=False)
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild_id
        days = max(1, min(days, 30))
        until = now_ts() + days * 86400

        await self.cog.bot.db.execute(
            """
            INSERT INTO users(guild_id,user_id,coins,obedience,opted_out,safeword_on,vacation_until_ts,vacation_last_used_ts)
            VALUES(?,?,0,0,0,0,?,0)
            ON CONFLICT(guild_id,user_id)
            DO UPDATE SET vacation_until_ts=excluded.vacation_until_ts, vacation_last_used_ts=0
            """,
            (gid, member.id, until)
        )

        import json
        await self.cog.bot.db.execute(
            "INSERT INTO staff_actions(guild_id,staff_id,user_id,action,meta_json,ts) VALUES(?,?,?,?,?,?)",
            (gid, interaction.user.id, member.id, "vacation_set", json.dumps({"days": days, "bypass": bypass_locks}), now_ts())
        )

        await interaction.followup.send(
            embed=isla_embed(
                f"Set.\n\n{member.mention} is on vacation for **{days} days**.\n᲼᲼",
                title="Staff Override"
            ),
            ephemeral=True
        )

    @app_commands.command(name="vacation_clear", description="Force-end a user's vacation (staff override).")
    @app_commands.describe(member="Target", start_cooldown="Start the 24h cooldown")
    async def vacation_clear(self, interaction: discord.Interaction, member: discord.Member, start_cooldown: bool = True):
        if not staff_check(interaction):
            embed = create_embed("No.", color="info", is_dm=False, is_system=False)
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild_id
        now = now_ts()

        last_used = now if start_cooldown else 0
        await self.cog.bot.db.execute(
            "UPDATE users SET vacation_until_ts=0, vacation_last_used_ts=? WHERE guild_id=? AND user_id=?",
            (last_used, gid, member.id)
        )

        import json
        await self.cog.bot.db.execute(
            "INSERT INTO staff_actions(guild_id,staff_id,user_id,action,meta_json,ts) VALUES(?,?,?,?,?,?)",
            (gid, interaction.user.id, member.id, "vacation_clear", json.dumps({"cooldown": start_cooldown}), now)
        )

        await interaction.followup.send(
            embed=isla_embed(
                f"Done.\n\n{member.mention} is no longer on vacation.\n᲼᲼",
                title="Staff Override"
            ),
            ephemeral=True
        )

    @app_commands.command(name="vacation_cooldown_clear", description="Clear a user's vacation cooldown.")
    @app_commands.describe(member="Target")
    async def vacation_cooldown_clear(self, interaction: discord.Interaction, member: discord.Member):
        if not staff_check(interaction):
            embed = create_embed("No.", color="info", is_dm=False, is_system=False)
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild_id
        await self.cog.bot.db.execute(
            "UPDATE users SET vacation_last_used_ts=0 WHERE guild_id=? AND user_id=?",
            (gid, member.id)
        )
        import json
        await self.cog.bot.db.execute(
            "INSERT INTO staff_actions(guild_id,staff_id,user_id,action,meta_json,ts) VALUES(?,?,?,?,?,?)",
            (gid, interaction.user.id, member.id, "vacation_cooldown_clear", "{}", now_ts())
        )
        await interaction.followup.send(
            embed=isla_embed(
                f"Cleared.\n\n{member.mention} can use `/vacation` again.\n᲼᲼",
                title="Staff Override"
            ),
            ephemeral=True
        )

    @app_commands.command(name="safeword_set", description="Set a user's safeword status (staff override).")
    @app_commands.describe(member="Target", enabled="Enable or disable safeword")
    async def safeword_set(self, interaction: discord.Interaction, member: discord.Member, enabled: bool):
        if not staff_check(interaction):
            embed = create_embed("No.", color="info", is_dm=False, is_system=False)
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild_id
        now = now_ts()

        await ensure_user_row(self.cog.bot.db, gid, member.id)

        await self.cog.bot.db.execute(
            "UPDATE users SET safeword_on=?, safeword_set_ts=? WHERE guild_id=? AND user_id=?",
            (1 if enabled else 0, now, gid, member.id)
        )

        import json
        await self.cog.bot.db.execute(
            "INSERT INTO staff_actions(guild_id,staff_id,user_id,action,meta_json,ts) VALUES(?,?,?,?,?,?)",
            (gid, interaction.user.id, member.id, "safeword_set", json.dumps({"enabled": enabled}), now)
        )

        status = "enabled" if enabled else "disabled"
        await interaction.followup.send(
            embed=isla_embed(
                f"Set.\n\nSafeword is now **{status}** for {member.mention}.\n᲼᲼",
                title="Staff Override"
            ),
            ephemeral=True
        )

    @app_commands.command(name="safeword_status", description="View a user's safeword status (staff).")
    @app_commands.describe(member="Target")
    async def safeword_status_staff(self, interaction: discord.Interaction, member: discord.Member):
        if not staff_check(interaction):
            embed = create_embed("No.", color="info", is_dm=False, is_system=False)
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild_id

        row = await self.cog.bot.db.fetchone(
            "SELECT safeword_on, safeword_set_ts, safeword_reason FROM users WHERE guild_id=? AND user_id=?",
            (gid, member.id)
        )
        if not row:
            return await interaction.followup.send(
                embed=isla_embed(f"No data for {member.mention}.", title="Safeword Status"),
                ephemeral=True
            )

        on = int(row["safeword_on"] or 0)
        since = int(row["safeword_set_ts"] or 0)
        reason = str(row["safeword_reason"] or "")

        desc = f"**Status:** {'On' if on else 'Off'}\n"
        if since > 0:
            desc += f"**Set:** <t:{since}:R>\n"
        if reason:
            desc += f"**Reason:** {reason}\n"
        desc += "᲼᲼"

        await interaction.followup.send(
            embed=isla_embed(desc, title=f"Safeword Status - {member.display_name}"),
            ephemeral=True
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Onboarding(bot))
