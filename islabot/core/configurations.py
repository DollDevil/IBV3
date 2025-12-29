"""
Configuration and service modules.
Consolidates: config, channel_cfg, features, flags, ranks
"""

from __future__ import annotations
import yaml
from typing import Any

# ============================================================================
# CONFIG (from config.py)
# ============================================================================

class Config(dict):
    @staticmethod
    def load(path: str) -> "Config":
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return Config(data)

    def get(self, *keys, default=None):
        cur: Any = self
        for k in keys:
            if isinstance(cur, dict) and k in cur:
                cur = cur[k]
            else:
                return default
        return cur

# ============================================================================
# CHANNEL CONFIG SERVICE (from channel_cfg.py)
# ============================================================================

class ChannelConfigService:
    def __init__(self, db):
        self.db = db

    async def get(self, gid: int, cid: int, key: str, default: str | None = None) -> str | None:
        """Get channel config value."""
        row = await self.db.fetchone(
            "SELECT value FROM channel_config WHERE guild_id=? AND channel_id=? AND key=?",
            (gid, cid, key),
        )
        return row["value"] if row else default

    async def set(self, gid: int, cid: int, key: str, value: str):
        """Set channel config value."""
        await self.db.execute(
            """INSERT INTO channel_config(guild_id,channel_id,key,value)
               VALUES(?,?,?,?)
               ON CONFLICT(guild_id,channel_id,key) DO UPDATE SET value=excluded.value""",
            (gid, cid, key, value),
        )

    async def delete(self, gid: int, cid: int, key: str):
        """Delete channel config key."""
        await self.db.execute(
            "DELETE FROM channel_config WHERE guild_id=? AND channel_id=? AND key=?",
            (gid, cid, key),
        )

# ============================================================================
# FEATURES (from features.py)
# ============================================================================

FEATURES = {
    "orders": "Orders module",
    "shop": "Shop module",
    "tributes": "Tributes module",
    "events": "Seasonal events module",
    "leaderboard": "Spotlight/leaderboard module",
    "economy": "Economy module",
    "profile": "Profile module",
    "public_callouts": "Any public callout posting",
}

DEFAULT_ENABLED = {k: True for k in FEATURES.keys()}

# ============================================================================
# FLAGS SERVICE (from flags.py)
# ============================================================================

class FlagService:
    def __init__(self, db):
        self.db = db

    async def is_enabled(self, guild_id: int, feature: str, channel_id: int | None = None) -> bool:
        """Check if a feature is enabled at guild or channel level."""
        # Channel override first
        if channel_id is not None:
            row = await self.db.fetchone(
                "SELECT enabled FROM feature_flags WHERE guild_id=? AND scope='channel' AND scope_id=? AND feature=?",
                (guild_id, channel_id, feature),
            )
            if row is not None:
                return int(row["enabled"]) == 1

        # Guild default override
        row = await self.db.fetchone(
            "SELECT enabled FROM feature_flags WHERE guild_id=? AND scope='guild' AND scope_id=? AND feature=?",
            (guild_id, guild_id, feature),
        )
        if row is not None:
            return int(row["enabled"]) == 1

        # Default if not configured
        return True

    async def set_guild(self, guild_id: int, feature: str, enabled: bool):
        """Set feature flag at guild level."""
        await self.db.execute(
            """INSERT OR REPLACE INTO feature_flags(guild_id,scope,scope_id,feature,enabled)
               VALUES(?,?,?,?,?)""",
            (guild_id, "guild", guild_id, feature, 1 if enabled else 0),
        )

    async def set_channel(self, guild_id: int, channel_id: int, feature: str, enabled: bool):
        """Set feature flag at channel level."""
        await self.db.execute(
            """INSERT OR REPLACE INTO feature_flags(guild_id,scope,scope_id,feature,enabled)
               VALUES(?,?,?,?,?)""",
            (guild_id, "channel", channel_id, feature, 1 if enabled else 0),
        )

# ============================================================================
# RANKS (from ranks.py)
# ============================================================================

RANKS = [
    ("Stray", 0, 500),
    ("Worthless Pup", 500, 1000),
    ("Leashed Pup", 1000, 5000),
    ("Collared Dog", 5000, 10000),
    ("Trained Pet", 10000, 15000),
    ("Devoted Dog", 15000, 20000),
    ("Cherished Pet", 20000, 50000),
    ("Favorite Puppy", 50000, 10**18),
]

def rank_from_lce(lce: int) -> str:
    for name, lo, hi in RANKS:
        if lo <= lce < hi:
            return name
    return "Stray"

