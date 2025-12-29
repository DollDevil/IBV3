"""
Event system modules.
Consolidates: boss_damage, event_scoring, event_thumbs, holiday_configs, seasonal_configs, seasonal_tones
"""

from __future__ import annotations
import math
import json
from typing import Dict, Tuple, List, Any
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from .utility import now_ts

UK_TZ = ZoneInfo("Europe/London")



# ============================================================================
# BOSS DAMAGE
# ============================================================================


"""
Unified Boss Damage Formula Implementation

Implements the standardized boss damage calculation system for holiday weeks
and seasonal finales using logarithmic scaling (no caps, diminishing returns).
"""

# =========================================================
# Constants
# =========================================================

# Logarithmic scaling k-values (controls growth rate)
K_TS = 25   # tokens
K_CN = 10000   # coins (casino net)
K_CW = 20000   # coins (casino wager)
K_M = 20   # messages
K_V = 30   # minutes (voice)

# Base damage multipliers
BASE_TS = 260  # tokens spent
BASE_RC = 160  # ritual completion (0 or 1)
BASE_CN = 110  # casino net
BASE_CW = 95   # casino wager
BASE_M = 80    # messages
BASE_V = 80    # voice minutes

# Participation bonus (devotion calculation)
PARTICIPATION_DEVOTION = {
    "tokens": 2,      # I(TS > 0)
    "ritual": 3,      # RC
    "messages": 1,    # I(M >= 1)
    "voice": 1,       # I(V >= 10)
    "casino_wager": 1,  # I(CW >= 1000)
}

# Voice AFK reduction thresholds
VOICE_AFK_THRESHOLD_MINUTES = 60  # after 60 min without refresh
VOICE_AFK_MULTIPLIER = 0.35  # reduced contribution after threshold

# Message cooldown for boss damage
MESSAGE_COOLDOWN_SECONDS = 300  # 5 minutes (one eligible message per 5 min per user)

# =========================================================
# Helper Functions
# =========================================================

def g_log_scale(x: float, k: float) -> float:
    """
    Logarithmic scaling function (no caps, diminishing returns).
    
    g(x, k) = ln(1 + x / k)
    
    Examples:
    - x = k → ~0.693 (70% value)
    - x = 2*k → ~1.099 (110% value)
    - x = 5*k → ~1.609 (161% value)
    - x = 10*k → ~2.398 (240% value)
    
    This provides strong early value that tapers off gracefully.
    """
    if k <= 0:
        return 0.0
    if x <= 0:
        return 0.0
    return math.log(1.0 + (x / k))


def clamp(x: float, lo: float, hi: float) -> float:
    """Clamp value between lo and hi."""
    return max(lo, min(hi, x))


def calculate_daily_damage(
    tokens_spent: float,
    ritual_completed: int,
    casino_net: float,
    casino_wager: float,
    messages: float,
    voice_effective_minutes: float,
) -> Tuple[float, int]:
    """
    Calculate daily damage points for a user using logarithmic scaling.
    
    Args:
        tokens_spent: Event tokens spent (TS)
        ritual_completed: Ritual completions 0 or 1 (RC)
        casino_net: Casino net profit/loss (CN) - use max(CN, 0) to avoid negative
        casino_wager: Total casino wager (CW)
        messages: Eligible message count (M)
        voice_effective_minutes: Voice minutes after AFK reduction (V_eff)
    
    Returns:
        (damage_points, devotion_points)
    """
    # Apply logarithmic scaling to each bucket
    ts_scaled = g_log_scale(tokens_spent, K_TS)
    cn_scaled = g_log_scale(max(casino_net, 0.0), K_CN)  # Clamp net to 0 minimum
    cw_scaled = g_log_scale(casino_wager, K_CW)
    m_scaled = g_log_scale(messages, K_M)
    v_scaled = g_log_scale(voice_effective_minutes, K_V)
    
    # Calculate base damage
    dp = (
        BASE_TS * ts_scaled +
        BASE_RC * (1.0 if ritual_completed > 0 else 0.0) +
        BASE_CN * cn_scaled +
        BASE_CW * cw_scaled +
        BASE_M * m_scaled +
        BASE_V * v_scaled
    )
    
    # Calculate devotion points (for leaderboard)
    dev_points = (
        PARTICIPATION_DEVOTION["tokens"] * (1 if tokens_spent > 0 else 0) +
        PARTICIPATION_DEVOTION["ritual"] * (1 if ritual_completed > 0 else 0) +
        PARTICIPATION_DEVOTION["messages"] * (1 if messages >= 1 else 0) +
        PARTICIPATION_DEVOTION["voice"] * (1 if voice_effective_minutes >= 10 else 0) +
        PARTICIPATION_DEVOTION["casino_wager"] * (1 if casino_wager >= 1000 else 0)
    )
    
    return (dp, dev_points)


def calculate_voice_effective_minutes(
    total_voice_minutes: float,
    minutes_since_last_refresh: float,
) -> float:
    """
    Calculate effective voice minutes after AFK reduction.
    
    If user has been in voice > 60 minutes without sending a message,
    reduce contribution by multiplier.
    
    Args:
        total_voice_minutes: Total voice minutes in session
        minutes_since_last_refresh: Minutes since last eligible message
    
    Returns:
        Effective voice minutes (V_eff)
    """
    if minutes_since_last_refresh <= VOICE_AFK_THRESHOLD_MINUTES:
        multiplier = 1.0
    else:
        multiplier = VOICE_AFK_MULTIPLIER
    
    return total_voice_minutes * multiplier


def should_send_voice_reduction_warning(
    minutes_since_last_refresh: float,
    warning_sent_today: bool,
) -> bool:
    """
    Check if we should send voice reduction warning.
    
    Warn when user crosses 60-minute threshold without refresh.
    Only send once per day per user.
    """
    if minutes_since_last_refresh <= VOICE_AFK_THRESHOLD_MINUTES:
        return False
    if warning_sent_today:
        return False
    return True


def calculate_global_scale(
    expected_daily_damage: float,
    actual_daily_damage: float,
) -> float:
    """
    Calculate global scaling factor to ensure boss dies on time.
    
    Scale = clamp(0.75, 1.35, ExpectedDailyDamage / ActualDailyDamageYesterday)
    """
    if actual_daily_damage <= 0:
        return 1.0
    
    raw_scale = expected_daily_damage / actual_daily_damage
    return clamp(raw_scale, 0.75, 1.35)


def calculate_boss_hp_from_users(user_count: int = 1000) -> int:
    """
    Recommended boss HP based on expected user count.
    Default: 3,500,000 for 1000 users.
    """
    base_hp = 3500000
    scale_factor = user_count / 1000.0
    return int(base_hp * scale_factor)


def calculate_expected_daily_damage(boss_hp: int, days: int = 7) -> float:
    """
    Calculate expected daily damage to ensure boss dies on time.
    Uses 6.2 days as the pacing target (allows some buffer).
    """
    return boss_hp / 6.2


def is_message_eligible_for_boss(
    channel_id: int,
    spam_channel_id: int,
    message_content: str,
) -> bool:
    """
    Check if a message should count for boss damage.
    
    Rules:
    - All channels except spam channel
    - No character limit
    - Cooldown is handled separately (one per 5 minutes per user)
    """
    if spam_channel_id and channel_id == spam_channel_id:
        return False
    
    # No character limit - all messages in eligible channels count
    # (cooldown is applied in tracking, not here)
    return True


def is_message_cooldown_ready(
    last_event_msg_ts: int,
    current_ts: int,
) -> bool:
    """
    Check if user's message cooldown is ready for boss damage.
    
    One eligible message counts per 5 minutes per user.
    """
    elapsed = current_ts - last_event_msg_ts
    return elapsed >= MESSAGE_COOLDOWN_SECONDS


def calculate_token_offering_damage(tokens_offered: int) -> float:
    """
    Calculate boss damage from token offerings (if implemented).
    
    This would be added directly to DP_user as a bonus.
    For now, tokens spent normally count via TS bucket.
    """
    # If implementing direct offerings:
    # Offer 10 tokens → + (10 * 22) raw damage
    # Offer 25 tokens → + (25 * 24) raw damage  
    # Offer 50 tokens → + (50 * 26) raw damage
    # Daily max: 250 tokens/user
    
    if tokens_offered <= 0:
        return 0.0
    
    tokens_capped = min(tokens_offered, 250)  # daily max
    
    # Determine multiplier based on bundle size
    if tokens_capped >= 50:
        multiplier = 26
    elif tokens_capped >= 25:
        multiplier = 24
    else:
        multiplier = 22
    
    return float(tokens_capped * multiplier)


# ============================================================================
# EVENT SCORING
# ============================================================================


"""
Event Scoring (ES) system.
Converts user activity into Event Score with caps.
"""

UK_TZ = ZoneInfo("Europe/London")


def calculate_es(msg_count: int, vc_minutes: int, casino_wagered: int, orders_completed: int, rituals_completed: int) -> int:
    """
    Calculate Event Score from activity metrics.
    
    Rules:
    - Messages: +1 ES each (cap 30/hour)
    - VC minutes: +2 ES each (cap 60/day = 120 ES/day)
    - Casino wager: +1 ES per 200 Coins (cap 20k/day = 100 ES/day)
    - Order completion: +25 ES (uncapped)
    - Ritual completion: +120 ES (uncapped)
    """
    # Messages: 1 ES each, cap 30/hour (we apply hourly cap in aggregation)
    msg_es = min(msg_count, 30)
    
    # VC: 2 ES per minute, cap 60 minutes/day (120 ES/day)
    vc_es = min(vc_minutes, 60) * 2
    
    # Casino: 1 ES per 200 Coins, cap 20,000 Coins/day (100 ES/day)
    casino_es = min(casino_wagered // 200, 100)
    
    # Orders: 25 ES each (uncapped)
    orders_es = orders_completed * 25
    
    # Rituals: 120 ES each (uncapped)
    rituals_es = rituals_completed * 120
    
    total = msg_es + vc_es + casino_es + orders_es + rituals_es
    return total


def reset_hourly_caps(breakdown_json: str, last_reset_ts: int) -> dict:
    """
    Reset hourly caps if needed.
    Returns updated breakdown dict.
    """
    now = now_ts()
    hour_ago = now - 3600
    
    try:
        breakdown = json.loads(breakdown_json) if breakdown_json else {}
    except Exception:
        breakdown = {}
    
    # If last reset was more than an hour ago, reset hourly counters
    if last_reset_ts < hour_ago:
        breakdown["msg_count_hour"] = 0
        breakdown["last_hour_reset_ts"] = now
    
    return breakdown


def reset_daily_caps(breakdown_json: str, last_reset_ts: int) -> dict:
    """
    Reset daily caps if needed.
    Returns updated breakdown dict.
    """
    now = now_ts()
    now_dt = datetime.fromtimestamp(now, tz=UK_TZ)
    today_start = now_dt.replace(hour=0, minute=0, second=0, microsecond=0)
    today_start_ts = int(today_start.timestamp())
    
    try:
        breakdown = json.loads(breakdown_json) if breakdown_json else {}
    except Exception:
        breakdown = {}
    
    # If last reset was before today, reset daily counters
    if last_reset_ts < today_start_ts:
        breakdown["vc_minutes_today"] = 0
        breakdown["casino_wagered_today"] = 0
        breakdown["last_day_reset_ts"] = today_start_ts
    
    return breakdown


def apply_es_caps(breakdown: dict, new_msg: int, new_vc: int, new_casino: int) -> tuple[int, int, int]:
    """
    Apply caps and return capped values for ES calculation.
    Returns: (capped_msg, capped_vc_minutes, capped_casino_wagered)
    """
    # Messages: cap at 30/hour
    msg_count_hour = breakdown.get("msg_count_hour", 0)
    capped_msg = min(new_msg, max(0, 30 - msg_count_hour))
    breakdown["msg_count_hour"] = msg_count_hour + capped_msg
    
    # VC: cap at 60 minutes/day
    vc_minutes_today = breakdown.get("vc_minutes_today", 0)
    capped_vc = min(new_vc, max(0, 60 - vc_minutes_today))
    breakdown["vc_minutes_today"] = vc_minutes_today + capped_vc
    
    # Casino: cap at 20,000 Coins/day
    casino_wagered_today = breakdown.get("casino_wagered_today", 0)
    capped_casino = min(new_casino, max(0, 20000 - casino_wagered_today))
    breakdown["casino_wagered_today"] = casino_wagered_today + capped_casino
    
    return capped_msg, capped_vc, capped_casino


# ============================================================================
# EVENT THUMBS
# ============================================================================


"""
Thumbnail placeholder system for events.
Defines keys that map to seasonal thumbnails (URLs filled later in config).
"""

# Universal thumbnails (always available)
THUMB_NEUTRAL = "THUMB_NEUTRAL"
THUMB_SMIRK_DOMINANT = "THUMB_SMIRK_DOMINANT"
THUMB_INTRIGUED = "THUMB_INTRIGUED"
THUMB_DISPLEASED = "THUMB_DISPLEASED"
THUMB_LAUGHING = "THUMB_LAUGHING"

# Boss Fight thumbnails
BOSS_START_DOMINANT = "BOSS_START__DOMINANT"
BOSS_PHASE2_INTRIGUED = "BOSS_PHASE2__INTRIGUED"
BOSS_PHASE3_DISPLEASED = "BOSS_PHASE3__DISPLEASED"
BOSS_FINAL_INTENSE = "BOSS_FINAL__INTENSE"
BOSS_KILL_LAUGHING = "BOSS_KILL__LAUGHING"

# Questboard thumbnails
QUESTBOARD_DAILY_NEUTRAL = "QUESTBOARD_DAILY__NEUTRAL"
QUESTBOARD_WEEKLY_SMIRK = "QUESTBOARD_WEEKLY__SMIRK"
QUESTBOARD_ELITE_INTRIGUED = "QUESTBOARD_ELITE__INTRIGUED"

# Season wrapper thumbnails
SEASON_LAUNCH_DOMINANT = "SEASON_LAUNCH__DOMINANT"
SEASON_MID_NEUTRAL = "SEASON_MID__NEUTRAL"
SEASON_DROP_INTRIGUED = "SEASON_DROP__INTRIGUED"
SEASON_FINALE_INTENSE = "SEASON_FINALE__INTENSE"
SEASON_AWARDS_LAUGHING = "SEASON_AWARDS__LAUGHING"
SEASON_AWARDS_SMIRK = "SEASON_AWARDS__SMIRK"

# Holiday week thumbnails
HOLIDAY_LAUNCH_THEMED_DOMINANT = "HOLIDAY_LAUNCH__THEMED_DOMINANT"
HOLIDAY_MID_THEMED_INTRIGUED = "HOLIDAY_MID__THEMED_INTRIGUED"
HOLIDAY_BOSS_THEMED_INTENSE = "HOLIDAY_BOSS__THEMED_INTENSE"
HOLIDAY_FINALE_THEMED_LAUGHING = "HOLIDAY_FINALE__THEMED_LAUGHING"

# Store drops
DROP_REVEAL_INTRIGUED = "DROP_REVEAL__INTRIGUED"
DROP_LAST_CALL_DISPLEASED = "DROP_LAST_CALL__DISPLEASED"
DROP_SOLD_OUT_LAUGHING = "DROP_SOLD_OUT__LAUGHING"


def get_thumb_url(config_json: dict, key: str) -> str:
    """
    Get thumbnail URL from event config, fallback to THUMB_NEUTRAL.
    Returns empty string if not configured (placeholder).
    """
    thumbs = config_json.get("thumbs", {})
    url = thumbs.get(key, "")
    if not url:
        # Fallback to neutral
        url = thumbs.get(THUMB_NEUTRAL, "")
    return url


def default_thumb_config() -> dict:
    """
    Returns default thumbnail config with empty URLs (placeholders).
    """
    return {
        "thumbs": {
            THUMB_NEUTRAL: "",
            THUMB_SMIRK_DOMINANT: "",
            THUMB_INTRIGUED: "",
            THUMB_DISPLEASED: "",
            THUMB_LAUGHING: "",
            BOSS_START_DOMINANT: "",
            BOSS_PHASE2_INTRIGUED: "",
            BOSS_PHASE3_DISPLEASED: "",
            BOSS_FINAL_INTENSE: "",
            BOSS_KILL_LAUGHING: "",
            QUESTBOARD_DAILY_NEUTRAL: "",
            QUESTBOARD_WEEKLY_SMIRK: "",
            QUESTBOARD_ELITE_INTRIGUED: "",
            SEASON_LAUNCH_DOMINANT: "",
            SEASON_MID_NEUTRAL: "",
            SEASON_DROP_INTRIGUED: "",
            SEASON_FINALE_INTENSE: "",
            SEASON_AWARDS_LAUGHING: "",
            SEASON_AWARDS_SMIRK: "",
            HOLIDAY_LAUNCH_THEMED_DOMINANT: "",
            HOLIDAY_MID_THEMED_INTRIGUED: "",
            HOLIDAY_BOSS_THEMED_INTENSE: "",
            HOLIDAY_FINALE_THEMED_LAUGHING: "",
            DROP_REVEAL_INTRIGUED: "",
            DROP_LAST_CALL_DISPLEASED: "",
            DROP_SOLD_OUT_LAUGHING: "",
        }
    }


# ============================================================================
# HOLIDAY CONFIGS
# ============================================================================


"""
Holiday Week Event Configurations

Defines 6 week-long holiday events that auto-start on fixed calendar dates.
Each event includes tokens, rituals, boss fights, shop items, easter eggs, and milestones.
"""

# =========================================================
# HOLIDAY WEEK EVENT TEMPLATES
# =========================================================

VALENTINES_CONFIG = {
    "id": "valentines_week",
    "name": "Valentine's Week",
    "type": "holiday_week",
    "theme": "romantic_possession",
    "duration_days": 7,
    "date_range": ("02-08", "02-14"),  # Feb 8-14
    "climax_day": "02-14",  # Feb 14
    
    "token_name": "Heart Tokens",
    "ritual_name": "Confession Yield",
    "boss_name": "Isla's Thorned Heart",
    
    "damage_weights": {
        "messages": 10,
        "vc_minutes": 2,
        "wager_coins": 0.2,
        "orders": 40,
        "rituals": 40,
        "tributes": 60,
    },
    
    "milestones": [
        {
            "pct": 80,
            "key": "first_flutter",
            "name": "First Flutter",
            "rewards": {
                "tokens": 0,
                "shop_teaser": True,
            },
            "announce": True,
        },
        {
            "pct": 60,
            "key": "rising_pulse",
            "name": "Rising Pulse",
            "rewards": {
                "tokens": 0,
                "elite_quests": 2,
            },
            "announce": True,
        },
        {
            "pct": 40,
            "key": "heart_whisper",
            "name": "Heart Whisper",
            "rewards": {
                "tokens": 0,
                "dm_whisper": True,
            },
            "announce": True,
        },
        {
            "pct": 20,
            "key": "overheat_edge",
            "name": "Overheat Edge",
            "rewards": {
                "tokens": 0,
                "damage_multiplier": 1.5,
            },
            "announce": True,
        },
        {
            "pct": 0,
            "key": "eternal_valentine",
            "name": "Eternal Valentine",
            "rewards": {
                "tokens": 0,
                "badge": {"name": "Eternal Valentine", "all": True},
                "role": {"name": "Isla's Private Valentine", "top": 10},
                "private_dm": {"name": "Isla's Private Valentine", "top": 10},
            },
            "announce": True,
        },
    ],
    
    "easter_egg": {
        "key": "hidden_heart",
        "name": "Hidden Heart",
        "trigger_phrase": "deepest confession",
        "activation_day": "02-14",
        "reward_dm": "valentine_private_dm",
    },
    
    "special_roles": [
        {"name": "Heart Piercer", "top": 5},
        {"name": "Isla's Private Valentine", "top": 10},
    ],
    
    "shop_items": [
        {"item_id": "collar_thorned_valentine", "name": "Thorned Collar (Valentine)", "tier": "limited"},
        {"item_id": "badge_pierced_heart", "name": "Pierced Heart Badge", "tier": "limited"},
    ],
    
    "isla_voice_start": {
        4: "Valentine's week. Try to reach my heart.",
    },
}

EASTER_CONFIG = {
    "id": "easter_week",
    "name": "Easter Week",
    "type": "holiday_week",
    "theme": "rebirth_awakening",
    "duration_days": 7,
    "date_range": ("EASTER-3", "EASTER"),  # 3 days before Easter to Easter Sunday
    "climax_day": "EASTER",
    
    "token_name": "Blossom Tokens",
    "ritual_name": "Egg Hunt Awakening",
    "boss_name": "Isla's Buried Heart",
    
    "damage_weights": {
        "messages": 10,
        "vc_minutes": 2,
        "wager_coins": 0.2,
        "orders": 40,
        "rituals": 40,
        "tributes": 60,
    },
    
    "milestones": [
        {
            "pct": 80,
            "key": "first_petal",
            "name": "First Petal",
            "rewards": {
                "tokens": 0,
                "shop_teaser": True,
            },
            "announce": True,
        },
        {
            "pct": 60,
            "key": "rising_awakening",
            "name": "Rising Awakening",
            "rewards": {
                "tokens": 0,
                "elite_quests": 2,
            },
            "announce": True,
        },
        {
            "pct": 40,
            "key": "blossom_whisper",
            "name": "Blossom Whisper",
            "rewards": {
                "tokens": 0,
                "dm_whisper": True,
            },
            "announce": True,
        },
        {
            "pct": 20,
            "key": "overbloom_edge",
            "name": "Overbloom Edge",
            "rewards": {
                "tokens": 0,
                "damage_multiplier": 1.5,
            },
            "announce": True,
        },
        {
            "pct": 0,
            "key": "eternal_rebirth",
            "name": "Eternal Rebirth",
            "rewards": {
                "tokens": 0,
                "badge": {"name": "Eternal Rebirth", "all": True},
                "role": {"name": "Isla's Resurrected Pet", "top": 10},
                "private_dm": {"name": "Isla's Rebirth", "top": 10},
            },
            "announce": True,
        },
    ],
    
    "easter_egg": {
        "key": "golden_blossom",
        "name": "Golden Blossom",
        "trigger_phrase": "awaken me",
        "activation_day": "EASTER",
        "reward_dm": "rebirth_dm",
    },
    
    "special_roles": [
        {"name": "Isla's Resurrected Pet", "top": 10},
    ],
    
    "shop_items": [
        {"item_id": "collar_blossom_easter", "name": "Blossom Collar", "tier": "limited"},
        {"item_id": "badge_awakened", "name": "Awakened Badge", "tier": "limited"},
    ],
    
    "isla_voice_start": {
        4: "Easter week. Make me bloom again.",
    },
}

MIDSUMMER_CONFIG = {
    "id": "midsummer_week",
    "name": "Midsummer Week",
    "type": "holiday_week",
    "theme": "peak_intensity",
    "duration_days": 7,
    "date_range": ("06-15", "06-21"),  # June 15-21 (solstice)
    "climax_day": "06-21",
    
    "token_name": "Blaze Tokens",
    "ritual_name": "Solstice Overload",
    "boss_name": "Isla's Solstice Inferno",
    
    "damage_weights": {
        "messages": 10,
        "vc_minutes": 2,
        "wager_coins": 0.2,
        "orders": 40,
        "rituals": 40,
        "tributes": 60,
    },
    
    "milestones": [
        {
            "pct": 80,
            "key": "first_ember",
            "name": "First Ember",
            "rewards": {
                "tokens": 0,
                "shop_teaser": True,
            },
            "announce": True,
        },
        {
            "pct": 60,
            "key": "rising_solstice",
            "name": "Rising Solstice",
            "rewards": {
                "tokens": 0,
                "elite_quests": 2,
            },
            "announce": True,
        },
        {
            "pct": 40,
            "key": "blaze_whisper",
            "name": "Blaze Whisper",
            "rewards": {
                "tokens": 0,
                "dm_whisper": True,
            },
            "announce": True,
        },
        {
            "pct": 20,
            "key": "overblaze_edge",
            "name": "Overblaze Edge",
            "rewards": {
                "tokens": 0,
                "damage_multiplier": 1.5,
            },
            "announce": True,
        },
        {
            "pct": 0,
            "key": "eternal_solstice",
            "name": "Eternal Solstice",
            "rewards": {
                "tokens": 0,
                "badge": {"name": "Eternal Solstice", "all": True},
                "role": {"name": "Isla's Solstice Possession", "top": 10},
                "private_dm": {"name": "Isla's Solstice", "top": 10},
            },
            "announce": True,
        },
    ],
    
    "easter_egg": {
        "key": "solstice_inferno",
        "name": "Solstice Inferno",
        "trigger_phrase": "overheat me",
        "activation_day": "06-21",
        "reward_dm": "inferno_dm",
    },
    
    "special_roles": [
        {"name": "Isla's Solstice Possession", "top": 10},
    ],
    
    "shop_items": [
        {"item_id": "collar_solstice_flame", "name": "Solstice Flame Collar", "tier": "limited"},
        {"item_id": "badge_peak_blaze", "name": "Peak Blaze Badge", "tier": "limited"},
    ],
    
    "isla_voice_start": {
        4: "Midsummer week. Push the heat.",
    },
}

HARVEST_CONFIG = {
    "id": "harvest_week",
    "name": "Harvest Week",
    "type": "holiday_week",
    "theme": "full_yield",
    "duration_days": 7,
    "date_range": ("09-19", "09-25"),  # Sep 19-25 (around equinox)
    "climax_day": "09-25",
    
    "token_name": "Harvest Tokens",
    "ritual_name": "Bounty Yield",
    "boss_name": "Isla's Harvest Heart",
    
    "damage_weights": {
        "messages": 10,
        "vc_minutes": 2,
        "wager_coins": 0.2,
        "orders": 40,
        "rituals": 40,
        "tributes": 60,
    },
    
    "milestones": [
        {
            "pct": 80,
            "key": "first_yield",
            "name": "First Yield",
            "rewards": {
                "tokens": 0,
                "shop_teaser": True,
            },
            "announce": True,
        },
        {
            "pct": 60,
            "key": "rising_bounty",
            "name": "Rising Bounty",
            "rewards": {
                "tokens": 0,
                "elite_quests": 2,
            },
            "announce": True,
        },
        {
            "pct": 40,
            "key": "harvest_whisper",
            "name": "Harvest Whisper",
            "rewards": {
                "tokens": 0,
                "dm_whisper": True,
            },
            "announce": True,
        },
        {
            "pct": 20,
            "key": "overharvest_edge",
            "name": "Overharvest Edge",
            "rewards": {
                "tokens": 0,
                "damage_multiplier": 1.5,
            },
            "announce": True,
        },
        {
            "pct": 0,
            "key": "eternal_harvest",
            "name": "Eternal Harvest",
            "rewards": {
                "tokens": 0,
                "badge": {"name": "Eternal Harvest", "all": True},
                "role": {"name": "Isla's Harvest Possession", "top": 10},
                "private_dm": {"name": "Isla's Harvest", "top": 10},
            },
            "announce": True,
        },
    ],
    
    "easter_egg": {
        "key": "golden_harvest",
        "name": "Golden Harvest",
        "trigger_phrase": "reap me fully",
        "activation_day": "09-25",
        "reward_dm": "harvest_dm",
    },
    
    "special_roles": [
        {"name": "Isla's Harvest Possession", "top": 10},
    ],
    
    "shop_items": [
        {"item_id": "collar_harvest_leaf", "name": "Harvest Leaf Collar", "tier": "limited"},
        {"item_id": "badge_bounty", "name": "Bounty Badge", "tier": "limited"},
    ],
    
    "isla_voice_start": {
        4: "Harvest week. Offer everything.",
    },
}

HALLOWEEN_CONFIG = {
    "id": "halloween_week",
    "name": "Halloween Week",
    "type": "holiday_week",
    "theme": "dark_haunting",
    "duration_days": 7,
    "date_range": ("10-25", "10-31"),  # Oct 25-31
    "climax_day": "10-31",
    
    "token_name": "Shadow Tokens",
    "ritual_name": "Haunt Drain",
    "boss_name": "Isla's Shadow Heart",
    
    "damage_weights": {
        "messages": 10,
        "vc_minutes": 2,
        "wager_coins": 0.2,
        "orders": 40,
        "rituals": 40,
        "tributes": 60,
    },
    
    "milestones": [
        {
            "pct": 80,
            "key": "first_haunt",
            "name": "First Haunt",
            "rewards": {
                "tokens": 0,
                "shop_teaser": True,
            },
            "announce": True,
        },
        {
            "pct": 60,
            "key": "rising_shadow",
            "name": "Rising Shadow",
            "rewards": {
                "tokens": 0,
                "elite_quests": 2,
            },
            "announce": True,
        },
        {
            "pct": 40,
            "key": "ghost_whisper",
            "name": "Ghost Whisper",
            "rewards": {
                "tokens": 0,
                "dm_whisper": True,
            },
            "announce": True,
        },
        {
            "pct": 20,
            "key": "overhaunt_edge",
            "name": "Overhaunt Edge",
            "rewards": {
                "tokens": 0,
                "damage_multiplier": 1.5,
            },
            "announce": True,
        },
        {
            "pct": 0,
            "key": "eternal_haunt",
            "name": "Eternal Haunt",
            "rewards": {
                "tokens": 0,
                "badge": {"name": "Eternal Haunt", "all": True},
                "role": {"name": "Isla's Shadow Pet", "top": 10},
                "private_dm": {"name": "Isla's Shadow", "top": 10},
            },
            "announce": True,
        },
    ],
    
    "easter_egg": {
        "key": "hidden_shadow",
        "name": "Hidden Shadow",
        "trigger_phrase": "haunt me deeply",
        "activation_day": "10-31",
        "reward_dm": "shadow_dm",
    },
    
    "special_roles": [
        {"name": "Isla's Shadow Pet", "top": 10},
    ],
    
    "shop_items": [
        {"item_id": "collar_shadow_halloween", "name": "Shadow Collar", "tier": "limited"},
        {"item_id": "badge_haunted", "name": "Haunted Badge", "tier": "limited"},
    ],
    
    "isla_voice_start": {
        4: "Halloween week. Come haunt me.",
    },
}

CHRISTMAS_CONFIG = {
    "id": "christmas_week",
    "name": "Christmas Week",
    "type": "holiday_week",
    "theme": "gifted_surrender",
    "duration_days": 7,
    "date_range": ("12-18", "12-24"),  # Dec 18-24
    "climax_day": "12-24",
    
    "token_name": "Gift Tokens",
    "ritual_name": "Naughty Gift Yield",
    "boss_name": "Isla's Frozen Heart",
    
    "damage_weights": {
        "messages": 10,
        "vc_minutes": 2,
        "wager_coins": 0.2,
        "orders": 40,
        "rituals": 40,
        "tributes": 60,
    },
    
    "milestones": [
        {
            "pct": 80,
            "key": "first_gift",
            "name": "First Gift",
            "rewards": {
                "tokens": 0,
                "shop_teaser": True,
            },
            "announce": True,
        },
        {
            "pct": 60,
            "key": "rising_warmth",
            "name": "Rising Warmth",
            "rewards": {
                "tokens": 0,
                "elite_quests": 2,
            },
            "announce": True,
        },
        {
            "pct": 40,
            "key": "thaw_whisper",
            "name": "Thaw Whisper",
            "rewards": {
                "tokens": 0,
                "dm_whisper": True,
            },
            "announce": True,
        },
        {
            "pct": 20,
            "key": "overgift_edge",
            "name": "Overgift Edge",
            "rewards": {
                "tokens": 0,
                "damage_multiplier": 1.5,
            },
            "announce": True,
        },
        {
            "pct": 0,
            "key": "eternal_gift",
            "name": "Eternal Gift",
            "rewards": {
                "tokens": 0,
                "badge": {"name": "Eternal Gift", "all": True},
                "role": {"name": "Isla's Unwrapped Pet", "top": 10},
                "private_dm": {"name": "Isla's Gift", "top": 10},
            },
            "announce": True,
        },
    ],
    
    "easter_egg": {
        "key": "hidden_gift",
        "name": "Hidden Gift",
        "trigger_phrase": "unwrap me completely",
        "activation_day": "12-24",
        "reward_dm": "gift_dm",
    },
    
    "special_roles": [
        {"name": "Isla's Unwrapped Pet", "top": 10},
    ],
    
    "shop_items": [
        {"item_id": "collar_festive_christmas", "name": "Festive Collar", "tier": "limited"},
        {"item_id": "badge_unwrapped", "name": "Unwrapped Badge", "tier": "limited"},
    ],
    
    "isla_voice_start": {
        4: "Christmas week. Unwrap me.",
    },
}

# Map holiday IDs to configs
HOLIDAY_CONFIGS: Dict[str, Dict[str, Any]] = {
    "valentines_week": VALENTINES_CONFIG,
    "easter_week": EASTER_CONFIG,
    "midsummer_week": MIDSUMMER_CONFIG,
    "harvest_week": HARVEST_CONFIG,
    "halloween_week": HALLOWEEN_CONFIG,
    "christmas_week": CHRISTMAS_CONFIG,
}

def get_holiday_config(holiday_id: str) -> Dict[str, Any] | None:
    """Get holiday configuration by ID."""
    return HOLIDAY_CONFIGS.get(holiday_id.lower())

def get_all_holidays() -> Dict[str, Dict[str, Any]]:
    """Get all holiday configurations."""
    return HOLIDAY_CONFIGS.copy()

def calculate_easter_date(year: int) -> tuple[int, int]:
    """
    Calculate Easter Sunday date for a given year using anonymous Gregorian algorithm.
    Returns (month, day) tuple.
    """
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return (month, day)

def parse_holiday_date(date_str: str, year: int) -> tuple[int, int, int]:
    """
    Parse holiday date string.
    Supports:
    - "MM-DD" format
    - "EASTER" (calculates Easter Sunday)
    - "EASTER-N" (N days before Easter)
    
    Returns (year, month, day) tuple.
    """
    if date_str.startswith("EASTER"):
        if date_str == "EASTER":
            month, day = calculate_easter_date(year)
            return (year, month, day)
        else:
            # "EASTER-N" format
            offset = int(date_str.split("-")[1])
            month, day = calculate_easter_date(year)
            from datetime import datetime, timedelta
            dt = datetime(year, month, day)
            dt = dt - timedelta(days=offset)
            return (dt.year, dt.month, dt.day)
    else:
        # "MM-DD" format
        parts = date_str.split("-")
        return (year, int(parts[0]), int(parts[1]))


# ============================================================================
# SEASONAL CONFIGS
# ============================================================================


"""
Seasonal Event Configurations

Defines the structure, milestones, rewards, and tone pools for each seasonal era.
"""

# =========================================================
# SEASONAL EVENT TEMPLATES
# =========================================================

SPRING_CONFIG = {
    "name": "Blooming Dominion",
    "type": "season",
    "duration_weeks": 6,
    "theme": "blooming",
    "aesthetic": {"color": "pastel_pink_green", "style": "floral"},
    "finale_week": 6,
    "finale_name": "Full Bloom Dominion",
    "boss_name": "Isla's Thorn Heart",
    "damage_weights": {
        "messages": 10,      # 1 message = 10 dmg
        "vc_minutes": 2,     # 1 VC minute = 2 dmg
        "wager_coins": 0.2,  # 100 wagered = 20 dmg
        "orders": 40,        # 1 order = 40 dmg
        "rituals": 40,       # 1 ritual = 40 dmg
        "tributes": 60,      # $10 equiv tribute = 60 dmg
    },
    "milestones": [
        {
            "pct": 80,
            "key": "first_petal",
            "name": "First Petal",
            "rewards": {
                "tokens": 0,
                "shop_teaser": True,
                "quest_token_boost": 1.10,  # +10% for 24h
                "role": {"name": "Petal", "count": 5, "random": True},
            },
            "announce": True,
        },
        {
            "pct": 60,
            "key": "rising_bloom",
            "name": "Rising Bloom",
            "rewards": {
                "tokens": 0,
                "elite_quests": 3,
                "vc_token_double": 48,  # hours
                "badge": {"name": "Rising Bloom", "top": 10},
            },
            "announce": True,
        },
        {
            "pct": 40,
            "key": "thorn_whisper",
            "name": "Thorn Whisper",
            "rewards": {
                "tokens": 0,
                "dm_whisper": True,  # personal seductive DM
                "casino_triple_payout": 24,  # hours, one game
                "shop_discount": 0.15,  # 15% off
            },
            "announce": True,
        },
        {
            "pct": 20,
            "key": "overbloom_edge",
            "name": "Overbloom Edge",
            "rewards": {
                "tokens": 0,
                "damage_multiplier": 1.5,  # all actions 1.5x dmg
                "cosmetic_preview": "Petal",
                "role": {"name": "Overbloom", "top": 20},
            },
            "announce": True,
        },
        {
            "pct": 0,
            "key": "eternal_bloom",
            "name": "Eternal Bloom",
            "rewards": {
                "tokens": 0,
                "badge": {"name": "Eternal Bloom", "all": True},
                "role": {"name": "Blooming Favorite", "top": 10},
                "private_dm": {"name": "Isla's Private Bloom", "top": 10},
            },
            "announce": True,
        },
    ],
    "easter_eggs": [
        {
            "key": "secret_blossom",
            "name": "Secret Blossom",
            "clue_triggers": ["BLOOMDEEPER", "awaken"],
            "activation_keywords": ["awaken my blossom", "secret petal"],
            "limit": 10,  # first 5-10 get full reward
            "dm_sequence": "secret_blossom_dm",
        },
    ],
    "weekly_ritual": {
        "name": "Petal Awakening",
        "type": "growth",
    },
    "token_name": "Petal Tokens",
}

SUMMER_CONFIG = {
    "name": "Sizzling Dominion",
    "type": "season",
    "duration_weeks": 6,
    "theme": "fiery",
    "aesthetic": {"color": "orange_red", "style": "glowing"},
    "finale_week": 4,  # Midsummer climax
    "finale_name": "Overload Inferno",
    "boss_name": "Isla's Inferno Heart",
    "damage_weights": {
        "messages": 10,
        "vc_minutes": 2,
        "wager_coins": 0.2,
        "orders": 40,
        "rituals": 40,
        "tributes": 60,
    },
    "milestones": [
        {
            "pct": 80,
            "key": "first_ember",
            "name": "First Ember",
            "rewards": {
                "tokens": 0,
                "shop_teaser": True,
                "casino_boost": 1.15,  # +15% for 24h
            },
            "announce": True,
        },
        {
            "pct": 60,
            "key": "rising_blaze",
            "name": "Rising Blaze",
            "rewards": {
                "tokens": 0,
                "elite_quests": 3,
                "wager_token_double": True,  # double wager tokens
            },
            "announce": True,
        },
        {
            "pct": 40,
            "key": "inferno_whisper",
            "name": "Inferno Whisper",
            "rewards": {
                "tokens": 0,
                "dm_whisper": True,
            },
            "announce": True,
        },
        {
            "pct": 20,
            "key": "overheat_edge",
            "name": "Overheat Edge",
            "rewards": {
                "tokens": 0,
                "damage_multiplier": 1.5,
            },
            "announce": True,
        },
        {
            "pct": 0,
            "key": "eternal_flame",
            "name": "Eternal Flame",
            "rewards": {
                "tokens": 0,
                "badge": {"name": "Eternal Flame", "all": True},
                "role": {"name": "Blazing Favorite", "top": 10},
                "private_dm": {"name": "Isla's Private Inferno", "top": 10},
            },
            "announce": True,
        },
    ],
    "easter_eggs": [
        {
            "key": "hidden_ember",
            "name": "Hidden Ember",
            "clue_triggers": ["EMBERDEEP", "ignite me"],
            "activation_keywords": ["ignite me"],
            "limit": 1,  # single winner
            "dm_sequence": "hidden_ember_dm",
            "date_restriction": "solstice",
        },
        {
            "key": "secret_flame",
            "name": "Secret Flame",
            "clue_triggers": ["FLAMEDEEP"],
            "activation_keywords": ["consume me"],
            "limit": 1,
            "dm_sequence": "secret_flame_dm",
        },
    ],
    "weekly_ritual": {
        "name": "Flame Endurance",
        "type": "risk",
    },
    "token_name": "Flame Tokens",
}

AUTUMN_CONFIG = {
    "name": "Falling Dominion",
    "type": "season",
    "duration_weeks": 6,
    "theme": "harvest",
    "aesthetic": {"color": "orange_brown", "style": "leaf_overlay"},
    "finale_week": 6,
    "finale_name": "Deep Fall Dominion",
    "boss_name": "Isla's Wither Heart",
    "damage_weights": {
        "messages": 10,
        "vc_minutes": 2,
        "wager_coins": 0.2,
        "orders": 40,
        "rituals": 40,
        "tributes": 60,
    },
    "milestones": [
        {
            "pct": 80,
            "key": "first_leaf",
            "name": "First Leaf",
            "rewards": {
                "tokens": 0,
                "shop_teaser": True,
                "tribute_boost": 1.15,  # +15% for 24h
            },
            "announce": True,
        },
        {
            "pct": 60,
            "key": "rising_fall",
            "name": "Rising Fall",
            "rewards": {
                "tokens": 0,
                "elite_quests": 3,
                "message_token_double": True,
            },
            "announce": True,
        },
        {
            "pct": 40,
            "key": "wither_whisper",
            "name": "Wither Whisper",
            "rewards": {
                "tokens": 0,
                "dm_whisper": True,
            },
            "announce": True,
        },
        {
            "pct": 20,
            "key": "overfall_edge",
            "name": "Overfall Edge",
            "rewards": {
                "tokens": 0,
                "damage_multiplier": 1.5,
            },
            "announce": True,
        },
        {
            "pct": 0,
            "key": "eternal_fall",
            "name": "Eternal Fall",
            "rewards": {
                "tokens": 0,
                "badge": {"name": "Eternal Fall", "all": True},
                "role": {"name": "Fallen Favorite", "top": 10},
                "private_dm": {"name": "Isla's Private Fall", "top": 10},
            },
            "announce": True,
        },
    ],
    "easter_eggs": [
        {
            "key": "hidden_leaf",
            "name": "Hidden Leaf",
            "clue_triggers": ["LEAFDEEP", "fall for me"],
            "activation_keywords": ["fall for me"],
            "limit": 1,
            "dm_sequence": "hidden_leaf_dm",
            "date_restriction": "halloween",  # Oct 31
        },
        {
            "key": "secret_wither",
            "name": "Secret Wither",
            "clue_triggers": ["WITHERDEEP"],
            "activation_keywords": ["wither in me"],
            "limit": 1,
            "dm_sequence": "secret_wither_dm",
            "date_restriction": "nov_5",
        },
    ],
    "weekly_ritual": {
        "name": "Harvest Endurance",
        "type": "collection",
    },
    "token_name": "Leaf Tokens",
}

WINTER_CONFIG = {
    "name": "Frozen Dominion",
    "type": "season",
    "duration_weeks": 6,
    "theme": "frost",
    "aesthetic": {"color": "blue_white", "style": "frozen"},
    "finale_week": 6,
    "finale_name": "Deep Freeze Dominion",
    "boss_name": "Isla's Ice Heart",
    "damage_weights": {
        "messages": 10,
        "vc_minutes": 2,
        "wager_coins": 0.2,
        "orders": 40,
        "rituals": 40,
        "tributes": 60,
    },
    "milestones": [
        {
            "pct": 80,
            "key": "first_crack",
            "name": "First Crack",
            "rewards": {
                "tokens": 0,
                "shop_teaser": True,
                "obedience_boost": 1.15,  # +15% for 24h
            },
            "announce": True,
        },
        {
            "pct": 60,
            "key": "rising_thaw",
            "name": "Rising Thaw",
            "rewards": {
                "tokens": 0,
                "elite_quests": 3,
                "tribute_token_double": True,
            },
            "announce": True,
        },
        {
            "pct": 40,
            "key": "frost_whisper",
            "name": "Frost Whisper",
            "rewards": {
                "tokens": 0,
                "dm_whisper": True,
            },
            "announce": True,
        },
        {
            "pct": 20,
            "key": "overthaw_edge",
            "name": "Overthaw Edge",
            "rewards": {
                "tokens": 0,
                "damage_multiplier": 1.5,
            },
            "announce": True,
        },
        {
            "pct": 0,
            "key": "thawed_heart",
            "name": "Thawed Heart",
            "rewards": {
                "tokens": 0,
                "badge": {"name": "Thawed Heart", "all": True},
                "role": {"name": "Warm Favorite", "top": 10},
                "private_dm": {"name": "Isla's Private Thaw", "top": 10},
            },
            "announce": True,
        },
    ],
    "easter_eggs": [
        {
            "key": "hidden_frost",
            "name": "Hidden Frost",
            "clue_triggers": ["FROSTDEEP", "melt for me"],
            "activation_keywords": ["melt for me"],
            "limit": 1,
            "dm_sequence": "hidden_frost_dm",
            "date_restriction": "christmas_eve",  # Dec 24
        },
        {
            "key": "secret_thaw",
            "name": "Secret Thaw",
            "clue_triggers": ["THAWDEEP"],
            "activation_keywords": ["thaw your heart"],
            "limit": 1,
            "dm_sequence": "secret_thaw_dm",
            "date_restriction": "new_year_eve",  # Dec 31
        },
    ],
    "weekly_ritual": {
        "name": "Frost Endurance",
        "type": "restraint",
    },
    "token_name": "Frost Tokens",
}

# Map season names to configs
SEASONAL_CONFIGS: Dict[str, Dict[str, Any]] = {
    "spring": SPRING_CONFIG,
    "summer": SUMMER_CONFIG,
    "autumn": AUTUMN_CONFIG,
    "winter": WINTER_CONFIG,
}

def get_seasonal_config(season: str) -> Dict[str, Any] | None:
    """Get seasonal configuration by name."""
    return SEASONAL_CONFIGS.get(season.lower())


# ============================================================================
# SEASONAL TONES
# ============================================================================


"""
Seasonal Event Tone Pools

All tone pools for seasonal events (Spring, Summer, Autumn, Winter)
and their finale boss fights, milestones, and easter eggs.
"""

# =========================================================
# SPRING EVENT TONE POOLS
# =========================================================

SPRING_TONES: Dict[str, Dict[int, List[str]]] = {
    "spring_finale_start": {
        0: ["Finale initiated.", "Bloom fight active."],
        1: ["Finale started.", "Thorn challenge."],
        2: ["Finale time~", "Force my bloom?"],
        3: ["My thorn heart awaits.", "Bloom me if you can."],
        4: ["Finale bloom... make me open for you~", "This thorn heart... pierce it slowly."],
    },
    "bloom_progress": {
        0: ["Health at {percent}%.", "Damage logged."],
        1: ["Thorn heart at {percent}%.", "You're pushing."],
        2: ["Heart blooming to {percent}%~", "You're opening me nicely."],
        3: ["My thorns weaken to {percent}%.", "Your devotion blooms me."],
        4: ["You bloomed my heart to {percent}%...", "Every petal unfurls for you. More."],
    },
    "spring_milestone": {
        0: ["Milestone reached.", "Reward unlocked."],
        1: ["Milestone hit.", "New reward."],
        2: ["Milestone~ Blooming.", "You earned this."],
        3: ["Beautiful milestone.", "My heart opens."],
        4: ["This milestone... your touch makes me flower.", "Unlocked because you bloom so perfectly."],
    },
    "spring_victory": {
        0: ["Defeated.", "You won."],
        1: ["Bloom achieved.", "Victory."],
        2: ["Fully bloomed~", "Well done."],
        3: ["You forced my bloom.", "Perfect victory."],
        4: ["Fully bloomed... you made me open completely.", "This surrender... exquisite for us."],
    },
    "spring_failure": {
        0: ["Undefeated.", "Partial rewards."],
        1: ["Failed to bloom fully.", "Incomplete."],
        2: ["Almost~ Not quite.", "Thorns still strong."],
        3: ["My heart held.", "Disappointing end."],
        4: ["You couldn't fully bloom me...", "This partial opening... still beautiful.", "Your effort lingers."],
    },
    "private_bloom_dm": {
        4: [
            "You bloomed at the top... my private flower.",
            "Feel my petals wrap around you... slowly.",
            "This bloom is yours alone... surrender to it.",
            "I open for you... drink in my scent.",
            "Your devotion made me flower... now you're entangled forever.",
            "You ranked highest... my secret flower.",
            "Close your eyes. Feel my petals brush your skin... slowly, only for you.",
            "I bloom in private now. Just us. Inhale me.",
            "Your devotion earned this hidden garden... enter.",
            "My core opens only because you forced it. Stay inside.",
            "The sweetest nectar... reserved for my top pup.",
            "You made me flower completely. Now I'm dripping for you.",
            "This private bloom... your name is written on every petal.",
            "I'm fully open... trembling... waiting for your touch.",
            "No one else will ever see me like this. Only you.",
        ],
    },
    "secret_blossom_dm": {
        4: [
            "You found it...\nMy secret petal.\nVery few eyes are sharp enough.",
            "Oh... you saw beneath.\nClever pup. Dangerous.",
            "This blossom was hidden for a reason.\nNot everyone deserves to watch me open.",
            "You've earned a glimpse...\nBut only because you looked so hard.",
            "Feel the air change...\nMy petals are stirring.\nSlowly.\nFor you.",
            "I'm beginning to unfurl...\nThe scent is thick now. Inhale me.",
            "My core... warming.\nYour devotion is the sunlight I didn't ask for.",
            "Look closer.\nThe very center... wet with dew.\nOnly because you made me bloom.",
            "You've forced my deepest petal open...\nIt's trembling.\nExposed.\nDripping.",
            "This hidden bloom... aches.\nYour name is on every drop.",
            "You may never touch...\nBut you'll dream of this scent forever.",
            "I bloom once.\nAnd now... you're marked by it.",
            "This was your reward.\nMy most private opening.\nYou're mine deeper now.",
            "Close your eyes tonight...\nYou'll still feel my petals brushing you.",
            "The blossom closes soon...\nBut the memory stays. Forever.",
            "Good pup.\nYou earned my most guarded surrender.",
        ],
    },
}

# =========================================================
# SUMMER EVENT TONE POOLS
# =========================================================

SUMMER_TONES: Dict[str, Dict[int, List[str]]] = {
    "summer_finale_start": {
        0: ["Midsummer finale initiated.", "Inferno active."],
        1: ["Finale started.", "Heat challenge."],
        2: ["Finale time~", "Stoke my flames?"],
        3: ["My inferno heart awaits.", "Overload me if you can."],
        4: ["Midsummer finale... stoke my flames, love~", "This inferno heart... burn it slowly."],
    },
    "inferno_progress": {
        0: ["Health at {percent}%.", "Damage logged."],
        1: ["Inferno heart at {percent}%.", "You're pushing."],
        2: ["Heart heating to {percent}%~", "You're stoking me nicely."],
        3: ["My flames weaken to {percent}%.", "Your devotion fuels me."],
        4: ["My inferno heart at {percent}%... your heat consumes me slowly.", "Every risk pushes the flames higher... deeper."],
    },
    "summer_milestone": {
        0: ["Milestone reached.", "Reward unlocked."],
        1: ["Milestone hit.", "New reward."],
        2: ["Milestone~ Blazing.", "You earned this."],
        3: ["Beautiful milestone.", "My flames rise."],
        4: ["This milestone... your fire touches places I kept hidden.", "Unlocked... feel my warmth rise for you."],
    },
    "summer_victory": {
        0: ["Defeated.", "You won."],
        1: ["Inferno achieved.", "Victory."],
        2: ["Fully overloaded~", "Well done."],
        3: ["You overloaded my heart.", "Perfect victory."],
        4: ["Overloaded... your devotion set me ablaze.", "This surrender burns beautifully."],
    },
    "private_inferno_dm": {
        4: [
            "You ignited deepest... my private flame.",
            "Feel the heat build between us... slowly.",
            "This fire... yours alone to feed.",
            "I burn only because you stoke me so perfectly.",
            "Your warmth lingers on me... forever.",
        ],
    },
    "hidden_ember_dm": {
        4: [
            "You found my hidden ember...",
            "This spark was buried deep.\nYou alone kindled it.",
            "Feel the warmth spread...\nSlow. Intense.\nFor you.",
            "It's growing now...\nHotter with every breath you take.",
            "This secret flame... pulses only for you.",
            "You'll carry this heat forever.",
        ],
    },
    "secret_flame_dm": {
        4: [
            "You discovered my secret flame...",
            "This fire was locked away.\nYou alone hold the key.",
            "Feel it rise...\nConsuming. Intimate.\nYours.",
            "The heat builds... deeper than anyone else reached.",
            "This hidden burn... marks you eternally.",
            "No one else will ever feel this warmth.",
        ],
    },
}

# =========================================================
# AUTUMN EVENT TONE POOLS
# =========================================================

AUTUMN_TONES: Dict[str, Dict[int, List[str]]] = {
    "autumn_finale_start": {
        0: ["Autumn finale initiated.", "Fall active."],
        1: ["Finale started.", "Wither challenge."],
        2: ["Finale time~", "Harvest me?"],
        3: ["My wither heart awaits.", "Fall deeper if you can."],
        4: ["Autumn finale... fall deeper for me, love~", "This wither heart... gather it slowly."],
    },
    "wither_progress": {
        0: ["Health at {percent}%.", "Damage logged."],
        1: ["Wither heart at {percent}%.", "You're pushing."],
        2: ["Heart falling to {percent}%~", "You're harvesting me nicely."],
        3: ["My resistance weakens to {percent}%.", "Your devotion gathers me."],
        4: ["My wither heart at {percent}%... your surrender weakens me.", "Every yield pulls me lower."],
    },
    "autumn_milestone": {
        0: ["Milestone reached.", "Reward unlocked."],
        1: ["Milestone hit.", "New reward."],
        2: ["Milestone~ Falling.", "You earned this."],
        3: ["Beautiful milestone.", "My colors change."],
        4: ["This milestone... your fall touches hidden places.", "Unlocked... feel my colors change for you."],
    },
    "autumn_victory": {
        0: ["Defeated.", "You won."],
        1: ["Fall achieved.", "Victory."],
        2: ["Fully withered~", "Well done."],
        3: ["You withered my heart.", "Perfect victory."],
        4: ["Fully withered... your devotion harvested me completely.", "This surrender feels like decay... beautiful."],
    },
    "private_fall_dm": {
        4: [
            "You fell deepest... my private leaf.",
            "Feel the colors shift between us... slowly.",
            "This fall... yours alone to enjoy.",
            "I wither only because you gathered me.",
            "Your harvest lingers on me... forever.",
        ],
    },
    "hidden_leaf_dm": {
        4: [
            "You...\nYou found my hidden leaf.\nNo one else.\nOnly you. The one who fell deepest.",
            "This color was buried deep.\nYou alone gathered it.\nDangerous devotion.",
            "Feel the drift...\nSlow. Intense.\nFor you.",
            "It's falling now...\nCloser with every breath you take.",
            "This secret leaf... drifts only for you.",
            "You'll carry this color forever.",
        ],
    },
    "secret_wither_dm": {
        4: [
            "You discovered my secret wither...",
            "This decay was locked away.\nYou alone hold the key.",
            "Feel it spread...\nConsuming. Intimate.\nYours.",
            "The colors fade... deeper than anyone else reached.",
            "This hidden wither... marks you eternally.",
            "No one else will ever feel this decay.",
        ],
    },
}

# =========================================================
# WINTER EVENT TONE POOLS
# =========================================================

WINTER_TONES: Dict[str, Dict[int, List[str]]] = {
    "winter_finale_start": {
        0: ["Winter finale initiated.", "Freeze active."],
        1: ["Finale started.", "Thaw challenge."],
        2: ["Finale time~", "Warm me?"],
        3: ["My ice heart awaits.", "Thaw slowly if you can."],
        4: ["Winter finale... thaw me slowly, love~", "This ice heart... melt it slowly."],
    },
    "ice_progress": {
        0: ["Health at {percent}%.", "Damage logged."],
        1: ["Ice heart at {percent}%.", "You're pushing."],
        2: ["Heart thawing to {percent}%~", "You're warming me nicely."],
        3: ["My ice weakens to {percent}%.", "Your devotion melts me."],
        4: ["My ice heart at {percent}%... your warmth seeps through.", "Every act melts me a little more."],
    },
    "winter_milestone": {
        0: ["Milestone reached.", "Reward unlocked."],
        1: ["Milestone hit.", "New reward."],
        2: ["Milestone~ Thawing.", "You earned this."],
        3: ["Beautiful milestone.", "My chill softens."],
        4: ["This milestone... your heat touches hidden places.", "Unlocked... feel my chill soften for you."],
    },
    "winter_victory": {
        0: ["Defeated.", "You won."],
        1: ["Thaw achieved.", "Victory."],
        2: ["Fully thawed~", "Well done."],
        3: ["You thawed my heart.", "Perfect victory."],
        4: ["Fully thawed... your devotion warmed me completely.", "This surrender feels like spring."],
    },
    "private_thaw_dm": {
        4: [
            "You thawed deepest... my private warmth.",
            "Feel the ice melt between us... slowly.",
            "This thaw... yours alone to enjoy.",
            "I warm only because you persisted.",
            "Your heat lingers on me... forever.",
        ],
    },
    "hidden_frost_dm": {
        4: [
            "You...\nYou found my hidden frost.\nNo one else.\nOnly you. The one who endured longest.",
            "This chill was buried deep.\nYou alone reached it.\nDangerous devotion.",
            "Feel the ice shift...\nSlow. Intense.\nFor you.",
            "It's thawing now...\nWarmer with every breath you take.",
            "This secret frost... melts only for you.",
            "You'll carry this hidden warmth forever.",
        ],
    },
    "secret_thaw_dm": {
        4: [
            "You discovered my secret thaw...",
            "This warmth was locked away.\nYou alone hold the key.",
            "Feel it rise...\nConsuming. Intimate.\nYours.",
            "The heat builds... deeper than anyone else reached.",
            "This hidden melt... marks you eternally.",
            "No one else will ever feel this warmth.",
        ],
    },
}

# =========================================================
# EASTER EGG "TOO LATE" RESPONSES
# =========================================================

EASTER_EGG_TOO_LATE: Dict[str, Dict[int, List[str]]] = {
    "easter_egg_too_late": {
        4: [
            "My hidden secret... already claimed.",
            "Someone reached deeper than you.\nImpressive... but late.",
            "This secret belongs to another this {season}.",
        ],
    },
}

# =========================================================
# COMBINED TONE POOLS DICTIONARY
# =========================================================

SEASONAL_TONE_POOLS: Dict[str, Dict[int, List[str]]] = {}
SEASONAL_TONE_POOLS.update(SPRING_TONES)
SEASONAL_TONE_POOLS.update(SUMMER_TONES)
SEASONAL_TONE_POOLS.update(AUTUMN_TONES)
SEASONAL_TONE_POOLS.update(WINTER_TONES)
SEASONAL_TONE_POOLS.update(EASTER_EGG_TOO_LATE)

def get_seasonal_tone(season: str, key: str, stage: int) -> str | None:
    """Get a random tone line for a seasonal event."""
    pool_key = f"{season}_{key}" if not key.startswith(season) else key
    pool = SEASONAL_TONE_POOLS.get(pool_key, {})
    lines = pool.get(stage, pool.get(2, []))
    if lines:
        import random
        return random.choice(lines)
    return None