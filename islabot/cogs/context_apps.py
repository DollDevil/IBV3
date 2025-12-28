from __future__ import annotations
import discord
from discord.ext import commands
from discord import app_commands

from utils.isla_style import isla_embed, fmt
from utils.guild_config import cfg_get
from utils.economy import ensure_wallet, get_wallet, add_coins
from utils.uk_parse import now_ts
from utils.embed_utils import create_embed

# -------------------------
# Helpers
# -------------------------

def is_mod(member: discord.Member) -> bool:
    p = member.guild_permissions
    return p.manage_messages or p.moderate_members or p.administrator

async def has_consent(bot, guild_id: int, member: discord.Member) -> bool:
    """
    Consent role check (config: roles.consent)
    """
    role_id = await cfg_get(bot.db, guild_id, "roles.consent", "")
    if not role_id:
        return False
    try:
        rid = int(role_id)
    except ValueError:
        return False
    return any(r.id == rid for r in member.roles)

async def log_action(bot, guild: discord.Guild, title: str, desc: str):
    logs_id = await cfg_get(bot.db, guild.id, "channels.logs", "")
    if not logs_id:
        return
    try:
        ch = guild.get_channel(int(logs_id))
    except Exception:
        return
    if isinstance(ch, discord.TextChannel):
        await ch.send(embed=isla_embed(desc + "\n᲼᲼", title=title))

# -------------------------
# Modals
# -------------------------

class AddNoteModal(discord.ui.Modal, title="Add Staff Note"):
    note = discord.ui.TextInput(
        label="Note",
        style=discord.TextStyle.long,
        max_length=1000
    )

    def __init__(self, bot: commands.Bot, target: discord.Member):
        super().__init__()
        self.bot = bot
        self.target = target

    async def on_submit(self, interaction: discord.Interaction):
        await self.bot.db.execute(
            """
            INSERT INTO user_notes(guild_id,user_id,note,added_by,ts)
            VALUES(?,?,?,?,?)
            """,
            (interaction.guild_id, self.target.id, self.note.value, interaction.user.id, now_ts())
        )

        await log_action(
            self.bot,
            interaction.guild,
            "Staff Note Added",
            f"User: {self.target.mention}\nBy: {interaction.user.mention}\n\n{self.note.value}"
        )

        await interaction.response.send_message(
            embed=isla_embed("Saved.\n᲼᲼", title="Note"),
            ephemeral=True
        )

class CoinTipModal(discord.ui.Modal, title="Coin Tip"):
    amount = discord.ui.TextInput(label="Amount", max_length=10)
    reason = discord.ui.TextInput(label="Reason (optional)", required=False, max_length=200)

    def __init__(self, bot: commands.Bot, target: discord.Member):
        super().__init__()
        self.bot = bot
        self.target = target

    async def on_submit(self, interaction: discord.Interaction):
        try:
            amt = int(self.amount.value)
        except ValueError:
            return await interaction.response.send_message(
                embed=isla_embed("Invalid amount.\n᲼᲼", title="Coin Tip"),
                ephemeral=True
            )

        if amt <= 0:
            return await interaction.response.send_message(
                embed=isla_embed("Amount must be positive.\n᲼᲼", title="Coin Tip"),
                ephemeral=True
            )

        gid = interaction.guild_id
        await ensure_wallet(self.bot.db, gid, interaction.user.id)
        await ensure_wallet(self.bot.db, gid, self.target.id)

        w = await get_wallet(self.bot.db, gid, interaction.user.id)
        if w.coins < amt:
            return await interaction.response.send_message(
                embed=isla_embed("You don't have enough Coins.\n᲼᲼", title="Coin Tip"),
                ephemeral=True
            )

        await add_coins(self.bot.db, gid, interaction.user.id, -amt, kind="tip", reason=self.reason.value, other_user_id=self.target.id)
        await add_coins(self.bot.db, gid, self.target.id, amt, kind="tip", reason=self.reason.value, other_user_id=interaction.user.id)

        await interaction.response.send_message(
            embed=isla_embed(
                f"Tipped **{fmt(amt)} Coins** to {self.target.mention}.\n᲼᲼",
                title="Coin Tip"
            ),
            ephemeral=True
        )

# -------------------------
# Context Menu Cog
# -------------------------

class ContextApps(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # -------------------------
    # Praise (mods only)
    # -------------------------
    async def praise(self, interaction: discord.Interaction, member: discord.Member):
        if not interaction.guild or not isinstance(interaction.user, discord.Member) or not is_mod(interaction.user):
            return await interaction.response.send_message(
                embed=isla_embed("Not for you.\n᲼᲼", title="Praise"),
                ephemeral=True
            )

        lines = [
            "Good work.",
            "I noticed your consistency.",
            "You handled that well.",
            "Reliable.",
            "Keep that up."
        ]

        msg = (
            f"{member.mention}\n\n"
            f"{lines[hash(member.id) % len(lines)]}\n"
            "᲼᲼"
        )

        await interaction.response.send_message(
            embed=isla_embed(msg, title="Praise"),
            ephemeral=False
        )

        await log_action(
            self.bot,
            interaction.guild,
            "Praise",
            f"Target: {member.mention}\nBy: {interaction.user.mention}"
        )

    # -------------------------
    # Humiliate (mods only, consent required)
    # -------------------------
    async def humiliate(self, interaction: discord.Interaction, member: discord.Member):
        if not interaction.guild or not isinstance(interaction.user, discord.Member) or not is_mod(interaction.user):
            return await interaction.response.send_message(
                embed=isla_embed("Not for you.\n᲼᲼", title="Humiliate"),
                ephemeral=True
            )

        if not await has_consent(self.bot, interaction.guild_id, member):
            return await interaction.response.send_message(
                embed=isla_embed(
                    "That user hasn't consented to this.\n᲼᲼",
                    title="Humiliate"
                ),
                ephemeral=True
            )

        lines = [
            "That wasn't your best.",
            "You can do better than that.",
            "Disappointing effort.",
            "Sloppy. Fix it.",
            "Not impressed."
        ]

        msg = (
            f"{member.mention}\n\n"
            f"{lines[hash(interaction.user.id) % len(lines)]}\n"
            "᲼᲼"
        )

        await interaction.response.send_message(
            embed=isla_embed(msg, title="Correction"),
            ephemeral=False
        )

        await log_action(
            self.bot,
            interaction.guild,
            "Humiliate",
            f"Target: {member.mention}\nBy: {interaction.user.mention}"
        )

    # -------------------------
    # Add Note (mods only)
    # -------------------------
    async def add_note(self, interaction: discord.Interaction, member: discord.Member):
        if not interaction.guild or not isinstance(interaction.user, discord.Member) or not is_mod(interaction.user):
            return await interaction.response.send_message(
                embed=isla_embed("Not for you.\n᲼᲼", title="Add Note"),
                ephemeral=True
            )

        await interaction.response.send_modal(AddNoteModal(self.bot, member))

    # -------------------------
    # Coin Tip (any user)
    # -------------------------
    async def coin_tip(self, interaction: discord.Interaction, member: discord.Member):
        if not interaction.guild or member.bot or member.id == interaction.user.id:
            return await interaction.response.send_message(
                embed=isla_embed("No.\n᲼᲼", title="Coin Tip"),
                ephemeral=True
            )

        await interaction.response.send_modal(CoinTipModal(self.bot, member))

async def setup(bot: commands.Bot):
    cog = ContextApps(bot)
    await bot.add_cog(cog)
    
    # Register context menus manually (can't use decorator inside class)
    praise_cmd = app_commands.ContextMenu(name="Praise", callback=cog.praise, type=discord.AppCommandType.user)
    humiliate_cmd = app_commands.ContextMenu(name="Humiliate", callback=cog.humiliate, type=discord.AppCommandType.user)
    add_note_cmd = app_commands.ContextMenu(name="Add Note", callback=cog.add_note, type=discord.AppCommandType.user)
    coin_tip_cmd = app_commands.ContextMenu(name="Coin Tip", callback=cog.coin_tip, type=discord.AppCommandType.user)
    
    try:
        bot.tree.add_command(praise_cmd)
        bot.tree.add_command(humiliate_cmd)
        bot.tree.add_command(add_note_cmd)
        bot.tree.add_command(coin_tip_cmd)
    except Exception:
        pass  # Commands already registered

