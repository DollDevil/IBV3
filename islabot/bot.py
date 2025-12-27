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
from discord import app_commands

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
        
        # Track if commands have been synced
        self._commands_synced = False

    async def on_ready(self):
        """Called when the bot is ready. Register and sync commands."""
        print(f"\n{'='*60}")
        print(f"Bot is ready! Logged in as {self.user} (ID: {self.user.id})")
        print(f"Connected to {len(self.guilds)} guild(s)")
        print(f"{'='*60}\n")
        
        if not self._commands_synced:
            print("Registering and syncing commands...")
            # In discord.py 2.0+, @app_commands.command() in cogs ARE automatically added to the tree
            # But we'll verify and manually register any that might be missing
            await self._register_cog_commands()
            await self._sync_commands()
    
    async def on_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        """Global error handler for app commands."""
        if isinstance(error, app_commands.CommandOnCooldown):
            await interaction.response.send_message(
                f"This command is on cooldown. Try again in {error.retry_after:.1f} seconds.",
                ephemeral=True
            )
        elif isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                "You don't have permission to use this command.",
                ephemeral=True
            )
        elif isinstance(error, app_commands.BotMissingPermissions):
            await interaction.response.send_message(
                "I don't have the required permissions to execute this command.",
                ephemeral=True
            )
        else:
            # Log unexpected errors
            print(f"Unhandled command error: {error}")
            import traceback
            traceback.print_exc()
            try:
                if interaction.response.is_done():
                    await interaction.followup.send(
                        "An error occurred while executing this command.",
                        ephemeral=True
                    )
                else:
                    await interaction.response.send_message(
                        "An error occurred while executing this command.",
                        ephemeral=True
                    )
            except Exception:
                pass  # Ignore errors in error handler
    
    async def on_error(self, event_method: str, *args, **kwargs):
        """Global error handler for events."""
        print(f"Error in event {event_method}:")
        import traceback
        traceback.print_exc()
    
    async def _sync_commands(self):
        """Helper method to sync commands."""
        # List all commands in the tree before syncing
        all_commands = []
        for cmd in self.tree.walk_commands():
            all_commands.append(cmd.qualified_name)
        print(f"\n{'='*60}")
        print(f"Commands in tree before sync: {len(all_commands)}")
        if all_commands:
            print(f"  Commands: {', '.join(all_commands[:20])}")
            if len(all_commands) > 20:
                print(f"  ... and {len(all_commands) - 20} more")
        else:
            print("  WARNING: No commands found in tree! This is likely the problem.")
        print(f"{'='*60}\n")
        
        guild_ids_raw = self.cfg.get("guilds", default=[])
        
        # Handle different formats: list, string with commas, or single value
        guild_ids = []
        if isinstance(guild_ids_raw, list):
            # Normalize list items (handle mixed types and nested lists)
            for item in guild_ids_raw:
                item_str = str(item).strip()
                # Check if list item itself is a comma-separated string
                if ',' in item_str:
                    # Split and add each ID
                    guild_ids.extend([gid.strip() for gid in item_str.split(",") if gid.strip()])
                elif isinstance(item, (list, tuple)):
                    # Handle nested lists
                    guild_ids.extend([str(subitem).strip() for subitem in item if subitem])
                else:
                    guild_ids.append(item_str)
        elif isinstance(guild_ids_raw, str):
            # Handle comma-separated string (common issue from environment variables)
            # Also handle if it's a string representation of a list
            if guild_ids_raw.strip().startswith('[') and guild_ids_raw.strip().endswith(']'):
                # Try to parse as JSON-like list
                import ast
                try:
                    parsed = ast.literal_eval(guild_ids_raw)
                    if isinstance(parsed, list):
                        guild_ids = [str(item).strip() for item in parsed if item]
                    else:
                        guild_ids = [str(parsed).strip()]
                except:
                    # Fall back to comma splitting
                    guild_ids = [gid.strip() for gid in guild_ids_raw.split(",") if gid.strip()]
            else:
                # Simple comma-separated string
                guild_ids = [gid.strip() for gid in guild_ids_raw.split(",") if gid.strip()]
        elif guild_ids_raw:
            # Single value (not a list) - convert to list
            # Check if it's a comma-separated string
            item_str = str(guild_ids_raw).strip()
            if ',' in item_str:
                guild_ids = [gid.strip() for gid in item_str.split(",") if gid.strip()]
            else:
                guild_ids = [item_str]
        
        # Debug output
        if guild_ids:
            print(f"Parsed {len(guild_ids)} guild ID(s) from config")
        
        if guild_ids:
            # Sync commands to each guild directly (guild-specific commands)
            for gid in guild_ids:
                try:
                    # Convert to int, handling string IDs
                    guild_id_int = int(str(gid).strip())
                    g = discord.Object(id=guild_id_int)
                    # Sync directly to guild (don't use copy_global_to - that's for copying global commands)
                    synced = await self.tree.sync(guild=g)
                    print(f"✓ Synced {len(synced)} commands to guild {guild_id_int}")
                    if synced:
                        for cmd in synced[:10]:  # Show first 10
                            print(f"  - {cmd.name}")
                        if len(synced) > 10:
                            print(f"  ... and {len(synced) - 10} more")
                except ValueError as e:
                    print(f"✗ Warning: Invalid guild ID format '{gid}': {e}")
                    print(f"  Guild IDs must be numeric. Check your config.yml")
                except discord.Forbidden:
                    print(f"✗ Warning: Missing access to guild {gid}. Skipping command sync for this guild.")
                    print(f"  Make sure the bot has 'applications.commands' scope in the invite URL!")
                except Exception as e:
                    print(f"✗ Warning: Failed to sync commands for guild {gid}: {e}")
                    import traceback
                    traceback.print_exc()
        else:
            # No guild IDs specified, sync globally
            synced = await self.tree.sync()
            print(f"✓ Synced {len(synced)} global commands")
            if synced:
                for cmd in synced[:10]:  # Show first 10
                    print(f"  - {cmd.name}")
                if len(synced) > 10:
                    print(f"  ... and {len(synced) - 10} more")
        
        print(f"\n{'='*60}")
        print("IMPORTANT: If commands don't appear in Discord:")
        print("1. Make sure your bot invite URL includes 'applications.commands' scope")
        print("2. Wait 1-2 minutes for Discord to update")
        print("3. Try restarting Discord client (Ctrl+R)")
        print(f"{'='*60}\n")
        
        self._commands_synced = True

    async def setup_hook(self):
        """Called when the bot is setting up. Initialize database and load cogs."""
        print(f"\n{'='*60}")
        print("Initializing IslaBot...")
        print(f"{'='*60}\n")
        
        # Initialize database
        try:
            await self.db.connect()
            print("✓ Database connected")
            await self.db.migrate()
            print("✓ Database migrations completed")
        except Exception as e:
            print(f"✗ Database error during setup: {e}")
            import traceback
            traceback.print_exc()
            raise

        # Load all cogs
        loaded_count = 0
        failed_count = 0
        for ext in COGS:
            try:
                await self.load_extension(ext)
                loaded_count += 1
                print(f"✓ Loaded: {ext}")
            except Exception as e:
                failed_count += 1
                print(f"✗ Failed to load {ext}: {e}")
                import traceback
                traceback.print_exc()
                # Continue loading other extensions
        
        print(f"\n{'='*60}")
        print(f"Extensions: {loaded_count} loaded, {failed_count} failed")
        print("Waiting for bot to be ready...")
        print(f"{'='*60}\n")
    
    async def _register_cog_commands(self):
        """Register all app_commands from loaded cogs to the command tree.
        
        Note: In discord.py 2.0+, commands defined with @app_commands.command() 
        in cogs ARE automatically added to the tree when bot.add_cog() is called.
        This function verifies and manually registers any that might be missing.
        """
        print("Checking command registration...")
        
        # First, check what's already in the tree (from auto-registration)
        existing_commands = {cmd.qualified_name for cmd in self.tree.walk_commands()}
        print(f"  Commands already in tree (auto-registered): {len(existing_commands)}")
        
        registered_count = 0
        skipped_count = 0
        found_commands = []
        
        # Scan all cogs for app_commands
        for cog_name, cog in self.cogs.items():
            # Get all attributes of the cog
            for attr_name in dir(cog):
                # Skip private attributes and methods
                if attr_name.startswith('_'):
                    continue
                
                try:
                    attr = getattr(cog, attr_name, None)
                    
                    # Check if it's an app_commands.Command or app_commands.Group
                    if isinstance(attr, (app_commands.Command, app_commands.Group)):
                        found_commands.append(attr.qualified_name)
                        
                        # Check if command is already in tree
                        if attr.qualified_name in existing_commands:
                            skipped_count += 1
                            continue
                            
                        # Command not in tree, add it manually
                        try:
                            self.tree.add_command(attr)
                            registered_count += 1
                            print(f"  ✓ Manually registered: {attr.qualified_name}")
                            existing_commands.add(attr.qualified_name)
                        except Exception as e:
                            print(f"  ✗ Failed to register {attr.qualified_name}: {e}")
                            
                except Exception:
                    # Silently skip errors when checking attributes
                    pass
        
        print(f"\nCommand Registration Summary:")
        print(f"  - Found in cogs: {len(found_commands)}")
        print(f"  - Already in tree: {skipped_count}")
        print(f"  - Manually registered: {registered_count}")
        print(f"  - Total in tree now: {len(existing_commands)}")
        
        if len(existing_commands) == 0:
            print(f"\n{'='*60}")
            print("⚠ CRITICAL WARNING: NO COMMANDS FOUND IN TREE!")
            print("This means commands aren't being registered properly.")
            print("Check:")
            print("  1. Are cogs loading without errors?")
            print("  2. Do cogs have @app_commands.command() decorators?")
            print("  3. Are setup() functions calling bot.add_cog()?")
            print(f"{'='*60}\n")
        elif len(found_commands) > len(existing_commands):
            print(f"\n⚠ Warning: Found {len(found_commands)} commands in cogs but only {len(existing_commands)} in tree")
            print("Some commands may not be registered properly.\n")
        
        # Verify data collection listeners are active
        listeners_active = []
        if self.get_cog("Moderation"):
            listeners_active.append("message tracking")
        if self.get_cog("VoiceTracker"):
            listeners_active.append("voice tracking")
        if self.get_cog("MessageTracker"):
            listeners_active.append("message hourly tracking")
        if self.get_cog("Leaderboard"):
            listeners_active.append("spotlight tracking")
        if self.get_cog("EventActivityTracker"):
            listeners_active.append("event activity tracking")
        
        if listeners_active:
            print(f"✓ Data collection active: {', '.join(listeners_active)}")
        else:
            print("⚠ Warning: Some data collection listeners may not be active")
        
        # Verify database is accessible
        try:
            test_result = await self.db.fetchone("SELECT 1 as test")
            if test_result:
                print("✓ Database connection verified")
        except Exception as e:
            print(f"⚠ Warning: Database health check failed: {e}")

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
            # Only token and guilds are required - channels and roles can be configured later via Discord commands
            guild_id = os.getenv("DISCORD_GUILDS", "")
            if not guild_id:
                guild_id = "123456789012345678"  # placeholder, will need to be set
            
            config_content = f"""token: "{token}"

guilds:
  - {guild_id}

# Channels and roles can be configured later via /config commands or Discord settings
# These are optional - the bot will work with defaults (0 means not configured)
channels:
  spotlight: 0
  orders: 0
  casino: 0
  spam: 0
  mod_logs: 0
  announcements: 0
  logs: 0

roles:
  verified_18: 0
  consent: 0
  humiliation_optin: 0

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
    
    db = Database(db_path)
    bot = IslaBot(cfg, db)
    
    # Retry logic for rate limiting
    max_retries = 5
    retry_delay = 5  # Start with 5 seconds
    for attempt in range(max_retries):
        try:
            await bot.start(cfg["token"])
            break  # Success, exit retry loop
        except discord.HTTPException as e:
            if e.status == 429:  # Rate limited
                if attempt < max_retries - 1:
                    wait_time = retry_delay * (2 ** attempt)  # Exponential backoff: 5, 10, 20, 40, 80 seconds
                    print(f"Rate limited (429). Waiting {wait_time} seconds before retry ({attempt + 1}/{max_retries})...")
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    print(f"ERROR: Rate limited after {max_retries} attempts. Please wait and try again later.")
                    sys.exit(1)
            else:
                # Other HTTP errors - raise immediately
                raise
        except discord.LoginFailure as e:
            print(f"ERROR: Discord Login Failure: {e}")
            print("Please check your bot token in config.yml or DISCORD_BOT_TOKEN environment variable.")
            sys.exit(1)
        except KeyboardInterrupt:
            print("\nBot shutdown requested by user")
            break
        except Exception as e:
            print(f"Fatal error starting bot: {e}")
            import traceback
            traceback.print_exc()
            raise

if __name__ == "__main__":
    asyncio.run(main())

