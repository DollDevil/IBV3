from __future__ import annotations

import json
import discord
from discord.ext import commands
from discord import app_commands

from core.features import FEATURES
from core.utils import now_ts, day_key
from utils.helpers import isla_embed

class AdminTools(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _is_admin(self, interaction: discord.Interaction) -> bool:
        return bool(interaction.user and getattr(interaction.user, "guild_permissions", None) and interaction.user.guild_permissions.administrator)

    def _is_mod(self, interaction: discord.Interaction) -> bool:
        perms = getattr(interaction.user, "guild_permissions", None)
        return bool(perms and (perms.manage_guild or perms.moderate_members or perms.administrator))

    # ---------------------------
    # Feature toggles
    # ---------------------------

    @app_commands.command(name="feature_list", description="(Mod) List feature flags (available modules).")
    async def feature_list(self, interaction: discord.Interaction):
        if not interaction.guild or not self._is_mod(interaction):
            await interaction.response.send_message("Mods only.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        lines = [f"- `{k}`: {v}" for k, v in FEATURES.items()]
        await interaction.followup.send("\n".join(lines), ephemeral=True)

    @app_commands.command(name="feature_set", description="(Admin) Enable/disable a feature at guild level.")
    @app_commands.describe(feature="Feature name", enabled="Enable or disable")
    async def feature_set(self, interaction: discord.Interaction, feature: str, enabled: bool):
        if not interaction.guild or not self._is_admin(interaction):
            await interaction.response.send_message("Admin only.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild.id
        if feature not in FEATURES:
            await interaction.followup.send("Unknown feature. Use /feature_list.", ephemeral=True)
            return

        await self.bot.flags.set_guild(gid, feature, enabled)
        await self.bot.db.audit(gid, interaction.user.id, None, "toggle_feature_guild", json.dumps({"feature": feature, "enabled": enabled}), now_ts())
        await interaction.followup.send(f"Guild feature `{feature}` set to {enabled}.", ephemeral=True)

    @app_commands.command(name="feature_set_channel", description="(Admin) Enable/disable a feature in a channel.")
    @app_commands.describe(feature="Feature name", channel="Channel to configure", enabled="Enable or disable")
    async def feature_set_channel(self, interaction: discord.Interaction, feature: str, channel: discord.TextChannel, enabled: bool):
        if not interaction.guild or not self._is_admin(interaction):
            await interaction.response.send_message("Admin only.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild.id
        if feature not in FEATURES:
            await interaction.followup.send("Unknown feature. Use /feature_list.", ephemeral=True)
            return

        await self.bot.flags.set_channel(gid, channel.id, feature, enabled)
        await self.bot.db.audit(gid, interaction.user.id, None, "toggle_feature_channel", json.dumps({"feature": feature, "channel_id": channel.id, "enabled": enabled}), now_ts())
        await interaction.followup.send(f"Channel {channel.mention} feature `{feature}` set to {enabled}.", ephemeral=True)

    # ---------------------------
    # Per-channel config
    # ---------------------------

    @app_commands.command(name="channelcfg_set", description="(Admin) Set a channel config key=value.")
    @app_commands.describe(channel="Channel to configure", key="Config key", value="Config value")
    async def channelcfg_set(self, interaction: discord.Interaction, channel: discord.TextChannel, key: str, value: str):
        if not interaction.guild or not self._is_admin(interaction):
            await interaction.response.send_message("Admin only.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild.id
        await self.bot.chan_cfg.set(gid, channel.id, key, value)
        await self.bot.db.audit(gid, interaction.user.id, None, "channelcfg_set", json.dumps({"channel_id": channel.id, "key": key, "value": value}), now_ts())
        await interaction.followup.send(f"Set {channel.mention} `{key}` = `{value}`", ephemeral=True)

    @app_commands.command(name="channelcfg_get", description="(Mod) Get a channel config key.")
    @app_commands.describe(channel="Channel to check", key="Config key")
    async def channelcfg_get(self, interaction: discord.Interaction, channel: discord.TextChannel, key: str):
        if not interaction.guild or not self._is_mod(interaction):
            await interaction.response.send_message("Mods only.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild.id
        v = await self.bot.chan_cfg.get(gid, channel.id, key, default=None)
        await interaction.followup.send(f"{channel.mention} `{key}` = `{v}`", ephemeral=True)

    @app_commands.command(name="channelcfg_del", description="(Admin) Delete a channel config key.")
    @app_commands.describe(channel="Channel to configure", key="Config key to delete")
    async def channelcfg_del(self, interaction: discord.Interaction, channel: discord.TextChannel, key: str):
        if not interaction.guild or not self._is_admin(interaction):
            await interaction.response.send_message("Admin only.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild.id
        await self.bot.chan_cfg.delete(gid, channel.id, key)
        await self.bot.db.audit(gid, interaction.user.id, None, "channelcfg_del", json.dumps({"channel_id": channel.id, "key": key}), now_ts())
        await interaction.followup.send(f"Deleted {channel.mention} `{key}`", ephemeral=True)

    # ---------------------------
    # Notes + discipline
    # ---------------------------

    @app_commands.command(name="note_set", description="(Mod) Set a private admin note on a user.")
    @app_commands.describe(user="User to note", note="Note text")
    async def note_set(self, interaction: discord.Interaction, user: discord.Member, note: str):
        if not interaction.guild or not self._is_mod(interaction):
            await interaction.response.send_message("Mods only.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        gid, uid = interaction.guild.id, user.id
        await self.bot.db.ensure_user(gid, uid)

        await self.bot.db.execute(
            """INSERT INTO user_admin_notes(guild_id,user_id,note,created_by,created_ts,updated_ts)
               VALUES(?,?,?,?,?,NULL)
               ON CONFLICT(guild_id,user_id) DO UPDATE SET note=excluded.note, updated_ts=?""",
            (gid, uid, note[:2000], interaction.user.id, now_ts(), now_ts()),
        )
        await self.bot.db.audit(gid, interaction.user.id, uid, "note_set", json.dumps({}), now_ts())
        await interaction.followup.send(f"Note saved for {user.mention}.", ephemeral=True)

    @app_commands.command(name="note_view", description="(Mod) View a private admin note on a user.")
    @app_commands.describe(user="User to view")
    async def note_view(self, interaction: discord.Interaction, user: discord.Member):
        if not interaction.guild or not self._is_mod(interaction):
            await interaction.response.send_message("Mods only.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        gid, uid = interaction.guild.id, user.id
        row = await self.bot.db.fetchone(
            "SELECT note,created_by,created_ts,updated_ts FROM user_admin_notes WHERE guild_id=? AND user_id=?",
            (gid, uid),
        )
        if not row:
            await interaction.followup.send("No note.", ephemeral=True)
            return
        updated = f'<t:{int(row["updated_ts"])}:R>' if row["updated_ts"] else "—"
        await interaction.followup.send(
            f"**Note for {user.mention}:**\n{row['note']}\nCreated: <t:{int(row['created_ts'])}:R> by <@{int(row['created_by'])}>\nUpdated: {updated}",
            ephemeral=True,
        )

    @app_commands.command(name="discipline_add", description="(Mod) Add a warning/discipline entry (private log).")
    @app_commands.describe(user="User to discipline", kind="Type: warning|discipline|strike", points="Points (1-10)", reason="Reason (optional)")
    async def discipline_add(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        kind: str,
        points: app_commands.Range[int, 1, 10] = 1,
        reason: str | None = None,
    ):
        if not interaction.guild or not self._is_mod(interaction):
            await interaction.response.send_message("Mods only.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)

        kind = kind.lower().strip()
        if kind not in ("warning", "discipline", "strike"):
            await interaction.followup.send("kind must be warning|discipline|strike", ephemeral=True)
            return

        gid, uid = interaction.guild.id, user.id
        await self.bot.db.ensure_user(gid, uid)

        await self.bot.db.execute(
            "INSERT INTO user_discipline(guild_id,user_id,kind,reason,points,created_by,created_ts) VALUES(?,?,?,?,?,?,?)",
            (gid, uid, kind, (reason or "")[:500], int(points), interaction.user.id, now_ts()),
        )
        await self.bot.db.audit(gid, interaction.user.id, uid, "discipline_add", json.dumps({"kind": kind, "points": points}), now_ts())
        await interaction.followup.send(f"Logged {kind} for {user.mention} (+{points}).", ephemeral=True)

    @app_commands.command(name="discipline_view", description="(Mod) View discipline totals + last entries.")
    @app_commands.describe(user="User to view", limit="Number of recent entries (1-10)")
    async def discipline_view(self, interaction: discord.Interaction, user: discord.Member, limit: app_commands.Range[int, 1, 10] = 5):
        if not interaction.guild or not self._is_mod(interaction):
            await interaction.response.send_message("Mods only.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)

        gid, uid = interaction.guild.id, user.id
        totals = await self.bot.db.fetchone(
            """SELECT
                 SUM(CASE WHEN kind='warning' THEN points ELSE 0 END) AS warnings,
                 SUM(CASE WHEN kind='discipline' THEN points ELSE 0 END) AS disciplines,
                 SUM(CASE WHEN kind='strike' THEN points ELSE 0 END) AS strikes
               FROM user_discipline WHERE guild_id=? AND user_id=?""",
            (gid, uid),
        )
        rows = await self.bot.db.fetchall(
            "SELECT kind,points,reason,created_by,created_ts FROM user_discipline WHERE guild_id=? AND user_id=? ORDER BY created_ts DESC LIMIT ?",
            (gid, uid, int(limit)),
        )
        lines = []
        for r in rows:
            lines.append(f"- {r['kind']} (+{int(r['points'])}) by <@{int(r['created_by'])}> <t:{int(r['created_ts'])}:R> — {r['reason'] or '—'}")
        msg = (
            f"Totals for {user.mention}:\n"
            f"- warnings: **{int(totals['warnings'] or 0)}**\n"
            f"- disciplines: **{int(totals['disciplines'] or 0)}**\n"
            f"- strikes: **{int(totals['strikes'] or 0)}**\n\n"
            f"Recent:\n" + ("\n".join(lines) if lines else "—")
        )
        await interaction.followup.send(msg, ephemeral=True)

    # ---------------------------
    # Admin user profile view
    # ---------------------------

    @app_commands.command(name="admin_profile", description="(Mod) Deep view of a user's Isla profile + activity.")
    @app_commands.describe(user="User to view")
    async def admin_profile(self, interaction: discord.Interaction, user: discord.Member):
        if not interaction.guild or not self._is_mod(interaction):
            await interaction.response.send_message("Mods only.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)

        gid, uid = interaction.guild.id, user.id
        await self.bot.db.ensure_user(gid, uid)

        u = await self.bot.db.fetchone("SELECT coins,lce,debt,stage,last_msg_ts FROM users WHERE guild_id=? AND user_id=?", (gid, uid))
        c = await self.bot.db.fetchone("SELECT * FROM consent WHERE guild_id=? AND user_id=?", (gid, uid))
        note = await self.bot.db.fetchone("SELECT note,created_ts,updated_ts FROM user_admin_notes WHERE guild_id=? AND user_id=?", (gid, uid))

        # last 14 days activity summary
        today = day_key()
        rows = await self.bot.db.fetchall(
            """SELECT day_key,messages,commands,coins_earned,coins_burned,orders_taken,orders_completed,tributes_logged
               FROM user_activity_daily
               WHERE guild_id=? AND user_id=? AND day_key>=?
               ORDER BY day_key DESC""",
            (gid, uid, today - 14),
        )

        # tribute history (last 5)
        trib = await self.bot.db.fetchall(
            "SELECT amount,note,ts FROM tribute_log WHERE guild_id=? AND user_id=? ORDER BY ts DESC LIMIT 5",
            (gid, uid),
        )

        tenure = f"Joined: {user.joined_at.isoformat() if user.joined_at else '—'}"
        msg = [
            f"**{user}** ({user.mention})",
            tenure,
            f"Coins: **{int(u['coins'])}** | Debt: **{int(u['debt'])}** | LCE: **{int(u['lce'])}** | Stage: **{int(u['stage'])}**",
            f"Last msg: {f'<t:{int(u['last_msg_ts'])}:R>' if u['last_msg_ts'] else '—'}",
            "",
            "**Consent:**",
            f"- verified_18: {'✅' if int(c['verified_18']) else '❌'} | consent_ok: {'✅' if int(c['consent_ok']) else '❌'}",
            f"- orders: {'✅' if int(c['opt_orders']) else '❌'} | dm: {'✅' if int(c['opt_dm']) else '❌'} | humiliation: {'✅' if int(c['opt_humiliation']) else '❌'}",
            "",
            "**Admin Note:**",
            (note["note"] if note else "—"),
            "",
            "**Activity (last 14d):**",
        ]

        if rows:
            for r in rows[:7]:
                msg.append(
                    f"- day {int(r['day_key'])}: msgs {int(r['messages'])}, cmds {int(r['commands'])}, +{int(r['coins_earned'])}, burned {int(r['coins_burned'])}, orders {int(r['orders_completed'])}/{int(r['orders_taken'])}, tributes {int(r['tributes_logged'])}"
                )
        else:
            msg.append("—")

        msg.append("")
        msg.append("**Tributes (last 5):**")
        if trib:
            for t in trib:
                msg.append(f"- **{int(t['amount'])}** <t:{int(t['ts'])}:R> — {t['note'] or '—'}")
        else:
            msg.append("—")

        await interaction.followup.send("\n".join(msg)[:3900], ephemeral=True)

    # ---------------------------
    # Admin user control: opt-out/opt-in + safeword
    # ---------------------------

    @app_commands.command(name="user_optout", description="(Admin) Force-opt-out a user: hard delete Isla data + stop tracking.")
    @app_commands.describe(user="User to opt-out", reason="Reason (optional)")
    async def user_optout(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        reason: str | None = None
    ):
        if not interaction.guild or not self._is_admin(interaction):
            await interaction.response.send_message("Admin only.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild.id
        target_id = user.id

        # Mark audit first
        await self.bot.db.audit(
            gid,
            actor_id=interaction.user.id,
            target_user_id=target_id,
            action="admin_user_optout_requested",
            meta=json.dumps({"reason": (reason or "")[:500]}),
            ts=now_ts(),
        )

        # Hard delete + optout flag
        await self.bot.db.hard_delete_user(gid, target_id)
        await self.bot.db.set_optout(gid, target_id, True, now_ts())

        await self.bot.db.audit(
            gid,
            actor_id=interaction.user.id,
            target_user_id=target_id,
            action="admin_user_optout_completed",
            meta=json.dumps({"reason": (reason or "")[:500]}),
            ts=now_ts(),
        )

        # Best-effort DM notice
        try:
            await user.send(
                f"You have been opted out of Isla tracking in **{interaction.guild.name}**.\n"
                f"Your Isla data in that server was deleted and Isla will not track you.\n"
                f"If this was a mistake, ask an admin to opt you back in."
            )
        except discord.Forbidden:
            pass

        await interaction.followup.send(
            f"✅ {user.mention} has been **force-opted out** (data deleted + tracking disabled).\n"
            f"Reason: {reason or '—'}",
            ephemeral=True,
        )

    @app_commands.command(name="user_optin", description="(Admin) Re-enable Isla tracking for a previously opted-out user.")
    @app_commands.describe(user="User to opt-in", reason="Reason (optional)")
    async def user_optin(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        reason: str | None = None
    ):
        if not interaction.guild or not self._is_admin(interaction):
            await interaction.response.send_message("Admin only.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild.id
        target_id = user.id

        await self.bot.db.set_optout(gid, target_id, False, None)
        await self.bot.db.ensure_user(gid, target_id)

        await self.bot.db.audit(
            gid,
            actor_id=interaction.user.id,
            target_user_id=target_id,
            action="admin_user_optin",
            meta=json.dumps({"reason": (reason or "")[:500]}),
            ts=now_ts(),
        )

        try:
            await user.send(
                f"You have been opted back in to Isla tracking in **{interaction.guild.name}**.\n"
                f"If you want to leave again, you can use /optout (if enabled) or ask an admin."
            )
        except discord.Forbidden:
            pass

        await interaction.followup.send(
            f"✅ {user.mention} has been **opted in**.\nReason: {reason or '—'}",
            ephemeral=True,
        )

    @app_commands.command(name="user_safeword", description="(Admin) Force safeword on a user (pause Isla interactions).")
    @app_commands.describe(user="User to apply safeword to", minutes="Duration in minutes (5-10080)", reason="Reason (optional)")
    async def user_safeword(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        minutes: app_commands.Range[int, 5, 10080] = 60,
        reason: str | None = None
    ):
        if not interaction.guild or not self._is_admin(interaction):
            await interaction.response.send_message("Admin only.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild.id
        target_id = user.id

        until = now_ts() + int(minutes) * 60
        await self.bot.db.set_user_safeword(gid, target_id, until)

        await self.bot.db.audit(
            gid,
            actor_id=interaction.user.id,
            target_user_id=target_id,
            action="admin_user_safeword_set",
            meta=json.dumps({"minutes": minutes, "until": until, "reason": (reason or "")[:500]}),
            ts=now_ts(),
        )

        # Best-effort DM notice
        try:
            await user.send(
                f"An admin applied a safeword/pause for you in **{interaction.guild.name}**.\n"
                f"Duration: {minutes} minutes.\n"
                f"During this time Isla should not engage/track you.\n"
                f"Reason: {reason or '—'}"
            )
        except discord.Forbidden:
            pass

        await interaction.followup.send(
            f"🛑 Safeword applied to {user.mention} for **{minutes}** minutes. (until <t:{until}:R>)\n"
            f"Reason: {reason or '—'}",
            ephemeral=True,
        )

    @app_commands.command(name="user_unsafeword", description="(Admin) Clear a user's safeword/pause immediately.")
    @app_commands.describe(user="User to clear safeword for", reason="Reason (optional)")
    async def user_unsafeword(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        reason: str | None = None
    ):
        if not interaction.guild or not self._is_admin(interaction):
            await interaction.response.send_message("Admin only.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild.id
        target_id = user.id

        await self.bot.db.set_user_safeword(gid, target_id, None)

        await self.bot.db.audit(
            gid,
            actor_id=interaction.user.id,
            target_user_id=target_id,
            action="admin_user_safeword_cleared",
            meta=json.dumps({"reason": (reason or "")[:500]}),
            ts=now_ts(),
        )

        try:
            await user.send(
                f"Your safeword/pause was cleared in **{interaction.guild.name}**.\n"
                f"Reason: {reason or '—'}"
            )
        except discord.Forbidden:
            pass

        await interaction.followup.send(
            f"✅ Safeword cleared for {user.mention}.\nReason: {reason or '—'}",
            ephemeral=True,
        )

    @app_commands.command(name="user_status", description="(Mod) View Isla status for a user (opt-out + safeword + core stats).")
    @app_commands.describe(user="User to check")
    async def user_status(self, interaction: discord.Interaction, user: discord.Member):
        if not interaction.guild or not self._is_mod(interaction):
            await interaction.response.send_message("Mods only.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        gid, uid = interaction.guild.id, user.id

        opted_out = await self.bot.db.is_opted_out(gid, uid)
        row = await self.bot.db.fetchone(
            "SELECT coins,debt,stage,safeword_until_ts,last_msg_ts FROM users WHERE guild_id=? AND user_id=?",
            (gid, uid),
        )

        if not row:
            await interaction.followup.send(
                f"{user.mention}\nOpt-out: **{'YES' if opted_out else 'NO'}**\nNo Isla user row yet.",
                ephemeral=True,
            )
            return

        sw = row["safeword_until_ts"]
        sw_txt = "—"
        if sw and int(sw) > now_ts():
            sw_txt = f"ACTIVE until <t:{int(sw)}:R>"

        await interaction.followup.send(
            f"**Isla status for {user.mention}**\n"
            f"- Opted out: **{'YES' if opted_out else 'NO'}**\n"
            f"- Safeword: **{sw_txt}**\n"
            f"- Coins: **{int(row['coins'])}** | Debt: **{int(row['debt'])}** | Stage: **{int(row['stage'])}**\n"
            f"- Last msg: {f'<t:{int(row['last_msg_ts'])}:R>' if row['last_msg_ts'] else '—'}",
            ephemeral=True,
        )

async def setup(bot: commands.Bot):
    await bot.add_cog(AdminTools(bot))

