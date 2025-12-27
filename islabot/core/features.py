from __future__ import annotations

FEATURES = {
    "orders": "Orders module",
    "shop": "Shop module",
    "tributes": "Tributes module",
    "events": "Seasonal events module",
    "leaderboard": "Spotlight/leaderboard module",
    "economy": "Economy module",
    "profile": "Profile module",
    "public_callouts": "Any public callout posting",
}

DEFAULT_ENABLED = {k: True for k in FEATURES.keys()}

