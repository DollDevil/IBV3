"""
Thumbnail placeholder system for events.
Defines keys that map to seasonal thumbnails (URLs filled later in config).
"""

import json

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

