from __future__ import annotations
import secrets
import discord
from discord.ext import commands, tasks
from discord import app_commands

from core.utils import now_local
from core.isla_text import sanitize_isla_text
from utils.helpers import now_ts, format_time_left, isla_embed as helper_isla_embed, ensure_user_row

REMINDER_AFTER_SECONDS = 48 * 3600  # 48 hours
REMINDER_COOLDOWN_SECONDS = 24 * 3600  # 24 hours (don't nag more than once/day)

VACATION_MIN_DAYS = 3
VACATION_MAX_DAYS = 21
VACATION_COOLDOWN_SECONDS = 24 * 3600  # 24 hours static cooldown
TAX_LOCK_HOURS = 24

STYLE1_DEFAULT = "https://i.imgur.com/5nsuuCV.png"

# -------- Embed constants --------
WELCOME_UNVERIFIED = {
    "title": "Welcome to Isla",
    "description": (
        "Hey.\n"
        "You found me.\n\n"
        "Before you get too comfortable, a couple of quick things.\n\n"
        "I'll wait.\n"
        "᲼᲼"
    ),
    "fields": [
        ("Step 1 — Read the Rules",
         "Go read #rules.\nWhen you're done, click **Accept Rules**."),
        ("Step 2 — Get Roles",
         "After verification, select your roles from #roles.\nLets you customize your experience."),
        ("Step 3 — Start Exploring",
         "Then the rest opens up:\nChats, quests, orders, casino… everything.")
    ],
    "footer": "You can always use /start later if you forget."
}

AFTER_RULES_EPHEMERAL = "Good.\nYou're in now."

AFTER_RULES_DM = {
    "title": "You're In",
    "description": (
        "Mmm.\n"
        "Nice work.\n\n"
        "Here's what I'd do first — it makes everything else feel better.\n"
        "᲼᲼"
    ),
    "fields": [
        ("Roles",
         "Choose your roles in #roles.\nIt changes how I speak to you."),
        ("Introduce Yourself",
         "Drop something in #introductions.\nThat's how I really start noticing you."),
        ("Your First Commands",
         "/profile — see what I think of you\n"
         "/daily — free coins\n"
         "/quests — things worth doing\n"
         "/order_personal — your first real task")
    ],
    "footer": "No rush. I'll be watching."
}

START_UNVERIFIED = {
    "title": "Almost There",
    "description": (
        "Hey.\n\n"
        "One last step before I let you in fully.\n"
        "᲼᲼"
    ),
    "fields": [
        ("What To Do",
         "1) Read #rules\n2) Press **Accept Rules**"),
        ("After That",
         "Everything opens — chats, quests, orders, casino.")
    ],
    "footer": "Run /start again anytime if you get lost."
}

START_VERIFIED = {
    "title": "You're Ready",
    "description": (
        "Good.\n\n"
        "Here's the simplest way to start earning my attention.\n"
        "᲼᲼"
    ),
    "fields": [
        ("Basic Commands",
         "/profile — your server profile\n"
         "/daily — claim free coins daily\n"
         "/quests — tasks to complete\n"
         "/order_personal — a task just for you"),
        ("Channels",
         "#orders — my announcements\n"
         "#spotlight — who's impressing me\n"
         "#casino — where you risk it all"),
        ("Stop IslaBot Interactions",
         "/opt-out — Stops IslaBot activity interactions\n"
         "/safeword — Changes IslaBot's tone to be neutral\n"
         "/vacation — Pauses IslaBot interactions such as Tax & task failures for a minimum of 3 days.")
    ],
    "footer": "Take your time. I'm not going anywhere."
}

REMINDER_48H_DM = {
    "title": "Gentle Reminder",
    "description": (
        "Hey.\n\n"
        "You still haven't accepted the rules, so parts of me are locked to you.\n\n"
        "If you want everything, go back to #rules and press **Accept Rules**.\n"
        "᲼᲼"
    ),
    "footer": "No pressure. Just thought you should know."
}

def isla_embed(desc: str, thumb: str = "", title: str | None = None) -> discord.Embed:
    return helper_isla_embed(desc, title=title, thumb=thumb)



class PronounSelect(discord.ui.Select):
    def __init__(self, role_map: dict[str, int]):
        options = [
            discord.SelectOption(label="puppy he/him", value="puppy"),
            discord.SelectOption(label="kitten she/her", value="kitten"),
            discord.SelectOption(label="pet they/them", value="pet"),
            discord.SelectOption(label="none", value="none"),
        ]
        super().__init__(placeholder="Pick your pronouns…", min_values=1, max_values=1, options=options)
        self.role_map = role_map

    async def callback(self, interaction: discord.Interaction):
        guild = interaction.guild
        if not guild:
            return await interaction.response.send_message("Server only.", ephemeral=True)

        choice = self.values[0]
        member = interaction.user if isinstance(interaction.user, discord.Member) else guild.get_member(interaction.user.id)
        if not member:
            return await interaction.response.send_message("Member not found.", ephemeral=True)

        # remove all pronoun roles first
        to_remove = []
        for k, rid in self.role_map.items():
            if rid:
                role = guild.get_role(rid)
                if role and role in member.roles:
                    to_remove.append(role)
        if to_remove:
            try:
                await member.remove_roles(*to_remove, reason="Pronoun role switch")
            except discord.Forbidden:
                pass

        if choice != "none":
            rid = self.role_map.get(choice)
            if rid:
                role = guild.get_role(rid)
                if role:
                    try:
                        await member.add_roles(role, reason="Pronoun role set")
                    except discord.Forbidden:
                        pass

        await interaction.response.send_message("Noted.", ephemeral=True)


class OnboardingView(discord.ui.View):
    def __init__(self, cog: "Onboarding"):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="Accept Rules", style=discord.ButtonStyle.success, custom_id="isla_accept_rules")
    async def accept_rules(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.handle_accept_rules(interaction)

    @discord.ui.button(label="How to Start", style=discord.ButtonStyle.primary, custom_id="isla_how_to_start")
    async def how_to_start(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.handle_how_to_start(interaction)

    @discord.ui.button(label="Set Pronouns", style=discord.ButtonStyle.secondary, custom_id="isla_set_pronouns")
    async def set_pronouns(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.handle_set_pronouns(interaction)


class Onboarding(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

        # configure in your config
        self.welcome_channel_id = int(bot.cfg.get("channels", "welcome", default=0) or 0)
        self.rules_channel_id = int(bot.cfg.get("channels", "rules", default=0) or 0)
        self.intro_channel_id = int(bot.cfg.get("channels", "introductions", default=0) or 0)
        self.spam_channel_id = int(bot.cfg.get("channels", "spam", default=0) or 0)

        self.role_unverified_id = int(bot.cfg.get("roles", "unverified", default=0) or 0)
        self.role_verified_id = int(bot.cfg.get("roles", "verified", default=0) or 0)

        # pronoun roles
        self.pronoun_roles = {
            "puppy": int(bot.cfg.get("roles", "puppy_role", default=0) or 0),
            "kitten": int(bot.cfg.get("roles", "kitten_role", default=0) or 0),
            "pet": int(bot.cfg.get("roles", "pet_role", default=0) or 0),
        }

        self.view = OnboardingView(self)
        bot.add_view(self.view)  # persistent buttons (for reminder fallback)
        self.unverified_reminder_loop.start()
        
        # Staff controls
        self.staff = StaffControls(self)
        # Remove command if it exists, then add it
        bot.tree.remove_command("staff")
        bot.tree.add_command(self.staff)

    def cog_unload(self):
        self.unverified_reminder_loop.cancel()

    # -------- helpers --------
    def _ch(self, guild: discord.Guild, cid: int) -> discord.TextChannel | None:
        ch = guild.get_channel(cid) if cid else None
        return ch if isinstance(ch, discord.TextChannel) else None

    async def _give_starter_coins(self, guild_id: int, user_id: int, amount: int = 250):
        """Give starter coins to a new user."""
        # Use economy cog's method if available, otherwise direct DB
        economy = self.bot.get_cog("Economy")
        if economy and hasattr(economy, "_add_coins"):
            await economy._add_coins(guild_id, user_id, amount, "onboarding_starter")
        else:
            # Fallback: direct DB access
            await self.bot.db.execute(
                """
                INSERT INTO users(guild_id,user_id,coins,obedience,lce,last_active_ts)
                VALUES(?,?,?,0,0,?)
                ON CONFLICT(guild_id,user_id)
                DO UPDATE SET coins=coins+excluded.coins
                """,
                (guild_id, user_id, amount, now_ts())
            )


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

    # -------- events --------
    @commands.Cog.listener("on_member_join")
    async def on_member_join(self, member: discord.Member):
        if member.bot:
            return
            
        guild = member.guild
        welcome = self._ch(guild, self.welcome_channel_id)
        if not welcome:
            return

        # add unverified role if configured
        unv = guild.get_role(self.role_unverified_id) if self.role_unverified_id else None
        if unv:
            try:
                await member.add_roles(unv, reason="New join unverified")
            except discord.Forbidden:
                pass

        # Track onboarding state
        await self.bot.db.execute(
            """
            INSERT INTO onboarding_state(guild_id,user_id,joined_ts,verified_ts,last_reminder_ts)
            VALUES(?,?,?,?,0)
            ON CONFLICT(guild_id,user_id)
            DO UPDATE SET joined_ts=excluded.joined_ts, verified_ts=0, last_reminder_ts=0
            """,
            (guild.id, member.id, now_ts(), 0)
        )

        # Welcome message (no buttons/view)
        ping = f"||{member.mention}||"
        rules_mention = f"<#{self.rules_channel_id}>" if self.rules_channel_id else "#rules"
        e = isla_embed(WELCOME_UNVERIFIED["description"], title=WELCOME_UNVERIFIED["title"])
        # Replace #rules placeholder with actual mention
        fields = []
        for n, v in WELCOME_UNVERIFIED["fields"]:
            # Replace #rules with actual channel mention in field values
            v_processed = v.replace("#rules", rules_mention) if self.rules_channel_id else v
            fields.append((n, v_processed))
        for n, v in fields:
            e.add_field(name=n, value=v, inline=False)
        e.set_footer(text=WELCOME_UNVERIFIED["footer"])
        await welcome.send(content=ping, embed=e)

    # -------- button handlers --------
    async def handle_accept_rules(self, interaction: discord.Interaction):
        guild = interaction.guild
        if not guild:
            return await interaction.response.send_message("Server only.", ephemeral=True)

        member = interaction.user if isinstance(interaction.user, discord.Member) else guild.get_member(interaction.user.id)
        if not member:
            return await interaction.response.send_message("Member not found.", ephemeral=True)

        verified = guild.get_role(self.role_verified_id) if self.role_verified_id else None
        unv = guild.get_role(self.role_unverified_id) if self.role_unverified_id else None

        if verified and verified not in member.roles:
            try:
                await member.add_roles(verified, reason="Accepted rules")
            except discord.Forbidden:
                pass
        if unv and unv in member.roles:
            try:
                await member.remove_roles(unv, reason="Accepted rules")
            except discord.Forbidden:
                pass

        # Update onboarding state
        await self.bot.db.execute(
            "UPDATE onboarding_state SET verified_ts=?, last_reminder_ts=0 WHERE guild_id=? AND user_id=?",
            (now_ts(), guild.id, member.id)
        )

        # Give starter coins
        await self._give_starter_coins(guild.id, member.id, 250)

        # Public confirmation (ephemeral)
        await interaction.response.send_message(AFTER_RULES_EPHEMERAL, ephemeral=True)

        # DM starter guide (best effort)
        try:
            roles_mention = "#roles"  # You can add config for this if needed
            intro_mention = f"<#{self.intro_channel_id}>" if self.intro_channel_id else "#introductions"
            e = isla_embed(AFTER_RULES_DM["description"], title=AFTER_RULES_DM["title"])
            # Replace placeholders in fields
            for n, v in AFTER_RULES_DM["fields"]:
                v_processed = v.replace("#roles", roles_mention).replace("#introductions", intro_mention)
                e.add_field(name=n, value=v_processed, inline=False)
            e.set_footer(text=AFTER_RULES_DM["footer"])
            await member.send(embed=e)
        except discord.Forbidden:
            pass

    async def handle_how_to_start(self, interaction: discord.Interaction):
        guild = interaction.guild
        if not guild:
            return await interaction.response.send_message("Server only.", ephemeral=True)
        intro_ch_mention = f"<#{self.intro_channel_id}>" if self.intro_channel_id else "#introductions"
        spam_ch_mention = f"<#{self.spam_channel_id}>" if self.spam_channel_id else "#spam"
        desc = (
            "Start.\n\n"
            f"1) Accept rules.\n"
            f"2) Introduce yourself in {intro_ch_mention}.\n"
            f"3) Use commands in {spam_ch_mention}.\n\n"
            "Try:\n"
            "• `/profile`\n"
            "• `/daily`\n"
            "• `/quests`\n"
            "• `/order_personal`\n"
            "• `/casino`\n"
            "᲼᲼"
        )
        await interaction.response.send_message(embed=isla_embed(desc), ephemeral=True)

    async def handle_set_pronouns(self, interaction: discord.Interaction):
        view = discord.ui.View(timeout=60)
        view.add_item(PronounSelect(self.pronoun_roles))
        await interaction.response.send_message("Pick one.", view=view, ephemeral=True)

    # -------- slash commands --------
    @app_commands.command(name="start", description="Get started with Isla.")
    async def start(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        if not guild:
            return await interaction.followup.send("Server only.", ephemeral=True)

        verified_role = guild.get_role(self.role_verified_id) if self.role_verified_id else None
        member = interaction.user if isinstance(interaction.user, discord.Member) else guild.get_member(interaction.user.id)
        is_verified = bool(member and verified_role and verified_role in member.roles)

        if not is_verified:
            rules_mention = f"<#{self.rules_channel_id}>" if self.rules_channel_id else "#rules"
            e = isla_embed(START_UNVERIFIED["description"], title=START_UNVERIFIED["title"])
            for n, v in START_UNVERIFIED["fields"]:
                v_processed = v.replace("#rules", rules_mention)
                e.add_field(name=n, value=v_processed, inline=False)
            e.set_footer(text=START_UNVERIFIED["footer"])
            return await interaction.followup.send(embed=e, ephemeral=True)

        orders_id = int(self.bot.cfg.get("channels", "orders", default=0) or 0)
        spotlight_id = int(self.bot.cfg.get("channels", "spotlight", default=0) or 0)
        casino_id = int(self.bot.cfg.get("channels", "casino", default=0) or 0)
        orders_mention = f"<#{orders_id}>" if orders_id else "#orders"
        spotlight_mention = f"<#{spotlight_id}>" if spotlight_id else "#spotlight"
        casino_mention = f"<#{casino_id}>" if casino_id else "#casino"
        e = isla_embed(START_VERIFIED["description"], title=START_VERIFIED["title"])
        for n, v in START_VERIFIED["fields"]:
            v_processed = v.replace("#orders", orders_mention).replace("#spotlight", spotlight_mention).replace("#casino", casino_mention)
            e.add_field(name=n, value=v_processed, inline=False)
        e.set_footer(text=START_VERIFIED["footer"])
        await interaction.followup.send(embed=e, ephemeral=True)

    @app_commands.command(name="opt-out", description="Stop IslaBot interactions and reset your progress.")
    async def opt_out(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild_id
        if not gid:
            return await interaction.followup.send("Server only.", ephemeral=True)

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
            return await interaction.followup.send("Server only.", ephemeral=True)

        row = await self.bot.db.fetchone(
            "SELECT token, expires_ts FROM optout_confirm WHERE guild_id=? AND user_id=?",
            (gid, interaction.user.id)
        )
        if not row:
            return await interaction.followup.send("No active opt-out request. Use /opt-out first.", ephemeral=True)

        if now_ts() > int(row["expires_ts"]):
            return await interaction.followup.send("That token expired. Use /opt-out again.", ephemeral=True)

        if token.strip().upper() != str(row["token"]).upper():
            return await interaction.followup.send("Wrong token.", ephemeral=True)

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
            return await interaction.followup.send("Server only.", ephemeral=True)

        await ensure_user_row(self.bot.db, gid, interaction.user.id)
        await self.bot.db.execute(
            "UPDATE users SET opted_out=0 WHERE guild_id=? AND user_id=?",
            (gid, interaction.user.id)
        )
        e = isla_embed("Good.\nYou're back in.\nUse `/start` if you need the basics.\n᲼᲼", title="Opted In")
        await interaction.followup.send(embed=e, ephemeral=True)

    @app_commands.command(name="vacation", description="Pause IslaBot penalties for a while (min 3 days).")
    @app_commands.describe(days="Vacation duration (3–21 days)")
    async def vacation(self, interaction: discord.Interaction, days: int):
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild_id
        if not gid:
            return await interaction.followup.send("Server only.", ephemeral=True)

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
            return await interaction.followup.send("Server only.", ephemeral=True)

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

        # End vacation and start 24h cooldown (reset welcomed_ts so they don't get welcome back message)
        await self.bot.db.execute(
            """
            UPDATE users
            SET vacation_until_ts=0,
                vacation_last_used_ts=?,
                vacation_welcomed_ts=0
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

    # -------- reminder system --------
    @tasks.loop(minutes=30)
    async def unverified_reminder_loop(self):
        await self.bot.wait_until_ready()
        now = now_ts()

        for guild in self.bot.guilds:
            gid = guild.id
            welcome = self._ch(guild, self.welcome_channel_id)

            # Find unverified users who joined >=48h ago and haven't been reminded in 24h
            rows = await self.bot.db.fetchall(
                """
                SELECT user_id, joined_ts, verified_ts, last_reminder_ts
                FROM onboarding_state
                WHERE guild_id=? AND verified_ts=0
                """,
                (gid,)
            )

            if not rows:
                continue

            for r in rows:
                uid = int(r["user_id"])
                joined_ts = int(r["joined_ts"])
                last_rem = int(r["last_reminder_ts"] or 0)

                if now - joined_ts < REMINDER_AFTER_SECONDS:
                    continue
                if last_rem and (now - last_rem) < REMINDER_COOLDOWN_SECONDS:
                    continue

                member = guild.get_member(uid)
                if not member:
                    # user left; clean row
                    await self.bot.db.execute("DELETE FROM onboarding_state WHERE guild_id=? AND user_id=?", (gid, uid))
                    continue

                # If they somehow got verified role but verified_ts not set, fix it
                verified_role = guild.get_role(self.role_verified_id) if self.role_verified_id else None
                if verified_role and verified_role in member.roles:
                    await self.bot.db.execute(
                        "UPDATE onboarding_state SET verified_ts=? WHERE guild_id=? AND user_id=?",
                        (now, gid, uid)
                    )
                    continue

                # Compose reminder (updated text)
                rules_mention = f"<#{self.rules_channel_id}>" if self.rules_channel_id else "#rules"
                desc = REMINDER_48H_DM["description"].replace("#rules", rules_mention)
                e = isla_embed(desc, title=REMINDER_48H_DM["title"])
                e.set_footer(text=REMINDER_48H_DM["footer"])

                # Try DM first
                sent = False
                try:
                    await member.send(embed=e)
                    sent = True
                except discord.Forbidden:
                    sent = False

                # Fallback: #welcome ping (spoiler mention to avoid visual spam)
                if not sent and welcome:
                    ping = f"||<@{uid}>||"
                    await welcome.send(content=ping, embed=e, view=self.view)

                await self.bot.db.execute(
                    "UPDATE onboarding_state SET last_reminder_ts=? WHERE guild_id=? AND user_id=?",
                    (now, gid, uid)
                )

    @unverified_reminder_loop.before_loop
    async def before_reminder_loop(self):
        await self.bot.wait_until_ready()

    # -------- cleanup --------
    @commands.Cog.listener("on_member_remove")
    async def on_member_remove(self, member: discord.Member):
        """Clean up onboarding state when a user leaves."""
        await self.bot.db.execute("DELETE FROM onboarding_state WHERE guild_id=? AND user_id=?", (member.guild.id, member.id))


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
            return await interaction.response.send_message("No.", ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild_id
        days = max(1, min(days, 30))
        until = now_ts() + days * 86400

        await self.cog.bot.db.execute(
            """
            INSERT INTO users(guild_id,user_id,coins,obedience,opted_out,safeword_on,vacation_until_ts,vacation_last_used_ts,vacation_welcomed_ts)
            VALUES(?,?,0,0,0,0,?,0,0)
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
            return await interaction.response.send_message("No.", ephemeral=True)

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
            return await interaction.response.send_message("No.", ephemeral=True)

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
            return await interaction.response.send_message("No.", ephemeral=True)

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
            return await interaction.response.send_message("No.", ephemeral=True)

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
