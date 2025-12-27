from __future__ import annotations

import asyncio
import os
import sys
import time
import discord
from discord.ext import commands

# Add islabot directory to Python path for Railway compatibility
BOT_DIR = os.path.dirname(os.path.abspath(__file__))
if BOT_DIR not in sys.path:
    sys.path.insert(0, BOT_DIR)

# Use full module path for cogs when running as module (Railway)
# Check if we're being run as a module (python -m islabot.bot)
COG_PREFIX = "islabot." if __package__ else ""

from core.config import Config
from core.db import Database
from core.flags import FlagService
from core.channel_cfg import ChannelConfigService
from core.personality import Personality
from core.tone import DEFAULT_POOLS

COGS = [
    f"{COG_PREFIX}cogs.alive",
    f"{COG_PREFIX}cogs.moderation",
    f"{COG_PREFIX}cogs.onboarding",
    f"{COG_PREFIX}cogs.economy",
    f"{COG_PREFIX}cogs.progression",
    f"{COG_PREFIX}cogs.shop",
    f"{COG_PREFIX}cogs.profile",
    f"{COG_PREFIX}cogs.voice_stats",
    f"{COG_PREFIX}cogs.casino_core",
    f"{COG_PREFIX}cogs.casino_games",
    f"{COG_PREFIX}cogs.casino_bigwin_dm",
    f"{COG_PREFIX}cogs.casino_royalty",
    f"{COG_PREFIX}cogs.casino_daily_recap",
    f"{COG_PREFIX}cogs.orders",
    f"{COG_PREFIX}cogs.events",
    # Event system (load in order: voice -> message -> scheduler -> commands)
    f"{COG_PREFIX}cogs.voice_tracker",
    f"{COG_PREFIX}cogs.message_tracker",
    f"{COG_PREFIX}cogs.event_scheduler",
    f"{COG_PREFIX}cogs.event_group",  # /event group with subcommands
    f"{COG_PREFIX}cogs.daily_presence",
    f"{COG_PREFIX}cogs.vacation_watch",
    f"{COG_PREFIX}cogs.safeword",
    f"{COG_PREFIX}cogs.info_unified",
    f"{COG_PREFIX}cogs.quarterly_tax",
    f"{COG_PREFIX}cogs.privacy",
    f"{COG_PREFIX}cogs.admin_tools",
    f"{COG_PREFIX}cogs.core_commands",
    f"{COG_PREFIX}cogs.coins_group",
    f"{COG_PREFIX}cogs.orders_group",
    f"{COG_PREFIX}cogs.discipline_group",
    f"{COG_PREFIX}cogs.duel_cog",
    f"{COG_PREFIX}cogs.custom_events_group",
    f"{COG_PREFIX}cogs.announce_and_remind",
    f"{COG_PREFIX}cogs.config_group",
    f"{COG_PREFIX}cogs.context_apps",
]

class IslaBot(commands.Bot):
    def __init__(self, cfg: Config, db: Database):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True

        super().__init__(
            command_prefix=commands.when_mentioned_or("!"),
            intents=intents,
        )
        self.cfg = cfg
        self.db = db
        self.flags = FlagService(db)
        self.chan_cfg = ChannelConfigService(db)
        self.started_ts = int(time.time())
        
        # Hot-reload personality responses
        personality_path = os.path.join(BOT_DIR, "personality.json")
        self.personality = Personality(path=personality_path, fallback=DEFAULT_POOLS)
        self.personality.load()
        self.personality.sanitize()

    async def setup_hook(self):
        await self.db.connect()
        await self.db.migrate()

        for ext in COGS:
            await self.load_extension(ext)

        # Sync slash commands (per guild for fast iteration)
        guild_ids = self.cfg.get("guilds", default=[])
        if guild_ids:
            for gid in guild_ids:
                g = discord.Object(id=int(gid))
                self.tree.copy_global_to(guild=g)
                await self.tree.sync(guild=g)
        else:
            await self.tree.sync()

    async def close(self):
        await super().close()
        await self.db.close()

async def main():
    # Use paths relative to bot.py location (Wispbyte compatible)
    config_path = os.path.join(BOT_DIR, "config.yml")
    db_path = os.path.join(BOT_DIR, "islabot.sqlite3")
    
    # Check if config.yml exists
    if not os.path.exists(config_path):
        print("=" * 60)
        print("ERROR: config.yml file not found!")
        print("=" * 60)
        print(f"Expected location: {config_path}")
        print("\nTo fix this:")
        print("1. Create config.yml in the islabot/ directory")
        print("2. Add your bot token and configuration")
        print("3. On Railway: Use the file editor or upload via Variables")
        print("\nExample config.yml structure:")
        print("  token: \"YOUR_BOT_TOKEN_HERE\"")
        print("  guilds:")
        print("    - YOUR_GUILD_ID")
        print("  channels:")
        print("    spotlight: CHANNEL_ID")
        print("    # ... other settings")
        print("=" * 60)
        sys.exit(1)
    
    cfg = Config.load(config_path)
    
    # Check if token is set
    if not cfg.get("token") or cfg.get("token") == "PUT_YOUR_BOT_TOKEN_HERE":
        print("=" * 60)
        print("ERROR: Bot token not configured!")
        print("=" * 60)
        print("Please set your bot token in config.yml")
        print("=" * 60)
        sys.exit(1)
    
    db = Database(db_path)
    bot = IslaBot(cfg, db)
    await bot.start(cfg["token"])

if __name__ == "__main__":
    asyncio.run(main())

