from __future__ import annotations

import asyncio
import time
import discord
from discord.ext import commands

from core.config import Config
from core.db import Database

COGS = [
    "cogs.alive",
    "cogs.moderation",
    "cogs.onboarding",
    "cogs.economy",
    "cogs.progression",
    "cogs.shop",
    "cogs.profile",
    "cogs.voice_stats",
    "cogs.casino_core",
    "cogs.casino_games",
    "cogs.casino_bigwin_dm",
    "cogs.casino_royalty",
    "cogs.casino_daily_recap",
    "cogs.orders",
    "cogs.events",
    # Event system (load in order: voice -> message -> scheduler -> commands)
    "cogs.voice_tracker",
    "cogs.message_tracker",
    "cogs.event_scheduler",
    "cogs.event_group",  # /event group with subcommands
    "cogs.daily_presence",
    "cogs.vacation_watch",
    "cogs.safeword",
    "cogs.info_unified",
    "cogs.quarterly_tax",
    "cogs.privacy",
    "cogs.admin_tools",
    "cogs.core_commands",
    "cogs.coins_group",
    "cogs.orders_group",
    "cogs.discipline_group",
    "cogs.duel_cog",
    "cogs.custom_events_group",
    "cogs.announce_and_remind",
    "cogs.config_group",
    "cogs.context_apps",
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
        self.personality = Personality(path="personality.json", fallback=DEFAULT_POOLS)
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
    cfg = Config.load("config.yml")
    db = Database("islabot.sqlite3")
    bot = IslaBot(cfg, db)
    await bot.start(cfg["token"])

if __name__ == "__main__":
    asyncio.run(main())

