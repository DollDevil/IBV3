from __future__ import annotations

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

