"""
Unified Boss Damage Formula Implementation

Implements the standardized boss damage calculation system for holiday weeks
and seasonal finales using logarithmic scaling (no caps, diminishing returns).
"""

from __future__ import annotations
import math
from typing import Dict, Tuple

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
