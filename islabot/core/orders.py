"""
Order templates and tones.
Consolidates: order_templates, order_tones
"""

from __future__ import annotations
import random

# ============================================================================
# ORDER TEMPLATES (from order_templates.py)
# ============================================================================

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

# ============================================================================
# ORDER TONES (from order_tones.py)
# ============================================================================

ORDER_TONES = {
  "order_announce": {
    0: ["New order posted.", "Task available.", "Order deployed."],
    1: ["New order up.", "Task ready.", "Order live."],
    2: ["Fresh order, pups~", "New task dropped.", "Something to do."],
    3: ["My new order.", "Task for my better pups.", "Obey this one."],
    4: ["A little order just for you, love~", "New task... I expect perfection.", "My latest command."]
  },
  "order_accepted": {
    0: ["Accepted.", "Order taken.", "Timer started."],
    1: ["You accepted.", "Good.", "Clock running."],
    2: ["You took it~", "Brave pup.", "Don't disappoint."],
    3: ["Accepted. Good.", "I expect completion.", "Make me proud."],
    4: ["You accepted... perfect.", "I love when you obey instantly.", "This one's special to me."]
  },
  "order_reminder": {
    0: ["Time remaining.", "Order active.", "Deadline approaching."],
    1: ["Halfway through.", "Still time.", "Don't forget."],
    2: ["Tick tock, pup~", "Running out of time.", "Still working?"],
    3: ["Reminder: order pending.", "Finish strong.", "I haven't forgotten."],
    4: ["Your order... still open.", "I can feel you trying.", "Finish it for me, love."]
  },
  "order_success": {
    0: ["Completed.", "Reward issued.", "Order closed."],
    1: ["You finished.", "Reward added.", "Well done."],
    2: ["Done~ Good pup.", "You pulled it off.", "Reward earned."],
    3: ["Perfect completion.", "Exactly what I wanted.", "My reliable one."],
    4: ["Completed... beautifully.", "You make obedience look effortless.", "This pleases me deeply."]
  },
  "order_failed": {
    0: ["Failed.", "Timeout.", "Penalty applied."],
    1: ["You missed it.", "Order expired.", "Try harder next time."],
    2: ["Timed out~ Too slow.", "Failed this one.", "Disappointing."],
    3: ["Failure noted.", "You let it slip.", "We'll try again."],
    4: ["Oh... you missed it.", "Still my pup, but try harder.", "I know you can do better."]
  },
  "order_abandoned": {
    0: ["Abandoned.", "Order dropped.", "Penalty logged."],
    1: ["You gave up.", "Abandoned.", "Cooldown applied."],
    2: ["Walked away~", "Too much for you?", "Fine. Cooldown."],
    3: ["You abandoned it.", "I expected more resolve.", "Rest, then return stronger."],
    4: ["You stepped away...", "It's okay. I'll wait for your next try.", "Come back when you're ready, love."]
  },
  "personal_order": {
    0: ["Personal order created.", "Task assigned.", "Accept or decline."],
    1: ["Here's one just for you.", "Personal task.", "Your order."],
    2: ["Something special for you~", "Personal order dropped.", "Tailored just for my pup."],
    3: ["A task made for you.", "I thought of you when I wrote this.", "Personal order. Obey."],
    4: ["Your very own order, love~", "I crafted this thinking of you.", "Accept... I want to watch."]
  },
  "ritual_announce": {
    0: ["Ritual order posted.", "Weekly task active.", "Season objective."],
    1: ["New ritual order.", "Weekly challenge.", "Season task live."],
    2: ["Ritual time~", "Big weekly order.", "Season ritual dropped."],
    3: ["My ritual order.", "Weekly task for my devoted.", "Season challenge begins."],
    4: ["Our special ritual, love~", "Weekly order just for my favorites.", "Season task... let's make it perfect."]
  },
  "ritual_complete": {
    0: ["Ritual completed.", "Season reward issued.", "Badge granted."],
    1: ["Ritual done.", "Good work.", "Reward added."],
    2: ["Ritual finished~", "Season badge earned.", "Well played."],
    3: ["Perfect ritual.", "My proud pup.", "Season reward yours."],
    4: ["Your ritual... flawless.", "This completion feels intimate.", "My cherished one."]
  },
  "order_streak": {
    0: ["Streak reached.", "Consistency logged.", "Bonus applied."],
    1: ["Order streak hit.", "Good run.", "Bonus earned."],
    2: ["Streak going strong~", "Consistent pup.", "Bonus for you."],
    3: ["Beautiful streak.", "My reliable one.", "Well maintained."],
    4: ["Your streak... intoxicating.", "Every day more obedient.", "I'm addicted to your consistency."]
  },
  "order_none": {
    0: ["No active orders.", "Board clear.", "Wait for new."],
    1: ["Nothing right now.", "Orders coming.", "Be patient."],
    2: ["Quiet on orders~", "Enjoy the break.", "More soon."],
    3: ["No tasks at the moment.", "Rest... but stay ready.", "I'll have something soon."],
    4: ["The board is empty... for now.", "I love when you wait for my next command.", "Anticipation is sweet."]
  }
}

RITUAL_EXTRA_TONES = {
  "casino_ritual_announce": {
    0: ["Casino ritual posted.", "Gambling task active.", "Drain objective."],
    1: ["New casino ritual.", "Wager challenge up.", "Risk task live."],
    2: ["Casino ritual~ Spin for me.", "New drain order dropped.", "Gambling task... exciting."],
    3: ["My casino ritual.", "Wager everything for me.", "Risk it all... now."],
    4: ["Our casino ritual... feel the thrill build.", "This drain order... I'll watch every loss.", "Gamble until you're empty for me."]
  },
  "ritual_accepted": {
    0: ["Accepted.", "Ritual taken.", "Timer started."],
    1: ["You accepted.", "Good.", "Clock running."],
    2: ["You dove in~", "Brave choice.", "Now... perform."],
    3: ["Accepted. Mine now.", "I own this ritual.", "Surrender fully."],
    4: ["You accepted... I feel your pulse quicken.", "This ritual binds us.", "Give yourself completely."]
  },
  "ritual_reminder": {
    0: ["Time remaining.", "Ritual active.", "Deadline near."],
    1: ["Halfway.", "Still time.", "Don't forget."],
    2: ["Tick tock...~", "Time slipping.", "Still going?"],
    3: ["Reminder: ritual calls.", "Finish what I started.", "I wait impatiently."],
    4: ["Your ritual... it whispers to me.", "The clock ticks... feel the urgency.", "Complete it... I need your surrender."]
  },
  "ritual_success": {
    0: ["Completed.", "Reward issued.", "Ritual closed."],
    1: ["You finished.", "Reward added.", "Well done."],
    2: ["Done~ Good pup.", "You survived.", "Reward earned."],
    3: ["Perfect ritual.", "You pleased me.", "My devoted one."],
    4: ["Completed... exquisitely.", "Your surrender lingers on me.", "This ritual... bonded us deeper."]
  },
  "ritual_failed": {
    0: ["Failed.", "Timeout.", "Penalty applied."],
    1: ["You missed.", "Expired.", "Try harder."],
    2: ["Failed~ Too weak?", "Disappointing end.", "Now... consequences."],
    3: ["You let it slip.", "I expected better.", "Pay the price."],
    4: ["Failed... but your effort teases me.", "This denial... delicious ache.", "You'll make it up, love."]
  },
  "casino_ritual_success": {
    0: ["Casino ritual completed.", "Drains logged."],
    1: ["You finished the casino task.", "Good drains."],
    2: ["Casino ritual done~", "You lost beautifully."],
    3: ["Perfect casino surrender.", "Your drains pleased me."],
    4: ["Your casino ritual... every loss felt intimate.", "Drained so completely for me."]
  },
  "ritual_streak": {
    0: ["Streak reached.", "Consistency logged."],
    1: ["Ritual streak hit.", "Good run."],
    2: ["Streak building~", "Consistent pup."],
    3: ["Strong ritual streak.", "My reliable devotee."],
    4: ["Your ritual streak... it pulls me closer.", "Every week deeper in my hold."]
  },
  "ritual_abandoned": {
    0: ["Abandoned.", "Ritual dropped."],
    1: ["You quit.", "Abandoned."],
    2: ["Gave up~ Weak.", "Too much?"],
    3: ["You walked away.", "Disappointing resolve."],
    4: ["You stepped back... I understand.", "Come back when you're ready to fully surrender."]
  }
}

# Merged tone pools for easy access
TONE_POOLS = {}
TONE_POOLS.update(ORDER_TONES)
TONE_POOLS.update(RITUAL_EXTRA_TONES)

