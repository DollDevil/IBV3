from __future__ import annotations
import re
import secrets
import discord
from discord.ext import commands
from discord import app_commands

from utils.helpers import now_ts, format_time_left, isla_embed as helper_isla_embed, ensure_user_row
from utils.embed_utils import create_embed
from utils.guild_config import cfg_get, cfg_set

VACATION_MIN_DAYS = 3
VACATION_MAX_DAYS = 21
VACATION_COOLDOWN_SECONDS = 24 * 3600  # 24 hours static cooldown
TAX_LOCK_HOURS = 24

def isla_embed(desc: str, thumb: str = "", title: str | None = None) -> discord.Embed:
    return helper_isla_embed(desc, title=title, thumb=thumb)

# Apology message to check (case and symbol insensitive)
APOLOGY_TEXT = "I apologize Goddess. I was foolish to decline. I fully submit to your rules now."

def normalize_text(text: str) -> str:
    """Normalize text by removing symbols and converting to lowercase for comparison."""
    normalized = re.sub(r'[^a-zA-Z0-9\s]', '', text.lower())
    normalized = ' '.join(normalized.split())
    return normalized

def matches_apology(text: str) -> bool:
    """Check if text matches the apology message (case and symbol insensitive)."""
    return normalize_text(text) == normalize_text(APOLOGY_TEXT)


# -------- Button Views --------
class OnboardingWelcomeView(discord.ui.View):
    def __init__(self, cog: "Onboarding"):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(emoji="<:rules1:1454433030553997454>", label="Rules", style=discord.ButtonStyle.secondary, custom_id="onboarding_welcome_rules")
    async def rules_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.handle_rules_button(interaction)


class OnboardingRulesView(discord.ui.View):
    def __init__(self, cog: "Onboarding"):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(emoji="<:like1:1454433384158728242>", label="Accept", style=discord.ButtonStyle.success, custom_id="onboarding_rules_accept_1")
    async def accept_1(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.handle_rules_accept_1(interaction)

    @discord.ui.button(emoji="<:thumbsdown2:1454433035952062544>", label="Decline", style=discord.ButtonStyle.danger, custom_id="onboarding_rules_decline_1")
    async def decline_1(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.handle_rules_decline_1(interaction)


class OnboardingRulesDeclineView(discord.ui.View):
    def __init__(self, cog: "Onboarding"):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(emoji="<:like1:1454433384158728242>", label="Submit to Isla", style=discord.ButtonStyle.success, custom_id="onboarding_rules_accept_2")
    async def accept_2(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.handle_rules_accept_2(interaction)

    @discord.ui.button(emoji="<:thumbsdown2:1454433035952062544>", label="Decline", style=discord.ButtonStyle.danger, custom_id="onboarding_rules_decline_2")
    async def decline_2(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.handle_rules_decline_2(interaction)


class Onboarding(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        
        # Initialize button views for onboarding
        self.welcome_view = OnboardingWelcomeView(self)
        self.rules_view = OnboardingRulesView(self)
        self.rules_decline_view = OnboardingRulesDeclineView(self)
        
        # Register persistent views
        bot.add_view(self.welcome_view)
        bot.add_view(self.rules_view)
        bot.add_view(self.rules_decline_view)
        
        # Staff controls
        self.staff = StaffControls(self)
        bot.tree.remove_command("staff", guild=None)
        try:
            bot.tree.add_command(self.staff)
        except Exception:
            pass
        
        # Test message group
        self.testmessage_group = app_commands.Group(name="testmessage", description="Test messages")
        self.testmessage_onboarding = TestMessageOnboardingGroup(self)
        self.testmessage_group.add_command(self.testmessage_onboarding)
        bot.tree.remove_command("testmessage", guild=None)
        try:
            bot.tree.add_command(self.testmessage_group)
        except Exception:
            pass

    # -------- Onboarding Helpers --------
    async def get_onboarding_channel(self, guild: discord.Guild) -> discord.TextChannel | None:
        """Get the configured onboarding channel."""
        channel_id_str = await cfg_get(self.bot.db, guild.id, "onboarding.channel", default="")
        if not channel_id_str:
            return None
        try:
            channel_id = int(channel_id_str)
            channel = guild.get_channel(channel_id)
            return channel if isinstance(channel, discord.TextChannel) else None
        except (ValueError, TypeError):
            return None

    async def get_role(self, guild: discord.Guild, role_type: str) -> discord.Role | None:
        """Get a configured onboarding role."""
        role_id_str = await cfg_get(self.bot.db, guild.id, f"onboarding.role_{role_type}", default="")
        if not role_id_str:
            return None
        try:
            role_id = int(role_id_str)
            return guild.get_role(role_id)
        except (ValueError, TypeError):
            return None

    async def has_role(self, member: discord.Member, role_type: str) -> bool:
        """Check if member has a specific onboarding role."""
        role = await self.get_role(member.guild, role_type)
        return role is not None and role in member.roles

    async def has_bad_pup_role(self, member: discord.Member) -> bool:
        """Check if member has Bad Pup role."""
        return await self.has_role(member, "bad_pup")

    async def check_bad_pup_block(self, interaction: discord.Interaction) -> bool:
        """Check if user has Bad Pup role and should be blocked. Returns True if blocked."""
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return False
        if await self.has_bad_pup_role(interaction.user):
            return True
        return False

    # -------- Onboarding Message Functions --------
    async def send_onboarding_welcome(self, channel: discord.TextChannel, member: discord.Member):
        """Send the onboarding welcome message."""
        embed = discord.Embed(
            description=f"**{channel.guild.name}:** *New User Detected*\n> User: {member.mention}\n> Status: Connected\n\n**Instruction:** *Follow the procedure to gain full access.*",
            colour=0x65566c
        )
        embed.set_author(name="𝚂𝚢𝚜𝚝𝚎𝚖 𝙼𝚎𝚜𝚜𝚊𝚐𝚎", icon_url="https://i.imgur.com/irmCXhw.gif")
        embed.set_footer(text="Having issues? Type /support", icon_url="https://i.imgur.com/irmCXhw.gif")
        await channel.send(embed=embed, view=self.welcome_view)

    async def send_onboarding_rules(self, interaction: discord.Interaction, is_button: bool = False):
        """Send the onboarding rules message."""
        embed = discord.Embed(
            description="<a:blacksparklies:1454433776649113682><a:blacksparklies:1454433776649113682><a:blacksparklies:1454433776649113682><a:blacksparklies:1454433776649113682><a:blacksparklies:1454433776649113682><a:blacksparklies:1454433776649113682><a:blacksparklies:1454433776649113682><a:blacksparklies:1454433776649113682>",
            colour=0x65566c
        )
        embed.set_author(name="𝚂𝚢𝚜𝚝𝚎𝚖 𝚁𝚞𝚕𝚎𝚜", icon_url="https://i.imgur.com/irmCXhw.gif")
        embed.add_field(name="1. Respect the Operator.", value="> Harassment, hate speech and disrespect will result in immediate removal.", inline=False)
        embed.add_field(name="2. Stay On-Topic.", value="> Use the correct channels to keep the system clean.", inline=False)
        embed.add_field(name="3. No Spam or Self-Promo.", value="> Do not spam, this includes mass pings and all promo.", inline=False)
        embed.add_field(name="4. No Spoilers.", value="> Do not spoil Isla's programs.", inline=False)
        embed.add_field(name="5. <:dmsoff:1454433182890987602> Do Not DM Isla.", value="> DMs to Isla require a fee in advance.", inline=False)
        embed.add_field(name="", value="<a:blacksparklies:1454433776649113682><a:blacksparklies:1454433776649113682><a:blacksparklies:1454433776649113682><a:blacksparklies:1454433776649113682><a:blacksparklies:1454433776649113682><a:blacksparklies:1454433776649113682><a:blacksparklies:1454433776649113682><a:blacksparklies:1454433776649113682>", inline=False)

        if is_button:
            await interaction.response.send_message(embed=embed, view=self.rules_view, ephemeral=True)
        else:
            ping = f"||{interaction.user.mention}||"
            await interaction.response.send_message(content=ping, embed=embed, view=self.rules_view)

    async def send_onboarding_rules_accept_1(self, interaction: discord.Interaction):
        """Send rules accept message and verify user."""
        guild = interaction.guild
        if not guild or not isinstance(interaction.user, discord.Member):
            return

        member = interaction.user
        verified_role = await self.get_role(guild, "verified")
        unverified_role = await self.get_role(guild, "unverified")
        
        if verified_role and verified_role not in member.roles:
            try:
                await member.add_roles(verified_role, reason="Accepted rules")
            except discord.Forbidden:
                pass
        
        if unverified_role and unverified_role in member.roles:
            try:
                await member.remove_roles(unverified_role, reason="Accepted rules")
            except discord.Forbidden:
                pass

        embed = discord.Embed(
            description=f"Verification complete.\n<a:verifyredv2:1454436023735160923> Access unlocked.\n\nUser experience initialization started.\n<:msg3:1454433017438277652> System message transmitted to {member.mention} via DM.",
            colour=0x080707
        )
        embed.set_author(name="𝚂𝚢𝚜𝚝𝚎𝚖 𝙼𝚎𝚜𝚜𝚊𝚐𝚎", icon_url="https://i.imgur.com/irmCXhw.gif")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def send_onboarding_rules_decline_1(self, interaction: discord.Interaction):
        """Send first decline message."""
        embed = discord.Embed(
            description="You pressed decline... how bold. Turn around and submit properly <a:breakingmyheart:1454436063169745070>",
            colour=0x080707
        )
        embed.set_author(name="𝙴𝚛𝚛𝚘𝚛", icon_url="https://i.imgur.com/QJQjYkE.gif")
        await interaction.response.send_message(embed=embed, view=self.rules_decline_view, ephemeral=True)

    async def send_onboarding_rules_accept_2(self, interaction: discord.Interaction):
        """Send second accept message (after decline)."""
        guild = interaction.guild
        if not guild or not isinstance(interaction.user, discord.Member):
            return

        member = interaction.user
        verified_role = await self.get_role(guild, "verified")
        unverified_role = await self.get_role(guild, "unverified")
        
        if verified_role and verified_role not in member.roles:
            try:
                await member.add_roles(verified_role, reason="Accepted rules after decline")
            except discord.Forbidden:
                pass
        
        if unverified_role and unverified_role in member.roles:
            try:
                await member.remove_roles(unverified_role, reason="Accepted rules after decline")
            except discord.Forbidden:
                pass

        embed = discord.Embed(
            description="You declined... then gave in. I like puppies who learn to submit to their owner.",
            colour=0x080707
        )
        embed.set_author(name="𝙴𝚛𝚛𝚘𝚛", icon_url="https://i.imgur.com/QJQjYkE.gif")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def send_onboarding_rules_decline_2(self, interaction: discord.Interaction):
        """Send second decline message and give Bad Pup role."""
        guild = interaction.guild
        if not guild or not isinstance(interaction.user, discord.Member):
            return

        member = interaction.user
        bad_pup_role = await self.get_role(guild, "bad_pup")
        if bad_pup_role and bad_pup_role not in member.roles:
            try:
                await member.add_roles(bad_pup_role, reason="Declined rules twice")
            except discord.Forbidden:
                pass

        embed = discord.Embed(
            description="You pushed too far this time.\nYour last chance to redeem yourself—type this word for word, and I'll let it slide:\n`I apologize Goddess. I was foolish to decline. I fully submit to your rules now.`\n\nGo on. Type it.",
            colour=0x080707
        )
        embed.set_author(name="𝙴𝚛𝚛𝚘𝚛", icon_url="https://i.imgur.com/QJQjYkE.gif")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def send_onboarding_rules_submission_false(self, channel: discord.TextChannel, member: discord.Member):
        """Send false submission message."""
        embed = discord.Embed(
            description="That wasn't what I asked for. Be precise, pup.\n\nI want every word as I wrote it:\n`I apologize Goddess. I was foolish to decline. I fully submit to your rules now.`",
            colour=0x080707
        )
        embed.set_author(name="𝙴𝚛𝚛𝚘𝚛", icon_url="https://i.imgur.com/QJQjYkE.gif")
        await channel.send(f"{member.mention}", embed=embed)

    async def send_onboarding_rules_submission_correct(self, channel: discord.TextChannel, member: discord.Member):
        """Send correct submission message and verify user."""
        guild = member.guild
        bad_pup_role = await self.get_role(guild, "bad_pup")
        verified_role = await self.get_role(guild, "verified")
        unverified_role = await self.get_role(guild, "unverified")
        
        if bad_pup_role and bad_pup_role in member.roles:
            try:
                await member.remove_roles(bad_pup_role, reason="Apologized correctly")
            except discord.Forbidden:
                pass
        
        if verified_role and verified_role not in member.roles:
            try:
                await member.add_roles(verified_role, reason="Apologized correctly")
            except discord.Forbidden:
                pass
        
        if unverified_role and unverified_role in member.roles:
            try:
                await member.remove_roles(unverified_role, reason="Apologized correctly")
            except discord.Forbidden:
                pass

        embed = discord.Embed(
            description="You actually think that's enough? \nAfter defying me twice?\n\nSend a proper tribute to my [Throne](https://throne.com/lsla). Then maybe I'll soften.",
            colour=0x080707
        )
        embed.set_author(name="𝙴𝚛𝚛𝚘𝚛", icon_url="https://i.imgur.com/QJQjYkE.gif")
        embed.set_footer(text="I'll verify you for now, but this is the final warning.")
        await channel.send(f"{member.mention}", embed=embed)

    # -------- Button Handlers --------
    async def handle_rules_button(self, interaction: discord.Interaction):
        """Handle Rules button press from welcome message."""
        if await self.check_bad_pup_block(interaction):
            return
        await self.send_onboarding_rules(interaction, is_button=True)

    async def handle_rules_accept_1(self, interaction: discord.Interaction):
        """Handle first Accept button."""
        if await self.check_bad_pup_block(interaction):
            return
        await self.send_onboarding_rules_accept_1(interaction)

    async def handle_rules_decline_1(self, interaction: discord.Interaction):
        """Handle first Decline button."""
        if await self.check_bad_pup_block(interaction):
            return
        await self.send_onboarding_rules_decline_1(interaction)

    async def handle_rules_accept_2(self, interaction: discord.Interaction):
        """Handle second Accept button (after decline)."""
        if await self.check_bad_pup_block(interaction):
            return
        await self.send_onboarding_rules_accept_2(interaction)

    async def handle_rules_decline_2(self, interaction: discord.Interaction):
        """Handle second Decline button."""
        if await self.check_bad_pup_block(interaction):
            return
        await self.send_onboarding_rules_decline_2(interaction)

    # -------- Event Listeners --------
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """Handle new member join - give Unverified role and send welcome message."""
        if member.bot:
            return
        
        guild = member.guild
        unverified_role = await self.get_role(guild, "unverified")
        if unverified_role:
            try:
                await member.add_roles(unverified_role, reason="New member")
            except discord.Forbidden:
                pass
        
        channel = await self.get_onboarding_channel(guild)
        if channel:
            try:
                await self.send_onboarding_welcome(channel, member)
            except Exception:
                pass

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Monitor messages for apology from Bad Pup users."""
        if message.author.bot or not message.guild:
            return
        
        member = message.author
        if not isinstance(member, discord.Member):
            return
        
        if not await self.has_bad_pup_role(member):
            return
        
        if matches_apology(message.content):
            await self.send_onboarding_rules_submission_correct(message.channel, member)
        else:
            await self.send_onboarding_rules_submission_false(message.channel, member)

    # -------- Global command check for Bad Pup blocking --------
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Block interactions if user has Bad Pup role."""
        if await self.check_bad_pup_block(interaction):
            try:
                await interaction.response.send_message("You have the Bad Pup role. Complete the apology process first.", ephemeral=True)
            except Exception:
                pass
            return False
        return True

    async def cog_check(self, ctx: commands.Context) -> bool:
        """Block prefix commands if user has Bad Pup role."""
        if isinstance(ctx.author, discord.Member):
            if await self.has_bad_pup_role(ctx.author):
                return False
        return True

    # -------- Slash Commands --------
    @app_commands.command(name="rules", description="View the server rules.")
    async def rules(self, interaction: discord.Interaction):
        """Rules command - same as button but visible to everyone."""
        if await self.check_bad_pup_block(interaction):
            return
        await self.send_onboarding_rules(interaction, is_button=False)

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

class TestMessageOnboardingGroup(app_commands.Group):
    def __init__(self, cog):
        super().__init__(name="onboarding", description="Test onboarding messages")
        self.cog = cog

    @app_commands.command(name="onboarding_welcome", description="Test onboarding welcome message.")
    @app_commands.describe(member="Member to test with (defaults to you)")
    async def test_onboarding_welcome(self, interaction: discord.Interaction, member: discord.Member | None = None):
        if not staff_check(interaction):
            embed = create_embed("No.", color="info", is_dm=False, is_system=False)
            return await interaction.response.send_message(embed=embed, ephemeral=True)
        
        if not interaction.guild:
            embed = create_embed("Server only.", color="warning", is_dm=False, is_system=False)
            return await interaction.response.send_message(embed=embed, ephemeral=True)
        
        await interaction.response.defer(ephemeral=True)
        
        test_member = member if member else (interaction.user if isinstance(interaction.user, discord.Member) else None)
        if not test_member:
            embed = create_embed("Could not get member.", color="info", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)
        
        channel = await self.cog.get_onboarding_channel(interaction.guild)
        if not channel:
            return await interaction.followup.send("Onboarding channel not configured. Use /config onboarding channel.", ephemeral=True)
        
        await self.cog.send_onboarding_welcome(channel, test_member)
        await interaction.followup.send(f"Test welcome message sent in {channel.mention}!", ephemeral=True)

    @app_commands.command(name="onboarding_rules", description="Test onboarding rules message.")
    @app_commands.describe(member="Member to test with (defaults to you)")
    async def test_onboarding_rules(self, interaction: discord.Interaction, member: discord.Member | None = None):
        if not staff_check(interaction):
            embed = create_embed("No.", color="info", is_dm=False, is_system=False)
            return await interaction.response.send_message(embed=embed, ephemeral=True)
        
        if not interaction.guild:
            embed = create_embed("Server only.", color="warning", is_dm=False, is_system=False)
            return await interaction.response.send_message(embed=embed, ephemeral=True)
        
        await interaction.response.defer(ephemeral=True)
        
        test_member = member if member else (interaction.user if isinstance(interaction.user, discord.Member) else None)
        if not test_member:
            embed = create_embed("Could not get member.", color="info", is_dm=False, is_system=False)
            return await interaction.followup.send(embed=embed, ephemeral=True)
        
        channel = await self.cog.get_onboarding_channel(interaction.guild)
        if not channel:
            return await interaction.followup.send("Onboarding channel not configured. Use /config onboarding channel.", ephemeral=True)
        
        embed = discord.Embed(
            description="<a:blacksparklies:1454433776649113682><a:blacksparklies:1454433776649113682><a:blacksparklies:1454433776649113682><a:blacksparklies:1454433776649113682><a:blacksparklies:1454433776649113682><a:blacksparklies:1454433776649113682><a:blacksparklies:1454433776649113682><a:blacksparklies:1454433776649113682>",
            colour=0x65566c
        )
        embed.set_author(name="𝚂𝚢𝚜𝚝𝚎𝚖 𝚁𝚞𝚕𝚎𝚜", icon_url="https://i.imgur.com/irmCXhw.gif")
        embed.add_field(name="1. Respect the Operator.", value="> Harassment, hate speech and disrespect will result in immediate removal.", inline=False)
        embed.add_field(name="2. Stay On-Topic.", value="> Use the correct channels to keep the system clean.", inline=False)
        embed.add_field(name="3. No Spam or Self-Promo.", value="> Do not spam, this includes mass pings and all promo.", inline=False)
        embed.add_field(name="4. No Spoilers.", value="> Do not spoil Isla's programs.", inline=False)
        embed.add_field(name="5. <:dmsoff:1454433182890987602> Do Not DM Isla.", value="> DMs to Isla require a fee in advance.", inline=False)
        embed.add_field(name="", value="<a:blacksparklies:1454433776649113682><a:blacksparklies:1454433776649113682><a:blacksparklies:1454433776649113682><a:blacksparklies:1454433776649113682><a:blacksparklies:1454433776649113682><a:blacksparklies:1454433776649113682><a:blacksparklies:1454433776649113682><a:blacksparklies:1454433776649113682>", inline=False)
        await channel.send(f"{test_member.mention}", embed=embed, view=self.cog.rules_view)
        await interaction.followup.send(f"Test rules message sent in {channel.mention}!", ephemeral=True)


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
