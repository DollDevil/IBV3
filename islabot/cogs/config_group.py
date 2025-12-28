from __future__ import annotations
import discord
from discord.ext import commands
from discord import app_commands

from utils.embed_utils import create_embed
from utils.guild_config import cfg_set, cfg_get
from utils.uk_parse import parse_duration_to_seconds

def is_admin(m: discord.Member) -> bool:
    return m.guild_permissions.administrator or m.guild_permissions.manage_guild

# ---------- Modals ----------
class RolesModal(discord.ui.Modal, title="Config: Roles"):
    role_18 = discord.ui.TextInput(label="18+ verified role ID", required=False, max_length=24)
    consent = discord.ui.TextInput(label="Consent role ID", required=False, max_length=24)
    muted = discord.ui.TextInput(label="Muted role ID", required=False, max_length=24)
    punish = discord.ui.TextInput(label="Punishment role ID", required=False, max_length=24)
    ranks = discord.ui.TextInput(label="Ranks roles (comma role IDs)", required=False, max_length=200)

    def __init__(self, bot: commands.Bot):
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        gid = interaction.guild_id
        if not gid:
            embed = create_embed("Server only.", color="warning", is_dm=False, is_system=False)
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        await cfg_set(self.bot.db, gid, "roles.verified18", self.role_18.value.strip())
        await cfg_set(self.bot.db, gid, "roles.consent", self.consent.value.strip())
        await cfg_set(self.bot.db, gid, "roles.muted", self.muted.value.strip())
        await cfg_set(self.bot.db, gid, "roles.punishment", self.punish.value.strip())
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

# ---------- Cog ----------
class ConfigGroup(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config = app_commands.Group(name="config", description="Server setup")
        self.onboarding_config = OnboardingConfigGroup(bot)
        self.config.add_command(self.onboarding_config)
        self._register()

    async def _require_admin(self, interaction: discord.Interaction) -> bool:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            embed = create_embed("Server only.", color="warning", is_dm=False, is_system=False)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return False
        if not is_admin(interaction.user):
            embed = create_embed("Not for you.\n᲼᲼", title="Config", color="error", is_dm=False, is_system=False)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return False
        return True

    @app_commands.command(name="roles", description="Wizard to set role IDs.")
    async def roles(self, interaction: discord.Interaction):
        if not await self._require_admin(interaction):
            return
        await interaction.response.send_modal(RolesModal(self.bot))

    @app_commands.command(name="channels", description="Wizard to set channel IDs.")
    async def channels(self, interaction: discord.Interaction):
        if not await self._require_admin(interaction):
            return
        await interaction.response.send_modal(ChannelsModal(self.bot))

    @app_commands.command(name="economy", description="Wizard to set economy rules.")
    async def economy(self, interaction: discord.Interaction):
        if not await self._require_admin(interaction):
            return
        await interaction.response.send_modal(EconomyModal(self.bot))

    @app_commands.command(name="orders", description="Wizard to set order rules.")
    async def orders(self, interaction: discord.Interaction):
        if not await self._require_admin(interaction):
            return
        await interaction.response.send_modal(OrdersModal(self.bot))

    @app_commands.command(name="moderation", description="Wizard to set moderation rules.")
    async def moderation(self, interaction: discord.Interaction):
        if not await self._require_admin(interaction):
            return
        await interaction.response.send_modal(ModerationModal(self.bot))

    def _register(self):
        self.config.add_command(self.roles)
        self.config.add_command(self.channels)
        self.config.add_command(self.economy)
        self.config.add_command(self.orders)
        self.config.add_command(self.moderation)

async def setup(bot: commands.Bot):
    # Remove command if it exists before creating cog (to avoid conflicts)
    bot.tree.remove_command("config", guild=None)
    cog = ConfigGroup(bot)
    # Add cog - commands will be auto-registered
    try:
        await bot.add_cog(cog)
    except Exception as e:
        # If command already registered, remove it and try again
        if "CommandAlreadyRegistered" in str(e):
            bot.tree.remove_command("config", guild=None)
            await bot.add_cog(cog)
        else:
            raise
    # Ensure command is in tree with override
    try:
        bot.tree.add_command(cog.config, override=True)
    except Exception:
        pass  # Command already registered - ignore

