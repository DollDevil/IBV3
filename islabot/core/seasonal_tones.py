"""
Seasonal Event Tone Pools

All tone pools for seasonal events (Spring, Summer, Autumn, Winter)
and their finale boss fights, milestones, and easter eggs.
"""

from __future__ import annotations
from typing import Dict, List

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

