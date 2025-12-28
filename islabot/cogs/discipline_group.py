from __future__ import annotations

import time
import discord
from discord.ext import commands, tasks
from discord import app_commands

from utils.economy import add_coins, get_wallet, ensure_wallet
from utils.uk_time import uk_day_ymd

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

def parse_duration_to_seconds(text: str) -> int:
    """
    Accepts: 10m, 2h, 3d, 1w
    """
    s = text.strip().lower()
    if not s:
        return 0
    mult = 1
    if s.endswith("m"):
        mult = 60
        s = s[:-1]
    elif s.endswith("h"):
        mult = 3600
        s = s[:-1]
    elif s.endswith("d"):
        mult = 86400
        s = s[:-1]
    elif s.endswith("w"):
        mult = 7 * 86400
        s = s[:-1]
    try:
        val = int(s)
        return max(0, val * mult)
    except Exception:
        return 0

class DisciplineGroup(commands.Cog):
    """
    User-facing:
      /punishments
      /penance
      /debt

    Moderator-facing:
      /discipline warn
      /discipline strike
      /discipline timeout
      /discipline mute
      /discipline nickname
      /discipline seize
      /discipline fine
      /discipline pardon

    Includes timed expiry loop for mutes + nicknames + expiring punishments.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot

        self.logs_channel_id = int(bot.cfg.get("channels", "logs", default="0") or 0)
        self.mute_role_id = int(bot.cfg.get("roles", "mute_role", default="0") or 0)

        self.discipline = app_commands.Group(name="discipline", description="Moderator discipline tools")

        self._register()
        self.expiry_loop.start()

    def cog_unload(self):
        self.expiry_loop.cancel()

    # -------------------------
    # Permissions helpers
    # -------------------------
    def _is_mod(self, member: discord.Member) -> bool:
        perms = member.guild_permissions
        return perms.moderate_members or perms.manage_messages or perms.administrator

    async def _log(self, guild: discord.Guild, title: str, desc: str):
        if not self.logs_channel_id:
            return
        ch = guild.get_channel(self.logs_channel_id)
        if isinstance(ch, discord.TextChannel):
            await ch.send(embed=isla_embed(desc, title=title))

    async def _audit_row(self, guild_id: int, action: str, target_id: int, moderator_id: int, amount: int = 0, duration_seconds: int = 0, reason: str = ""):
        await self.bot.db.execute(
            """
            INSERT INTO discipline_log(guild_id,ts,action,target_id,moderator_id,amount,duration_seconds,reason)
            VALUES(?,?,?,?,?,?,?,?)
            """,
            (guild_id, now_ts(), action, int(target_id), int(moderator_id), int(amount), int(duration_seconds), reason or "")
        )

    async def _ensure_strikes(self, gid: int, uid: int):
        await self.bot.db.execute(
            "INSERT OR IGNORE INTO discipline_strikes(guild_id,user_id,strikes,last_strike_ts) VALUES(?,?,0,0)",
            (gid, uid)
        )

    async def _ensure_debt(self, gid: int, uid: int):
        await self.bot.db.execute(
            "INSERT OR IGNORE INTO discipline_debt(guild_id,user_id,debt,updated_ts) VALUES(?,?,0,0)",
            (gid, uid)
        )

    # -------------------------
    # User-facing: /punishments
    # -------------------------
    @app_commands.command(name="punishments", description="Shows your active punishments, duration, and conditions to clear.")
    async def punishments(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild_id
        uid = interaction.user.id
        if not gid:
            embed = create_embed("Server only.", color="warning", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)

        rows = await self.bot.db.fetchall(
            """
            SELECT id, kind, reason, created_ts, ends_ts, conditions
            FROM discipline_punishments
            WHERE guild_id=? AND user_id=? AND active=1
            ORDER BY created_ts DESC
            """,
            (gid, uid)
        )

        if not rows:
            return await interaction.followup.send(embed=isla_embed("None.\n᲼᲼", title="Punishments"), ephemeral=True)

        lines = []
        for r in rows:
            pid = int(r["id"])
            kind = str(r["kind"])
            ends = int(r["ends_ts"] or 0)
            dur = "Permanent" if ends == 0 else f"Ends <t:{ends}:R>"
            cond = str(r["conditions"] or "").strip()
            if cond:
                lines.append(f"**#{pid}** {kind} — {dur}\n• {cond}")
            else:
                lines.append(f"**#{pid}** {kind} — {dur}")

        e = isla_embed("Here's what's active.\n᲼᲼", title="Punishments")
        e.add_field(name="Active", value="\n\n".join(lines[:10]), inline=False)
        await interaction.followup.send(embed=e, ephemeral=True)

    # -------------------------
    # User-facing: /debt
    # -------------------------
    @app_commands.command(name="debt", description="Shows debt / penalties owed.")
    async def debt(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild_id
        uid = interaction.user.id
        if not gid:
            embed = create_embed("Server only.", color="warning", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)

        await self._ensure_debt(gid, uid)
        d = await self.bot.db.fetchone(
            "SELECT debt FROM discipline_debt WHERE guild_id=? AND user_id=?",
            (gid, uid)
        )
        debt_amt = int(d["debt"] or 0)

        w = await get_wallet(self.bot.db, gid, uid)  # includes tax_debt too
        e = isla_embed(
            f"Debt.\n\n"
            f"Discipline debt: **{fmt(debt_amt)} Coins**\n"
            f"Tax debt: **{fmt(w.tax_debt)} Coins**\n"
            "᲼᲼",
            title="Debt"
        )
        e.add_field(name="Work it off", value="Use `/penance`.\nOr pay it down by staying active.", inline=False)
        await interaction.followup.send(embed=e, ephemeral=True)

    # -------------------------
    # User-facing: /penance
    # -------------------------
    @app_commands.command(name="penance", description="Generates a penance task to work off debt / penalties.")
    async def penance(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild_id
        uid = interaction.user.id
        if not gid:
            embed = create_embed("Server only.", color="warning", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)

        await self._ensure_debt(gid, uid)
        d = await self.bot.db.fetchone("SELECT debt FROM discipline_debt WHERE guild_id=? AND user_id=?", (gid, uid))
        debt_amt = int(d["debt"] or 0)

        # Penance options (PG-13, constructive)
        tasks = [
            ("Write one helpful message in a non-spam channel.", 25),
            ("Spend 10 minutes in voice, then send one message summarizing what you did.", 40),
            ("Complete one order today and come back.", 60),
            ("Help a new member: answer one question politely.", 50),
            ("Post one resource link relevant to the server topic.", 35),
        ]
        task, value = tasks[min(len(tasks)-1, debt_amt // 200)] if debt_amt > 0 else tasks[0]

        # Apply immediate reduction (you can change to "confirm completion" later)
        reduce_by = min(value, debt_amt) if debt_amt > 0 else 0
        if reduce_by > 0:
            await self.bot.db.execute(
                "UPDATE discipline_debt SET debt=debt-?, updated_ts=? WHERE guild_id=? AND user_id=?",
                (reduce_by, now_ts(), gid, uid)
            )

        e = isla_embed(
            "Penance.\n\n"
            f"Task: **{task}**\n"
            f"Debt reduction: **{fmt(reduce_by)} Coins**\n"
            "᲼᲼",
            title="Penance"
        )
        await interaction.followup.send(embed=e, ephemeral=True)

    # ============================================================
    # Moderator-facing: /discipline group
    # ============================================================

    async def _require_mod(self, interaction: discord.Interaction) -> bool:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            embed = create_embed("Server only.", color="warning", is_dm=False, is_system=False)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return False
        if not self._is_mod(interaction.user):
            await interaction.response.send_message(embed=isla_embed("Not for you.\n᲼᲼", title="Discipline"), ephemeral=True)
            return False
        return True

    # /discipline warn <user> [reason]
    @app_commands.command(name="warn", description="Warn a user (logged).")
    async def d_warn(self, interaction: discord.Interaction, user: discord.Member, reason: str | None = None):
        if not await self._require_mod(interaction):
            return
        await interaction.response.defer(ephemeral=True)

        gid = interaction.guild_id
        mod_id = interaction.user.id

        await self.bot.db.execute(
            """
            INSERT INTO discipline_punishments(guild_id,user_id,kind,reason,created_ts,ends_ts,conditions,active,issued_by)
            VALUES(?,?,?,?,?,?,?,?,?)
            """,
            (gid, user.id, "warn", reason or "", now_ts(), 0, "Avoid repeating the behavior.", 1, mod_id)
        )
        await self._audit_row(gid, "warn", user.id, mod_id, reason=reason or "")

        e_user = isla_embed(
            "Warning.\n\n"
            "Don't test limits.\n"
            "᲼᲼",
            title="Notice"
        )
        if reason:
            e_user.add_field(name="Reason", value=reason[:900], inline=False)

        # Try DM, fail silently
        try:
            await user.send(embed=e_user)
        except discord.Forbidden:
            pass

        await self._log(interaction.guild, "Warn", f"{user.mention}\nReason: {reason or '—'}\nIssued by: <@{mod_id}>\n᲼᲼")

        await interaction.followup.send(embed=isla_embed("Warned.\n᲼᲼", title="Discipline"), ephemeral=True)

    # /discipline strike <user> <count> [reason]
    @app_commands.command(name="strike", description="Add strikes (auto escalation).")
    async def d_strike(self, interaction: discord.Interaction, user: discord.Member, count: int, reason: str | None = None):
        if not await self._require_mod(interaction):
            return
        await interaction.response.defer(ephemeral=True)

        gid = interaction.guild_id
        mod_id = interaction.user.id
        count = max(1, min(10, int(count)))

        await self._ensure_strikes(gid, user.id)

        await self.bot.db.execute(
            "UPDATE discipline_strikes SET strikes=strikes+?, last_strike_ts=? WHERE guild_id=? AND user_id=?",
            (count, now_ts(), gid, user.id)
        )
        srow = await self.bot.db.fetchone(
            "SELECT strikes FROM discipline_strikes WHERE guild_id=? AND user_id=?",
            (gid, user.id)
        )
        strikes = int(srow["strikes"] or 0)

        await self._audit_row(gid, "strike", user.id, mod_id, amount=count, reason=reason or "")

        # Escalation rules (tune):
        # 3 strikes => 10m timeout
        # 5 strikes => 1h timeout
        # 7 strikes => 24h timeout
        auto_timeout = 0
        if strikes >= 7:
            auto_timeout = 24 * 3600
        elif strikes >= 5:
            auto_timeout = 3600
        elif strikes >= 3:
            auto_timeout = 600

        if auto_timeout > 0:
            try:
                from datetime import timedelta
                until = discord.utils.utcnow() + timedelta(seconds=auto_timeout)
            except Exception:
                from datetime import timedelta
                until = discord.utils.utcnow() + timedelta(seconds=auto_timeout)

            try:
                await user.timeout(until, reason=f"Auto escalation ({strikes} strikes)")
            except Exception:
                pass

            ends = now_ts() + auto_timeout
            await self.bot.db.execute(
                """
                INSERT INTO discipline_punishments(guild_id,user_id,kind,reason,created_ts,ends_ts,conditions,active,issued_by)
                VALUES(?,?,?,?,?,?,?,?,?)
                """,
                (gid, user.id, "timeout", f"Auto escalation ({strikes} strikes). {reason or ''}".strip(),
                 now_ts(), ends, "Wait out the timer and follow the rules.", 1, mod_id)
            )

        await self._log(
            interaction.guild,
            "Strike",
            f"{user.mention}\n+{count} strikes → **{strikes} total**\nReason: {reason or '—'}\nIssued by: <@{mod_id}>\n᲼᲼"
        )

        e = isla_embed(
            f"Strikes updated.\n\n"
            f"{user.mention}\n"
            f"Total: **{strikes}**\n"
            "᲼᲼",
            title="Discipline"
        )
        if auto_timeout:
            e.add_field(name="Escalation", value=f"Auto timeout: {auto_timeout//60} minutes", inline=False)
        await interaction.followup.send(embed=e, ephemeral=True)

    # /discipline timeout <user> <duration> [reason] [seize]
    @app_commands.command(name="timeout", description="Timeout + optional Coin seizure.")
    @app_commands.describe(user="User to timeout", duration="Duration (10m, 2h, 3d)", reason="Reason", seize="Coins to seize")
    async def d_timeout(self, interaction: discord.Interaction, user: discord.Member, duration: str, reason: str | None = None, seize: int | None = None):
        if not await self._require_mod(interaction):
            return
        await interaction.response.defer(ephemeral=True)

        seconds = parse_duration_to_seconds(duration)
        if seconds <= 0:
            return await interaction.followup.send(embed=isla_embed("Bad duration.\nUse 10m / 2h / 3d.\n᲼᲼", title="Timeout"), ephemeral=True)

        mod_id = interaction.user.id
        gid = interaction.guild_id

        # Apply timeout
        try:
            from datetime import timedelta
            from utils.embed_utils import create_embed
            until = discord.utils.utcnow() + timedelta(seconds=seconds)
            await user.timeout(until, reason=reason or "discipline timeout")
        except Exception:
            pass

        ends = now_ts() + seconds
        await self.bot.db.execute(
            """
            INSERT INTO discipline_punishments(guild_id,user_id,kind,reason,created_ts,ends_ts,conditions,active,issued_by)
            VALUES(?,?,?,?,?,?,?,?,?)
            """,
            (gid, user.id, "timeout", reason or "", now_ts(), ends, "Wait out the timer.", 1, mod_id)
        )

        seized = 0
        if seize and int(seize) > 0:
            seized = int(seize)
            await ensure_wallet(self.bot.db, gid, user.id)
            w = await get_wallet(self.bot.db, gid, user.id)
            seized = min(seized, w.coins)
            if seized > 0:
                await add_coins(self.bot.db, gid, user.id, -seized, kind="discipline_seize", reason=reason or "timeout seizure")

        await self._audit_row(gid, "timeout", user.id, mod_id, amount=seized, duration_seconds=seconds, reason=reason or "")
        await self._log(interaction.guild, "Timeout", f"{user.mention}\nDuration: {duration}\nSeized: {fmt(seized)}\nReason: {reason or '—'}\nBy: <@{mod_id}>\n᲼᲼")

        e = isla_embed(
            f"Timeout applied.\n\n"
            f"{user.mention}\n"
            f"Ends: <t:{ends}:R>\n"
            "᲼᲼",
            title="Discipline"
        )
        if seized:
            e.add_field(name="Coins seized", value=fmt(seized), inline=True)
        if reason:
            e.add_field(name="Reason", value=reason[:900], inline=False)
        await interaction.followup.send(embed=e, ephemeral=True)

    # /discipline mute <user> <duration> [reason]
    @app_commands.command(name="mute", description="Mute role assignment.")
    @app_commands.describe(user="User to mute", duration="Duration (10m, 2h, 3d)", reason="Reason")
    async def d_mute(self, interaction: discord.Interaction, user: discord.Member, duration: str, reason: str | None = None):
        if not await self._require_mod(interaction):
            return
        await interaction.response.defer(ephemeral=True)

        if not self.mute_role_id:
            return await interaction.followup.send(embed=isla_embed("Mute role not configured.\n᲼᲼", title="Mute"), ephemeral=True)

        seconds = parse_duration_to_seconds(duration)
        if seconds <= 0:
            return await interaction.followup.send(embed=isla_embed("Bad duration.\nUse 10m / 2h / 3d.\n᲼᲼", title="Mute"), ephemeral=True)

        gid = interaction.guild_id
        mod_id = interaction.user.id
        role = interaction.guild.get_role(self.mute_role_id)
        if not role:
            return await interaction.followup.send(embed=isla_embed("Mute role missing.\n᲼᲼", title="Mute"), ephemeral=True)

        try:
            await user.add_roles(role, reason=reason or "discipline mute")
        except Exception:
            return await interaction.followup.send(embed=isla_embed("Couldn't apply mute.\n᲼᲼", title="Mute"), ephemeral=True)

        ends = now_ts() + seconds

        await self.bot.db.execute(
            """
            INSERT INTO discipline_punishments(guild_id,user_id,kind,reason,created_ts,ends_ts,conditions,active,issued_by)
            VALUES(?,?,?,?,?,?,?,?,?)
            """,
            (gid, user.id, "mute", reason or "", now_ts(), ends, "Wait out the timer.", 1, mod_id)
        )

        await self._audit_row(gid, "mute", user.id, mod_id, duration_seconds=seconds, reason=reason or "")
        await self._log(interaction.guild, "Mute", f"{user.mention}\nDuration: {duration}\nReason: {reason or '—'}\nBy: <@{mod_id}>\n᲼᲼")

        e = isla_embed(f"Muted.\n\n{user.mention}\nEnds: <t:{ends}:R>\n᲼᲼", title="Discipline")
        await interaction.followup.send(embed=e, ephemeral=True)

    # /discipline nickname <user> <nickname> [duration]
    @app_commands.command(name="nickname", description="Temporary enforced nickname.")
    @app_commands.describe(user="User to nickname", nickname="New nickname", duration="Duration (default 24h)")
    async def d_nickname(self, interaction: discord.Interaction, user: discord.Member, nickname: str, duration: str | None = None):
        if not await self._require_mod(interaction):
            return
        await interaction.response.defer(ephemeral=True)

        gid = interaction.guild_id
        mod_id = interaction.user.id

        seconds = parse_duration_to_seconds(duration) if duration else (24 * 3600)
        seconds = max(60, min(30 * 86400, seconds))  # 1m to 30d
        ends = now_ts() + seconds

        old = user.nick or ""
        try:
            await user.edit(nick=nickname, reason="discipline nickname")
        except Exception:
            return await interaction.followup.send(embed=isla_embed("Couldn't change nickname.\n᲼᲼", title="Nickname"), ephemeral=True)

        # record
        await self.bot.db.execute(
            """
            INSERT INTO discipline_nicknames(guild_id,user_id,old_nick,new_nick,ends_ts,active)
            VALUES(?,?,?,?,?,1)
            ON CONFLICT(guild_id,user_id) DO UPDATE SET
              old_nick=excluded.old_nick,
              new_nick=excluded.new_nick,
              ends_ts=excluded.ends_ts,
              active=1
            """,
            (gid, user.id, old, nickname, ends)
        )

        await self.bot.db.execute(
            """
            INSERT INTO discipline_punishments(guild_id,user_id,kind,reason,created_ts,ends_ts,conditions,active,issued_by,meta_json)
            VALUES(?,?,?,?,?,?,?,?,?,?)
            """,
            (gid, user.id, "nickname", "Temporary nickname enforced.", now_ts(), ends,
             "Wait for expiry or ask staff.", 1, mod_id, "{}")
        )

        await self._audit_row(gid, "nickname", user.id, mod_id, duration_seconds=seconds, reason=f"nick -> {nickname}")
        await self._log(interaction.guild, "Nickname", f"{user.mention}\nNew: {nickname}\nEnds: <t:{ends}:R>\nBy: <@{mod_id}>\n᲼᲼")

        e = isla_embed(f"Nickname set.\n\n{user.mention}\nEnds: <t:{ends}:R>\n᲼᲼", title="Discipline")
        await interaction.followup.send(embed=e, ephemeral=True)

    # /discipline seize <user> <amount> [reason]
    @app_commands.command(name="seize", description="Remove Coins.")
    @app_commands.describe(user="User to seize from", amount="Coins to seize", reason="Reason")
    async def d_seize(self, interaction: discord.Interaction, user: discord.Member, amount: int, reason: str | None = None):
        if not await self._require_mod(interaction):
            return
        await interaction.response.defer(ephemeral=True)

        gid = interaction.guild_id
        mod_id = interaction.user.id
        amt = max(1, int(amount))

        await ensure_wallet(self.bot.db, gid, user.id)
        w = await get_wallet(self.bot.db, gid, user.id)
        seized = min(amt, w.coins)

        if seized <= 0:
            return await interaction.followup.send(embed=isla_embed("Nothing to seize.\n᲼᲼", title="Seize"), ephemeral=True)

        await add_coins(self.bot.db, gid, user.id, -seized, kind="discipline_seize", reason=reason or "seized")

        await self._audit_row(gid, "seize", user.id, mod_id, amount=seized, reason=reason or "")
        await self._log(interaction.guild, "Seize", f"{user.mention}\nAmount: {fmt(seized)}\nReason: {reason or '—'}\nBy: <@{mod_id}>\n᲼᲼")

        e = isla_embed(f"Seized.\n\n{user.mention}\n-**{fmt(seized)} Coins**\n᲼᲼", title="Discipline")
        await interaction.followup.send(embed=e, ephemeral=True)

    # /discipline fine <user> <amount> [reason]  (adds debt instead of removal)
    @app_commands.command(name="fine", description="Adds debt instead of removing Coins.")
    @app_commands.describe(user="User to fine", amount="Debt amount", reason="Reason")
    async def d_fine(self, interaction: discord.Interaction, user: discord.Member, amount: int, reason: str | None = None):
        if not await self._require_mod(interaction):
            return
        await interaction.response.defer(ephemeral=True)

        gid = interaction.guild_id
        mod_id = interaction.user.id
        amt = max(1, int(amount))

        await self._ensure_debt(gid, user.id)
        await self.bot.db.execute(
            "UPDATE discipline_debt SET debt=debt+?, updated_ts=? WHERE guild_id=? AND user_id=?",
            (amt, now_ts(), gid, user.id)
        )

        await self._audit_row(gid, "fine", user.id, mod_id, amount=amt, reason=reason or "")
        await self._log(interaction.guild, "Fine", f"{user.mention}\nDebt +{fmt(amt)}\nReason: {reason or '—'}\nBy: <@{mod_id}>\n᲼᲼")

        e = isla_embed(f"Debt added.\n\n{user.mention}\n+**{fmt(amt)} Coins** (debt)\n᲼᲼", title="Discipline")
        if reason:
            e.add_field(name="Reason", value=reason[:900], inline=False)
        await interaction.followup.send(embed=e, ephemeral=True)

    # /discipline pardon <user> [reason]
    @app_commands.command(name="pardon", description="Clears punishments/strikes.")
    @app_commands.describe(user="User to pardon", reason="Reason")
    async def d_pardon(self, interaction: discord.Interaction, user: discord.Member, reason: str | None = None):
        if not await self._require_mod(interaction):
            return
        await interaction.response.defer(ephemeral=True)

        gid = interaction.guild_id
        mod_id = interaction.user.id

        # Clear active punishments
        await self.bot.db.execute(
            "UPDATE discipline_punishments SET active=0 WHERE guild_id=? AND user_id=? AND active=1",
            (gid, user.id)
        )
        # Reset strikes
        await self._ensure_strikes(gid, user.id)
        await self.bot.db.execute(
            "UPDATE discipline_strikes SET strikes=0 WHERE guild_id=? AND user_id=?",
            (gid, user.id)
        )
        # Disable nickname enforcement record (expiry loop will revert if still active)
        await self.bot.db.execute(
            "UPDATE discipline_nicknames SET active=0 WHERE guild_id=? AND user_id=?",
            (gid, user.id)
        )

        await self._audit_row(gid, "pardon", user.id, mod_id, reason=reason or "")
        await self._log(interaction.guild, "Pardon", f"{user.mention}\nReason: {reason or '—'}\nBy: <@{mod_id}>\n᲼᲼")

        e = isla_embed(f"Cleared.\n\n{user.mention}\n᲼᲼", title="Discipline")
        await interaction.followup.send(embed=e, ephemeral=True)

    # ============================================================
    # Auto-expiry loop: mutes + nicknames + punishments
    # ============================================================
    @tasks.loop(seconds=30)
    async def expiry_loop(self):
        await self.bot.wait_until_ready()
        now = now_ts()

        for guild in self.bot.guilds:
            gid = guild.id

            # 1) Get expiring punishments (check mutes first before marking inactive)
            exp = await self.bot.db.fetchall(
                """
                SELECT id, user_id, kind
                FROM discipline_punishments
                WHERE guild_id=? AND active=1 AND ends_ts > 0 AND ends_ts <= ?
                """,
                (gid, now)
            )
            
            # 2) Expire mute role (if configured) - check before marking inactive
            if self.mute_role_id and exp:
                role = guild.get_role(self.mute_role_id)
                if role:
                    # Find mutes in the expiring list
                    for r in exp:
                        if str(r["kind"]) == "mute":
                            member = guild.get_member(int(r["user_id"]))
                            if member:
                                try:
                                    await member.remove_roles(role, reason="mute expired")
                                except Exception:
                                    pass
            
            # 3) Mark punishments as inactive
            if exp:
                ids = [int(r["id"]) for r in exp]
                await self.bot.db.execute(
                    f"UPDATE discipline_punishments SET active=0 WHERE id IN ({','.join(['?']*len(ids))})",
                    tuple(ids)
                )

            # 3) Expire nickname enforcement + revert
            nicks = await self.bot.db.fetchall(
                """
                SELECT user_id, old_nick, ends_ts
                FROM discipline_nicknames
                WHERE guild_id=? AND active=1 AND ends_ts <= ?
                """,
                (gid, now)
            )
            for r in nicks:
                uid = int(r["user_id"])
                old = str(r["old_nick"] or "")
                member = guild.get_member(uid)
                if member:
                    try:
                        await member.edit(nick=(old if old else None), reason="nickname enforcement expired")
                    except Exception:
                        pass
                await self.bot.db.execute(
                    "UPDATE discipline_nicknames SET active=0 WHERE guild_id=? AND user_id=?",
                    (gid, uid)
                )

    # -------------------------
    # Register commands
    # -------------------------
    def _register(self):
        # Add mod commands into /discipline group
        self.discipline.add_command(self.d_warn)
        self.discipline.add_command(self.d_strike)
        self.discipline.add_command(self.d_timeout)
        self.discipline.add_command(self.d_mute)
        self.discipline.add_command(self.d_nickname)
        self.discipline.add_command(self.d_seize)
        self.discipline.add_command(self.d_fine)
        self.discipline.add_command(self.d_pardon)

async def setup(bot: commands.Bot):
    # Remove command if it exists before creating cog (to avoid conflicts)
    bot.tree.remove_command("discipline", guild=None)
    cog = DisciplineGroup(bot)
    # Add cog - commands will be auto-registered
    try:
        await bot.add_cog(cog)
    except Exception as e:
        # If command already registered, remove it and try again
        if "CommandAlreadyRegistered" in str(e):
            bot.tree.remove_command("discipline", guild=None)
            await bot.add_cog(cog)
        else:
            raise
    # Ensure command is in tree with override
    try:
        bot.tree.add_command(cog.discipline, override=True)
    except Exception:
        pass  # Command already registered - ignore

