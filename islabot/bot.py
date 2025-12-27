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
        try:
            await self.db.connect()
            await self.db.migrate()
        except Exception as e:
            print(f"Database error during setup: {e}")
            import traceback
            traceback.print_exc()
            raise

        for ext in COGS:
            try:
                await self.load_extension(ext)
            except Exception as e:
                print(f"Warning: Failed to load extension {ext}: {e}")
                # Continue loading other extensions

        # Sync slash commands (per guild for fast iteration)
        guild_ids = self.cfg.get("guilds", default=[])
        if guild_ids:
            for gid in guild_ids:
                try:
                    g = discord.Object(id=int(gid))
                    self.tree.copy_global_to(guild=g)
                    await self.tree.sync(guild=g)
                except discord.Forbidden:
                    print(f"Warning: Missing access to guild {gid}. Skipping command sync for this guild.")
                except Exception as e:
                    print(f"Warning: Failed to sync commands for guild {gid}: {e}")
        else:
            await self.tree.sync()

    async def close(self):
        await super().close()
        await self.db.close()

async def main():
    # Use paths relative to bot.py location (Wispbyte compatible)
    config_path = os.path.join(BOT_DIR, "config.yml")
    db_path = os.path.join(BOT_DIR, "islabot.sqlite3")
    
    # Check if config.yml exists, if not try to create from environment variables
    if not os.path.exists(config_path):
        print("=" * 60)
        print("config.yml not found. Attempting to create from environment variables...")
        print("=" * 60)
        
        # Try to create config.yml from environment variables (Railway compatible)
        token = os.getenv("DISCORD_BOT_TOKEN")
        if token:
            # Create basic config from environment variables
            config_content = f"""token: "{token}"

guilds:
  - {os.getenv("DISCORD_GUILDS", "123456789012345678")}

channels:
  spotlight: {os.getenv("CHANNEL_SPOTLIGHT", "123")}
  orders: {os.getenv("CHANNEL_ORDERS", "456")}
  casino: {os.getenv("CHANNEL_CASINO", "789")}
  spam: {os.getenv("CHANNEL_SPAM", "111")}
  mod_logs: {os.getenv("CHANNEL_MOD_LOGS", "222")}
  announcements: {os.getenv("CHANNEL_ANNOUNCEMENTS", "111111111111111111")}
  logs: {os.getenv("CHANNEL_LOGS", "333333333333333333")}

roles:
  verified_18: {os.getenv("ROLE_VERIFIED_18", "555555555555555555")}
  consent: {os.getenv("ROLE_CONSENT", "666666666666666666")}
  humiliation_optin: {os.getenv("ROLE_HUMILIATION_OPTIN", "777777777777777777")}

isla:
  timezone: "Europe/London"
  stage_cap: 2
  dm_style_allowed: true

economy:
  daily_coins: 120
  inactivity_tax_pct_daily: 5
  burn_min: 10
  burn_max: 5000

orders:
  max_active_per_user: 1
  default_minutes: 90
  penalty_debt: 25

presence:
  enabled: true
  thoughts_path: "data/isla_presence_thoughts.json"
  morning_start_window: "12:00-15:00"
  sleep_window: "00:00-03:00"
  awake_posts_per_day_min: 10
  awake_posts_per_day_max: 25
  spotlight_posts_per_day_max: 3
  low_activity_msg_threshold: 18
  low_activity_unique_threshold: 6
  reaction_threshold: 3
  mood_awake_fast_mult: 0.7
  mood_tired_slow_mult: 1.4

casino_recap:
  min_total_wagered: 25000
  min_rounds: 120
  min_unique_players: 25
  time_uk: "21:15"
"""
            try:
                with open(config_path, "w", encoding="utf-8") as f:
                    f.write(config_content)
                print(f"✓ Created config.yml from environment variables at {config_path}")
            except Exception as e:
                print(f"✗ Failed to create config.yml: {e}")
                sys.exit(1)
        else:
            print("ERROR: config.yml file not found and DISCORD_BOT_TOKEN not set!")
            print("=" * 60)
            print(f"Expected location: {config_path}")
            print("\nTo fix this:")
            print("1. Create config.yml in the islabot/ directory, OR")
            print("2. Set DISCORD_BOT_TOKEN environment variable in Railway")
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
    
    try:
        db = Database(db_path)
        bot = IslaBot(cfg, db)
        await bot.start(cfg["token"])
    except KeyboardInterrupt:
        print("\nBot shutdown requested by user")
    except Exception as e:
        print(f"Fatal error starting bot: {e}")
        import traceback
        traceback.print_exc()
        raise

if __name__ == "__main__":
    asyncio.run(main())

