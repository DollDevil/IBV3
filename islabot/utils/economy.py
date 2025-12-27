from __future__ import annotations
import time
from dataclasses import dataclass

def now_ts() -> int:
    return int(time.time())

@dataclass
class Wallet:
    coins: int
    tax_debt: int
    last_tax_ts: int

async def ensure_wallet(db, guild_id: int, user_id: int):
    await db.execute(
        "INSERT OR IGNORE INTO economy_wallet(guild_id,user_id,coins,tax_debt,last_tax_ts) VALUES(?,?,0,0,0)",
        (guild_id, user_id)
    )

async def get_wallet(db, guild_id: int, user_id: int) -> Wallet:
    await ensure_wallet(db, guild_id, user_id)
    row = await db.fetchone(
        "SELECT coins,tax_debt,last_tax_ts FROM economy_wallet WHERE guild_id=? AND user_id=?",
        (guild_id, user_id)
    )
    return Wallet(int(row["coins"]), int(row["tax_debt"]), int(row["last_tax_ts"]))

async def add_coins(db, guild_id: int, user_id: int, delta: int, kind: str, reason: str = "", other_user_id: int | None = None):
    await ensure_wallet(db, guild_id, user_id)
    await db.execute(
        "UPDATE economy_wallet SET coins = coins + ? WHERE guild_id=? AND user_id=?",
        (delta, guild_id, user_id)
    )
    await db.execute(
        "INSERT INTO economy_ledger(guild_id,user_id,ts,delta,kind,reason,other_user_id) VALUES(?,?,?,?,?,?,?)",
        (guild_id, user_id, now_ts(), int(delta), kind, reason or "", other_user_id)
    )

async def set_tax_debt(db, guild_id: int, user_id: int, debt: int):
    await ensure_wallet(db, guild_id, user_id)
    await db.execute(
        "UPDATE economy_wallet SET tax_debt=? WHERE guild_id=? AND user_id=?",
        (int(debt), guild_id, user_id)
    )

async def get_recent_ledger(db, guild_id: int, user_id: int, limit: int = 20):
    return await db.fetchall(
        """
        SELECT ts, delta, kind, reason, other_user_id
        FROM economy_ledger
        WHERE guild_id=? AND user_id=?
        ORDER BY ts DESC
        LIMIT ?
        """,
        (guild_id, user_id, int(limit))
    )

