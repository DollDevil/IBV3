"""
Personality system modules.
Consolidates: isla_text, tone, personality, embedder, memory, conversation, reply_engine, favor
"""

from __future__ import annotations
import json
import os
import re
import random
from typing import Optional, Dict, List, Any, Tuple
import discord
from .db import Database
from .utility import now_ts




# ============================================================================
# ISLA TEXT
# ============================================================================


ADDRESS_WORDS = [
    "simps", "simp",
    "pups", "pup", "puppies", "puppy",
    "dogs", "dog",
    "pets", "pet",
    "kittens", "kitten"
]

# Patterns like "Good morning, pups" -> "Good morning pups"
_COMMA_AFTER_ADDRESS = re.compile(rf"\b({'|'.join(ADDRESS_WORDS)})\b\s*,", re.IGNORECASE)
_COMMA_BEFORE_ADDRESS = re.compile(rf",\s*\b({'|'.join(ADDRESS_WORDS)})\b", re.IGNORECASE)

# Fix cases like:
# "Good morning,\npups" -> "Good morning pups"
_SPLIT_ADDRESS_ACROSS_LINES = re.compile(
    rf"(\b(?:good morning|morning|hey|hi)\b)\s*,?\s*\n\s*\b({'|'.join(ADDRESS_WORDS)})\b",
    re.IGNORECASE
)

# Also fix: "Good morning,\n simps" etc.
_SPLIT_ADDRESS_GENERIC = re.compile(
    rf",?\s*\n\s*\b({'|'.join(ADDRESS_WORDS)})\b",
    re.IGNORECASE
)

def sanitize_isla_text(text: str) -> str:
    """
    Enforces global tone rules:
    - Never use commas when referencing simps/pups/pets/dogs/etc (in direct address phrases).
    - Never split the address phrase across lines.
    - Light cleanup of spacing.
    """
    if not text:
        return text

    t = text

    # 1) Fix "Good morning,\npups" -> "Good morning pups"
    t = _SPLIT_ADDRESS_ACROSS_LINES.sub(r"\1 \2", t)

    # 2) Fix ",\n pups" etc -> " pups" (rare)
    # (only when it immediately precedes an address word)
    t = _SPLIT_ADDRESS_GENERIC.sub(lambda m: " " + m.group(1), t)

    # 3) Remove comma before/after address word
    # "pups, ..." -> "pups ..."
    t = _COMMA_AFTER_ADDRESS.sub(lambda m: m.group(1), t)
    # "..., pups" -> "... pups"
    t = _COMMA_BEFORE_ADDRESS.sub(lambda m: " " + m.group(1), t)

    # 4) Normalize a few common awkward punctuation combos
    t = t.replace(" ,", " ")
    t = re.sub(r"[ \t]{2,}", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t)

    return t.strip()


# ============================================================================
# TONE
# ============================================================================


# Note: sanitize_isla_text is defined above in ISLA TEXT section

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


# ============================================================================
# PERSONALITY
# ============================================================================


# Note: sanitize_isla_text and DEFAULT_POOLS are defined above

class Personality:
    """
    Loads tone pools from a JSON file. If file missing/invalid, uses fallback.
    File format example:
    {
      "balance": { "stage_0": ["..."], "stage_1": ["..."] },
      "daily":   { "stage_0": ["..."], ... }
    }
    """
    def __init__(self, path: str, fallback: dict[str, Any], memory_service: Optional[Any] = None):
        self.path = path
        self.fallback = fallback
        self.pools = fallback
        self.last_mtime = 0.0
        self.memory = memory_service  # Optional memory service for context-aware responses

    def load(self) -> tuple[bool, str]:
        """Load personality from file. Returns (success, message)."""
        if not os.path.exists(self.path):
            self.pools = self.fallback
            return False, "personality file missing; using fallback"

        try:
            mtime = os.path.getmtime(self.path)
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError("Root must be object/dict")
            self.pools = data
            self.last_mtime = mtime
            return True, "loaded"
        except Exception as e:
            self.pools = self.fallback
            return False, f"failed to load; fallback used: {e}"

    def maybe_reload(self) -> bool:
        """Check if file changed and reload if needed. Returns True if reloaded."""
        try:
            if not os.path.exists(self.path):
                return False
            mtime = os.path.getmtime(self.path)
            if mtime > self.last_mtime:
                self.load()
                return True
        except Exception:
            pass
        return False

    def sanitize(self):
        """Sanitize all strings in pools."""
        for k, block in list(self.pools.items()):
            if not isinstance(block, dict):
                continue
            for stage, lines in list(block.items()):
                if isinstance(lines, list):
                    block[stage] = [sanitize_isla_text(str(x)) for x in lines]
    
    async def get_response_with_memory(
        self,
        pool_key: str,
        stage: int,
        guild_id: Optional[int] = None,
        user_id: Optional[int] = None,
        context: Optional[dict[str, Any]] = None
    ) -> str:
        """Get a response from a pool, enhanced with memory if available."""
        # Get base response
        stage_key = f"stage_{min(stage, 4)}"
        pool = self.pools.get(pool_key, {})
        responses = pool.get(stage_key, [])
        
        if not responses:
            # Fallback to stage_0
            responses = pool.get("stage_0", [])
        
        if not responses:
            return ""
        
        import random
        response = random.choice(responses)
        
        # Enhance with memory if available
        if self.memory and guild_id and user_id:
            memories = await self.memory.get_all_user_memories(guild_id, user_id)
            # Could add memory-based enhancements here
            # For example, replace placeholders with memory values
        
        return response


# ============================================================================
# EMBEDDER
# ============================================================================


STYLE_1 = {
    "confident_smirk": [
        "https://i.imgur.com/5nsuuCV.png",
        "https://i.imgur.com/8qQkq0p.png",
        "https://i.imgur.com/8AsaLI5.png",
        "https://i.imgur.com/sGDoIDA.png",
        "https://i.imgur.com/qC0MOZN.png",
        "https://i.imgur.com/rcgIEtj.png",
    ],
    "bothered": ["https://i.imgur.com/k7AexFe.png"],
    "laughing": [
        "https://i.imgur.com/eoNSHQ1.png",
        "https://i.imgur.com/TS1KMQe.png",
        "https://i.imgur.com/zcb1ztK.png",
        "https://i.imgur.com/lpMQlWO.png",
    ],
    "displeased": [
        "https://i.imgur.com/9g4g7iV.png",
        "https://i.imgur.com/h68lq5E.png",
        "https://i.imgur.com/0pFNbQc.png",
        "https://i.imgur.com/8Ay5met.png",
        "https://i.imgur.com/ZQQIji3.png",
        "https://i.imgur.com/KmAneUM.png",
        "https://i.imgur.com/9oUjOQQ.png",
    ],
    "pleased": [
        "https://i.imgur.com/sCjhY7W.png",
        "https://i.imgur.com/0BM3E8t.png",
        "https://i.imgur.com/qTvUqq6.png",
        "https://i.imgur.com/JAXB48Q.png",
        "https://i.imgur.com/W3uzVdO.png",
    ],
    "soft_smirk": [
        "https://i.imgur.com/qC0MOZN.png",
        "https://i.imgur.com/rcgIEtj.png",
        "https://i.imgur.com/8qQkq0p.png",
    ],
    "neutral": ["https://i.imgur.com/9oUjOQQ.png"],
}

STYLE_2 = {
    "blue": [
        "https://i.imgur.com/fzk4mNv.png",
        "https://i.imgur.com/GZlj07G.png",
        "https://i.imgur.com/RGs0Igy.png",
        "https://i.imgur.com/5lChRC4.png",
        "https://i.imgur.com/DiUpVdA.png",
        "https://i.imgur.com/iF3oM08.png",
        "https://i.imgur.com/7LAxXuZ.png",
        "https://i.imgur.com/vnlOeXI.png",
    ],
    "red": [
        "https://i.imgur.com/9Xd0s3Y.png",
        "https://i.imgur.com/enz5kfa.png",
        "https://i.imgur.com/1vtsFtF.png",
        "https://i.imgur.com/3beMtf8.png",
        "https://i.imgur.com/0qsNN2f.png",
        "https://i.imgur.com/orzAm6z.png",
        "https://i.imgur.com/2Cj2trS.png",
        "https://i.imgur.com/Rf0c8si.png",
        "https://i.imgur.com/FEwzNfT.png",
    ],
    "purple": [
        "https://i.imgur.com/ACKlpwU.png",
        "https://i.imgur.com/P3mgFlp.png",
        "https://i.imgur.com/SpUB1fM.png",
        "https://i.imgur.com/3aBJXJN.png",
        "https://i.imgur.com/RrGSuFk.png",
        "https://i.imgur.com/eZdhcu0.png",
        "https://i.imgur.com/GPMXYBc.png",
    ],
}

STYLE_4 = [
    "https://i.imgur.com/wy83j2k.png",
    "https://i.imgur.com/7ZxrVfh.png",
    "https://i.imgur.com/7hfEObn.png",
    "https://i.imgur.com/GSCbvIM.png",
    "https://i.imgur.com/hFU8N24.png",
    "https://i.imgur.com/T03rsMr.png",
    "https://i.imgur.com/hdT0dzJ.png",
    "https://i.imgur.com/wEwasHO.png",
    "https://i.imgur.com/5IJf1gB.png",
    "https://i.imgur.com/o6anTbt.png",
]

class EmbedSpec:
    def __init__(self, color: int, title_pool: list[str], desc_pool: list[str], fields_pool: list[dict],
                 thumbnail_policy: dict):
        self.color = color
        self.title_pool = title_pool
        self.desc_pool = desc_pool
        self.fields_pool = fields_pool
        self.thumbnail_policy = thumbnail_policy

class Embedder:
    def __init__(self, cfg, db):
        self.cfg = cfg
        self.db = db

    async def build_embed(self, gid: int, context: str, spec: EmbedSpec, fmt: dict, is_dm: bool) -> discord.Embed:
        title = random.choice(spec.title_pool) if spec.title_pool else ""
        desc = random.choice(spec.desc_pool) if spec.desc_pool else ""
        if fmt:
            title = title.format(**fmt)
            desc = desc.format(**fmt)

        e = discord.Embed(title=title, description=desc, color=spec.color)

        for f in spec.fields_pool or []:
            name = f["name"]
            val = random.choice(f["values"]) if isinstance(f["values"], list) else str(f["values"])
            if fmt:
                name = name.format(**fmt)
                val = val.format(**fmt)
            e.add_field(name=name, value=val, inline=bool(f.get("inline", False)))

        # thumbnail selection
        pol = spec.thumbnail_policy or {"kind": "style_1", "emotions": ["neutral"]}
        kind = pol.get("kind", "style_1")

        if kind == "style_4":
            e.set_thumbnail(url=random.choice(STYLE_4))
            return e

        if kind == "style_2" and is_dm:
            themes = pol.get("themes", ["blue"])
            theme = random.choice(themes)
            urls = STYLE_2.get(theme, STYLE_2["blue"])
            e.set_thumbnail(url=random.choice(urls))
            return e

        # default public: style_1
        emos = pol.get("emotions", ["neutral"])
        emo = random.choice(emos)
        urls = STYLE_1.get(emo, STYLE_1["neutral"])
        e.set_thumbnail(url=random.choice(urls))
        return e

# Backward compatibility function
def isla_embed(title: str, desc: str, color: int = 0x673AB7) -> discord.Embed:
    """Simple embed helper for backward compatibility."""
    e = discord.Embed(title=title, description=desc, color=color)
    return e


# ============================================================================
# MEMORY
# ============================================================================


class MemoryService:
    """Memory management system for conversation history and user memory."""
    
    def __init__(self, db: Database):
        self.db = db
        # Memory retention: keep last 30 days
        self.retention_days = 30
    
    # ==================== Conversation History ====================
    
    async def save_conversation(
        self,
        guild_id: int,
        channel_id: int,
        user_id: int,
        message_content: str,
        bot_response: Optional[str] = None,
        message_id: Optional[int] = None,
        context: Optional[Dict[str, Any]] = None,
        interaction_type: str = "message"
    ):
        """Save a conversation entry."""
        context_json = json.dumps(context or {})
        await self.db.execute(
            """
            INSERT INTO conversation_history(
              guild_id, channel_id, user_id, message_id, message_content,
              bot_response, context_json, timestamp, interaction_type
            ) VALUES(?,?,?,?,?,?,?,?,?)
            """,
            (
                guild_id, channel_id, user_id, message_id, message_content,
                bot_response, context_json, now_ts(), interaction_type
            )
        )
    
    async def get_recent_conversations(
        self,
        guild_id: int,
        user_id: Optional[int] = None,
        channel_id: Optional[int] = None,
        limit: int = 10,
        since_ts: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Get recent conversation history."""
        params = [guild_id]
        where_clauses = ["guild_id=?"]
        
        if user_id:
            where_clauses.append("user_id=?")
            params.append(user_id)
        
        if channel_id:
            where_clauses.append("channel_id=?")
            params.append(channel_id)
        
        if since_ts:
            where_clauses.append("timestamp>=?")
            params.append(since_ts)
        
        where_sql = " AND ".join(where_clauses)
        params.append(limit)
        
        rows = await self.db.fetchall(
            f"""
            SELECT * FROM conversation_history
            WHERE {where_sql}
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            tuple(params)
        )
        
        result = []
        for row in rows:
            try:
                context = json.loads(row["context_json"] or "{}")
            except Exception:
                context = {}
            
            result.append({
                "id": int(row["id"]),
                "guild_id": int(row["guild_id"]),
                "channel_id": int(row["channel_id"]),
                "user_id": int(row["user_id"]),
                "message_id": int(row["message_id"]) if row["message_id"] else None,
                "message_content": str(row["message_content"]),
                "bot_response": str(row["bot_response"]) if row["bot_response"] else None,
                "context": context,
                "timestamp": int(row["timestamp"]),
                "interaction_type": str(row["interaction_type"])
            })
        
        return result
    
    async def prune_old_conversations(self):
        """Remove conversations older than retention period."""
        cutoff_ts = now_ts() - (self.retention_days * 86400)
        await self.db.execute(
            "DELETE FROM conversation_history WHERE timestamp < ?",
            (cutoff_ts,)
        )
    
    # ==================== User Memory ====================
    
    async def set_user_memory(
        self,
        guild_id: int,
        user_id: int,
        key: str,
        value: str
    ):
        """Store a persistent memory for a user."""
        await self.db.execute(
            """
            INSERT OR REPLACE INTO user_memory(guild_id, user_id, memory_key, memory_value, updated_ts)
            VALUES(?,?,?,?,?)
            """,
            (guild_id, user_id, key, value, now_ts())
        )
    
    async def get_user_memory(
        self,
        guild_id: int,
        user_id: int,
        key: str
    ) -> Optional[str]:
        """Retrieve a specific user memory."""
        row = await self.db.fetchone(
            "SELECT memory_value FROM user_memory WHERE guild_id=? AND user_id=? AND memory_key=?",
            (guild_id, user_id, key)
        )
        return str(row["memory_value"]) if row else None
    
    async def get_all_user_memories(
        self,
        guild_id: int,
        user_id: int
    ) -> Dict[str, str]:
        """Get all memories for a user."""
        rows = await self.db.fetchall(
            "SELECT memory_key, memory_value FROM user_memory WHERE guild_id=? AND user_id=?",
            (guild_id, user_id)
        )
        return {str(row["memory_key"]): str(row["memory_value"]) for row in rows}
    
    async def delete_user_memory(
        self,
        guild_id: int,
        user_id: int,
        key: str
    ):
        """Delete a specific user memory."""
        await self.db.execute(
            "DELETE FROM user_memory WHERE guild_id=? AND user_id=? AND memory_key=?",
            (guild_id, user_id, key)
        )
    
    async def clear_user_memories(
        self,
        guild_id: int,
        user_id: int
    ):
        """Clear all memories for a user."""
        await self.db.execute(
            "DELETE FROM user_memory WHERE guild_id=? AND user_id=?",
            (guild_id, user_id)
        )
    
    # ==================== Conversation Context ====================
    
    async def update_channel_context(
        self,
        guild_id: int,
        channel_id: int,
        context: Dict[str, Any]
    ):
        """Update short-term context for a channel."""
        context_json = json.dumps(context)
        await self.db.execute(
            """
            INSERT OR REPLACE INTO conversation_context(
              guild_id, channel_id, context_json, last_message_ts
            ) VALUES(?,?,?,?)
            """,
            (guild_id, channel_id, context_json, now_ts())
        )
    
    async def get_channel_context(
        self,
        guild_id: int,
        channel_id: int
    ) -> Dict[str, Any]:
        """Get short-term context for a channel."""
        row = await self.db.fetchone(
            "SELECT context_json FROM conversation_context WHERE guild_id=? AND channel_id=?",
            (guild_id, channel_id)
        )
        if not row:
            return {}
        try:
            return json.loads(row["context_json"] or "{}")
        except Exception:
            return {}
    
    async def clear_old_context(self, max_age_seconds: int = 3600):
        """Clear context older than max_age_seconds (default 1 hour)."""
        cutoff_ts = now_ts() - max_age_seconds
        await self.db.execute(
            "DELETE FROM conversation_context WHERE last_message_ts < ?",
            (cutoff_ts,)
        )


# ============================================================================
# CONVERSATION
# ============================================================================


# Note: MemoryService is defined below in MEMORY section
class ConversationTracker:
    """Tracks conversation context and provides context-aware utilities."""
    
    def __init__(self, memory: MemoryService, db: Database):
        self.memory = memory
        self.db = db
    
    async def get_user_context(
        self,
        guild_id: int,
        user_id: int,
        channel_id: Optional[int] = None,
        lookback_messages: int = 5
    ) -> Dict[str, Any]:
        """Get context for a user including recent conversations and memories."""
        # Get recent conversations
        conversations = await self.memory.get_recent_conversations(
            guild_id=guild_id,
            user_id=user_id,
            channel_id=channel_id,
            limit=lookback_messages
        )
        
        # Get user memories
        memories = await self.memory.get_all_user_memories(guild_id, user_id)
        
        # Get user relationship data
        user_row = await self.db.fetchone(
            "SELECT stage, favor_stage, obedience, coins FROM users WHERE guild_id=? AND user_id=?",
            (guild_id, user_id)
        )
        
        relationship = {}
        if user_row:
            relationship = {
                "stage": int(user_row["stage"] or 0),
                "favor_stage": int(user_row["favor_stage"] or 0),
                "obedience": int(user_row["obedience"] or 0),
                "coins": int(user_row["coins"] or 0)
            }
        
        # Get channel context if available
        channel_context = {}
        if channel_id:
            channel_context = await self.memory.get_channel_context(guild_id, channel_id)
        
        return {
            "conversations": conversations,
            "memories": memories,
            "relationship": relationship,
            "channel_context": channel_context
        }
    
    async def extract_keywords_from_conversations(
        self,
        conversations: List[Dict[str, Any]],
        max_keywords: int = 5
    ) -> List[str]:
        """Extract important keywords from recent conversations."""
        # Simple keyword extraction - can be enhanced
        keywords = set()
        for conv in conversations:
            content = conv.get("message_content", "").lower()
            # Extract words (simple approach)
            words = content.split()
            for word in words:
                if len(word) > 4:  # Only longer words
                    keywords.add(word)
                if len(keywords) >= max_keywords:
                    break
            if len(keywords) >= max_keywords:
                break
        return list(keywords)[:max_keywords]
    
    async def has_recent_interaction(
        self,
        guild_id: int,
        user_id: int,
        within_seconds: int = 300
    ) -> bool:
        """Check if user had recent interaction with bot."""
        since_ts = now_ts() - within_seconds
        conversations = await self.memory.get_recent_conversations(
            guild_id=guild_id,
            user_id=user_id,
            since_ts=since_ts,
            limit=1
        )
        return len(conversations) > 0


# ============================================================================
# REPLY ENGINE
# ============================================================================


# Note: MemoryService is defined below in MEMORY section
# Note: ConversationTracker is defined below in CONVERSATION section
# Personality class defined below
class ReplyEngine:
    """Engine for generating automated replies based on context and patterns."""
    
    def __init__(
        self,
        memory: MemoryService,
        conversation: ConversationTracker,
        personality: Personality,
        db: Database
    ):
        self.memory = memory
        self.conversation = conversation
        self.personality = personality
        self.db = db
        self.patterns = self._load_patterns()
    
    def _load_patterns(self) -> Dict[str, Any]:
        """Load reply patterns from JSON file."""
        bot_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        patterns_path = os.path.join(bot_dir, "data", "reply_patterns.json")
        
        if not os.path.exists(patterns_path):
            return {"patterns": {}, "fallback_responses": {}}
        
        try:
            with open(patterns_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"patterns": {}, "fallback_responses": {}}
    
    def _normalize_text(self, text: str) -> str:
        """Normalize text for matching."""
        return re.sub(r'[^a-zA-Z0-9\s]', '', text.lower())
    
    def _match_keywords(self, text: str, keywords: List[str]) -> bool:
        """Check if text contains any of the keywords."""
        normalized = self._normalize_text(text)
        for keyword in keywords:
            if keyword.lower() in normalized:
                return True
        return False
    
    async def _get_user_stage(self, guild_id: int, user_id: int) -> int:
        """Get user's relationship stage."""
        row = await self.db.fetchone(
            "SELECT stage FROM users WHERE guild_id=? AND user_id=?",
            (guild_id, user_id)
        )
        return int(row["stage"]) if row and row["stage"] else 0
    
    def _get_stage_key(self, stage: int) -> str:
        """Convert stage number to key."""
        if stage >= 4:
            return "stage_4"
        elif stage >= 3:
            return "stage_3"
        elif stage >= 2:
            return "stage_2"
        elif stage >= 1:
            return "stage_1"
        else:
            return "stage_0"
    
    async def find_matching_pattern(
        self,
        text: str,
        guild_id: int,
        user_id: int
    ) -> Optional[Tuple[str, List[str]]]:
        """Find matching pattern for text. Returns (pattern_name, responses) or None."""
        stage = await self._get_user_stage(guild_id, user_id)
        stage_key = self._get_stage_key(stage)
        
        patterns = self.patterns.get("patterns", {})
        for pattern_name, pattern_data in patterns.items():
            keywords = pattern_data.get("keywords", [])
            if self._match_keywords(text, keywords):
                responses = pattern_data.get("responses", {}).get(stage_key, [])
                if responses:
                    return (pattern_name, responses)
        
        return None
    
    async def generate_reply(
        self,
        text: str,
        guild_id: int,
        user_id: int,
        channel_id: Optional[int] = None,
        use_memory: bool = True
    ) -> Optional[str]:
        """Generate a contextual reply to user text."""
        # Check if user is opted out or has safeword
        opted_out = await self.db.is_opted_out(guild_id, user_id)
        if opted_out:
            return None
        
        user_row = await self.db.fetchone(
            "SELECT safeword_until_ts FROM users WHERE guild_id=? AND user_id=?",
            (guild_id, user_id)
        )
        if user_row and user_row["safeword_until_ts"]:
            # now_ts is imported at top
            if int(user_row["safeword_until_ts"] or 0) > now_ts():
                return None
        
        # Try to match pattern
        match = await self.find_matching_pattern(text, guild_id, user_id)
        if match:
            pattern_name, responses = match
            reply = random.choice(responses)
            
            # Enhance with memory if enabled
            if use_memory:
                memories = await self.memory.get_all_user_memories(guild_id, user_id)
                # Could add memory-based enhancements here
            
            return reply
        
        # Fallback to personality system
        stage = await self._get_user_stage(guild_id, user_id)
        stage_key = self._get_stage_key(stage)
        
        fallbacks = self.patterns.get("fallback_responses", {}).get(stage_key, [])
        if fallbacks:
            return random.choice(fallbacks)
        
        return None
    
    async def should_reply_to_mention(
        self,
        guild_id: int,
        user_id: int,
        channel_id: Optional[int] = None
    ) -> bool:
        """Determine if bot should reply to a mention."""
        # Check consent and safeword
        opted_out = await self.db.is_opted_out(guild_id, user_id)
        if opted_out:
            return False
        
        user_row = await self.db.fetchone(
            "SELECT safeword_until_ts FROM users WHERE guild_id=? AND user_id=?",
            (guild_id, user_id)
        )
        if user_row and user_row["safeword_until_ts"]:
            # now_ts is imported at top
            if int(user_row["safeword_until_ts"] or 0) > now_ts():
                return False
        
        # Check if user had recent interaction (cooldown)
        recent = await self.conversation.has_recent_interaction(
            guild_id, user_id, within_seconds=30
        )
        if recent:
            return False  # Cooldown
        
        return True


# ============================================================================
# FAVOR
# ============================================================================


# Note: calculate_attraction, favor_stage_from_attraction, clamp are defined above in TONE section

async def get_user_favor_stage(db, guild_id: int, user_id: int) -> int:
    """
    Get the current favor_stage for a user from the database.
    If not set, calculate it based on current stats.
    """
    row = await db.fetchone(
        "SELECT favor_stage, coins, lce FROM users WHERE guild_id=? AND user_id=?",
        (guild_id, user_id)
    )
    if not row:
        return 0
    
    # If favor_stage is already set and recently calculated, return it
    # Otherwise recalculate
    current_favor = int(row.get("favor_stage", 0))
    
    # For now, use coins/LCE as proxy until we have full obedience tracking
    coins = int(row.get("coins", 0))
    lce = int(row.get("lce", 0))
    
    # Simple calculation using coins as primary (can be enhanced later)
    # Stage thresholds: 0: <1k, 1: 1k-5k, 2: 5k-10k, 3: 10k-20k, 4: 20k+
    if coins < 1000:
        stage = 0
    elif coins < 5000:
        stage = 1
    elif coins < 10000:
        stage = 2
    elif coins < 20000:
        stage = 3
    else:
        stage = 4
    
    # Update if different
    if stage != current_favor:
        await db.execute(
            "UPDATE users SET favor_stage=? WHERE guild_id=? AND user_id=?",
            (stage, guild_id, user_id)
        )
    
    return stage

async def calculate_and_update_favor_stage(
    db,
    guild_id: int,
    user_id: int,
    coins: float = None,
    obedience_rate: float = 0.5,
    streak_days: int = 0,
    failures: int = 0
) -> int:
    """
    Calculate favor_stage using Attraction Meter formula and update database.
    
    Formula: attraction = (coins * 0.5) + (obedience_rate * 40) + (streak_days * 10) - (failures * 20)
    Stage: clamp(attraction // 5000, 0, 4)
    
    If coins is None, fetch from database.
    """
    if coins is None:
        row = await db.fetchone(
            "SELECT coins FROM users WHERE guild_id=? AND user_id=?",
            (guild_id, user_id)
        )
        coins = float(row["coins"]) if row else 0.0
    
    attraction = calculate_attraction(coins, obedience_rate, streak_days, failures)
    stage = favor_stage_from_attraction(attraction)
    stage = clamp(stage, 0, 4)
    
    await db.execute(
        "UPDATE users SET favor_stage=? WHERE guild_id=? AND user_id=?",
        (int(stage), guild_id, user_id)
    )
    
    return int(stage)