from __future__ import annotations
import random
from core.isla_text import sanitize_isla_text

# Core personality pools: Emotionless base (Stage 0) -> Earned emotion (Stage 4)
DEFAULT_POOLS = {
    "greeting": {
        "stage_0": [
            "Here.",
            "Online.",
            "Morning.",
            "Evening.",
            "Present.",
            "Checking in.",
            "Still active.",
            "Server status noted.",
            "You're here.",
            "I see activity."
        ],
        "stage_1": [
            "Morning.",
            "You're up.",
            "Hey.",
            "Noticed you.",
            "Back again.",
            "You're consistent."
        ],
        "stage_2": [
            "Morning, pup.",
            "You're early.",
            "Hey again.",
            "Still around.",
            "Predictable."
        ],
        "stage_3": [
            "Morning, pup.",
            "Good to see you.",
            "You're here early.",
            "My reliable one."
        ],
        "stage_4": [
            "Morning, my good pup.",
            "Hey you.",
            "Missed this.",
            "There you are."
        ]
    },
    "balance": {
        "stage_0": ["Balance: {coins}.", "Coins: {coins}.", "That's what you have: {coins}."],
        "stage_1": ["Coins: {coins}. Don't waste them.", "Balance: {coins}. Try harder."],
        "stage_2": ["{coins} Coins. I noticed.", "Balance: {coins}. Better."],
        "stage_3": ["{coins} Coins. Good pup.", "Balance: {coins}. Keep going."],
        "stage_4": ["{coins} Coins. That's my favorite number on you.", "Balance: {coins}. Stay close."],
    },
    "daily": {
        "stage_0": ["Daily claimed.", "Transaction complete.", "Here.", "Claimed."],
        "stage_1": ["Daily Coins. Don't disappoint me.", "Claimed. Move.", "Here. Don't waste."],
        "stage_2": ["Daily. Mildly useful.", "Fine. Take it.", "You showed up."],
        "stage_3": ["Good. Daily routine matters.", "That's better. Consistency.", "Good pup."],
        "stage_4": ["Good. I like when you show up for me.", "Daily claimed, love. Don't stop.", "Always here for me."],
    },
    "order": {
        "stage_0": [
            "React to confirm presence.",
            "Type 'present'.",
            "Acknowledge this message.",
            "Respond with any word.",
            "Silence for 5 minutes."
        ],
        "stage_1": [
            "Type 'I obey'.",
            "React if compliant.",
            "State your status."
        ],
        "stage_2": [
            "Say something worth reading.",
            "React with your choice.",
            "Prove you're listening."
        ],
        "stage_3": [
            "Tell me how you'll serve today.",
            "React if you're mine."
        ],
        "stage_4": [
            "Good pups react with ❤️.",
            "Tell me why you deserve attention."
        ]
    },
    "tease": {
        "stage_0": [
            "Continue.",
            "Expected more.",
            "Adequate.",
            "Insufficient.",
            "Noted.",
            "Proceed."
        ],
        "stage_1": [
            "Slight improvement.",
            "You're trying.",
            "Marginally better.",
            "Keep going."
        ],
        "stage_2": [
            "Amusing effort.",
            "You're persistent.",
            "Almost impressive."
        ],
        "stage_3": [
            "You're earning notice.",
            "Better.",
            "I see potential."
        ],
        "stage_4": [
            "You're making me soften.",
            "Good behavior.",
            "This pleases me."
        ]
    },
    "observation": {
        "stage_0": [
            "Low activity.",
            "Server quiet.",
            "Minimal interaction.",
            "Standard lull."
        ],
        "stage_1": [
            "Activity increased.",
            "Some participation.",
            "Slight uptick."
        ],
        "stage_2": [
            "Chat picked up.",
            "You respond to presence.",
            "Predictable reaction."
        ],
        "stage_3": [
            "Energy rises when I appear.",
            "You come alive for me."
        ],
        "stage_4": [
            "The way you light up... satisfying.",
            "This is how it should be."
        ]
    },
    "goodnight": {
        "stage_0": [
            "Offline.",
            "Ending session.",
            "Night cycle.",
            "Server unattended.",
            "Logging off."
        ],
        "stage_1": [
            "Night.",
            "Going silent.",
            "Rest cycle."
        ],
        "stage_2": [
            "Night, pups.",
            "Sleep.",
            "Until tomorrow."
        ],
        "stage_3": [
            "Good night.",
            "Rest well.",
            "Be good while I'm gone."
        ],
        "stage_4": [
            "Good night, my devoted one.",
            "Sleep well. You earned it.",
            "Dream of me."
        ]
    },
    "nudge": {
        "stage_0": [
            "{mentions} inactive.",
            "{mentions} no recent input.",
            "{mentions} silent."
        ],
        "stage_1": [
            "{mentions} you've been quiet.",
            "{mentions} still there?"
        ],
        "stage_2": [
            "{mentions} hiding?",
            "{mentions} come back."
        ],
        "stage_3": [
            "{mentions} I noticed your absence.",
            "{mentions} missed you."
        ],
        "stage_4": [
            "{mentions} where did you go, love?",
            "{mentions} come back soon."
        ]
    },
    "stats": {
        "stage_0": [
            "{msg_count} messages logged.",
            "Voice usage: {voice_mins} minutes.",
            "{hacks} challenges completed.",
            "Activity registered.",
            "Server operational.",
            "Standard output."
        ],
        "stage_1": [
            "{msg_count} messages. Acceptable.",
            "Voice active for {voice_mins} minutes.",
            "{hacks} solved. Noted.",
            "Some effort detected."
        ],
        "stage_2": [
            "{msg_count} messages. Not bad.",
            "<@{top_voice}> dominated voice.",
            "{hacks} cracked. Interesting."
        ],
        "stage_3": [
            "Good numbers today.",
            "<@{top_voice}> performed well.",
            "Solid activity."
        ],
        "stage_4": [
            "These stats... pleasing.",
            "<@{top_voice}> you did well.",
            "Exactly what I expect from my best."
        ]
    },
    "safeword": {
        "stage_0": ["Okay.", "Paused.", "Noted."],
        "stage_1": ["Noted. I'll stop.", "Fine. You're paused."],
        "stage_2": ["Understood. No pressure.", "Okay. I'll be quiet."],
        "stage_3": ["Good. Take care. I'll back off.", "Noted. You're safe."],
        "stage_4": ["Always. You're safe with me.", "Okay love. I'm backing off."],
    }
}

def clamp(x: float, lo: float, hi: float) -> float:
    """Clamp value between lo and hi."""
    return max(lo, min(hi, x))

def calculate_attraction(coins: float, obedience_rate: float, streak_days: int, failures: int) -> float:
    """
    Attraction Meter formula from document:
    attraction = (coins * 0.5) + (obedience_rate * 40) + (streak_days * 10) - (failures * 20)
    """
    return (coins * 0.5) + (obedience_rate * 40) + (streak_days * 10) - (failures * 20)

def favor_stage_from_attraction(attraction: float) -> int:
    """
    Calculate favor stage (0-4) from attraction score.
    Stage 0: 0-1,000 Coins (or equivalent attraction)
    Stage 1: 1,000-5,000
    Stage 2: 5,000-10,000
    Stage 3: 10,000-20,000
    Stage 4: 20,000+
    """
    # Using attraction directly (since coins*0.5 is primary component)
    # Convert to approximate coin thresholds
    if attraction < 500: return 0  # ~1k coins
    if attraction < 2500: return 1  # ~5k coins
    if attraction < 5000: return 2  # ~10k coins
    if attraction < 10000: return 3  # ~20k coins
    return 4

def stage_from_coins(coins: int) -> int:
    """Legacy function - prefer favor_stage_from_attraction for personality progression."""
    # Simple thresholds (mapped to favor stages)
    if coins < 1000: return 0
    if coins < 5000: return 1
    if coins < 10000: return 2
    if coins < 20000: return 3
    return 4

def apply_stage_cap(stage: int, cap: int) -> int:
    return min(max(stage, 0), max(cap, 0))

def pick(pool: dict, key: str, stage: int, fmt: dict = None) -> str:
    """
    Pick a random line from the pool for the given key and stage.
    Falls back to stage_0 if stage-specific pool doesn't exist.
    
    Args:
        pool: Dictionary of pools (e.g., DEFAULT_POOLS)
        key: Pool key (e.g., "greeting", "order")
        stage: Favor stage (0-4)
        fmt: Optional format dict for string formatting
    """
    if fmt is None:
        fmt = {}
    block = pool.get(key, {})
    lines = block.get(f"stage_{stage}", []) or block.get("stage_0", [])
    s = random.choice(lines) if lines else ""
    if fmt:
        try:
            s = s.format(**fmt)
        except KeyError:
            # Missing format key - return as-is
            pass
    return sanitize_isla_text(s)

def get_stage_pool(pool: dict, key: str, stage: int) -> list[str]:
    """Get the list of lines for a specific stage, falling back to stage_0."""
    block = pool.get(key, {})
    return block.get(f"stage_{stage}", []) or block.get("stage_0", [])

