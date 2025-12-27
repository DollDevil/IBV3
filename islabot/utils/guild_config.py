from __future__ import annotations
import time

def now_ts() -> int:
    return int(time.time())

async def cfg_get(db, guild_id: int, key: str, default: str = "") -> str:
    row = await db.fetchone("SELECT value FROM guild_config WHERE guild_id=? AND key=?", (guild_id, key))
    return str(row["value"]) if row else default

async def cfg_set(db, guild_id: int, key: str, value: str):
    await db.execute(
        """
        INSERT INTO guild_config(guild_id,key,value,updated_ts)
        VALUES(?,?,?,?)
        ON CONFLICT(guild_id,key) DO UPDATE SET value=excluded.value, updated_ts=excluded.updated_ts
        """,
        (guild_id, key, str(value), now_ts())
    )

