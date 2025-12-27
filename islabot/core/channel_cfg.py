from __future__ import annotations

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

