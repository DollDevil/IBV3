"""
Seasonal Event Configurations

Defines the structure, milestones, rewards, and tone pools for each seasonal era.
"""

from __future__ import annotations
from typing import Dict, List, Any

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

