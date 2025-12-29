# Core package - centralized exports
# All core functionality is organized into consolidated modules:
# - configurations.py: Config, ChannelConfigService, FEATURES, FlagService, RANKS
# - utility.py: now_ts, fmt, day_key, etc.
# - personality.py: Personality, MemoryService, ConversationTracker, ReplyEngine, etc.
# - events.py: event calculations, holiday/seasonal configs
# - orders.py: ORDER_TONES, templates, etc.
# - db.py: Database class and schema

# Configurations
from .configurations import Config, ChannelConfigService, FEATURES, FlagService, RANKS, rank_from_lce

# Database
from .db import Database

# Utility
from .utility import now_ts, now_local, tz, clamp, day_key, week_key, current_season_tag, parse_schedule, fmt, ensure_not_opted_out, ensure_not_safeworded

# Personality
from .personality import (
    Personality, DEFAULT_POOLS, pick, calculate_attraction, favor_stage_from_attraction,
    sanitize_isla_text, isla_embed, MemoryService, ConversationTracker, ReplyEngine,
    get_user_favor_stage, calculate_and_update_favor_stage
)

# Events
from .events import (
    calculate_daily_damage, calculate_global_scale, calculate_boss_hp_from_users,
    calculate_expected_daily_damage, calculate_voice_effective_minutes,
    g_log_scale, K_TS, K_CN, K_CW, K_M, K_V,
    HOLIDAY_CONFIGS, get_holiday_config, get_all_holidays, parse_holiday_date,
    SEASONAL_CONFIGS, get_seasonal_config,
    SEASONAL_TONE_POOLS, get_seasonal_tone,
    calculate_es, reset_hourly_caps, reset_daily_caps, apply_es_caps
)

# Orders
from .orders import ORDER_TONES, RITUAL_EXTRA_TONES, TONE_POOLS, PERSONAL_TEMPLATES, RITUAL_TEMPLATES, weighted_choice

__all__ = [
    # Configurations
    'Config', 'ChannelConfigService', 'FEATURES', 'FlagService', 'RANKS', 'rank_from_lce',
    # Database
    'Database',
    # Utility
    'now_ts', 'now_local', 'tz', 'clamp', 'day_key', 'week_key', 'current_season_tag', 'parse_schedule', 'fmt',
    'ensure_not_opted_out', 'ensure_not_safeworded',
    # Personality
    'Personality', 'DEFAULT_POOLS', 'pick', 'calculate_attraction', 'favor_stage_from_attraction',
    'sanitize_isla_text', 'isla_embed', 'MemoryService', 'ConversationTracker', 'ReplyEngine',
    'get_user_favor_stage', 'calculate_and_update_favor_stage',
    # Events
    'calculate_daily_damage', 'calculate_global_scale', 'calculate_boss_hp_from_users',
    'calculate_expected_daily_damage', 'calculate_voice_effective_minutes',
    'g_log_scale', 'K_TS', 'K_CN', 'K_CW', 'K_M', 'K_V',
    'HOLIDAY_CONFIGS', 'get_holiday_config', 'get_all_holidays', 'parse_holiday_date',
    'SEASONAL_CONFIGS', 'get_seasonal_config',
    'SEASONAL_TONE_POOLS', 'get_seasonal_tone',
    'calculate_es', 'reset_hourly_caps', 'reset_daily_caps', 'apply_es_caps',
    # Orders
    'ORDER_TONES', 'RITUAL_EXTRA_TONES', 'TONE_POOLS', 'PERSONAL_TEMPLATES', 'RITUAL_TEMPLATES', 'weighted_choice',
]
