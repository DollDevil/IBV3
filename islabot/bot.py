from __future__ import annotations

import asyncio
import ast
import json
import os
import re
import sys
import time
import traceback
from itertools import islice
import discord
from discord.ext import commands

# Add islabot directory to Python path for Railway compatibility
BOT_DIR = os.path.dirname(os.path.abspath(__file__))
if BOT_DIR not in sys.path:
    sys.path.insert(0, BOT_DIR)

# Use full module path for cogs when running as module (Railway)
COG_PREFIX = "islabot." if __package__ else ""

from core.configurations import Config, ChannelConfigService, FlagService
from core.db import Database
from core.personality import Personality, MemoryService, DEFAULT_POOLS
from discord import app_commands

COGS = [
    # New consolidated structure
    f"{COG_PREFIX}cogs.commands",          # Commands: alive, core_commands, info_unified, context_apps
    f"{COG_PREFIX}cogs.onboarding",      # Onboarding: onboarding (includes consent functionality)
    f"{COG_PREFIX}cogs.user",            # User: privacy, profile, safeword, vacation_watch, auto_reply, duel_cog
    f"{COG_PREFIX}cogs.economy",         # Economy: economy, shop, quarterly_tax, coins_group
    f"{COG_PREFIX}cogs.admin",           # Admin: admin_tools, config_group, discipline_group
    f"{COG_PREFIX}cogs.data",            # Data: moderation, progression, voice_tracker, message_tracker, event_activity_tracker, voice_stats
    f"{COG_PREFIX}cogs.announcements",   # Announcements: daily_presence, announce_and_remind, leaderboard, casino_daily_recap
    f"{COG_PREFIX}cogs.orders",          # Orders: orders, orders_group, tributes
    f"{COG_PREFIX}cogs.events",          # Events: events, event_group, event_scheduler, event_boss_cmd, custom_events_group
    f"{COG_PREFIX}cogs.casino_core",     # Gambling: casino_core, casino_games, casino_bigwin_dm, casino_royalty (consolidated)
]

# Constants
SEPARATOR = "=" * 60
SYNC_ERROR_MESSAGES = {
    "missing_permission": "Bot missing 'Use Application Commands' permission",
    "role_position": "Bot role position too low",
    "missing_scope": "Missing 'applications.commands' scope in invite URL",
}

# Cog names for data collection listener verification
COG_LISTENER_NAMES = {
    "Data": "message tracking, voice tracking, event activity tracking",
    "Announcements": "spotlight tracking, daily presence, announcements",
    "Events": "event scheduling, boss tick, quest refresh, flush loops",
}

# Config template for environment variable creation
DEFAULT_CONFIG_TEMPLATE = """token: "{token}"

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


# Helper functions for consistent output formatting
def _print_section(title: str = ""):
    """Print a section separator with optional title."""
    print(f"\n{SEPARATOR}")
    if title:
        print(title)
        print(SEPARATOR)


def _print_list(items: list, max_items: int = 10, prefix: str = "  "):
    """Print a list with truncation."""
    for item in items[:max_items]:
        print(f"{prefix}- {item}")
    if len(items) > max_items:
        print(f"{prefix}... and {len(items) - max_items} more")


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
        
        # Initialize memory service first (needed by personality)
        self.memory = MemoryService(db)
        
        # Hot-reload personality responses (with memory integration)
        personality_path = os.path.join(BOT_DIR, "personality.json")
        self.personality = Personality(path=personality_path, fallback=DEFAULT_POOLS, memory_service=self.memory)
        self.personality.load()
        self.personality.sanitize()
        
        self._commands_synced = False
        self._guild_ids_cache = None  # Cache parsed guild IDs

    def _parse_guild_ids(self, guild_ids_raw) -> list[str]:
        """Parse guild IDs from various formats (list, string, etc.). Cached result."""
        # #region agent log
        cached = self._guild_ids_cache is not None
        # #endregion
        
        if self._guild_ids_cache is not None:
            # #region agent log
            try:
                with open(r"c:\Users\Yuu\Documents\IslaBotV3\.cursor\debug.log", "a", encoding="utf-8") as f:
                    f.write(json.dumps({"sessionId": "perf-cleanup", "runId": "run1", "hypothesisId": "C", "location": "bot.py:_parse_guild_ids", "message": "Guild ID cache hit", "data": {"cached": True}, "timestamp": int(time.time() * 1000)}) + "\n")
            except Exception:
                pass
            # #endregion
            return self._guild_ids_cache
        
        if not guild_ids_raw:
            self._guild_ids_cache = []
            return []
        
        def _split_comma_separated(s: str) -> list[str]:
            """Split comma-separated string into list of trimmed IDs."""
            return [gid.strip() for gid in s.split(",") if gid.strip()]
        
        guild_ids = []
        
        if isinstance(guild_ids_raw, list):
            for item in guild_ids_raw:
                item_str = str(item).strip()
                if ',' in item_str:
                    guild_ids.extend(_split_comma_separated(item_str))
                elif isinstance(item, (list, tuple)):
                    guild_ids.extend([str(subitem).strip() for subitem in item if subitem])
                elif item_str:
                    guild_ids.append(item_str)
        else:
            # Handle string or other types
            item_str = str(guild_ids_raw).strip()
            if item_str.startswith('[') and item_str.endswith(']'):
                try:
                    parsed = ast.literal_eval(item_str)
                    parsed_list = parsed if isinstance(parsed, list) else [parsed]
                    guild_ids = [str(item).strip() for item in parsed_list if item]
                except (ValueError, SyntaxError):
                    guild_ids = _split_comma_separated(item_str)
            elif ',' in item_str:
                guild_ids = _split_comma_separated(item_str)
            elif item_str:
                guild_ids = [item_str]
        
        self._guild_ids_cache = guild_ids
        
        # #region agent log
        try:
            with open(r"c:\Users\Yuu\Documents\IslaBotV3\.cursor\debug.log", "a", encoding="utf-8") as f:
                f.write(json.dumps({"sessionId": "perf-cleanup", "runId": "run1", "hypothesisId": "C", "location": "bot.py:_parse_guild_ids", "message": "Guild ID cache miss", "data": {"cached": False, "guild_count": len(guild_ids)}, "timestamp": int(time.time() * 1000)}) + "\n")
        except Exception:
            pass
        # #endregion
        
        return guild_ids

    def _force_remove_command(self, cmd_name: str) -> bool:
        """Forcefully remove a command from the tree using multiple strategies."""
        removed = False
        
        # Strategy 1: Remove global command
        try:
            if self.tree.remove_command(cmd_name, guild=None) is not None:
                removed = True
        except Exception:
            pass
        
        # Strategy 2: Remove from all guild contexts (use cached guild IDs)
        if self._guild_ids_cache is None:
            self._parse_guild_ids(self.cfg.get("guilds", default=[]))
        try:
            for gid_str in self._guild_ids_cache:
                try:
                    guild_obj = discord.Object(id=int(str(gid_str).strip()))
                    if self.tree.remove_command(cmd_name, guild=guild_obj) is not None:
                        removed = True
                except (ValueError, Exception):
                    pass
        except Exception:
            pass
        
        # Strategy 3: Verify removal
        try:
            result = self.tree.get_command(cmd_name, guild=None) is None
        except Exception:
            result = removed
        
        # #region agent log
        try:
            with open(r"c:\Users\Yuu\Documents\IslaBotV3\.cursor\debug.log", "a", encoding="utf-8") as f:
                f.write(json.dumps({"sessionId": "perf-cleanup", "runId": "run1", "hypothesisId": "D", "location": "bot.py:_force_remove_command", "message": "Command removal", "data": {"cmd_name": cmd_name, "removed": result, "used_cache": self._guild_ids_cache is not None}, "timestamp": int(time.time() * 1000)}) + "\n")
        except Exception:
            pass
        # #endregion
        
        return result

    async def _sync_guild_commands(self, guild_id_int: int, all_commands: list[str]) -> bool:
        """Sync commands to a specific guild. Returns True if successful."""
        try:
            guild_obj = discord.Object(id=guild_id_int)
            synced = await self.tree.sync(guild=guild_obj)
            
            if not synced and all_commands:
                print(f"⚠ Warning: 0 commands synced to guild {guild_id_int} (but {len(all_commands)} in tree)")
                print(f"  Possible causes:")
                for msg_key in ["missing_permission", "role_position", "missing_scope"]:
                    print(f"  - {SYNC_ERROR_MESSAGES[msg_key]}")
            else:
                print(f"✓ Successfully synced {len(synced)} commands to guild {guild_id_int}")
                if synced:
                    _print_list([cmd.name for cmd in synced])
            return True
        except discord.HTTPException as e:
            if e.status == 403:
                print(f"✗ Error: Forbidden (403) when syncing to guild {guild_id_int}")
                for msg_key in ["missing_permission", "role_position", "missing_scope"]:
                    print(f"  - {SYNC_ERROR_MESSAGES[msg_key]}")
            elif e.status == 429:
                print(f"⚠ Rate limited. Waiting before retry...")
                await asyncio.sleep(5)
                try:
                    synced = await self.tree.sync(guild=guild_obj)
                    print(f"✓ Retry successful: synced {len(synced)} commands")
                    return True
                except Exception as retry_error:
                    print(f"✗ Retry failed: {retry_error}")
            else:
                print(f"✗ HTTP Error {e.status}: {e}")
                raise
            return False
        except ValueError as e:
            print(f"✗ Error: Invalid guild ID format: {e}")
            print(f"  Guild IDs must be numeric. Check your config.yml")
            return False
        except Exception as e:
            print(f"✗ Error: Failed to sync commands for guild {guild_id_int}: {e}")
            traceback.print_exc()
            return False

    async def _sync_commands(self, all_commands: list[str] | None = None):
        """Sync commands to Discord. Accepts pre-computed command list to avoid duplicate tree walks."""
        # #region agent log
        sync_start = time.perf_counter()
        walked_commands = all_commands is None
        # #endregion
        
        if all_commands is None:
            all_commands = [cmd.qualified_name for cmd in self.tree.walk_commands()]
        
        # #region agent log
        try:
            with open(r"c:\Users\Yuu\Documents\IslaBotV3\.cursor\debug.log", "a", encoding="utf-8") as f:
                f.write(json.dumps({"sessionId": "perf-cleanup", "runId": "run1", "hypothesisId": "B", "location": "bot.py:_sync_commands", "message": "Command tree walk", "data": {"walked_commands": walked_commands, "command_count": len(all_commands)}, "timestamp": int(time.time() * 1000)}) + "\n")
        except Exception:
            pass
        # #endregion
        
        _print_section(f"Commands in tree before sync: {len(all_commands)}")
        
        if all_commands:
            _print_list(all_commands[:20], max_items=20)
        else:
            print("  WARNING: No commands found in tree! This is likely the problem.")
        print()
        
        guild_ids = self._parse_guild_ids(self.cfg.get("guilds", default=[]))
        
        if guild_ids:
            print(f"Parsed {len(guild_ids)} guild ID(s) from config")
            bot_guild_ids = {g.id for g in self.guilds}
            guild_list = list(bot_guild_ids)[:5]
            print(f"Bot is in {len(bot_guild_ids)} guild(s): {', '.join(str(gid) for gid in guild_list)}")
            if len(bot_guild_ids) > 5:
                print(f"  ... and {len(bot_guild_ids) - 5} more")
            
            print(f"\nSyncing commands to guilds (guild-specific only, no global sync)...")
            for gid in guild_ids:
                try:
                    guild_id_int = int(str(gid).strip())
                    if guild_id_int not in bot_guild_ids:
                        print(f"⚠ Warning: Bot is not in guild {guild_id_int}")
                        print(f"  The bot must be invited to the server before commands can sync.")
                        continue
                    await self._sync_guild_commands(guild_id_int, all_commands)
                except ValueError:
                    print(f"✗ Error: Invalid guild ID format '{gid}'")
        else:
            # No guild IDs specified - sync globally
            print("No specific guild IDs found in config. Syncing globally...")
            try:
                synced = await self.tree.sync()
                print(f"✓ Synced {len(synced)} global commands")
                if synced:
                    _print_list([cmd.name for cmd in synced])
            except Exception as e:
                print(f"✗ Global sync failed: {e}")
                traceback.print_exc()
        
        # Verification section
        _print_section("SYNC VERIFICATION")
        
        if self.user:
            print(f"✓ Bot is logged in as: {self.user.name}#{self.user.discriminator}")
            print(f"✓ Bot ID: {self.user.id}")
        else:
            print("✗ Bot user not found - connection issue!")
        
        if self.guilds:
            print(f"✓ Bot is in {len(self.guilds)} guild(s)")
            # Use islice for efficient slicing without full list conversion
            _print_list([f"{g.name} (ID: {g.id})" for g in islice(self.guilds, 3)], max_items=3)
        else:
            print("✗ Bot is not in any guilds!")
            print("  Invite the bot to your server first.")
        
        print(f"✓ Total commands registered: {len(all_commands)}")
        
        if not all_commands:
            print("  ⚠ WARNING: No commands found! This is a code issue.")
        elif guild_ids:
            _print_section("IF COMMANDS DON'T APPEAR IN DISCORD:")
            print("1. CHECK INVITE URL - Must include 'applications.commands' scope")
            print("   Correct format: https://discord.com/api/oauth2/authorize?client_id=YOUR_BOT_ID&permissions=8&scope=bot%20applications.commands")
            print("2. RE-INVITE the bot with the correct URL (even if already in server)")
            print("3. WAIT 1-2 minutes for Discord to propagate commands")
            print("4. RESTART Discord client (Ctrl+R or Cmd+R)")
            print("5. CHECK Railway logs above for sync errors")
            print()
        
        self._commands_synced = True

    async def _handle_command_already_registered(self, ext: str, cmd_name: str) -> bool:
        """Handle CommandAlreadyRegistered error. Returns True if extension loaded successfully."""
        try:
            # Try to unload the extension if it's partially loaded
            if ext in self.extensions:
                try:
                    await self.unload_extension(ext)
                except Exception:
                    pass
            
            # Remove command - try multiple times
            for _ in range(3):
                if self._force_remove_command(cmd_name):
                    break
                await asyncio.sleep(0.05)
            
            await asyncio.sleep(0.1)
            await self.load_extension(ext)
            print(f"✓ Loaded: {ext} (after removing duplicate '{cmd_name}' command)")
            return True
        except Exception as retry_error:
            print(f"✗ Failed to load {ext} even after removing duplicate command: {retry_error}")
            return False

    async def setup_hook(self):
        """Called when the bot is setting up. Initialize database and load cogs."""
        _print_section("Initializing IslaBot...")
        
        # Initialize database
        try:
            await self.db.connect()
            print("✓ Database connected")
            await self.db.migrate()
            print("✓ Database migrations completed")
        except Exception as e:
            print(f"✗ Database error during setup: {e}")
            traceback.print_exc()
            raise

        # Load all cogs
        loaded_count = 0
        failed_count = 0
        for ext in COGS:
            try:
                # If extension is already loaded, unload it first to avoid conflicts
                if ext in self.extensions:
                    try:
                        await self.unload_extension(ext)
                    except Exception:
                        pass
                
                await self.load_extension(ext)
                loaded_count += 1
                print(f"✓ Loaded: {ext}")
            except Exception as e:
                error_str = str(e)
                if "CommandAlreadyRegistered" in error_str:
                    match = re.search(r"Command '(\w+)' already registered", error_str)
                    if match:
                        if await self._handle_command_already_registered(ext, match.group(1)):
                            loaded_count += 1
                            continue
                failed_count += 1
                print(f"✗ Failed to load {ext}: {e}")
                traceback.print_exc()
        
        _print_section(f"Extensions: {loaded_count} loaded, {failed_count} failed")
        print("Waiting for bot to be ready...")
        print()

    async def _register_cog_commands(self, existing_commands: set[str] | None = None):
        """Verify command registration and check system health. Accepts pre-computed commands set."""
        # #region agent log
        start_time = time.perf_counter()
        # #endregion
        
        if existing_commands is None:
            existing_commands = {cmd.qualified_name for cmd in self.tree.walk_commands()}
        
        print(f"Commands in tree: {len(existing_commands)}")
        
        found_commands = []
        registered_count = 0
        
        # #region agent log
        cog_scan_start = time.perf_counter()
        cog_count = 0
        attr_checks = 0
        # #endregion
        
        # Scan cogs for app_commands - use vars() instead of dir() for better performance
        for cog in self.cogs.values():
            cog_count += 1
            # Use __dict__ instead of dir() - much faster, only gets instance attributes
            cog_dict = vars(cog)
            for attr_name, attr_value in cog_dict.items():
                attr_checks += 1
                if attr_name.startswith('_'):
                    continue
                if isinstance(attr_value, (app_commands.Command, app_commands.Group)):
                    found_commands.append(attr_value.qualified_name)
                    if attr_value.qualified_name not in existing_commands:
                        try:
                            self.tree.add_command(attr_value)
                            registered_count += 1
                            print(f"  ✓ Manually registered: {attr_value.qualified_name}")
                        except Exception as e:
                            print(f"  ✗ Failed to register {attr_value.qualified_name}: {e}")
        
        # #region agent log
        cog_scan_time = time.perf_counter() - cog_scan_start
        total_time = time.perf_counter() - start_time
        try:
            with open(r"c:\Users\Yuu\Documents\IslaBotV3\.cursor\debug.log", "a", encoding="utf-8") as f:
                f.write(json.dumps({"sessionId": "perf-cleanup", "runId": "run1", "hypothesisId": "A", "location": "bot.py:_register_cog_commands", "message": "Performance measurement", "data": {"cog_count": cog_count, "attr_checks": attr_checks, "cog_scan_ms": cog_scan_time * 1000, "total_ms": total_time * 1000}, "timestamp": int(time.time() * 1000)}) + "\n")
        except Exception:
            pass
        # #endregion
        
        if registered_count > 0:
            print(f"Manually registered {registered_count} command(s)")
        
        if not existing_commands:
            _print_section("⚠ CRITICAL WARNING: NO COMMANDS FOUND IN TREE!")
            print("Check: Are cogs loading? Do cogs have @app_commands.command()?")
            print()
        
        # Verify data collection listeners (use module-level constant to avoid recreating dict)
        listeners_active = [desc for cog_name, desc in COG_LISTENER_NAMES.items() if self.get_cog(cog_name)]
        
        if listeners_active:
            print(f"✓ Data collection active: {', '.join(listeners_active)}")
        
        # Verify database
        try:
            if await self.db.fetchone("SELECT 1 as test"):
                print("✓ Database connection verified")
        except Exception as e:
            print(f"⚠ Warning: Database health check failed: {e}")

    async def on_ready(self):
        """Called when the bot is ready. Register and sync commands."""
        _print_section()
        print(f"Bot is ready! Logged in as {self.user} (ID: {self.user.id})")
        print(f"Connected to {len(self.guilds)} guild(s)")
        print()
        
        if not self._commands_synced:
            print("Registering and syncing commands...")
            # Cache command list to avoid duplicate tree walks
            all_commands_list = [cmd.qualified_name for cmd in self.tree.walk_commands()]
            all_commands_set = set(all_commands_list)
            await self._register_cog_commands(all_commands_set)
            await self._sync_commands(all_commands_list)
    
    async def on_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        """Global error handler for app commands."""
        error_messages = {
            app_commands.CommandOnCooldown: lambda e: f"This command is on cooldown. Try again in {e.retry_after:.1f} seconds.",
            app_commands.MissingPermissions: "You don't have permission to use this command.",
            app_commands.BotMissingPermissions: "I don't have the required permissions to execute this command.",
        }
        
        message = None
        for error_type, msg in error_messages.items():
            if isinstance(error, error_type):
                message = msg(error) if callable(msg) else msg
                break
        
        if message:
            try:
                await interaction.response.send_message(message, ephemeral=True)
            except Exception:
                try:
                    await interaction.followup.send(message, ephemeral=True)
                except Exception:
                    pass
        else:
            # Log unexpected errors
            print(f"Unhandled command error: {error}")
            traceback.print_exc()
            try:
                error_msg = "An error occurred while executing this command."
                if interaction.response.is_done():
                    await interaction.followup.send(error_msg, ephemeral=True)
                else:
                    await interaction.response.send_message(error_msg, ephemeral=True)
            except Exception:
                pass
    
    async def on_error(self, event_method: str, *args, **kwargs):
        """Global error handler for events."""
        print(f"Error in event {event_method}:")
        traceback.print_exc()

    async def close(self):
        await super().close()
        await self.db.close()


async def main():
    config_path = os.path.join(BOT_DIR, "config.yml")
    db_path = os.path.join(BOT_DIR, "islabot.sqlite3")
    
    # Create config from environment variables if it doesn't exist
    if not os.path.exists(config_path):
        _print_section("config.yml not found. Attempting to create from environment variables...")
        
        token = os.getenv("DISCORD_BOT_TOKEN")
        if not token:
            print("ERROR: config.yml file not found and DISCORD_BOT_TOKEN not set!")
            print(SEPARATOR)
            print(f"Expected location: {config_path}")
            print("\nTo fix this:")
            print("1. Create config.yml in the islabot/ directory, OR")
            print("2. Set DISCORD_BOT_TOKEN environment variable in Railway")
            print("\nExample config.yml structure:")
            print("  token: \"YOUR_BOT_TOKEN_HERE\"")
            print("  guilds:")
            print("    - YOUR_GUILD_ID")
            print(SEPARATOR)
            sys.exit(1)
        
        guild_id = os.getenv("DISCORD_GUILDS", "123456789012345678")
        config_content = DEFAULT_CONFIG_TEMPLATE.format(token=token, guild_id=guild_id)
        
        try:
            with open(config_path, "w", encoding="utf-8") as f:
                f.write(config_content)
            print(f"✓ Created config.yml from environment variables at {config_path}")
        except Exception as e:
            print(f"✗ Failed to create config.yml: {e}")
            sys.exit(1)
    
    cfg = Config.load(config_path)
    
    # Check if token is set
    token = cfg.get("token")
    if not token or token == "PUT_YOUR_BOT_TOKEN_HERE":
        _print_section("ERROR: Bot token not configured!")
        print("Please set your bot token in config.yml")
        sys.exit(1)
    
    db = Database(db_path)
    bot = IslaBot(cfg, db)
    
    # Retry logic for rate limiting
    max_retries = 5
    for attempt in range(max_retries):
        try:
            await bot.start(token)
            break
        except discord.HTTPException as e:
            if e.status == 429:
                if attempt < max_retries - 1:
                    wait_time = 5 * (2 ** attempt)  # Exponential backoff: 5, 10, 20, 40, 80 seconds
                    print(f"Rate limited (429). Waiting {wait_time} seconds before retry ({attempt + 1}/{max_retries})...")
                    await asyncio.sleep(wait_time)
                    continue
                print(f"ERROR: Rate limited after {max_retries} attempts. Please wait and try again later.")
                sys.exit(1)
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
            traceback.print_exc()
            raise


if __name__ == "__main__":
    asyncio.run(main())
