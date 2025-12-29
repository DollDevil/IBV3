from __future__ import annotations

import json
import io
import time
import discord
from discord.ext import commands, tasks
from discord import app_commands

from core.configurations import FEATURES
from core.utility import now_ts, day_key, fmt
from utils.helpers import isla_embed
from utils.embed_utils import create_embed
from utils.guild_config import cfg_set, cfg_get
from utils.uk_parse import parse_duration_to_seconds
from utils.economy import add_coins, get_wallet, ensure_wallet
from utils.uk_time import uk_day_ymd

ISLA_ICON = "https://i.imgur.com/5nsuuCV.png"
STYLE1_NEUTRAL = "https://i.imgur.com/9oUjOQQ.png"

# ============================================================================
# CONFIG MODALS (from config_group.py)
# ============================================================================

def is_admin(m: discord.Member) -> bool:
    return m.guild_permissions.administrator or m.guild_permissions.manage_guild

class RolesModal(discord.ui.Modal, title="Config: Roles"):
    verified = discord.ui.TextInput(label="Verified role ID", required=False, max_length=24)
    muted = discord.ui.TextInput(label="Muted/Punishment role ID", required=False, max_length=24)
    ranks = discord.ui.TextInput(label="Ranks roles (comma role IDs)", required=False, max_length=200)

    def __init__(self, bot: commands.Bot):
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        gid = interaction.guild_id
        if not gid:
            embed = create_embed("Server only.", color="warning", is_dm=False, is_system=False)
            return await interaction.response.send_message(embed=embed, ephemeral=True)
        await cfg_set(self.bot.db, gid, "roles.verified", self.verified.value.strip())
        mute_value = self.muted.value.strip()
        await cfg_set(self.bot.db, gid, "roles.muted", mute_value)
        await cfg_set(self.bot.db, gid, "roles.punishment", mute_value)  # Keep for backwards compatibility
        await cfg_set(self.bot.db, gid, "roles.ranks", self.ranks.value.strip())
        embed = create_embed("Saved.\n᲼᲼", title="Config Roles", color="success", is_dm=False, is_system=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

class ChannelsModal(discord.ui.Modal, title="Config: Channels"):
    logs = discord.ui.TextInput(label="Logs channel ID", required=False, max_length=24)
    announcements = discord.ui.TextInput(label="Announcements channel ID", required=False, max_length=24)
    orders = discord.ui.TextInput(label="Orders channel ID", required=False, max_length=24)
    intros = discord.ui.TextInput(label="Introductions/Confession channel ID", required=False, max_length=24)
    spam = discord.ui.TextInput(label="Bot spam channel ID", required=False, max_length=24)

    def __init__(self, bot: commands.Bot):
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        gid = interaction.guild_id
        if not gid:
            embed = create_embed("Server only.", color="warning", is_dm=False, is_system=False)
            return await interaction.response.send_message(embed=embed, ephemeral=True)
        await cfg_set(self.bot.db, gid, "channels.logs", self.logs.value.strip())
        await cfg_set(self.bot.db, gid, "channels.announcements", self.announcements.value.strip())
        await cfg_set(self.bot.db, gid, "channels.orders", self.orders.value.strip())
        await cfg_set(self.bot.db, gid, "channels.intros", self.intros.value.strip())
        await cfg_set(self.bot.db, gid, "channels.spam", self.spam.value.strip())
        embed = create_embed("Saved.\n᲼᲼", title="Config Channels", color="success", is_dm=False, is_system=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

class EconomyModal(discord.ui.Modal, title="Config: Economy"):
    daily_amount = discord.ui.TextInput(label="Daily coin base amount", default="80", max_length=10)
    streak_step = discord.ui.TextInput(label="Streak bonus per day (coins)", default="10", max_length=10)
    transfer_limit = discord.ui.TextInput(label="Transfer limit per day", default="500", max_length=10)
    gambling_limit = discord.ui.TextInput(label="Gambling max bet (0=none)", default="0", max_length=10)
    tax_rule = discord.ui.TextInput(label="Tax rule preset (simple/custom)", default="simple", max_length=20)

    def __init__(self, bot: commands.Bot):
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        gid = interaction.guild_id
        if not gid:
            embed = create_embed("Server only.", color="warning", is_dm=False, is_system=False)
            return await interaction.response.send_message(embed=embed, ephemeral=True)
        await cfg_set(self.bot.db, gid, "economy.daily_base", self.daily_amount.value.strip())
        await cfg_set(self.bot.db, gid, "economy.streak_step", self.streak_step.value.strip())
        await cfg_set(self.bot.db, gid, "economy.transfer_limit", self.transfer_limit.value.strip())
        await cfg_set(self.bot.db, gid, "economy.gambling_limit", self.gambling_limit.value.strip())
        await cfg_set(self.bot.db, gid, "economy.tax_rule", self.tax_rule.value.strip())
        embed = create_embed("Saved.\n᲼᲼", title="Config Economy", color="success", is_dm=False, is_system=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

class OrdersModal(discord.ui.Modal, title="Config: Orders"):
    frequency = discord.ui.TextInput(label="Order frequency (e.g., hourly / daily)", default="daily", max_length=20)
    allowed_types = discord.ui.TextInput(label="Allowed types (comma): hourly,daily,event,personal", default="hourly,daily,event,personal", max_length=100)
    windows = discord.ui.TextInput(label="Time windows (UK) e.g. 09:00-23:00", default="09:00-23:00", max_length=30)
    penalties = discord.ui.TextInput(label="Default penalties (coins,obed) e.g. 50,10", default="50,10", max_length=20)
    rewards = discord.ui.TextInput(label="Reward multiplier e.g. 1.0", default="1.0", max_length=10)

    def __init__(self, bot: commands.Bot):
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        gid = interaction.guild_id
        if not gid:
            embed = create_embed("Server only.", color="warning", is_dm=False, is_system=False)
            return await interaction.response.send_message(embed=embed, ephemeral=True)
        await cfg_set(self.bot.db, gid, "orders.frequency", self.frequency.value.strip())
        await cfg_set(self.bot.db, gid, "orders.allowed_types", self.allowed_types.value.strip())
        await cfg_set(self.bot.db, gid, "orders.windows", self.windows.value.strip())
        await cfg_set(self.bot.db, gid, "orders.penalties", self.penalties.value.strip())
        await cfg_set(self.bot.db, gid, "orders.reward_mult", self.rewards.value.strip())
        embed = create_embed("Saved.\n᲼᲼", title="Config Orders", color="success", is_dm=False, is_system=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

class ModerationModal(discord.ui.Modal, title="Config: Moderation"):
    filters = discord.ui.TextInput(label="Filters preset (off/basic/strict)", default="basic", max_length=20)
    antispam = discord.ui.TextInput(label="Anti-spam sensitivity (1-10)", default="5", max_length=2)
    escalation = discord.ui.TextInput(label="Escalation thresholds (e.g. 3=10m,5=1h,7=24h)", default="3=10m,5=1h,7=24h", max_length=120)
    raid = discord.ui.TextInput(label="Raid mode behavior (off/lockdown/slowmode)", default="off", max_length=20)
    notes = discord.ui.TextInput(label="Notes (optional)", required=False, style=discord.TextStyle.long, max_length=400)

    def __init__(self, bot: commands.Bot):
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        gid = interaction.guild_id
        if not gid:
            embed = create_embed("Server only.", color="warning", is_dm=False, is_system=False)
            return await interaction.response.send_message(embed=embed, ephemeral=True)
        await cfg_set(self.bot.db, gid, "mod.filters", self.filters.value.strip())
        await cfg_set(self.bot.db, gid, "mod.antispam", self.antispam.value.strip())
        await cfg_set(self.bot.db, gid, "mod.escalation", self.escalation.value.strip())
        await cfg_set(self.bot.db, gid, "mod.raid", self.raid.value.strip())
        await cfg_set(self.bot.db, gid, "mod.notes", self.notes.value.strip())
        embed = create_embed("Saved.\n᲼᲼", title="Config Moderation", color="success", is_dm=False, is_system=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

# ---------- Onboarding Subgroup ----------
class OnboardingConfigGroup(app_commands.Group):
    def __init__(self, bot: commands.Bot):
        super().__init__(name="onboarding", description="Onboarding configuration")
        self.bot = bot

    @app_commands.command(name="channel", description="Set onboarding channel.")
    @app_commands.describe(channel="The channel for onboarding messages")
    async def channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            embed = create_embed("Server only.", color="warning", is_dm=False, is_system=False)
            return await interaction.response.send_message(embed=embed, ephemeral=True)
        if not is_admin(interaction.user):
            embed = create_embed("Not for you.\n᲼᲼", title="Config", color="error", is_dm=False, is_system=False)
            return await interaction.response.send_message(embed=embed, ephemeral=True)
        gid = interaction.guild.id
        await cfg_set(self.bot.db, gid, "onboarding.channel", str(channel.id))
        embed = create_embed(f"Onboarding channel set to {channel.mention}.\n᲼᲼", title="Config Onboarding", color="success", is_dm=False, is_system=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="role", description="Set onboarding role.")
    @app_commands.describe(role_type="Role type", role="The role to set")
    @app_commands.choices(role_type=[
        app_commands.Choice(name="Unverified", value="unverified"),
        app_commands.Choice(name="Verified", value="verified"),
        app_commands.Choice(name="Bad Pup", value="bad_pup"),
    ])
    async def role(self, interaction: discord.Interaction, role_type: app_commands.Choice[str], role: discord.Role):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            embed = create_embed("Server only.", color="warning", is_dm=False, is_system=False)
            return await interaction.response.send_message(embed=embed, ephemeral=True)
        if not is_admin(interaction.user):
            embed = create_embed("Not for you.\n᲼᲼", title="Config", color="error", is_dm=False, is_system=False)
            return await interaction.response.send_message(embed=embed, ephemeral=True)
        gid = interaction.guild.id
        await cfg_set(self.bot.db, gid, f"onboarding.role_{role_type.value}", str(role.id))
        embed = create_embed(f"{role_type.name} role set to {role.mention}.\n᲼᲼", title="Config Onboarding", color="success", is_dm=False, is_system=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

# ============================================================================
# MAIN ADMIN COG CLASS
# ============================================================================

class Admin(commands.Cog):
    """Consolidated Admin cog: Admin tools, config, and discipline management."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        
        # Setup command groups
        self.config = app_commands.Group(name="config", description="Server setup")
        self.discipline = app_commands.Group(name="discipline", description="Moderator discipline tools")
        self.onboarding_config = OnboardingConfigGroup(bot)
        self.config.add_command(self.onboarding_config)
        
        # Discipline settings
        self.logs_channel_id = int(bot.cfg.get("channels", "logs", default="0") or 0)
        # Try muted first, fallback to punishment for backwards compatibility
        self.mute_role_id = int(bot.cfg.get("roles", "muted", default="0") or 0) or int(bot.cfg.get("roles", "punishment", default="0") or 0)
        
        # Register commands
        self._register_config_commands()
        
        # Start discipline expiry loop (must be after registration)
        self.expiry_loop.start()

    def cog_unload(self):
        self.expiry_loop.cancel()
    
    # ========================================================================
    # PERMISSION HELPERS
    # ========================================================================
    
    def _is_admin(self, interaction: discord.Interaction) -> bool:
        return bool(interaction.user and getattr(interaction.user, "guild_permissions", None) and interaction.user.guild_permissions.administrator)

    def _is_mod(self, interaction: discord.Interaction) -> bool:
        perms = getattr(interaction.user, "guild_permissions", None)
        return bool(perms and (perms.manage_guild or perms.moderate_members or perms.administrator))
    
    def _is_mod_member(self, member: discord.Member) -> bool:
        perms = member.guild_permissions
        return perms.moderate_members or perms.manage_messages or perms.administrator
    
    async def _require_admin(self, interaction: discord.Interaction) -> bool:
        if not interaction.guild or not self._is_admin(interaction):
            embed = create_embed("Admin only.", color="info", is_dm=False, is_system=False)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return False
        return True
    
    async def _require_mod(self, interaction: discord.Interaction) -> bool:
        if not interaction.guild or not self._is_mod(interaction):
            embed = create_embed("Mods only.", color="info", is_dm=False, is_system=False)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return False
        return True
    
    async def _log(self, guild: discord.Guild, title: str, desc: str):
        if not self.logs_channel_id:
            return
        ch = guild.get_channel(self.logs_channel_id)
        if isinstance(ch, discord.TextChannel):
            await ch.send(embed=isla_embed(desc, title=title))
    
    # ========================================================================
    # CONFIG GROUP REGISTRATION (from config_group.py)
    # ========================================================================
    
    def _register_config_commands(self):
        self.config.add_command(self.config_roles)
        self.config.add_command(self.config_channels)
        self.config.add_command(self.config_economy)
        self.config.add_command(self.config_orders)
        self.config.add_command(self.config_moderation)
    
    @app_commands.command(name="roles", description="Wizard to set role IDs.")
    async def config_roles(self, interaction: discord.Interaction):
        if not await self._require_admin(interaction):
            return
        await interaction.response.send_modal(RolesModal(self.bot))

    @app_commands.command(name="channels", description="Wizard to set channel IDs.")
    async def config_channels(self, interaction: discord.Interaction):
        if not await self._require_admin(interaction):
            return
        await interaction.response.send_modal(ChannelsModal(self.bot))

    @app_commands.command(name="economy", description="Wizard to set economy rules.")
    async def config_economy(self, interaction: discord.Interaction):
        if not await self._require_admin(interaction):
            return
        await interaction.response.send_modal(EconomyModal(self.bot))

    @app_commands.command(name="orders", description="Wizard to set order rules.")
    async def config_orders(self, interaction: discord.Interaction):
        if not await self._require_admin(interaction):
            return
        await interaction.response.send_modal(OrdersModal(self.bot))

    @app_commands.command(name="moderation", description="Wizard to set moderation rules.")
    async def config_moderation(self, interaction: discord.Interaction):
        if not await self._require_admin(interaction):
            return
        await interaction.response.send_modal(ModerationModal(self.bot))
    
    # ========================================================================
    # FEATURE TOGGLES (from admin_tools.py)
    # ========================================================================
    
    @app_commands.command(name="feature_list", description="(Mod) List feature flags (available modules).")
    async def feature_list(self, interaction: discord.Interaction):
        if not interaction.guild or not self._is_mod(interaction):
            embed = create_embed("Mods only.", color="info", is_dm=False, is_system=False)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        lines = [f"- `{k}`: {v}" for k, v in FEATURES.items()]
        await interaction.followup.send("\n".join(lines), ephemeral=True)

    @app_commands.command(name="feature_set", description="(Admin) Enable/disable a feature at guild level.")
    @app_commands.describe(feature="Feature name", enabled="Enable or disable")
    async def feature_set(self, interaction: discord.Interaction, feature: str, enabled: bool):
        if not interaction.guild or not self._is_admin(interaction):
            embed = create_embed("Admin only.", color="info", is_dm=False, is_system=False)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild.id
        if feature not in FEATURES:
            embed = create_embed("Unknown feature. Use /feature_list.", color="info", is_dm=False, is_system=False)
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        await self.bot.flags.set_guild(gid, feature, enabled)
        await self.bot.db.audit(gid, interaction.user.id, None, "toggle_feature_guild", json.dumps({"feature": feature, "enabled": enabled}), now_ts())
        embed = create_embed(f"Guild feature `{feature}` set to {enabled}.", color="info", is_dm=False, is_system=False)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="feature_set_channel", description="(Admin) Enable/disable a feature in a channel.")
    @app_commands.describe(feature="Feature name", channel="Channel to configure", enabled="Enable or disable")
    async def feature_set_channel(self, interaction: discord.Interaction, feature: str, channel: discord.TextChannel, enabled: bool):
        if not interaction.guild or not self._is_admin(interaction):
            embed = create_embed("Admin only.", color="info", is_dm=False, is_system=False)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild.id
        if feature not in FEATURES:
            embed = create_embed("Unknown feature. Use /feature_list.", color="info", is_dm=False, is_system=False)
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        await self.bot.flags.set_channel(gid, channel.id, feature, enabled)
        await self.bot.db.audit(gid, interaction.user.id, None, "toggle_feature_channel", json.dumps({"feature": feature, "channel_id": channel.id, "enabled": enabled}), now_ts())
        embed = create_embed(f"Channel {channel.mention} feature `{feature}` set to {enabled}.", color="info", is_dm=False, is_system=False)
        await interaction.followup.send(embed=embed, ephemeral=True)
    
    # ========================================================================
    # CHANNEL CONFIG (from admin_tools.py)
    # ========================================================================
    
    @app_commands.command(name="channelcfg_set", description="(Admin) Set a channel config key=value.")
    @app_commands.describe(channel="Channel to configure", key="Config key", value="Config value")
    async def channelcfg_set(self, interaction: discord.Interaction, channel: discord.TextChannel, key: str, value: str):
        if not interaction.guild or not self._is_admin(interaction):
            embed = create_embed("Admin only.", color="info", is_dm=False, is_system=False)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild.id
        await self.bot.chan_cfg.set(gid, channel.id, key, value)
        await self.bot.db.audit(gid, interaction.user.id, None, "channelcfg_set", json.dumps({"channel_id": channel.id, "key": key, "value": value}), now_ts())
        embed = create_embed(f"Set {channel.mention} `{key}` = `{value}`", color="info", is_dm=False, is_system=False)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="channelcfg_get", description="(Mod) Get a channel config key.")
    @app_commands.describe(channel="Channel to check", key="Config key")
    async def channelcfg_get(self, interaction: discord.Interaction, channel: discord.TextChannel, key: str):
        if not interaction.guild or not self._is_mod(interaction):
            embed = create_embed("Mods only.", color="info", is_dm=False, is_system=False)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild.id
        v = await self.bot.chan_cfg.get(gid, channel.id, key, default=None)
        embed = create_embed(f"{channel.mention} `{key}` = `{v}`", color="info", is_dm=False, is_system=False)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="channelcfg_del", description="(Admin) Delete a channel config key.")
    @app_commands.describe(channel="Channel to configure", key="Config key to delete")
    async def channelcfg_del(self, interaction: discord.Interaction, channel: discord.TextChannel, key: str):
        if not interaction.guild or not self._is_admin(interaction):
            embed = create_embed("Admin only.", color="info", is_dm=False, is_system=False)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild.id
        await self.bot.chan_cfg.delete(gid, channel.id, key)
        await self.bot.db.audit(gid, interaction.user.id, None, "channelcfg_del", json.dumps({"channel_id": channel.id, "key": key}), now_ts())
        embed = create_embed(f"Deleted {channel.mention} `{key}`", color="info", is_dm=False, is_system=False)
        await interaction.followup.send(embed=embed, ephemeral=True)
    
    # ========================================================================
    # NOTES (from admin_tools.py)
    # ========================================================================
    
    @app_commands.command(name="note_set", description="(Mod) Set a private admin note on a user.")
    @app_commands.describe(user="User to note", note="Note text")
    async def note_set(self, interaction: discord.Interaction, user: discord.Member, note: str):
        if not interaction.guild or not self._is_mod(interaction):
            embed = create_embed("Mods only.", color="info", is_dm=False, is_system=False)
            await interaction.response.send_message(embed=embed, ephemeral=True)
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
        embed = create_embed(f"Note saved for {user.mention}.", color="info", is_dm=False, is_system=False)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="note_view", description="(Mod) View a private admin note on a user.")
    @app_commands.describe(user="User to view")
    async def note_view(self, interaction: discord.Interaction, user: discord.Member):
        if not interaction.guild or not self._is_mod(interaction):
            embed = create_embed("Mods only.", color="info", is_dm=False, is_system=False)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        gid, uid = interaction.guild.id, user.id
        row = await self.bot.db.fetchone(
            "SELECT note,created_by,created_ts,updated_ts FROM user_admin_notes WHERE guild_id=? AND user_id=?",
            (gid, uid),
        )
        if not row:
            embed = create_embed("No note.", color="info", is_dm=False, is_system=False)
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        updated = f'<t:{int(row["updated_ts"])}:R>' if row["updated_ts"] else "—"
        await interaction.followup.send(
            f"**Note for {user.mention}:**\n{row['note']}\nCreated: <t:{int(row['created_ts'])}:R> by <@{int(row['created_by'])}>\nUpdated: {updated}",
            ephemeral=True,
        )
    
    # ========================================================================
    # DISCIPLINE HELPERS (from discipline_group.py)
    # ========================================================================
    
    async def _audit_row(self, guild_id: int, action: str, target_id: int, moderator_id: int, amount: int = 0, duration_seconds: int = 0, reason: str = ""):
        await self.bot.db.execute(
            "INSERT INTO discipline_log(guild_id,ts,action,target_id,moderator_id,amount,duration_seconds,reason) VALUES(?,?,?,?,?,?,?,?)",
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
    
    # ========================================================================
    # DISCIPLINE: USER-FACING COMMANDS (from discipline_group.py)
    # ========================================================================
    
    @app_commands.command(name="punishments", description="Shows your active punishments, duration, and conditions to clear.")
    async def punishments(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild_id
        uid = interaction.user.id
        if not gid:
            embed = create_embed("Server only.", color="warning", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)

        rows = await self.bot.db.fetchall(
            "SELECT id, kind, reason, created_ts, ends_ts, conditions FROM discipline_punishments WHERE guild_id=? AND user_id=? AND active=1 ORDER BY created_ts DESC",
            (gid, uid)
        )

        if not rows:
            return await interaction.followup.send(embed=isla_embed("None.\n᲼᲼", title="Punishments", icon=ISLA_ICON), ephemeral=True)

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

        e = isla_embed("Here's what's active.\n᲼᲼", title="Punishments", icon=ISLA_ICON)
        e.add_field(name="Active", value="\n\n".join(lines[:10]), inline=False)
        await interaction.followup.send(embed=e, ephemeral=True)

    @app_commands.command(name="debt", description="Shows debt / penalties owed.")
    async def debt(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild_id
        uid = interaction.user.id
        if not gid:
            embed = create_embed("Server only.", color="warning", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)

        await self._ensure_debt(gid, uid)
        d = await self.bot.db.fetchone("SELECT debt FROM discipline_debt WHERE guild_id=? AND user_id=?", (gid, uid))
        debt_amt = int(d["debt"] or 0)

        w = await get_wallet(self.bot.db, gid, uid)
        e = isla_embed(
            f"Debt.\n\nDiscipline debt: **{fmt(debt_amt)} Coins**\nTax debt: **{fmt(w.tax_debt)} Coins**\n᲼᲼",
            title="Debt",
            icon=ISLA_ICON
        )
        e.add_field(name="Work it off", value="Use `/penance`.\nOr pay it down by staying active.", inline=False)
        await interaction.followup.send(embed=e, ephemeral=True)

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

        tasks = [
            ("Write one helpful message in a non-spam channel.", 25),
            ("Spend 10 minutes in voice, then send one message summarizing what you did.", 40),
            ("Complete one order today and come back.", 60),
            ("Help a new member: answer one question politely.", 50),
            ("Post one resource link relevant to the server topic.", 35),
        ]
        task, value = tasks[min(len(tasks)-1, debt_amt // 200)] if debt_amt > 0 else tasks[0]

        reduce_by = min(value, debt_amt) if debt_amt > 0 else 0
        if reduce_by > 0:
            await self.bot.db.execute(
                "UPDATE discipline_debt SET debt=debt-?, updated_ts=? WHERE guild_id=? AND user_id=?",
                (reduce_by, now_ts(), gid, uid)
            )

        e = isla_embed(
            f"Penance.\n\nTask: **{task}**\nDebt reduction: **{fmt(reduce_by)} Coins**\n᲼᲼",
            title="Penance",
            icon=ISLA_ICON
        )
        await interaction.followup.send(embed=e, ephemeral=True)
    
    # ========================================================================
    # DISCIPLINE: MOD-FACING COMMANDS (from discipline_group.py)
    # ========================================================================
    
    def _register_discipline_commands(self):
        self.discipline.add_command(self.d_warn)
        self.discipline.add_command(self.d_strike)
        self.discipline.add_command(self.d_timeout)
        self.discipline.add_command(self.d_mute)
        self.discipline.add_command(self.d_nickname)
        self.discipline.add_command(self.d_seize)
        self.discipline.add_command(self.d_fine)
        self.discipline.add_command(self.d_pardon)

    @app_commands.command(name="warn", description="Warn a user (logged).")
    async def d_warn(self, interaction: discord.Interaction, user: discord.Member, reason: str | None = None):
        if not await self._require_mod(interaction):
            return
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild_id
        mod_id = interaction.user.id
        await self.bot.db.execute(
            "INSERT INTO discipline_punishments(guild_id,user_id,kind,reason,created_ts,ends_ts,conditions,active,issued_by) VALUES(?,?,?,?,?,?,?,?,?)",
            (gid, user.id, "warn", reason or "", now_ts(), 0, "Avoid repeating the behavior.", 1, mod_id)
        )
        await self._audit_row(gid, "warn", user.id, mod_id, reason=reason or "")
        e_user = isla_embed("Warning.\n\nDon't test limits.\n᲼᲼", title="Notice", icon=ISLA_ICON)
        if reason:
            e_user.add_field(name="Reason", value=reason[:900], inline=False)
        try:
            await user.send(embed=e_user)
        except discord.Forbidden:
            pass
        await self._log(interaction.guild, "Warn", f"{user.mention}\nReason: {reason or '—'}\nIssued by: <@{mod_id}>\n᲼᲼")
        await interaction.followup.send(embed=isla_embed("Warned.\n᲼᲼", title="Discipline", icon=ISLA_ICON), ephemeral=True)

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
        srow = await self.bot.db.fetchone("SELECT strikes FROM discipline_strikes WHERE guild_id=? AND user_id=?", (gid, user.id))
        strikes = int(srow["strikes"] or 0)
        await self._audit_row(gid, "strike", user.id, mod_id, amount=count, reason=reason or "")
        auto_timeout = 0
        if strikes >= 7:
            auto_timeout = 24 * 3600
        elif strikes >= 5:
            auto_timeout = 3600
        elif strikes >= 3:
            auto_timeout = 600
        if auto_timeout > 0:
            from datetime import timedelta
            until = discord.utils.utcnow() + timedelta(seconds=auto_timeout)
            try:
                await user.timeout(until, reason=f"Auto escalation ({strikes} strikes)")
            except Exception:
                pass
            ends = now_ts() + auto_timeout
            await self.bot.db.execute(
                "INSERT INTO discipline_punishments(guild_id,user_id,kind,reason,created_ts,ends_ts,conditions,active,issued_by) VALUES(?,?,?,?,?,?,?,?,?)",
                (gid, user.id, "timeout", f"Auto escalation ({strikes} strikes). {reason or ''}".strip(), now_ts(), ends, "Wait out the timer and follow the rules.", 1, mod_id)
            )
        await self._log(interaction.guild, "Strike", f"{user.mention}\n+{count} strikes → **{strikes} total**\nReason: {reason or '—'}\nIssued by: <@{mod_id}>\n᲼᲼")
        e = isla_embed(f"Strikes updated.\n\n{user.mention}\nTotal: **{strikes}**\n᲼᲼", title="Discipline", icon=ISLA_ICON)
        if auto_timeout:
            e.add_field(name="Escalation", value=f"Auto timeout: {auto_timeout//60} minutes", inline=False)
        await interaction.followup.send(embed=e, ephemeral=True)

    @app_commands.command(name="timeout", description="Timeout + optional Coin seizure.")
    @app_commands.describe(user="User to timeout", duration="Duration (10m, 2h, 3d)", reason="Reason", seize="Coins to seize")
    async def d_timeout(self, interaction: discord.Interaction, user: discord.Member, duration: str, reason: str | None = None, seize: int | None = None):
        if not await self._require_mod(interaction):
            return
        await interaction.response.defer(ephemeral=True)
        seconds = parse_duration_to_seconds(duration)
        if seconds <= 0:
            return await interaction.followup.send(embed=isla_embed("Bad duration.\nUse 10m / 2h / 3d.\n᲼᲼", title="Timeout", icon=ISLA_ICON), ephemeral=True)
        mod_id = interaction.user.id
        gid = interaction.guild_id
        from datetime import timedelta
        until = discord.utils.utcnow() + timedelta(seconds=seconds)
        try:
            await user.timeout(until, reason=reason or "discipline timeout")
        except Exception:
            pass
        ends = now_ts() + seconds
        await self.bot.db.execute(
            "INSERT INTO discipline_punishments(guild_id,user_id,kind,reason,created_ts,ends_ts,conditions,active,issued_by) VALUES(?,?,?,?,?,?,?,?,?)",
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
        e = isla_embed(f"Timeout applied.\n\n{user.mention}\nEnds: <t:{ends}:R>\n᲼᲼", title="Discipline", icon=ISLA_ICON)
        if seized:
            e.add_field(name="Coins seized", value=fmt(seized), inline=True)
        if reason:
            e.add_field(name="Reason", value=reason[:900], inline=False)
        await interaction.followup.send(embed=e, ephemeral=True)

    @app_commands.command(name="mute", description="Mute role assignment.")
    @app_commands.describe(user="User to mute", duration="Duration (10m, 2h, 3d)", reason="Reason")
    async def d_mute(self, interaction: discord.Interaction, user: discord.Member, duration: str, reason: str | None = None):
        if not await self._require_mod(interaction):
            return
        await interaction.response.defer(ephemeral=True)
        if not self.mute_role_id:
            return await interaction.followup.send(embed=isla_embed("Mute role not configured.\n᲼᲼", title="Mute", icon=ISLA_ICON), ephemeral=True)
        seconds = parse_duration_to_seconds(duration)
        if seconds <= 0:
            return await interaction.followup.send(embed=isla_embed("Bad duration.\nUse 10m / 2h / 3d.\n᲼᲼", title="Mute", icon=ISLA_ICON), ephemeral=True)
        gid = interaction.guild_id
        mod_id = interaction.user.id
        role = interaction.guild.get_role(self.mute_role_id)
        if not role:
            return await interaction.followup.send(embed=isla_embed("Mute role missing.\n᲼᲼", title="Mute", icon=ISLA_ICON), ephemeral=True)
        try:
            await user.add_roles(role, reason=reason or "discipline mute")
        except Exception:
            return await interaction.followup.send(embed=isla_embed("Couldn't apply mute.\n᲼᲼", title="Mute", icon=ISLA_ICON), ephemeral=True)
        ends = now_ts() + seconds
        await self.bot.db.execute(
            "INSERT INTO discipline_punishments(guild_id,user_id,kind,reason,created_ts,ends_ts,conditions,active,issued_by) VALUES(?,?,?,?,?,?,?,?,?)",
            (gid, user.id, "mute", reason or "", now_ts(), ends, "Wait out the timer.", 1, mod_id)
        )
        await self._audit_row(gid, "mute", user.id, mod_id, duration_seconds=seconds, reason=reason or "")
        await self._log(interaction.guild, "Mute", f"{user.mention}\nDuration: {duration}\nReason: {reason or '—'}\nBy: <@{mod_id}>\n᲼᲼")
        e = isla_embed(f"Muted.\n\n{user.mention}\nEnds: <t:{ends}:R>\n᲼᲼", title="Discipline", icon=ISLA_ICON)
        await interaction.followup.send(embed=e, ephemeral=True)

    @app_commands.command(name="nickname", description="Temporary enforced nickname.")
    @app_commands.describe(user="User to nickname", nickname="New nickname", duration="Duration (default 24h)")
    async def d_nickname(self, interaction: discord.Interaction, user: discord.Member, nickname: str, duration: str | None = None):
        if not await self._require_mod(interaction):
            return
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild_id
        mod_id = interaction.user.id
        seconds = parse_duration_to_seconds(duration) if duration else (24 * 3600)
        seconds = max(60, min(30 * 86400, seconds))
        ends = now_ts() + seconds
        old = user.nick or ""
        try:
            await user.edit(nick=nickname, reason="discipline nickname")
        except Exception:
            return await interaction.followup.send(embed=isla_embed("Couldn't change nickname.\n᲼᲼", title="Nickname", icon=ISLA_ICON), ephemeral=True)
        await self.bot.db.execute(
            "INSERT INTO discipline_nicknames(guild_id,user_id,old_nick,new_nick,ends_ts,active) VALUES(?,?,?,?,?,1) ON CONFLICT(guild_id,user_id) DO UPDATE SET old_nick=excluded.old_nick, new_nick=excluded.new_nick, ends_ts=excluded.ends_ts, active=1",
            (gid, user.id, old, nickname, ends)
        )
        await self.bot.db.execute(
            "INSERT INTO discipline_punishments(guild_id,user_id,kind,reason,created_ts,ends_ts,conditions,active,issued_by,meta_json) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (gid, user.id, "nickname", "Temporary nickname enforced.", now_ts(), ends, "Wait for expiry or ask staff.", 1, mod_id, "{}")
        )
        await self._audit_row(gid, "nickname", user.id, mod_id, duration_seconds=seconds, reason=f"nick -> {nickname}")
        await self._log(interaction.guild, "Nickname", f"{user.mention}\nNew: {nickname}\nEnds: <t:{ends}:R>\nBy: <@{mod_id}>\n᲼᲼")
        e = isla_embed(f"Nickname set.\n\n{user.mention}\nEnds: <t:{ends}:R>\n᲼᲼", title="Discipline", icon=ISLA_ICON)
        await interaction.followup.send(embed=e, ephemeral=True)

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
            return await interaction.followup.send(embed=isla_embed("Nothing to seize.\n᲼᲼", title="Seize", icon=ISLA_ICON), ephemeral=True)
        await add_coins(self.bot.db, gid, user.id, -seized, kind="discipline_seize", reason=reason or "seized")
        await self._audit_row(gid, "seize", user.id, mod_id, amount=seized, reason=reason or "")
        await self._log(interaction.guild, "Seize", f"{user.mention}\nAmount: {fmt(seized)}\nReason: {reason or '—'}\nBy: <@{mod_id}>\n᲼᲼")
        e = isla_embed(f"Seized.\n\n{user.mention}\n-**{fmt(seized)} Coins**\n᲼᲼", title="Discipline", icon=ISLA_ICON)
        await interaction.followup.send(embed=e, ephemeral=True)

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
        e = isla_embed(f"Debt added.\n\n{user.mention}\n+**{fmt(amt)} Coins** (debt)\n᲼᲼", title="Discipline", icon=ISLA_ICON)
        if reason:
            e.add_field(name="Reason", value=reason[:900], inline=False)
        await interaction.followup.send(embed=e, ephemeral=True)

    @app_commands.command(name="pardon", description="Clears punishments/strikes.")
    @app_commands.describe(user="User to pardon", reason="Reason")
    async def d_pardon(self, interaction: discord.Interaction, user: discord.Member, reason: str | None = None):
        if not await self._require_mod(interaction):
            return
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild_id
        mod_id = interaction.user.id
        await self.bot.db.execute("UPDATE discipline_punishments SET active=0 WHERE guild_id=? AND user_id=? AND active=1", (gid, user.id))
        await self._ensure_strikes(gid, user.id)
        await self.bot.db.execute("UPDATE discipline_strikes SET strikes=0 WHERE guild_id=? AND user_id=?", (gid, user.id))
        await self.bot.db.execute("UPDATE discipline_nicknames SET active=0 WHERE guild_id=? AND user_id=?", (gid, user.id))
        await self._audit_row(gid, "pardon", user.id, mod_id, reason=reason or "")
        await self._log(interaction.guild, "Pardon", f"{user.mention}\nReason: {reason or '—'}\nBy: <@{mod_id}>\n᲼᲼")
        e = isla_embed(f"Cleared.\n\n{user.mention}\n᲼᲼", title="Discipline", icon=ISLA_ICON)
        await interaction.followup.send(embed=e, ephemeral=True)
    
    # ========================================================================
    # DISCIPLINE EXPIRY LOOP (from discipline_group.py)
    # ========================================================================
    
    @tasks.loop(seconds=30)
    async def expiry_loop(self):
        await self.bot.wait_until_ready()
        now = now_ts()
        for guild in self.bot.guilds:
            gid = guild.id
            exp = await self.bot.db.fetchall(
                "SELECT id, user_id, kind FROM discipline_punishments WHERE guild_id=? AND active=1 AND ends_ts > 0 AND ends_ts <= ?",
                (gid, now)
            )
            if self.mute_role_id and exp:
                role = guild.get_role(self.mute_role_id)
                if role:
                    for r in exp:
                        if str(r["kind"]) == "mute":
                            member = guild.get_member(int(r["user_id"]))
                            if member:
                                try:
                                    await member.remove_roles(role, reason="mute expired")
                                except Exception:
                                    pass
            if exp:
                ids = [int(r["id"]) for r in exp]
                await self.bot.db.execute(
                    f"UPDATE discipline_punishments SET active=0 WHERE id IN ({','.join(['?']*len(ids))})",
                    tuple(ids)
                )
            nicks = await self.bot.db.fetchall(
                "SELECT user_id, old_nick, ends_ts FROM discipline_nicknames WHERE guild_id=? AND active=1 AND ends_ts <= ?",
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
                await self.bot.db.execute("UPDATE discipline_nicknames SET active=0 WHERE guild_id=? AND user_id=?", (gid, uid))
    
    @expiry_loop.before_loop
    async def before_expiry_loop(self):
        await self.bot.wait_until_ready()
    
    # ========================================================================
    # ADMIN TOOLS: DISCIPLINE ADD/VIEW (from admin_tools.py)
    # ========================================================================
    
    @app_commands.command(name="discipline_add", description="(Mod) Add a warning/discipline entry (private log).")
    @app_commands.describe(user="User to discipline", kind="Type: warning|discipline|strike", points="Points (1-10)", reason="Reason (optional)")
    async def discipline_add(self, interaction: discord.Interaction, user: discord.Member, kind: str, points: app_commands.Range[int, 1, 10] = 1, reason: str | None = None):
        if not interaction.guild or not self._is_mod(interaction):
            embed = create_embed("Mods only.", color="info", is_dm=False, is_system=False)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        kind = kind.lower().strip()
        if kind not in ("warning", "discipline", "strike"):
            embed = create_embed("kind must be warning|discipline|strike", color="info", is_dm=False, is_system=False)
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        gid, uid = interaction.guild.id, user.id
        await self.bot.db.ensure_user(gid, uid)
        await self.bot.db.execute(
            "INSERT INTO user_discipline(guild_id,user_id,kind,reason,points,created_by,created_ts) VALUES(?,?,?,?,?,?,?)",
            (gid, uid, kind, (reason or "")[:500], int(points), interaction.user.id, now_ts()),
        )
        await self.bot.db.audit(gid, interaction.user.id, uid, "discipline_add", json.dumps({"kind": kind, "points": points}), now_ts())
        embed = create_embed(f"Logged {kind} for {user.mention} (+{points}).", color="info", is_dm=False, is_system=False)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="discipline_view", description="(Mod) View discipline totals + last entries.")
    @app_commands.describe(user="User to view", limit="Number of recent entries (1-10)")
    async def discipline_view(self, interaction: discord.Interaction, user: discord.Member, limit: app_commands.Range[int, 1, 10] = 5):
        if not interaction.guild or not self._is_mod(interaction):
            embed = create_embed("Mods only.", color="info", is_dm=False, is_system=False)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        gid, uid = interaction.guild.id, user.id
        totals = await self.bot.db.fetchone(
            "SELECT SUM(CASE WHEN kind='warning' THEN points ELSE 0 END) AS warnings, SUM(CASE WHEN kind='discipline' THEN points ELSE 0 END) AS disciplines, SUM(CASE WHEN kind='strike' THEN points ELSE 0 END) AS strikes FROM user_discipline WHERE guild_id=? AND user_id=?",
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
    
    # ========================================================================
    # ADMIN TOOLS: USER MANAGEMENT (from admin_tools.py)
    # ========================================================================
    
    @app_commands.command(name="admin_profile", description="(Mod) Deep view of a user's Isla profile + activity.")
    @app_commands.describe(user="User to view")
    async def admin_profile(self, interaction: discord.Interaction, user: discord.Member):
        if not interaction.guild or not self._is_mod(interaction):
            embed = create_embed("Mods only.", color="info", is_dm=False, is_system=False)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        gid, uid = interaction.guild.id, user.id
        await self.bot.db.ensure_user(gid, uid)
        u = await self.bot.db.fetchone("SELECT coins,lce,debt,stage,last_msg_ts FROM users WHERE guild_id=? AND user_id=?", (gid, uid))
        c = await self.bot.db.fetchone("SELECT * FROM consent WHERE guild_id=? AND user_id=?", (gid, uid))
        note = await self.bot.db.fetchone("SELECT note,created_ts,updated_ts FROM user_admin_notes WHERE guild_id=? AND user_id=?", (gid, uid))
        today = day_key()
        rows = await self.bot.db.fetchall(
            "SELECT day_key,messages,commands,coins_earned,coins_burned,orders_taken,orders_completed,tributes_logged FROM user_activity_daily WHERE guild_id=? AND user_id=? AND day_key>=? ORDER BY day_key DESC",
            (gid, uid, today - 14),
        )
        trib = await self.bot.db.fetchall(
            "SELECT amount,note,ts FROM tribute_log WHERE guild_id=? AND user_id=? ORDER BY ts DESC LIMIT 5",
            (gid, uid),
        )
        tenure = f"Joined: {user.joined_at.isoformat() if user.joined_at else '—'}"
        msg = [
            f"**{user}** ({user.mention})",
            tenure,
            f"Coins: **{int(u['coins'])}** | Debt: **{int(u['debt'])}** | LCE: **{int(u['lce'])}** | Stage: **{int(u['stage'])}**",
            f"Last msg: {'<t:' + str(int(u['last_msg_ts'])) + ':R>' if u['last_msg_ts'] else '—'}",
            "",
            "**Consent:**",
            f"- verified: {'✅' if int(c['verified_18']) else '❌'}",
            f"- orders: {'✅' if int(c['opt_orders']) else '❌'} | dm: {'✅' if int(c['opt_dm']) else '❌'} | humiliation: {'✅' if int(c['opt_humiliation']) else '❌'}",
            "",
            "**Admin Note:**",
            (note["note"] if note else "—"),
            "",
            "**Activity (last 14d):**",
        ]
        if rows:
            for r in rows[:7]:
                msg.append(f"- day {int(r['day_key'])}: msgs {int(r['messages'])}, cmds {int(r['commands'])}, +{int(r['coins_earned'])}, burned {int(r['coins_burned'])}, orders {int(r['orders_completed'])}/{int(r['orders_taken'])}, tributes {int(r['tributes_logged'])}")
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

    @app_commands.command(name="user_optout", description="(Admin) Force-opt-out a user: hard delete Isla data + stop tracking.")
    @app_commands.describe(user="User to opt-out", reason="Reason (optional)")
    async def user_optout(self, interaction: discord.Interaction, user: discord.Member, reason: str | None = None):
        if not interaction.guild or not self._is_admin(interaction):
            embed = create_embed("Admin only.", color="info", is_dm=False, is_system=False)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild.id
        target_id = user.id
        await self.bot.db.audit(gid, actor_id=interaction.user.id, target_user_id=target_id, action="admin_user_optout_requested", meta=json.dumps({"reason": (reason or "")[:500]}), ts=now_ts())
        await self.bot.db.hard_delete_user(gid, target_id)
        await self.bot.db.set_optout(gid, target_id, True, now_ts())
        await self.bot.db.audit(gid, actor_id=interaction.user.id, target_user_id=target_id, action="admin_user_optout_completed", meta=json.dumps({"reason": (reason or "")[:500]}), ts=now_ts())
        try:
            await user.send(f"You have been opted out of Isla tracking in **{interaction.guild.name}**.\nYour Isla data in that server was deleted and Isla will not track you.\nIf this was a mistake, ask an admin to opt you back in.")
        except discord.Forbidden:
            pass
        await interaction.followup.send(f"✅ {user.mention} has been **force-opted out** (data deleted + tracking disabled).\nReason: {reason or '—'}", ephemeral=True)

    @app_commands.command(name="user_optin", description="(Admin) Re-enable Isla tracking for a previously opted-out user.")
    @app_commands.describe(user="User to opt-in", reason="Reason (optional)")
    async def user_optin(self, interaction: discord.Interaction, user: discord.Member, reason: str | None = None):
        if not interaction.guild or not self._is_admin(interaction):
            embed = create_embed("Admin only.", color="info", is_dm=False, is_system=False)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild.id
        target_id = user.id
        await self.bot.db.set_optout(gid, target_id, False, None)
        await self.bot.db.ensure_user(gid, target_id)
        await self.bot.db.audit(gid, actor_id=interaction.user.id, target_user_id=target_id, action="admin_user_optin", meta=json.dumps({"reason": (reason or "")[:500]}), ts=now_ts())
        try:
            await user.send(f"You have been opted back in to Isla tracking in **{interaction.guild.name}**.\nIf you want to leave again, you can use /optout (if enabled) or ask an admin.")
        except discord.Forbidden:
            pass
        await interaction.followup.send(f"✅ {user.mention} has been **opted in**.\nReason: {reason or '—'}", ephemeral=True)

    @app_commands.command(name="user_safeword", description="(Admin) Force safeword on a user (pause Isla interactions).")
    @app_commands.describe(user="User to apply safeword to", minutes="Duration in minutes (5-10080)", reason="Reason (optional)")
    async def user_safeword(self, interaction: discord.Interaction, user: discord.Member, minutes: app_commands.Range[int, 5, 10080] = 60, reason: str | None = None):
        if not interaction.guild or not self._is_admin(interaction):
            embed = create_embed("Admin only.", color="info", is_dm=False, is_system=False)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild.id
        target_id = user.id
        until = now_ts() + int(minutes) * 60
        await self.bot.db.set_user_safeword(gid, target_id, until)
        await self.bot.db.audit(gid, actor_id=interaction.user.id, target_user_id=target_id, action="admin_user_safeword_set", meta=json.dumps({"minutes": minutes, "until": until, "reason": (reason or "")[:500]}), ts=now_ts())
        try:
            await user.send(f"An admin applied a safeword/pause for you in **{interaction.guild.name}**.\nDuration: {minutes} minutes.\nDuring this time Isla should not engage/track you.\nReason: {reason or '—'}")
        except discord.Forbidden:
            pass
        await interaction.followup.send(f"🛑 Safeword applied to {user.mention} for **{minutes}** minutes. (until <t:{until}:R>)\nReason: {reason or '—'}", ephemeral=True)

    @app_commands.command(name="user_unsafeword", description="(Admin) Clear a user's safeword/pause immediately.")
    @app_commands.describe(user="User to clear safeword for", reason="Reason (optional)")
    async def user_unsafeword(self, interaction: discord.Interaction, user: discord.Member, reason: str | None = None):
        if not interaction.guild or not self._is_admin(interaction):
            embed = create_embed("Admin only.", color="info", is_dm=False, is_system=False)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild.id
        target_id = user.id
        await self.bot.db.set_user_safeword(gid, target_id, None)
        await self.bot.db.audit(gid, actor_id=interaction.user.id, target_user_id=target_id, action="admin_user_safeword_cleared", meta=json.dumps({"reason": (reason or "")[:500]}), ts=now_ts())
        try:
            await user.send(f"Your safeword/pause was cleared in **{interaction.guild.name}**.\nReason: {reason or '—'}")
        except discord.Forbidden:
            pass
        await interaction.followup.send(f"✅ Safeword cleared for {user.mention}.\nReason: {reason or '—'}", ephemeral=True)

    @app_commands.command(name="user_status", description="(Mod) View Isla status for a user (opt-out + safeword + core stats).")
    @app_commands.describe(user="User to check")
    async def user_status(self, interaction: discord.Interaction, user: discord.Member):
        if not interaction.guild or not self._is_mod(interaction):
            embed = create_embed("Mods only.", color="info", is_dm=False, is_system=False)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        gid, uid = interaction.guild.id, user.id
        opted_out = await self.bot.db.is_opted_out(gid, uid)
        row = await self.bot.db.fetchone("SELECT coins,debt,stage,safeword_until_ts,last_msg_ts FROM users WHERE guild_id=? AND user_id=?", (gid, uid))
        if not row:
            await interaction.followup.send(f"{user.mention}\nOpt-out: **{'YES' if opted_out else 'NO'}**\nNo Isla user row yet.", ephemeral=True)
            return
        sw = row["safeword_until_ts"]
        sw_txt = "—"
        if sw and int(sw) > now_ts():
            sw_txt = f"ACTIVE until <t:{int(sw)}:R>"
        await interaction.followup.send(
            f"**Isla status for {user.mention}**\n- Opted out: **{'YES' if opted_out else 'NO'}**\n- Safeword: **{sw_txt}**\n- Coins: **{int(row['coins'])}** | Debt: **{int(row['debt'])}** | Stage: **{int(row['stage'])}**\n- Last msg: {'<t:' + str(int(row['last_msg_ts'])) + ':R>' if row['last_msg_ts'] else '—'}",
            ephemeral=True,
        )
    
    # ========================================================================
    # ADMIN TOOLS: AUDIT LOGS (from admin_tools.py)
    # ========================================================================
    
    @app_commands.command(name="audit", description="(Mod) View audit logs with filters.")
    @app_commands.describe(user="Filter by target user", actor="Filter by actor (who performed the action)", action="Filter by action type", days="Number of days to look back (default: 7)", limit="Maximum results (1-100, default: 50)")
    async def audit_view(self, interaction: discord.Interaction, user: discord.Member | None = None, actor: discord.Member | None = None, action: str | None = None, days: app_commands.Range[int, 1, 90] = 7, limit: app_commands.Range[int, 1, 100] = 50):
        if not interaction.guild or not self._is_mod(interaction):
            embed = create_embed("Mods only.", color="info", is_dm=False, is_system=False)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        from utils.audit import AuditService
        audit_service = AuditService(self.bot.db)
        since_ts = now_ts() - (days * 86400)
        logs = await audit_service.get_audit_logs(guild_id=interaction.guild.id, actor_id=actor.id if actor else None, target_user_id=user.id if user else None, action=action, since_ts=since_ts, limit=limit)
        if not logs:
            await interaction.followup.send("No audit logs found.", ephemeral=True)
            return
        lines = []
        for log in logs[:20]:
            actor_mention = f"<@{log['actor_id']}>" if log['actor_id'] else "System"
            target_mention = f"<@{log['target_user_id']}>" if log['target_user_id'] else "—"
            timestamp = f"<t:{log['created_ts']}:R>"
            lines.append(f"**{log['action']}** | {actor_mention} → {target_mention} | {timestamp}")
        msg = "\n".join(lines)
        if len(logs) > 20:
            msg += f"\n\n... and {len(logs) - 20} more (use export for full list)"
        await interaction.followup.send(msg[:1900], ephemeral=True)
    
    @app_commands.command(name="audit_export", description="(Mod) Export audit logs to CSV or JSON.")
    @app_commands.describe(format="Export format", days="Number of days to export (default: 30)")
    @app_commands.choices(format=[app_commands.Choice(name="CSV", value="csv"), app_commands.Choice(name="JSON", value="json")])
    async def audit_export(self, interaction: discord.Interaction, format: app_commands.Choice[str], days: app_commands.Range[int, 1, 90] = 30):
        if not interaction.guild or not self._is_mod(interaction):
            embed = create_embed("Mods only.", color="info", is_dm=False, is_system=False)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        from utils.audit import AuditService
        audit_service = AuditService(self.bot.db)
        since_ts = now_ts() - (days * 86400)
        if format.value == "csv":
            content = await audit_service.export_to_csv(guild_id=interaction.guild.id, since_ts=since_ts)
            filename = f"audit_log_{interaction.guild.id}_{now_ts()}.csv"
        else:
            content = await audit_service.export_to_json(guild_id=interaction.guild.id, since_ts=since_ts)
            filename = f"audit_log_{interaction.guild.id}_{now_ts()}.json"
        file = discord.File(io.BytesIO(content.encode('utf-8')), filename=filename)
        await interaction.followup.send(f"Audit log export ({days} days, {format.value.upper()}):", file=file, ephemeral=True)
    
    @app_commands.command(name="audit_stats", description="(Mod) View audit log statistics.")
    @app_commands.describe(days="Number of days to analyze (default: 30)")
    async def audit_stats(self, interaction: discord.Interaction, days: app_commands.Range[int, 1, 90] = 30):
        if not interaction.guild or not self._is_mod(interaction):
            embed = create_embed("Mods only.", color="info", is_dm=False, is_system=False)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        from utils.audit import AuditService
        audit_service = AuditService(self.bot.db)
        since_ts = now_ts() - (days * 86400)
        stats = await audit_service.get_statistics(guild_id=interaction.guild.id, since_ts=since_ts)
        lines = [f"**Audit Statistics (last {days} days)**", f"Total actions: **{stats['total']}**", "", "**Action Breakdown:**"]
        for action, count in list(stats['action_breakdown'].items())[:10]:
            lines.append(f"- {action}: {count}")
        lines.append("")
        lines.append("**Top Actors:**")
        for actor_id, count in list(stats['top_actors'].items())[:10]:
            lines.append(f"- <@{actor_id}>: {count}")
        await interaction.followup.send("\n".join(lines)[:1900], ephemeral=True)


async def setup(bot: commands.Bot):
    bot.tree.remove_command("config", guild=None)
    bot.tree.remove_command("discipline", guild=None)
    cog = Admin(bot)
    try:
        await bot.add_cog(cog)
    except Exception as e:
        if "CommandAlreadyRegistered" in str(e):
            bot.tree.remove_command("config", guild=None)
            bot.tree.remove_command("discipline", guild=None)
            await bot.add_cog(cog)
        else:
            raise
    try:
        bot.tree.add_command(cog.config, override=True)
        bot.tree.add_command(cog.discipline, override=True)
    except Exception:
        pass

