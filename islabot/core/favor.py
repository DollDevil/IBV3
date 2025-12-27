from __future__ import annotations
from core.tone import calculate_attraction, favor_stage_from_attraction, clamp

async def get_user_favor_stage(db, guild_id: int, user_id: int) -> int:
    """
    Get the current favor_stage for a user from the database.
    If not set, calculate it based on current stats.
    """
    row = await db.fetchone(
        "SELECT favor_stage, coins, lce FROM users WHERE guild_id=? AND user_id=?",
        (guild_id, user_id)
    )
    if not row:
        return 0
    
    # If favor_stage is already set and recently calculated, return it
    # Otherwise recalculate
    current_favor = int(row.get("favor_stage", 0))
    
    # For now, use coins/LCE as proxy until we have full obedience tracking
    coins = int(row.get("coins", 0))
    lce = int(row.get("lce", 0))
    
    # Simple calculation using coins as primary (can be enhanced later)
    # Stage thresholds: 0: <1k, 1: 1k-5k, 2: 5k-10k, 3: 10k-20k, 4: 20k+
    if coins < 1000:
        stage = 0
    elif coins < 5000:
        stage = 1
    elif coins < 10000:
        stage = 2
    elif coins < 20000:
        stage = 3
    else:
        stage = 4
    
    # Update if different
    if stage != current_favor:
        await db.execute(
            "UPDATE users SET favor_stage=? WHERE guild_id=? AND user_id=?",
            (stage, guild_id, user_id)
        )
    
    return stage

async def calculate_and_update_favor_stage(
    db,
    guild_id: int,
    user_id: int,
    coins: float = None,
    obedience_rate: float = 0.5,
    streak_days: int = 0,
    failures: int = 0
) -> int:
    """
    Calculate favor_stage using Attraction Meter formula and update database.
    
    Formula: attraction = (coins * 0.5) + (obedience_rate * 40) + (streak_days * 10) - (failures * 20)
    Stage: clamp(attraction // 5000, 0, 4)
    
    If coins is None, fetch from database.
    """
    if coins is None:
        row = await db.fetchone(
            "SELECT coins FROM users WHERE guild_id=? AND user_id=?",
            (guild_id, user_id)
        )
        coins = float(row["coins"]) if row else 0.0
    
    attraction = calculate_attraction(coins, obedience_rate, streak_days, failures)
    stage = favor_stage_from_attraction(attraction)
    stage = clamp(stage, 0, 4)
    
    await db.execute(
        "UPDATE users SET favor_stage=? WHERE guild_id=? AND user_id=?",
        (int(stage), guild_id, user_id)
    )
    
    return int(stage)

