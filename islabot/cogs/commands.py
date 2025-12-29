from __future__ import annotations
import time
import discord
from discord.ext import commands
from discord import app_commands

from core.utility import now_ts, day_key
from utils.embed_utils import create_embed
from utils.info_embed import info_embed
from utils.isla_style import isla_embed, fmt
from utils.guild_config import cfg_get
from utils.economy import ensure_wallet, get_wallet, add_coins

# ============================================================================
# INFO TOPICS (from info_unified.py)
# ============================================================================

INFO_TOPICS: dict[str, dict] = {
    "islabot": {
        "title": "IslaBot",
        "desc": (
            "Hey.\n\n"
            "IslaBot runs the server economy, quests, orders, and casino.\n"
            "It also tracks activity and ranks.\n\n"
            "Core commands:\n"
            "• `/start`\n"
            "• `/profile`\n"
            "• `/daily`\n"
            "• `/quests`\n"
            "• `/order_personal`\n"
            "• `/casino`\n\n"
            "Control commands:\n"
            "• `/safeword` (neutral tone)\n"
            "• `/vacation` (pause penalties)\n"
            "• `/opt-out` (reset + exclude)\n"
            "᲼᲼"
        ),
    },
    "casino": {
        "title": "Casino",
        "desc": (
            "Casino uses Coins.\n\n"
            "Games:\n"
            "• Blackjack\n"
            "• Roulette\n"
            "• Dice\n"
            "• Slots\n\n"
            "Main commands:\n"
            "• `/casino` (overview)\n"
            "• `/casino_stats`\n\n"
            "Game commands:\n"
            "• `/blackjack` • `/roulette` • `/dice` • `/slots`\n\n"
            "Notes:\n"
            "• Big wins can trigger a DM (max once/day)\n"
            "• Jackpots / 10,000+ wins may show in Spotlight\n"
            "᲼᲼"
        ),
    },
    "blackjack": {
        "title": "Blackjack",
        "desc": (
            "Goal: get close to 21 without going over.\n\n"
            "Commands:\n"
            "• `/blackjack <bet>`\n"
            "• `/blackjack_hit`\n"
            "• `/blackjack_stand`\n"
            "• `/blackjack_allin`\n\n"
            "Notes:\n"
            "• Bust = loss\n"
            "• Blackjack pays higher (if enabled)\n"
            "᲼᲼"
        ),
    },
    "roulette": {
        "title": "Roulette",
        "desc": (
            "Bet on outcomes, then spin.\n\n"
            "Commands:\n"
            "• `/roulette <bet> <choice>`\n"
            "• `/roulette_allin <choice>`\n\n"
            "Common choices:\n"
            "• `red` / `black`\n"
            "• `0–36` (if number bets enabled)\n"
            "᲼᲼"
        ),
    },
    "dice": {
        "title": "Dice",
        "desc": (
            "Roll a number and resolve payouts based on thresholds.\n\n"
            "Commands:\n"
            "• `/dice <bet>`\n"
            "• `/dice_allin`\n\n"
            "Notes:\n"
            "• Higher rolls pay more\n"
            "• Low rolls lose the wager\n"
            "᲼᲼"
        ),
    },
    "slots": {
        "title": "Slots",
        "desc": (
            "Spin reels for symbol matches.\n\n"
            "Commands:\n"
            "• `/slots <bet>`\n"
            "• `/slots_allin`\n\n"
            "Notes:\n"
            "• Small wins happen often\n"
            "• Big wins are rarer and may trigger DMs/Spotlight\n"
            "᲼᲼"
        ),
    },
    "orders": {
        "title": "Orders",
        "desc": (
            "Orders are timed tasks with rewards.\n\n"
            "Commands:\n"
            "• `/orders` (board)\n"
            "• `/order_accept <id>`\n"
            "• `/order_progress <id>`\n"
            "• `/order_complete <id>`\n\n"
            "Notes:\n"
            "• Vacation: private orders don't appear\n"
            "• Vacation: public orders don't count\n"
            "᲼᲼"
        ),
    },
    "quests": {
        "title": "Quests",
        "desc": (
            "Quests are structured goals (daily/weekly/elite).\n\n"
            "Commands:\n"
            "• `/quests [tier]`\n"
            "• `/quest_progress <id>`\n"
            "• `/quest_claim <id>`\n"
            "• `/quest_reroll`\n\n"
            "Rewards:\n"
            "• Coins / Obedience / Event Tokens\n"
            "᲼᲼"
        ),
    },
    "vacation": {
        "title": "Vacation",
        "desc": (
            "Vacation pauses penalties.\n\n"
            "Rules:\n"
            "• Min: 3 days\n"
            "• Max: 30 days\n"
            "• Cooldown: 24h after ending (natural or `/vacationstop`)\n\n"
            "Effects:\n"
            "• Tax won't accrue\n"
            "• Failure penalties won't trigger\n"
            "• Private orders/tasks won't appear\n"
            "• Public orders don't count\n\n"
            "Commands:\n"
            "• `/vacation <days>`\n"
            "• `/vacationstop`\n"
            "᲼᲼"
        ),
    },
    "safeword": {
        "title": "Safeword",
        "desc": (
            "Safeword switches Isla's tone to neutral for you.\n\n"
            "You still have access to:\n"
            "• coins, quests, orders, casino, profile\n\n"
            "Neutral means:\n"
            "• no degrading language\n"
            "• no flirt escalation\n"
            "• no targeted callouts\n\n"
            "Commands:\n"
            "• `/safeword` (toggle)\n"
            "• `/safeword_status`\n"
            "᲼᲼"
        ),
    },
    "optout": {
        "title": "Opt-Out",
        "desc": (
            "Opt-out removes you from IslaBot systems.\n\n"
            "What it does:\n"
            "• Stops earning coins/obedience\n"
            "• Removes tracking/leaderboards\n"
            "• Resets your progress\n\n"
            "Commands:\n"
            "• `/opt-out`\n"
            "• `/opt-out_confirm <token>`\n"
            "• `/opt-in`\n"
            "᲼᲼"
        ),
    },
}

TOPIC_CHOICES = [
    app_commands.Choice(name="IslaBot Overview", value="islabot"),
    app_commands.Choice(name="Casino (Overview)", value="casino"),
    app_commands.Choice(name="Casino: Blackjack", value="blackjack"),
    app_commands.Choice(name="Casino: Roulette", value="roulette"),
    app_commands.Choice(name="Casino: Dice", value="dice"),
    app_commands.Choice(name="Casino: Slots", value="slots"),
    app_commands.Choice(name="Orders", value="orders"),
    app_commands.Choice(name="Quests", value="quests"),
    app_commands.Choice(name="Vacation", value="vacation"),
    app_commands.Choice(name="Safeword", value="safeword"),
    app_commands.Choice(name="Opt-Out", value="optout"),
]

# ============================================================================
# PUBLIC COMMAND CATEGORIES (from core_commands.py)
# ============================================================================

PUBLIC_CATEGORIES: dict[str, dict] = {
    "start": {
        "title": "Getting Started",
        "blurb": "New here? Start clean. Opt in only what you want.",
        "items": [
            ("/about", "What Isla is, and how the system works."),
            ("/verify", "Mark yourself verified + consent-ready (server roles permitting)."),
            ("/consent view", "See what you're opted into."),
            ("/consent optin module:<...>", "Opt into modules you want."),
            ("/safeword", "Pause Isla for you instantly."),
        ],
    },
    "economy": {
        "title": "Coins & Economy",
        "blurb": "Coins are access. Attention is earned, not free.",
        "items": [
            ("/balance", "See your Coins and Debt."),
            ("/daily", "Claim your daily Coins."),
            ("/burn amount:<n>", "Burn Coins for symbolic attention."),
        ],
    },
    "orders": {
        "title": "Orders & Obedience",
        "blurb": "Obedience is optional. Opt in first. Earn the tone.",
        "items": [
            ("/orders", "Receive an order (opt-in required)."),
            ("/orders_complete proof:<text>", "Complete your active order."),
            ("/orders_refuse reason:<text>", "Refuse your active order (debt may apply)."),
        ],
    },
    "shop": {
        "title": "Shop & Cosmetics",
        "blurb": "Status is bought. Collars are chosen.",
        "items": [
            ("/shop", "Browse items available right now."),
            ("/buy item_key:<key>", "Buy an item."),
            ("/inventory", "View what you own."),
            ("/equipped", "See what you're currently wearing."),
            ("/equip item_key:<key>", "Equip a collar/role you own."),
            ("/unequip", "Remove your equipped collar/role."),
        ],
    },
    "spotlight": {
        "title": "Spotlight",
        "blurb": "Visible effort. Quiet power. Earn your place.",
        "items": [
            ("/spotlight", "Today's spotlight leaderboard."),
        ],
    },
    "profile": {
        "title": "Profile",
        "blurb": "Your standing—measured, remembered, and (only) what you consent to.",
        "items": [
            ("/profile", "View your profile."),
        ],
    },
    "events": {
        "title": "Seasonal Events",
        "blurb": "Limited windows. Different rules. Better rewards.",
        "items": [
            ("/event", "See the currently active seasonal event."),
        ],
    },
    "privacy": {
        "title": "Privacy",
        "blurb": "You control your participation. Always.",
        "items": [
            ("/resetme", "Reset your Isla stats (coins/consent/orders)."),
            ("/optout", "Hard leave: delete your progress + stop tracking (if enabled on this server)."),
            ("/optin", "Re-join after opting out (if enabled on this server)."),
        ],
    },
    "core": {
        "title": "Core",
        "blurb": "Housekeeping. Clarity. Control.",
        "items": [
            ("/commands", "Show command categories or commands in a category."),
            ("/ping", "Latency + uptime."),
            ("/status", "What's active right now (public-safe)."),
        ],
    },
}

PUBLIC_MODULES = [
    ("economy", "Coins & Economy"),
    ("orders", "Orders"),
    ("shop", "Shop"),
    ("tributes", "Tributes (log)"),
    ("leaderboard", "Spotlight"),
    ("events", "Seasonal Events"),
    ("profile", "Profile"),
]

# ============================================================================
# CONTEXT MENU HELPERS (from context_apps.py)
# ============================================================================

def is_mod(member: discord.Member) -> bool:
    p = member.guild_permissions
    return p.manage_messages or p.moderate_members or p.administrator

async def has_consent(bot, guild_id: int, member: discord.Member) -> bool:
    """Consent role check (config: roles.consent)"""
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

# ============================================================================
# CONTEXT MENU MODALS
# ============================================================================

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
        from utils.uk_parse import now_ts as now_ts_util
        await self.bot.db.execute(
            """
            INSERT INTO user_notes(guild_id,user_id,note,added_by,ts)
            VALUES(?,?,?,?,?)
            """,
            (interaction.guild_id, self.target.id, self.note.value, interaction.user.id, now_ts_util())
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

# ============================================================================
# MAIN COG CLASS
# ============================================================================

class Commands(commands.Cog):
    """Consolidated Commands cog: Core commands, info, context menus, and activity tracking."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ========================================================================
    # ACTIVITY TRACKING (from alive.py)
    # ========================================================================

    @commands.Cog.listener("on_message")
    async def on_message(self, msg: discord.Message):
        if msg.author.bot or not msg.guild:
            return
        gid, uid = msg.guild.id, msg.author.id

        # Hard opt-out means: no tracking
        if await self.bot.db.is_opted_out(gid, uid):
            return

        # Admin-applied safeword means: no tracking
        u = await self.bot.db.fetchone(
            "SELECT safeword_until_ts FROM users WHERE guild_id=? AND user_id=?",
            (gid, uid),
        )
        if u and u["safeword_until_ts"] and int(u["safeword_until_ts"]) > now_ts():
            return

        await self.bot.db.ensure_user(gid, uid)
        await self.bot.db.execute(
            "UPDATE users SET last_msg_ts=? WHERE guild_id=? AND user_id=?",
            (now_ts(), gid, uid),
        )

        dk = day_key()
        await self.bot.db.execute(
            """INSERT INTO user_activity_daily(guild_id,user_id,day_key,messages)
               VALUES(?,?,?,1)
               ON CONFLICT(guild_id,user_id,day_key) DO UPDATE SET messages=messages+1""",
            (gid, uid, dk),
        )

        # Hot-reload personality if file changed
        if hasattr(self.bot, "personality"):
            if self.bot.personality.maybe_reload():
                self.bot.personality.sanitize()

    # ========================================================================
    # CORE COMMANDS (from core_commands.py)
    # ========================================================================

    @app_commands.command(name="commands", description="Show commands by category.")
    @app_commands.describe(category="Category name (optional)")
    async def commands_cmd(self, interaction: discord.Interaction, category: str | None = None):
        await interaction.response.defer(ephemeral=True)

        def _normalize_category(cat: str) -> str:
            return (cat or "").strip().lower().replace(" ", "_")

        # If no category: show categories list
        if not category:
            lines = []
            for k, v in PUBLIC_CATEGORIES.items():
                lines.append(f"**{v['title']}** — `{k}`\n{v['blurb']}")
            e = isla_embed(
                "Command Categories",
                "\n\n".join(lines) + "\n\nUse `/commands category:<name>` to see commands in a category.",
            )
            await interaction.followup.send(embed=e, ephemeral=True)
            return

        cat = _normalize_category(category)
        if cat not in PUBLIC_CATEGORIES:
            await interaction.followup.send(
                "Unknown category. Use `/commands` to see the list.",
                ephemeral=True,
            )
            return

        block = PUBLIC_CATEGORIES[cat]
        items = block["items"]
        lines = [f"**{block['title']}**\n{block['blurb']}\n"]
        for cmd, desc in items:
            lines.append(f"• **{cmd}** — {desc}")

        e = isla_embed(block["title"], "\n".join(lines))
        await interaction.followup.send(embed=e, ephemeral=True)

    @app_commands.command(name="about", description="Learn what Isla is and how the system works.")
    async def about(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        text = (
            "**Isla** is a consent-based, coin-driven roleplay utility.\n\n"
            "**How it works:**\n"
            "• **Coins** are your access key. More Coins unlock warmer tone and more options.\n"
            "• **Obedience** is *optional* and requires opt-in. If you don't opt in, Isla stays neutral.\n"
            "• **Burn** is symbolic—spend Coins to signal attention-seeking.\n"
            "• **Consent controls everything.** You can opt into modules, pause with **/safeword**, or reset.\n\n"
            "If you want the soft version: earn Coins.\n"
            "If you want the stricter version: opt in—and prove consistency."
        )
        e = isla_embed("About Isla", text)
        await interaction.followup.send(embed=e, ephemeral=True)

    @app_commands.command(name="ping", description="Bot latency and uptime.")
    async def ping(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        # Latency is websocket latency in seconds
        latency_ms = int(getattr(self.bot, "latency", 0.0) * 1000)

        # Shard info (safe)
        shard_id = getattr(interaction, "shard_id", None)
        shard_txt = str(shard_id) if shard_id is not None else "—"

        # Uptime
        started_ts = getattr(self.bot, "started_ts", None)
        if started_ts:
            uptime_sec = int(time.time()) - int(started_ts)
            uptime_txt = f"{uptime_sec // 3600}h {(uptime_sec % 3600) // 60}m"
        else:
            uptime_txt = "—"

        e = isla_embed(
            "Ping",
            f"Latency: **{latency_ms}ms**\nShard: **{shard_txt}**\nUptime: **{uptime_txt}**",
        )
        await interaction.followup.send(embed=e, ephemeral=True)

    @app_commands.command(name="status", description="See active modules and event status (public-safe).")
    async def status(self, interaction: discord.Interaction):
        if not interaction.guild:
            embed = create_embed("Guild only.", color="warning", is_dm=False, is_system=False)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild.id
        cid = interaction.channel_id

        # Public module flags (enabled/disabled only)
        module_lines = []
        for feature_key, label in PUBLIC_MODULES:
            enabled = True
            if hasattr(self.bot, "flags"):
                enabled = await self.bot.flags.is_enabled(gid, feature_key, channel_id=cid)
            module_lines.append(f"• {label}: **{'ON' if enabled else 'OFF'}**")

        # "Config mode" (keep it generic & non-sensitive)
        mode = "Standard"
        if hasattr(self.bot, "chan_cfg"):
            v = await self.bot.chan_cfg.get(gid, cid, "mode", default=None)
            if v:
                safe = v.strip().title()
                if safe in ("Standard", "Soft", "Strict", "Event"):
                    mode = safe

        # Active event (safe)
        event_txt = "None"
        if await self._events_enabled(gid, cid):
            event = await self.bot.db.fetchone(
                """SELECT event_id, event_type, name, end_ts 
                   FROM events 
                   WHERE guild_id=? AND is_active=1 
                   ORDER BY start_ts DESC LIMIT 1""",
                (gid,),
            )
            if event and event["event_id"]:
                end_ts = int(event["end_ts"]) if event["end_ts"] else None
                if end_ts:
                    event_txt = f"`{event['name']}` (ends <t:{end_ts}:R>)"
                else:
                    event_txt = f"`{event['name']}`"

        desc = (
            f"Config mode: **{mode}**\n"
            f"Active event: **{event_txt}**\n\n"
            "**Modules (this channel):**\n" + "\n".join(module_lines)
        )

        e = isla_embed("Isla Status", desc)
        await interaction.followup.send(embed=e, ephemeral=True)

    async def _events_enabled(self, gid: int, cid: int) -> bool:
        if hasattr(self.bot, "flags"):
            return await self.bot.flags.is_enabled(gid, "events", channel_id=cid)
        return True

    # ========================================================================
    # INFO COMMAND (from info_unified.py)
    # ========================================================================

    @app_commands.command(name="info", description="Show info about IslaBot features.")
    @app_commands.choices(topic=TOPIC_CHOICES)
    async def info(self, interaction: discord.Interaction, topic: app_commands.Choice[str]):
        key = topic.value
        data = INFO_TOPICS.get(key) or INFO_TOPICS["islabot"]
        e = info_embed(data["title"], data["desc"])
        await interaction.response.send_message(embed=e, ephemeral=True)

    # ========================================================================
    # CONTEXT MENU HANDLERS (from context_apps.py)
    # ========================================================================

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

    async def add_note(self, interaction: discord.Interaction, member: discord.Member):
        if not interaction.guild or not isinstance(interaction.user, discord.Member) or not is_mod(interaction.user):
            return await interaction.response.send_message(
                embed=isla_embed("Not for you.\n᲼᲼", title="Add Note"),
                ephemeral=True
            )

        await interaction.response.send_modal(AddNoteModal(self.bot, member))

    async def coin_tip(self, interaction: discord.Interaction, member: discord.Member):
        if not interaction.guild or member.bot or member.id == interaction.user.id:
            return await interaction.response.send_message(
                embed=isla_embed("No.\n᲼᲼", title="Coin Tip"),
                ephemeral=True
            )

        await interaction.response.send_modal(CoinTipModal(self.bot, member))


async def setup(bot: commands.Bot):
    cog = Commands(bot)
    await bot.add_cog(cog)
    
    # Register context menus manually
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

