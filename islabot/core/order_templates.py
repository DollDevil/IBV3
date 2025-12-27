from __future__ import annotations
import random

# Each template returns:
# - title
# - description (human, clean)
# - requirement dict
# - duration_minutes
# - max_slots
# - reward_coins, reward_obedience (base; scaled later)

PERSONAL_TEMPLATES = [
    # ---------- CHAT ----------
    {
        "key": "chat_small",
        "weight": 5,
        "title": "Talk.",
        "desc_variants": [
            "Send **{count} messages**.\nKeep it moving.\n᲼᲼",
            "I want **{count} messages**.\nNo lurking.\n᲼᲼",
            "Speak.\n**{count} messages**.\n᲼᲼",
        ],
        "requirement": lambda spam_ch, count: {"type": "messages", "count": count, "channel_id": spam_ch},
        "duration_minutes": (90, 240),
        "slots": 1,
        "base_reward": (180, 5),
    },
    {
        "key": "chat_medium",
        "weight": 3,
        "title": "Be seen.",
        "desc_variants": [
            "Send **{count} messages** today.\nShow up.\n᲼᲼",
            "I want you active.\n**{count} messages**.\n᲼᲼",
        ],
        "requirement": lambda spam_ch, count: {"type": "messages", "count": count, "channel_id": spam_ch},
        "duration_minutes": (180, 360),
        "slots": 1,
        "base_reward": (260, 7),
    },

    # ---------- VC ----------
    {
        "key": "vc_small",
        "weight": 3,
        "title": "Voice time.",
        "desc_variants": [
            "Spend **{minutes} minutes** in voice.\nI'll notice.\n᲼᲼",
            "Voice.\n**{minutes} minutes**.\nDon't vanish.\n᲼᲼",
        ],
        "requirement": lambda _spam_ch, minutes: {"type": "vc_minutes", "minutes": minutes},
        "duration_minutes": (180, 480),
        "slots": 1,
        "base_reward": (240, 6),
    },

    # ---------- CASINO ----------
    {
        "key": "casino_rounds",
        "weight": 3,
        "title": "Casino.",
        "desc_variants": [
            "Play **{count} casino rounds**.\nDon't be shy.\n᲼᲼",
            "Give me **{count} rounds**.\nI want to watch.\n᲼᲼",
        ],
        "requirement": lambda _spam_ch, count: {"type": "casino_rounds", "count": count},
        "duration_minutes": (120, 360),
        "slots": 1,
        "base_reward": (220, 6),
    },
    {
        "key": "casino_wager",
        "weight": 2,
        "title": "Wager.",
        "desc_variants": [
            "Wager **{coins} Coins** total.\nMake it count.\n᲼᲼",
            "I want **{coins} Coins** wagered.\nShow commitment.\n᲼᲼",
        ],
        "requirement": lambda _spam_ch, coins: {"type": "casino_wager", "coins": coins},
        "duration_minutes": (120, 360),
        "slots": 1,
        "base_reward": (300, 8),
    },

    # ---------- MANUAL / PROOF (staff inbox) ----------
    {
        "key": "manual_proof",
        "weight": 1,
        "title": "Proof.",
        "desc_variants": [
            "Do something useful.\nSubmit proof with `/order_complete`.\n᲼᲼",
            "I want effort.\nSend proof when you're done.\n᲼᲼",
        ],
        "requirement": lambda _spam_ch, _x: {"type": "manual", "note": "Submit proof note. Staff reviews."},
        "duration_minutes": (240, 720),
        "slots": 1,
        "base_reward": (350, 9),
    },
]

# Weekly rituals (server scope, limited slots, 7 days)
RITUAL_TEMPLATES = [
    {
        "key": "drain_marathon",
        "theme": "casino",
        "title": "Ritual: Drain Marathon",
        "desc_variants": [
            "Wager **{coins} Coins** across the week.\nLosses still count.\n᲼᲼",
            "A slow drain.\nWager **{coins} Coins** this week.\n᲼᲼",
        ],
        "requirement": lambda coins: {"type": "casino_wager", "coins": coins},
        "duration_minutes": 7 * 24 * 60,
        "slots": 50,
        "base_reward": (2500, 35),
        "announce_key": "casino_ritual_announce",
        "success_key": "casino_ritual_success",
    },
    {
        "key": "luck_submission",
        "theme": "casino",
        "title": "Ritual: Luck Submission",
        "desc_variants": [
            "Play **{count} rounds** this week.\nConsistency matters.\n᲼᲼",
            "I want repetition.\n**{count} rounds**.\n᲼᲼",
        ],
        "requirement": lambda count: {"type": "casino_rounds", "count": count},
        "duration_minutes": 7 * 24 * 60,
        "slots": 50,
        "base_reward": (2200, 32),
        "announce_key": "casino_ritual_announce",
        "success_key": "casino_ritual_success",
    },
    {
        "key": "pack_warmup",
        "theme": "community",
        "title": "Ritual: Pack Warmup",
        "desc_variants": [
            "Send **{count} messages** in #spam this week.\nKeep the pack alive.\n᲼᲼",
            "No silence.\n**{count} messages** this week.\n᲼᲼",
        ],
        "requirement": lambda spam_ch, count: {"type": "messages", "count": count, "channel_id": spam_ch},
        "duration_minutes": 7 * 24 * 60,
        "slots": 80,
        "base_reward": (1800, 28),
        "announce_key": "ritual_announce",
        "success_key": "ritual_success",
    },
]


def weighted_choice(items: list[dict]) -> dict:
    total = sum(max(0, int(i.get("weight", 1))) for i in items)
    r = random.uniform(0, total)
    upto = 0.0
    for i in items:
        w = max(0, int(i.get("weight", 1)))
        if upto + w >= r:
            return i
        upto += w
    return items[-1]

