"""
Holiday Week Event Configurations

Defines 6 week-long holiday events that auto-start on fixed calendar dates.
Each event includes tokens, rituals, boss fights, shop items, easter eggs, and milestones.
"""

from __future__ import annotations
from typing import Dict, List, Any

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

