from __future__ import annotations

import time
import discord
from discord.ext import commands
from discord import app_commands
from utils.embed_utils import create_embed

def isla_embed(title: str, desc: str, color: int = 0x673AB7) -> discord.Embed:
    """Create an Isla embed with title, description, and optional color."""
    e = discord.Embed(title=title, description=desc, color=color)
    e.set_author(name="Isla", icon_url="https://i.imgur.com/5nsuuCV.png")
    return e

# ---------
# PUBLIC command catalog (ONLY show user-facing commands)
# Keep this curated so we never leak admin/private tools in /commands.
# ---------

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
    # "public_callouts" intentionally omitted from user-facing status unless you explicitly want it
]

def _normalize_category(cat: str) -> str:
    return (cat or "").strip().lower().replace(" ", "_")

class CoreCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # -------------------------
    # /commands [category]
    # -------------------------
    @app_commands.command(name="commands", description="Show commands by category.")
    @app_commands.describe(category="Category name (optional)")
    async def commands_cmd(self, interaction: discord.Interaction, category: str | None = None):
        await interaction.response.defer(ephemeral=True)

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

    # -------------------------
    # /about
    # -------------------------
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

    # -------------------------
    # /ping
    # -------------------------
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


    # -------------------------
    # /status (PUBLIC-SAFE)
    # -------------------------
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
        # You can evolve this later (e.g. Strict/Soft) based on a safe channelcfg value.
        mode = "Standard"
        if hasattr(self.bot, "chan_cfg"):
            v = await self.bot.chan_cfg.get(gid, cid, "mode", default=None)
            if v:
                # Only allow a safe display subset (avoid leaking internal config keys)
                safe = v.strip().title()
                if safe in ("Standard", "Soft", "Strict", "Event"):
                    mode = safe

        # Active event (safe)
        event_txt = "None"
        if await self._events_enabled(gid, cid):
            # Check events table for active events
            event = await self.bot.db.fetchone(
                """SELECT event_id, event_type, name, end_ts 
                   FROM events 
                   WHERE guild_id=? AND is_active=1 
                   ORDER BY start_ts DESC LIMIT 1""",
                (gid,),
            )
            if event and event["event_id"]:
                # Show only name + time window (no admin info)
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

async def setup(bot: commands.Bot):
    await bot.add_cog(CoreCommands(bot))

